import sys
import os
import json
import pytest
from unittest.mock import MagicMock

class MockAddress(str): pass
class MockBigInt(int): pass
class MockUserError(Exception): pass

class MockReturn:
    def __init__(self, calldata):
        self.calldata = calldata

class MockContractStub:
    def __init__(self, address, tracker):
        self.address = address
        self.tracker = tracker

    def emit_transfer(self, value):
        self.tracker.append({"to": self.address, "value": value})

class MockGL:
    class Contract:
        def __init__(self):
            self.grants = {}
            self.milestones = {}
            self.appeals = {}
            self.reputations = {}

    class public:
        @staticmethod
        def view(fn): return fn
        @staticmethod
        def write(fn): return fn

    class message:
        value = MockBigInt(0)
        sender_address = MockAddress("0xFunder")

    class nondet:
        class web:
            @staticmethod
            def render(url, mode="text"): return "Valid deliverable content"
        @staticmethod
        def exec_prompt(prompt, response_format="json"):
            import re
            canary = ""
            match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
            if match:
                canary = match.group(1)
            return {"verdict": "PARTIAL", "confidence": 100, "canary": canary, "reason": "50% delivered"}

    class vm:
        Return = MockReturn
        @staticmethod
        def run_nondet(leader_fn, validator_fn):
            res = leader_fn()
            ret = MockReturn(calldata=res)
            if not validator_fn(ret):
                raise MockUserError("Consensus Disagreement")
            return res

    def __init__(self):
        self.transfers = []

    def get_contract_at(self, address):
        return MockContractStub(address, self.transfers)

MockGL.public.write.payable = lambda fn: fn

mock_mod = MagicMock()
mock_mod.gl = MockGL()
mock_mod.allow_storage = lambda cls: cls
mock_mod.Address = MockAddress
mock_mod.bigint = MockBigInt
mock_mod.u256 = MockBigInt
mock_mod.UserError = MockUserError
mock_mod.TreeMap = dict

sys.modules["genlayer"] = mock_mod
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "contracts")))
import grant_auditor as contract_module
MockUserError = contract_module.UserError

class HarnessContract:
    def __init__(self):
        self.contract = contract_module.Contract()
        self.gl = mock_mod.gl
        self.gl.transfers = []
        contract_module.gl = self.gl
        self.contract.grants = {}
        self.contract.milestones = {}
        self.contract.appeals = {}
        self.contract.reputations = {}
        self.contract.next_grant_id = MockBigInt(1)
        self.current_caller = MockAddress("0xfunder")

    def connect(self, account):
        self.current_caller = MockAddress(str(account).lower())
        self.gl.message.sender_address = self.current_caller
        return self

    def create_grant(self, args, value=0):
        self.gl.message.value = MockBigInt(value)
        gid = self.contract.create_grant(
            grantee=args[0],
            title=args[1],
            proposal_url=args[2],
            milestone_amounts_str=args[3],
            milestone_criteria_json=args[4]
        )
        return MagicMock(return_value=gid)

    def submit_evidence(self, args):
        self.gl.message.value = MockBigInt(0)
        return self.contract.submit_evidence(
            grant_id=args[0],
            milestone_id=args[1],
            evidence_url=args[2],
            progress_report=args[3],
            evidence_hash=args[4] if len(args) > 4 else ""
        )

    def adjudicate_milestone(self, args):
        self.gl.message.value = MockBigInt(0)
        return self.contract.adjudicate_milestone(args[0], args[1])

    def file_appeal(self, args, value=0):
        self.gl.message.value = MockBigInt(value)
        return self.contract.file_appeal(
            grant_id=args[0],
            milestone_id=args[1],
            justification=args[2],
            supplemental_url=args[3] if len(args) > 3 else ""
        )

    def adjudicate_appeal(self, args):
        self.gl.message.value = MockBigInt(0)
        return self.contract.adjudicate_appeal(args[0], args[1])

    def get_grant(self, args):
        raw = self.contract.get_grant(args[0])
        return MagicMock(call=lambda: raw)


def _extract_canary(prompt):
    import re
    match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
    return match.group(1) if match else ""


def test_partial_release_followed_by_overturn_accounting():
    """
    Proves that a partial release followed by an overturned appeal only pays remaining liability.
    Steward Joaquín Requirement:
    - Grant with 2 milestones (multi-milestone requirement): 100 GEN each = 200 GEN total.
    - Milestone 0: Evaluated PARTIAL (50 released, 50 remaining liability).
    - Grantee appeals staking 20 GEN.
    - Appellate court rules OVERTURN (Award full milestone).
    - Grantee receives ONLY remaining 50 GEN (Total 100 paid out from escrow, NEVER > 100).
    - Invariant: total payouts strictly equal funding + stakes.
    """
    harness = HarnessContract()
    funder = "0xfunder"
    grantee = "0xgrantee"

    # 1. Create 2-milestone grant (multi-milestone requirement)
    # Total: 200 GEN (100 each)
    tx = harness.connect(funder).create_grant(
        args=[str(grantee), "Multi-Milestone Project", "https://example.org/prop", "100,100", "M1 Criteria|M2 Criteria"],
        value=200
    )
    grant_id = tx.return_value

    # Submit evidence for Milestone 0
    harness.connect(grantee).submit_evidence(
        args=[grant_id, "0", "https://example.org/evidence1", "Report 1", "hash1"]
    )

    # Mock AI Adjudication: PARTIAL (50% release)
    contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
        "verdict": "PARTIAL",
        "confidence": 90,
        "canary": _extract_canary(prompt),
        "reason": "50% completed."
    }
    harness.connect(funder).adjudicate_milestone(args=[grant_id, "0"])

    # Verify 50 disbursed, 50 remaining liability
    g_data = json.loads(harness.get_grant(args=[grant_id]).call())
    assert g_data["milestones"][0]["disbursed_to_grantee"] == "50"
    assert g_data["milestones"][0]["remaining_liability"] == "50"

    # Grantee files appeal with 20 stake
    harness.connect(grantee).file_appeal(
        args=[grant_id, "0", "Deliverables were 100% complete", "https://example.org/supp"],
        value=20
    )

    # Mock Appellate Court: OVERTURN (Award full milestone)
    contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
        "verdict": "OVERTURN",
        "confidence": 95,
        "canary": _extract_canary(prompt),
        "reason": "Criteria 100% fulfilled upon review."
    }
    harness.connect(grantee).adjudicate_appeal(args=[grant_id, "0"])

    # Verify Accounting: Grantee receives remaining 50 (Total 100 paid out, never > 100)
    g_after = json.loads(harness.get_grant(args=[grant_id]).call())
    assert g_after["milestones"][0]["disbursed_to_grantee"] == "100"
    assert g_after["milestones"][0]["remaining_liability"] == "0"

    # Verify transfers: 50 (initial) + 20 (stake refund) + 50 (remaining liability) = 120
    transfers = harness.gl.transfers
    assert len(transfers) == 3
    assert sum(t["value"] for t in transfers) == 120
    assert sum(t["value"] for t in transfers) <= 200 + 20 # Funding + Stake


def test_partial_release_followed_by_upheld_accounting():
    """
    Proves that a partial release followed by an upheld appeal refunds remaining liability to funder.
    Steward Joaquín Requirement:
    - Milestone 0: 100 GEN.
    - PARTIAL release: 50 GEN to grantee, 50 GEN liability reserved.
    - Grantee appeals with 20 GEN stake.
    - Appellate court rules UPHOLD (Appeal rejected).
    - Remaining 50 GEN refunded to funder + 20 GEN slashed stake to funder.
    - Total payouts from milestone escrow == 100 GEN (50 grantee + 50 funder).
    """
    harness = HarnessContract()
    funder = "0xfunder"
    grantee = "0xgrantee"

    tx = harness.connect(funder).create_grant(
        args=[str(grantee), "Upheld Appeal Project", "https://example.org/prop", "100", "M1 Criteria"],
        value=100
    )
    grant_id = tx.return_value

    harness.connect(grantee).submit_evidence(
        args=[grant_id, "0", "https://example.org/evidence1", "Report 1", "hash1"]
    )

    contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
        "verdict": "PARTIAL",
        "confidence": 90,
        "canary": _extract_canary(prompt),
        "reason": "50% completed."
    }
    harness.connect(funder).adjudicate_milestone(args=[grant_id, "0"])

    harness.connect(grantee).file_appeal(
        args=[grant_id, "0", "I contest the 50% rating", "https://example.org/supp"],
        value=20
    )

    contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
        "verdict": "UPHOLD",
        "confidence": 95,
        "canary": _extract_canary(prompt),
        "reason": "Appeal rejected."
    }
    harness.connect(grantee).adjudicate_appeal(args=[grant_id, "0"])

    g_after = json.loads(harness.get_grant(args=[grant_id]).call())
    assert g_after["milestones"][0]["disbursed_to_grantee"] == "50"
    assert g_after["milestones"][0]["disbursed_to_funder"] == "50"
    assert g_after["milestones"][0]["remaining_liability"] == "0"

    transfers = harness.gl.transfers
    assert len(transfers) == 3
    assert transfers[0]["to"] == grantee and transfers[0]["value"] == 50
    assert transfers[1]["to"] == funder and transfers[1]["value"] == 20 # Slashed stake
    assert transfers[2]["to"] == funder and transfers[2]["value"] == 50 # Remaining refund
    assert sum(t["value"] for t in transfers) == 120
    assert sum(t["value"] for t in transfers) <= 100 + 20


def test_repeated_appeal_blocked():
    """
    Proves that repeated appeals on the same milestone are strictly rejected.
    Steward Joaquín Requirement:
    - Enforce single appeal per milestone.
    - Attempting second appeal on same milestone MUST revert with UserError.
    """
    harness = HarnessContract()
    funder = "0xfunder"
    grantee = "0xgrantee"

    tx = harness.connect(funder).create_grant(
        args=[str(grantee), "Test Project", "https://example.org/prop", "100", "M1 Criteria"],
        value=100
    )
    grant_id = tx.return_value

    harness.connect(grantee).submit_evidence(
        args=[grant_id, "0", "https://example.org/evidence1", "Report 1", "hash1"]
    )

    # Adjudicate milestone -> enters PARTIAL / AWAITING_PAYOUT
    contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
        "verdict": "PARTIAL",
        "confidence": 90,
        "canary": _extract_canary(prompt),
        "reason": "50% completed."
    }
    harness.connect(funder).adjudicate_milestone(args=[grant_id, "0"])

    # First appeal succeeds
    harness.connect(grantee).file_appeal(
        args=[grant_id, "0", "First appeal", "https://example.org/supp"],
        value=10
    )

    # Attempt second appeal on same milestone -> MUST REVERT
    with pytest.raises(Exception, match="Only a single appeal per milestone is permitted"):
        harness.connect(grantee).file_appeal(
            args=[grant_id, "0", "Second repeated appeal attempt", "https://example.org/supp2"],
            value=10
        )
