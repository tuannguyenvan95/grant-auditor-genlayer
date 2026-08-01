# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from dataclasses import dataclass

@allow_storage
@dataclass
class Milestone:
    id: str
    amount: bigint
    evidence_url: str
    status: str  # PENDING, SUBMITTED, APPROVED, PARTIAL, CUT, ESCALATED

@allow_storage
@dataclass
class Grant:
    id: str
    funder: Address
    grantee: Address
    proposal_url: str
    total_amount: bigint
    num_milestones: bigint
    status: str  # ACTIVE, CLOSED

class Contract(gl.Contract):
    grants: TreeMap[str, Grant]
    milestones: TreeMap[str, Milestone]
    next_grant_id: bigint

    def __init__(self):
        # Do NOT reassign TreeMap or DynArray in __init__
        self.next_grant_id = bigint(1)

    @gl.public.write.payable
    def create_grant(self, grantee: Address, proposal_url: str, milestone_amounts_str: str) -> str:
        funder = Address(gl.message.sender_address)
        
        # Parse milestone amounts (supports comma-separated "100,200" or JSON array "[100, 200]")
        try:
            if milestone_amounts_str.strip().startswith("["):
                raw_amounts = json.loads(milestone_amounts_str)
            else:
                raw_amounts = [int(x.strip()) for x in milestone_amounts_str.split(",") if x.strip()]
        except Exception:
            raise UserError("Invalid milestone amounts format. Please pass comma-separated numbers (e.g. '100,200') or JSON array.")
            
        if not raw_amounts:
            raise UserError("At least one milestone amount is required.")
            
        total_calc = 0
        for val in raw_amounts:
            if val <= 0:
                raise UserError("Each milestone amount must be greater than 0.")
            total_calc += val
            
        total_amount = bigint(total_calc)
        
        # Check value locked
        if gl.message.value < total_amount:
            raise UserError(f"Insufficient funds sent. Expected {str(total_amount)}, got {str(gl.message.value)}.")

        grant_id = str(self.next_grant_id)
        self.next_grant_id += bigint(1)

        for i, val in enumerate(raw_amounts):
            ms_key = f"{grant_id}_{i}"
            self.milestones[ms_key] = Milestone(
                id=str(i),
                amount=bigint(val),
                evidence_url="",
                status="PENDING"
            )

        new_grant = Grant(
            id=grant_id,
            funder=funder,
            grantee=grantee,
            proposal_url=proposal_url,
            total_amount=total_amount,
            num_milestones=bigint(len(raw_amounts)),
            status="ACTIVE"
        )
        self.grants[grant_id] = new_grant
        return grant_id

    @gl.public.write
    def submit_evidence(self, grant_id: str, milestone_id: str, evidence_url: str) -> str:
        if grant_id not in self.grants:
            raise UserError("Grant not found.")
        
        grant = self.grants[grant_id]
        if gl.message.sender_address != grant.grantee:
            raise UserError("Only the grantee can submit milestones.")
            
        if grant.status == "CLOSED":
            raise UserError("This grant is closed.")
        
        ms_key = f"{grant_id}_{milestone_id}"
        if ms_key not in self.milestones:
            raise UserError("Milestone not found.")
            
        ms = self.milestones[ms_key]
        if ms.status != "PENDING":
            raise UserError(f"Milestone cannot be submitted. Current status: {ms.status} (preventing double claim).")
            
        if not evidence_url or not evidence_url.startswith("http"):
            raise UserError("Invalid evidence URL provided.")
            
        ms.evidence_url = evidence_url
        ms.status = "SUBMITTED"
        self.milestones[ms_key] = ms
        return "EVIDENCE_SUBMITTED"

    @gl.public.write
    def adjudicate_milestone(self, grant_id: str, milestone_id: str) -> str:
        if grant_id not in self.grants:
            raise UserError("Grant not found.")
            
        grant = self.grants[grant_id]
        if grant.status == "CLOSED":
            raise UserError("Grant is closed.")
            
        ms_key = f"{grant_id}_{milestone_id}"
        if ms_key not in self.milestones:
            raise UserError("Milestone not found.")
            
        ms = self.milestones[ms_key]
        if ms.status != "SUBMITTED":
            raise UserError(f"Milestone is not in SUBMITTED state. Current status: {ms.status}")

        raw_json = gl.vm.run_nondet(
            lambda: self._adjudicate_leader(grant.proposal_url, ms.evidence_url),
            self._adjudicate_validator
        )
        
        try:
            res_dict = json.loads(raw_json)
            verdict = str(res_dict.get("verdict", "ESCALATE")).upper()
            confidence = int(res_dict.get("confidence", 0))
            reason = str(res_dict.get("reason", "No reason provided."))
        except Exception:
            raise UserError("LLM returned malformed or invalid JSON.")

        if confidence < 65:
            verdict = "ESCALATE"
            reason = f"[Confidence below threshold: {confidence}%] " + reason

        amount = ms.amount
        payout_amount = bigint(0)

        if verdict == "RELEASE":
            payout_amount = amount
            ms.status = "APPROVED"
            # gl.get_contract_at(gl.current_contract_address).emit_transfer(grant.grantee, amount)
        elif verdict == "PARTIAL":
            half = amount // bigint(2)
            rem = amount - half
            payout_amount = half
            ms.status = "PARTIAL"
            if half > bigint(0):
                pass # gl.get_contract_at(gl.current_contract_address).emit_transfer(grant.grantee, half)
            if rem > bigint(0):
                pass # gl.get_contract_at(gl.current_contract_address).emit_transfer(grant.funder, rem)
        elif verdict == "CUT":
            payout_amount = bigint(0)
            ms.status = "CUT"
            # gl.get_contract_at(gl.current_contract_address).emit_transfer(grant.funder, amount)
        else:
            verdict = "ESCALATE"
            ms.status = "ESCALATED"
            # Escalate leaves funds locked in contract for human resolution

        self.milestones[ms_key] = ms
        
        # Check if all milestones completed or terminated to close grant
        all_done = True
        total_ms = int(str(grant.num_milestones))
        for i in range(total_ms):
            k = f"{grant_id}_{i}"
            if k in self.milestones and self.milestones[k].status in ["PENDING", "SUBMITTED"]:
                all_done = False
                break
        if all_done:
            grant.status = "CLOSED"
            self.grants[grant_id] = grant

        return json.dumps({"verdict": verdict, "reason": reason, "confidence": confidence, "payout": str(payout_amount)})

    def _adjudicate_leader(self, proposal_url: str, evidence_url: str) -> str:
        prop_res = gl.nondet.web.render(proposal_url)
        if not prop_res.ok:
            raise UserError("Failed to render proposal URL (404 / Timeout / Network Error).")
            
        ev_res = gl.nondet.web.render(evidence_url)
        if not ev_res.ok:
            raise UserError("Failed to render evidence URL (404 / Timeout / Network Error).")

        prompt = f"""
        You are an expert grant auditor for a decentralized DAO. 
        Your task is to evaluate the submitted evidence for a milestone against the original grant proposal.
        
        ORIGINAL PROPOSAL:
        {prop_res.content[:2500]}
        
        SUBMITTED EVIDENCE:
        {ev_res.content[:2500]}
        
        Evaluate whether the evidence proves the milestone was completed successfully according to the proposal.
        Respond with ONLY a JSON object in this exact format, with no extra text or markdown code blocks:
        {{"verdict": "RELEASE|PARTIAL|CUT|ESCALATE", "confidence": <integer from 0 to 100>, "reason": "<detailed explanation of your decision>"}}
        
        Rules for verdict:
        - RELEASE: The evidence clearly proves completion of the milestone requirements.
        - PARTIAL: The evidence proves partial completion or minor deliverables are missing.
        - CUT: The evidence clearly fails to prove completion or is fake/irrelevant.
        - ESCALATE: The evidence is contradictory, unclear, or you cannot confidently determine completion.
        """
        
        result = gl.nondet.exec_prompt(prompt)
        return result.content

    def _adjudicate_validator(self, res_leader: str, res_val: str) -> bool:
        try:
            leader_dict = json.loads(res_leader)
            validator_dict = json.loads(res_val)
            return str(leader_dict.get("verdict")).upper() == str(validator_dict.get("verdict")).upper()
        except Exception:
            return False

    @gl.public.view
    def get_grant(self, grant_id: str) -> str:
        if grant_id not in self.grants:
            raise UserError("Grant not found.")
        g = self.grants[grant_id]
        
        ms_list = []
        total_ms = int(str(g.num_milestones))
        for i in range(total_ms):
            ms_key = f"{grant_id}_{i}"
            if ms_key in self.milestones:
                m = self.milestones[ms_key]
                ms_list.append({
                    "id": m.id,
                    "amount": str(m.amount),
                    "evidence_url": m.evidence_url,
                    "status": m.status
                })
                
        res = {
            "id": g.id,
            "funder": str(g.funder),
            "grantee": str(g.grantee),
            "proposal_url": g.proposal_url,
            "total_amount": str(g.total_amount),
            "num_milestones": str(g.num_milestones),
            "status": g.status,
            "milestones": ms_list
        }
        return json.dumps(res)
    
    @gl.public.view
    def get_all_grants(self) -> str:
        res = []
        max_id = int(str(self.next_grant_id))
        for i in range(1, max_id):
            gid = str(i)
            if gid in self.grants:
                g = self.grants[gid]
                ms_list = []
                total_ms = int(str(g.num_milestones))
                for j in range(total_ms):
                    ms_key = f"{gid}_{j}"
                    if ms_key in self.milestones:
                        m = self.milestones[ms_key]
                        ms_list.append({
                            "id": m.id,
                            "amount": str(m.amount),
                            "evidence_url": m.evidence_url,
                            "status": m.status
                        })
                res.append({
                    "id": g.id,
                    "funder": str(g.funder),
                    "grantee": str(g.grantee),
                    "proposal_url": g.proposal_url,
                    "total_amount": str(g.total_amount),
                    "num_milestones": str(g.num_milestones),
                    "status": g.status,
                    "milestones": ms_list
                })
        return json.dumps(res)
