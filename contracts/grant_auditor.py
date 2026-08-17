# v0.3.0
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
    status: str  # PENDING, SUBMITTED, APPROVED, PARTIAL, CUT, ESCALATED, RETRY
    attempts: bigint
    reason: str

@allow_storage
@dataclass
class Grant:
    id: str
    title: str
    funder: str
    grantee: str
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

    def _milestone_key(self, grant_id: str, milestone_id: str) -> str:
        return f"{grant_id}_{milestone_id}"

    def _is_terminal_status(self, status: str) -> bool:
        # ESCALATED is NOT terminal: the grantee can resubmit evidence,
        # and funds should stay locked for DAO arbitration.
        return status in ["APPROVED", "PARTIAL", "CUT"]

    def _maybe_close_grant(self, grant_id: str, grant: Grant) -> None:
        total_ms = int(str(grant.num_milestones))
        for i in range(total_ms):
            ms_key = self._milestone_key(grant_id, str(i))
            if ms_key not in self.milestones:
                continue
            if not self._is_terminal_status(self.milestones[ms_key].status):
                return
        grant.status = "CLOSED"
        self.grants[grant_id] = grant

    @gl.public.write.payable
    def create_grant(self, grantee: str, title: str, proposal_url: str, milestone_amounts_str: str) -> str:
        funder = str(gl.message.sender_address).lower()
        grantee = str(grantee).lower()
        
        # Validate proposal_url is a proper URL (not mixed with title)
        url_str = str(proposal_url).strip()
        if not url_str.startswith("http://") and not url_str.startswith("https://"):
            raise UserError("proposal_url must be a valid HTTP/HTTPS URL.")
        
        title_str = str(title).strip()
        if not title_str:
            title_str = "Untitled Grant"
        
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
        
        # Require exact escrow amount for all milestones
        if gl.message.value < total_amount:
            raise UserError(f"Insufficient funds sent. Expected {str(total_amount)}, got {str(gl.message.value)}.")
        if gl.message.value > total_amount:
            raise UserError(f"Exact milestone escrow required. Expected {str(total_amount)}, got {str(gl.message.value)}.")

        grant_id = str(self.next_grant_id)
        self.next_grant_id += bigint(1)

        for i, val in enumerate(raw_amounts):
            ms_key = f"{grant_id}_{i}"
            self.milestones[ms_key] = Milestone(
                id=str(i),
                amount=bigint(val),
                evidence_url="",
                status="PENDING",
                attempts=bigint(0),
                reason="Awaiting deliverable submission."
            )

        new_grant = Grant(
            id=grant_id,
            title=title_str,
            funder=funder,
            grantee=grantee,
            proposal_url=url_str,
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
        if str(gl.message.sender_address).lower() != str(grant.grantee).lower():
            raise UserError("Only the grantee can submit milestones.")
            
        if grant.status == "CLOSED":
            raise UserError("This grant is closed.")
        
        ms_key = f"{grant_id}_{milestone_id}"
        if ms_key not in self.milestones:
            raise UserError("Milestone not found.")
            
        ms = self.milestones[ms_key]
        if ms.status not in ["PENDING", "RETRY", "ESCALATED"]:
            raise UserError(f"Milestone cannot be submitted in status: {ms.status}. Either already submitted/approved or permanently closed.")
            
        if not evidence_url or not str(evidence_url).strip():
            raise UserError("Evidence URL cannot be empty.")
            
        ms.attempts += bigint(1)
        if ms.attempts > bigint(3):
            raise UserError("Maximum 3 submission attempts reached for this milestone. Permanently locked.")
            
        ms.evidence_url = str(evidence_url).strip()
        ms.status = "SUBMITTED"
        ms.reason = f"Evidence submitted (Attempt {int(str(ms.attempts))}/3). Awaiting on-chain AI consensus adjudication."
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

        # Extract storage fields to local strings before entering nondeterministic lambda
        proposal_str = str(grant.proposal_url)
        evidence_str = str(ms.evidence_url)
        # Track extraction errors for hard runtime enforcement (not just LLM prompt rules)
        # Using a set to avoid duplicates when leader_fn is called multiple times by validators
        extraction_errors = set()

        def leader_fn():
            try:
                if proposal_str:
                    prop_res = gl.nondet.web.render(proposal_str, mode="text")
                    prop_text = prop_res.content if hasattr(prop_res, "content") else str(prop_res)
                    low_prop = prop_text.lower()
                    if "web_extraction_error" in low_prop or "404 not found" in low_prop or "dns_probe_finished" in low_prop or "unable to render" in low_prop or "connection refused" in low_prop:
                        extraction_errors.add("proposal")
                else:
                    prop_text = "No proposal URL provided."
            except Exception as e:
                prop_text = f"WEB_EXTRACTION_ERROR: Unable to render proposal URL: {str(e)}"
                extraction_errors.add("proposal")
                
            try:
                if evidence_str:
                    ev_res = gl.nondet.web.render(evidence_str, mode="text")
                    ev_text = ev_res.content if hasattr(ev_res, "content") else str(ev_res)
                    low_ev = ev_text.lower()
                    if "web_extraction_error" in low_ev or "404 not found" in low_ev or "dns_probe_finished" in low_ev or "unable to render" in low_ev or "connection refused" in low_ev:
                        extraction_errors.add("evidence")
                else:
                    ev_text = "No evidence URL provided."
            except Exception as e:
                ev_text = f"WEB_EXTRACTION_ERROR: Unable to render evidence URL: {str(e)}"
                extraction_errors.add("evidence")

            prompt = f"""
            You are an expert grant auditor and judge for a decentralized DAO on the GenLayer network.
            Your task is to evaluate the submitted evidence for a milestone against the original grant proposal.
            
            ORIGINAL PROPOSAL:
            {prop_text[:2500]}
            
            SUBMITTED EVIDENCE:
            {ev_text[:2500]}
            
            Evaluate whether the evidence proves the milestone was completed successfully according to the proposal.
            
            Rules for verdict:
            - RELEASE: The evidence clearly proves completion of the milestone requirements.
            - PARTIAL: The evidence proves partial completion or minor deliverables are missing.
            - CUT: The work submitted is definitively fraudulent, intentionally incorrect, or clearly contradicts the grant goals.
            - ESCALATE: The evidence is contradictory, ambiguous, or requires human arbitration.
            - RETRY: Minor formatting errors or incomplete deliverables that can be resubmitted.
            
            CRITICAL ESCROW PROTECTION RULE (MANDATORY): If either the proposal or submitted evidence contains "WEB_EXTRACTION_ERROR", a 404 error page, network timeout, unparseable summary structure, or an unreachable placeholder domain during extraction, you MUST NEVER return "CUT" (because CUT would improperly refund the Funder when work may be valid or temporary network failures occur). Instead, you MUST output verdict "ESCALATE" with confidence 100 and reason "Data extraction or network error during consensus rendering; escrowed funds are preserved and frozen in contract for safety and arbitration without improper customer refund."
            
            You MUST respond with ONLY a JSON object in this exact format:
            {{"verdict": "RELEASE|PARTIAL|CUT|ESCALATE|RETRY", "confidence": 100, "reason": "detailed explanation of your decision"}}
            """
            
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            if isinstance(res, dict):
                return res
            if hasattr(res, 'calldata') and isinstance(res.calldata, dict):
                return res.calldata
            try:
                text = res.content if hasattr(res, "content") else str(res)
                return self._parse_llm_json(text)
            except Exception:
                return {"verdict": "ESCALATE", "confidence": 100, "reason": "Escalated due to AI execution or JSON parse error to preserve escrowed funds without improper customer refund."}

        def validator_fn(leader_res) -> bool:
            leader_data = leader_res
            if hasattr(leader_res, "calldata"):
                leader_data = leader_res.calldata
            if not isinstance(leader_data, dict):
                try:
                    leader_data = self._parse_llm_json(str(leader_data))
                except Exception:
                    leader_data = {"verdict": "ESCALATE", "confidence": 100, "reason": "Invalid nondeterministic response; escrow preserved in contract."}
            mine_data = leader_fn()
            v_leader = str(leader_data.get("verdict", "")).upper().strip()
            v_mine = str(mine_data.get("verdict", "")).upper().strip()
            return v_leader == v_mine

        result = gl.vm.run_nondet(leader_fn, validator_fn)
        if not isinstance(result, dict):
            try:
                result = self._parse_llm_json(str(result))
            except Exception:
                result = {"verdict": "ESCALATE", "confidence": 0, "reason": "Failed to parse AI response."}

        verdict = str(result.get("verdict", "ESCALATE")).upper()
        try:
            confidence = int(result.get("confidence", 0))
        except Exception:
            confidence = 100
        reason = str(result.get("reason", "No reason provided."))

        # HARD RUNTIME ENFORCEMENT: If any extraction error occurred, NEVER allow CUT.
        # This is enforced at the contract logic level, independent of the LLM prompt.
        if len(extraction_errors) > 0 and verdict == "CUT":
            verdict = "ESCALATE"
            error_list = sorted(list(extraction_errors))  # Sort for deterministic output
            reason = f"[RUNTIME OVERRIDE: Extraction failed for {', '.join(error_list)}] Verdict CUT blocked. Escrow preserved for DAO arbitration. Original reason: {reason}"

        if confidence < 65:
            verdict = "ESCALATE"
            reason = f"[Confidence below threshold: {confidence}%] " + reason

        amount = ms.amount
        payout_amount = bigint(0)

        if verdict == "RELEASE":
            payout_amount = amount
            ms.status = "APPROVED"
            ms.reason = f"✓ [RELEASE (100%)] AI Consensus approved (Attempt {int(str(ms.attempts))}/3): {reason}"
            gl.get_contract_at(Address(str(grant.grantee))).emit_transfer(value=amount)
        elif verdict == "PARTIAL":
            half = amount // bigint(2)
            rem = amount - half
            payout_amount = half
            ms.status = "PARTIAL"
            ms.reason = f"⚠️ [PARTIAL (50%)] Partial fulfillment verified (Attempt {int(str(ms.attempts))}/3): {reason}"
            if half > bigint(0):
                gl.get_contract_at(Address(str(grant.grantee))).emit_transfer(value=half)
            if rem > bigint(0):
                gl.get_contract_at(Address(str(grant.funder))).emit_transfer(value=rem)
        elif verdict == "RETRY":
            payout_amount = bigint(0)
            ms.status = "RETRY"
            ms.reason = f"🔄 [RETRY REQUESTED - Attempt {int(str(ms.attempts))}/3] {reason} | Milestone reset for resubmission after 1-minute cooldown."
        elif verdict == "CUT":
            if ms.attempts < bigint(3):
                payout_amount = bigint(0)
                ms.status = "RETRY"
                ms.reason = f"🔄 [REJECTED - Attempt {int(str(ms.attempts))}/3] {reason} | Milestone reset for resubmission after 1-minute cooldown."
            else:
                payout_amount = bigint(0)
                ms.status = "CUT"
                ms.reason = f"🚫 [PERMANENTLY CLOSED - 3/3 Attempts Failed] {reason} | 100% Escrow Refunded back to Funder."
                gl.get_contract_at(Address(str(grant.funder))).emit_transfer(value=amount)
        else:
            verdict = "ESCALATE"
            ms.status = "ESCALATED"
            ms.reason = f"🚨 [ESCALATED TO DAO - ESCROW PRESERVED] {reason}"
            # Escalate leaves funds locked in contract for resolution without improper customer refund for resolution

        self.milestones[ms_key] = ms
        self._maybe_close_grant(grant_id, grant)

        return json.dumps({"verdict": verdict, "reason": reason, "confidence": confidence, "payout": str(payout_amount)})

    def _parse_llm_json(self, text) -> dict:
        if isinstance(text, dict):
            return text
        if hasattr(text, '__dict__'):
            return text.__dict__
        # json is already imported at module level
        text = str(text).strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

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
                    "status": m.status,
                    "attempts": str(m.attempts),
                    "reason": m.reason
                })
                
        res = {
            "id": g.id,
            "title": g.title,
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
                            "status": m.status,
                            "attempts": str(m.attempts),
                            "reason": m.reason
                        })
                res.append({
                    "id": g.id,
                    "title": g.title,
                    "funder": str(g.funder),
                    "grantee": str(g.grantee),
                    "proposal_url": g.proposal_url,
                    "total_amount": str(g.total_amount),
                    "num_milestones": str(g.num_milestones),
                    "status": g.status,
                    "milestones": ms_list
                })
        return json.dumps(res)
