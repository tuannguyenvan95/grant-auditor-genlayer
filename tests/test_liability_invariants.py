import sys
import os
import unittest
import json
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
            def render(url, mode="text"): return "Valid comprehensive deliverable proof"
        @staticmethod
        def exec_prompt(prompt, response_format="json"):
            import re
            canary = ""
            match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
            if match:
                canary = match.group(1)
            # Default response
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

class TestLiabilityInvariantsAndAppeals(unittest.TestCase):
    """
    Formal verification suite satisfying Steward Joaquín's exact review requirements:
    1. Partial release followed by OVERTURN (Grantee wins): No double payout of already-disbursed funds.
    2. Partial release followed by UPHELD (Appeal rejected): Remaining liability safely refunded.
    3. Multi-milestone grant lifecycle solvency invariant: Total payouts never exceed funding + stakes.
    4. Single appeal per milestone enforcement: Repeated appeals strictly rejected.
    """

    def setUp(self):
        self.gl = mock_mod.gl
        self.gl.transfers = []
        self.funder = MockAddress("0xfunder")
        self.grantee = MockAddress("0xgrantee")

        self.gl.message.sender_address = self.funder
        self.contract = contract_module.Contract()
        contract_module.gl = self.gl
        self.contract.grants = {}
        self.contract.milestones = {}
        self.contract.appeals = {}
        self.contract.reputations = {}
        self.contract.next_grant_id = MockBigInt(1)

    def _create_grant(self, amounts, total_amount):
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(total_amount)
        amounts_str = ",".join(str(a) for a in amounts)
        criteria_str = "|".join([f"Criteria {i+1}" for i in range(len(amounts))])
        return self.contract.create_grant(
            grantee=self.grantee,
            title="Solvency Invariant Grant",
            proposal_url="https://valid-dao.org/proposal",
            milestone_amounts_str=amounts_str,
            milestone_criteria_json=criteria_str
        )

    def test_partial_release_followed_by_appeal_overturn(self):
        """
        Scenario 1: Partial release followed by OVERTURN
        - Milestone: 100 GEN
        - AI gives PARTIAL: 50 GEN released to grantee, 50 GEN liability reserved.
        - Grantee appeals staking 10 GEN.
        - Appellate court rules OVERTURN.
        - Contract must ONLY pay remaining 50 GEN to grantee (NOT 100 GEN again) + 10 GEN stake refund.
        - Proves total payout from escrow == 100 GEN (exactly 100%), total transfers == 110 GEN (funding + stake).
        """
        ms_amount = MockBigInt(100)
        grant_id = self._create_grant([ms_amount], ms_amount)
        ms_key = f"{grant_id}_0"

        # 1. Submit evidence
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "0", "https://evidence.com/proof", "Completed milestone")

        # 2. Adjudicate milestone -> AI returns PARTIAL (50%)
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% delivered"
        }
        res_raw = self.contract.adjudicate_milestone(grant_id, "0")
        res = json.loads(res_raw)
        self.assertEqual(res["verdict"], "PARTIAL")

        ms = self.contract.milestones[ms_key]
        self.assertEqual(ms.status, "AWAITING_PAYOUT")
        self.assertEqual(ms.disbursed_to_grantee, 50)
        self.assertEqual(ms.disbursed_to_funder, 0)
        # Verify 50 GEN was transferred to grantee immediately upon partial release
        self.assertEqual(len(self.gl.transfers), 1)
        self.assertEqual(self.gl.transfers[0]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[0]["value"], 50)

        # 3. Grantee appeals during cooling-off window, staking 10 GEN
        stake_amount = MockBigInt(10)
        self.gl.message.sender_address = self.grantee
        self.gl.message.value = stake_amount
        self.contract.file_appeal(grant_id, "0", "I fulfilled 100% of the milestone requirements.")
        
        ms_appealed = self.contract.milestones[ms_key]
        self.assertEqual(ms_appealed.status, "APPEALED")
        self.assertEqual(ms_appealed.appeal_count, 1)

        # 4. Appellate court rules OVERTURN (Grantee wins)
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "OVERTURN", "confidence": 100, "canary": self._extract_appeal_canary(prompt), "reason": "Evidence proved 100% completion"
        }
        appeal_res_raw = self.contract.adjudicate_appeal(grant_id, "0")
        appeal_res = json.loads(appeal_res_raw)
        self.assertEqual(appeal_res["verdict"], "OVERTURN")

        # Transfers check:
        # Transfer 0: 50 GEN (initial partial release to grantee)
        # Transfer 1: 10 GEN (refund stake bond to appellant grantee)
        # Transfer 2: 50 GEN (REMAINING liability to grantee, NOT 100 GEN!)
        self.assertEqual(len(self.gl.transfers), 3)
        self.assertEqual(self.gl.transfers[1]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[1]["value"], 10) # Stake refund
        self.assertEqual(self.gl.transfers[2]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[2]["value"], 50) # Only remaining 50 GEN!

        final_ms = self.contract.milestones[ms_key]
        self.assertEqual(final_ms.status, "APPROVED")
        self.assertEqual(final_ms.disbursed_to_grantee, 100) # Total 100% disbursed to grantee
        self.assertEqual(final_ms.disbursed_to_funder, 0)

        # Solvency Invariant Proof:
        total_transferred = sum(t["value"] for t in self.gl.transfers)
        total_inflow = ms_amount + stake_amount
        self.assertEqual(total_transferred, total_inflow, "Total payouts must exactly equal funding + stake")
        self.assertLessEqual(total_transferred, total_inflow)

    def test_partial_release_followed_by_appeal_upheld(self):
        """
        Scenario 2: Partial release followed by UPHELD (Appeal rejected)
        - Milestone: 100 GEN
        - AI gives PARTIAL: 50 GEN released to grantee, 50 GEN liability reserved in escrow.
        - Grantee appeals staking 10 GEN.
        - Appellate court rules UPHELD (Appeal rejected).
        - Stake bond (10 GEN) slashed and awarded to Funder.
        - Remaining liability (50 GEN) refunded back to Funder (NOT 100 GEN!).
        - Proves total payout from escrow == 100 GEN (50 grantee + 50 funder), total transfers == 110 GEN.
        """
        ms_amount = MockBigInt(100)
        grant_id = self._create_grant([ms_amount], ms_amount)
        ms_key = f"{grant_id}_0"

        # 1. Submit evidence & partial release
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "0", "https://evidence.com/proof", "Completed partial")

        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% delivered"
        }
        self.contract.adjudicate_milestone(grant_id, "0")

        # 2. Grantee appeals staking 10 GEN
        stake_amount = MockBigInt(10)
        self.gl.message.sender_address = self.grantee
        self.gl.message.value = stake_amount
        self.contract.file_appeal(grant_id, "0", "Disputing partial rating.")

        # 3. Appellate court rules UPHELD (Appeal rejected)
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "UPHOLD", "confidence": 100, "canary": self._extract_appeal_canary(prompt), "reason": "Original partial rating was accurate"
        }
        self.contract.adjudicate_appeal(grant_id, "0")

        # Transfers check:
        # Transfer 0: 50 GEN (initial partial release to grantee)
        # Transfer 1: 10 GEN (slashed stake bond transferred to funder)
        # Transfer 2: 50 GEN (REMAINING 50 GEN refunded to funder, NOT 100 GEN!)
        self.assertEqual(len(self.gl.transfers), 3)
        self.assertEqual(self.gl.transfers[1]["to"], self.funder)
        self.assertEqual(self.gl.transfers[1]["value"], 10) # Slashed stake to funder
        self.assertEqual(self.gl.transfers[2]["to"], self.funder)
        self.assertEqual(self.gl.transfers[2]["value"], 50) # Remaining 50 GEN liability refund

        final_ms = self.contract.milestones[ms_key]
        self.assertEqual(final_ms.status, "CUT")
        self.assertEqual(final_ms.disbursed_to_grantee, 50)
        self.assertEqual(final_ms.disbursed_to_funder, 50)

        # Solvency Invariant Proof:
        total_transferred = sum(t["value"] for t in self.gl.transfers)
        total_inflow = ms_amount + stake_amount
        self.assertEqual(total_transferred, total_inflow)
        self.assertLessEqual(total_transferred, total_inflow)

    def test_single_appeal_enforcement_and_repeated_appeal_rejection(self):
        """
        Scenario 3: Enforce single appeal per milestone
        - Once an appeal is filed for a milestone, any subsequent attempt to file an appeal
          MUST revert with UserError("Milestone has already been appealed. Only a single appeal per milestone is permitted.")
        """
        ms_amount = MockBigInt(100)
        grant_id = self._create_grant([ms_amount], ms_amount)

        # Submit & partial adjudication
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "0", "https://evidence.com/proof", "Deliverable report")
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% delivered"
        }
        self.contract.adjudicate_milestone(grant_id, "0")

        # First appeal succeeds
        self.gl.message.sender_address = self.grantee
        self.gl.message.value = MockBigInt(10)
        self.contract.file_appeal(grant_id, "0", "First appeal justification")

        # Second appeal attempt while PENDING -> Rejection
        with self.assertRaises(MockUserError) as ctx1:
            self.contract.file_appeal(grant_id, "0", "Second appeal attempt")
        self.assertIn("Milestone has already been appealed", str(ctx1.exception))

        # Adjudicate first appeal
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "UPHOLD", "confidence": 100, "canary": self._extract_appeal_canary(prompt), "reason": "Rejected"
        }
        self.contract.adjudicate_appeal(grant_id, "0")

        # Second appeal attempt AFTER adjudication -> Rejection
        self.gl.message.value = MockBigInt(10)
        with self.assertRaises(MockUserError) as ctx2:
            self.contract.file_appeal(grant_id, "0", "Repeated appeal after CUT")
        self.assertIn("Milestone has already been appealed", str(ctx2.exception))

    def test_multi_milestone_grant_solvency_invariants(self):
        """
        Scenario 4: Multi-milestone grant proving total payouts never exceed funding and stakes
        - 3 Milestones: 30 GEN, 50 GEN, 20 GEN. Total Funding: 100 GEN.
        - Milestone 0: RELEASE (100%) -> Finalized without appeal -> 30 GEN to grantee.
        - Milestone 1: PARTIAL (50%) -> 25 GEN to grantee -> Appealed (5 GEN stake) -> OVERTURN -> 25 GEN to grantee + 5 GEN stake refund.
        - Milestone 2: PARTIAL (50%) -> 10 GEN to grantee -> Appealed (5 GEN stake) -> UPHELD -> 10 GEN to funder + 5 GEN stake to funder.
        - Verify: Total payouts across all milestones == 100 GEN (Funding) + 10 GEN (Stakes) = 110 GEN.
        - Solvency invariant: total_transfers <= total_funding + total_stakes is strictly satisfied.
        """
        amounts = [MockBigInt(30), MockBigInt(50), MockBigInt(20)]
        total_funding = MockBigInt(100)
        grant_id = self._create_grant(amounts, total_funding)

        # -----------------------------------------------
        # Milestone 0 (30 GEN): Full RELEASE and Finalize
        # -----------------------------------------------
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "0", "https://evidence.com/m0", "Milestone 0 complete")
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "RELEASE", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "100% complete"
        }
        self.contract.adjudicate_milestone(grant_id, "0")
        
        # Fast forward cooling-off window & finalize
        self.contract._get_current_timestamp = lambda: MockBigInt(2000000000)
        self.contract.finalize_milestone_payout(grant_id, "0")
        self.assertEqual(self.contract.milestones[f"{grant_id}_0"].disbursed_to_grantee, 30)

        # -----------------------------------------------
        # Milestone 1 (50 GEN): PARTIAL -> Appeal OVERTURN
        # -----------------------------------------------
        self.contract._get_current_timestamp = lambda: MockBigInt(1757250000)
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "1", "https://evidence.com/m1", "Milestone 1 partial")
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% complete"
        }
        self.contract.adjudicate_milestone(grant_id, "1")
        self.assertEqual(self.contract.milestones[f"{grant_id}_1"].disbursed_to_grantee, 25)

        # File appeal with 5 GEN stake
        self.gl.message.value = MockBigInt(5)
        self.contract.file_appeal(grant_id, "1", "Milestone 1 appeal")

        # Adjudicate appeal -> OVERTURN
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "OVERTURN", "confidence": 100, "canary": self._extract_appeal_canary(prompt), "reason": "Full work delivered"
        }
        self.contract.adjudicate_appeal(grant_id, "1")
        self.assertEqual(self.contract.milestones[f"{grant_id}_1"].disbursed_to_grantee, 50)

        # -----------------------------------------------
        # Milestone 2 (20 GEN): PARTIAL -> Appeal UPHELD
        # -----------------------------------------------
        self.contract.submit_evidence(grant_id, "2", "https://evidence.com/m2", "Milestone 2 partial")
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% complete"
        }
        self.contract.adjudicate_milestone(grant_id, "2")
        self.assertEqual(self.contract.milestones[f"{grant_id}_2"].disbursed_to_grantee, 10)

        # File appeal with 5 GEN stake
        self.gl.message.value = MockBigInt(5)
        self.contract.file_appeal(grant_id, "2", "Milestone 2 appeal")

        # Adjudicate appeal -> UPHELD
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "UPHOLD", "confidence": 100, "canary": self._extract_appeal_canary(prompt), "reason": "Only 50% delivered"
        }
        self.contract.adjudicate_appeal(grant_id, "2")
        self.assertEqual(self.contract.milestones[f"{grant_id}_2"].disbursed_to_grantee, 10)
        self.assertEqual(self.contract.milestones[f"{grant_id}_2"].disbursed_to_funder, 10)

        # -----------------------------------------------
        # Comprehensive Solvency Invariant Proof
        # -----------------------------------------------
        total_transferred = sum(t["value"] for t in self.gl.transfers)
        total_stakes = MockBigInt(10) # 5 + 5
        total_expected = total_funding + total_stakes # 100 + 10 = 110

        self.assertEqual(total_transferred, total_expected)
        self.assertLessEqual(total_transferred, total_funding + total_stakes, "Total payouts strictly never exceed funding and stakes")
        
        # Verify grant is closed
        grant = self.contract.grants[grant_id]
        self.assertEqual(grant.status, "CLOSED")

    def test_cooling_off_window_finalization_without_appeal(self):
        """
        Scenario 5: Milestone is PARTIAL, no appeal filed during 24h cooling off window.
        - Milestone: 100 GEN
        - PARTIAL verdict: 50 GEN released to grantee, 50 GEN reserved in escrow.
        - Window elapses (now >= payout_ready_at).
        - finalize_milestone_payout is called.
        - Remaining 50 GEN liability is refunded to funder.
        - Total payouts == 100 GEN.
        """
        ms_amount = MockBigInt(100)
        grant_id = self._create_grant([ms_amount], ms_amount)
        ms_key = f"{grant_id}_0"

        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(grant_id, "0", "https://evidence.com/proof", "Partial report")
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "PARTIAL", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "50% delivered"
        }
        self.contract.adjudicate_milestone(grant_id, "0")

        # Advance timestamp past 24h
        self.contract._get_current_timestamp = lambda: MockBigInt(2000000000)
        fin_res = self.contract.finalize_milestone_payout(grant_id, "0")
        self.assertEqual(fin_res, "PAYOUT_FINALIZED")

        ms = self.contract.milestones[ms_key]
        self.assertEqual(ms.status, "PARTIAL")
        self.assertEqual(ms.disbursed_to_grantee, 50)
        self.assertEqual(ms.disbursed_to_funder, 50)

        # Transfers: 50 to grantee, 50 to funder
        self.assertEqual(len(self.gl.transfers), 2)
        self.assertEqual(self.gl.transfers[0]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[0]["value"], 50)
        self.assertEqual(self.gl.transfers[1]["to"], self.funder)
        self.assertEqual(self.gl.transfers[1]["value"], 50)
        self.assertEqual(sum(t["value"] for t in self.gl.transfers), 100)

    def _extract_canary(self, prompt):
        import re
        match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
        return match.group(1) if match else ""

    def _extract_appeal_canary(self, prompt):
        import re
        match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
        return match.group(1) if match else ""

if __name__ == '__main__':
    unittest.main()
