import sys
import os
import re
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
            def render(url, mode="text"): return "Mock web render content"
        @staticmethod
        def exec_prompt(prompt, response_format="json"):
            import re
            canary = ""
            match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
            if match:
                canary = match.group(1)
            # Default response
            return {"verdict": "OVERTURN", "confidence": 100, "canary": canary, "reason": "Appellate jury approved"}

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

class TestGrantAuditorAppealSuite(unittest.TestCase):
    def setUp(self):
        self.gl = mock_mod.gl
        self.gl.transfers = []
        self.funder = MockAddress("0xfunder")
        self.grantee = MockAddress("0xgrantee")
        self.stranger = MockAddress("0xstranger")

        self.gl.message.sender_address = self.funder
        self.contract = contract_module.Contract()
        contract_module.gl = self.gl
        self.contract.grants = {}
        self.contract.milestones = {}
        self.contract.appeals = {}
        self.contract.reputations = {}

        # Create Grant: 1000 GEN for 1 milestone
        self.gl.message.value = MockBigInt(1000)
        self.gid = self.contract.create_grant(
            grantee=self.grantee,
            title="AI Protocol Integration",
            proposal_url="https://proposal.org/spec.pdf",
            milestone_amounts_str="1000",
            milestone_criteria_json='["Deploy protocol contract"]'
        )

    def test_01_file_appeal_requires_valid_stake_and_authorized_sender(self):
        """Tests that filing an appeal requires non-zero stake and authorized role."""
        # 1. Grantee submits evidence
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(self.gid, "0", "https://evidence.org/doc.pdf", "Finished work")

        # 2. Put milestone into ESCALATED state
        ms = self.contract.milestones[f"{self.gid}_0"]
        ms.status = "ESCALATED"
        self.contract.milestones[f"{self.gid}_0"] = ms

        # 3. Stranger attempts to appeal -> FAILS
        self.gl.message.sender_address = self.stranger
        self.gl.message.value = MockBigInt(100)
        with self.assertRaises(MockUserError):
            self.contract.file_appeal(self.gid, "0", "Disputing decision", "https://backup.org")

        # 4. Grantee attempts with 0 stake -> FAILS
        self.gl.message.sender_address = self.grantee
        self.gl.message.value = MockBigInt(0)
        with self.assertRaises(MockUserError):
            self.contract.file_appeal(self.gid, "0", "Disputing decision", "https://backup.org")

        # 5. Grantee files appeal with 200 stake -> SUCCEEDS
        self.gl.message.value = MockBigInt(200)
        res = self.contract.file_appeal(self.gid, "0", "Deliverable was valid, source link had transient outage", "https://mirror.org/proof.pdf")
        self.assertEqual(res, "APPEAL_FILED")

        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "APPEALED")

        # Verify stored appeal record
        appeal_raw = self.contract.get_appeal(self.gid, "0")
        appeal = json.loads(appeal_raw)
        self.assertEqual(appeal["status"], "PENDING")
        self.assertEqual(appeal["stake_amount"], "200")
        self.assertEqual(appeal["appellant"], self.grantee)

    def test_02_adjudicate_appeal_overturn_refunds_bond_and_releases_milestone(self):
        """Scenario A: AI Senior Jury OVERTURNS decision -> Refunds stake + releases milestone + boosts reputation."""
        # Setup milestone to APPEALED with 200 GEN bond
        ms = self.contract.milestones[f"{self.gid}_0"]
        ms.status = "APPEALED"
        self.contract.milestones[f"{self.gid}_0"] = ms
        self.contract.appeals[f"{self.gid}_0"] = contract_module.Appeal(
            grant_id=self.gid,
            milestone_id="0",
            appellant=str(self.grantee),
            stake_amount=MockBigInt(200),
            justification="Backup proof demonstrates completion",
            supplemental_url="https://backup.org/proof.pdf",
            status="PENDING",
            reason="Awaiting adjudication"
        )

        # Mock AI to return OVERTURN
        import re
        def mock_overturn(prompt, response_format="json"):
            canary = ""
            m = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
            if m:
                canary = m.group(1)
            return {
                "verdict": "OVERTURN",
                "confidence": 100,
                "canary": canary,
                "reason": "Supplemental evidence conclusively proves delivery."
            }
        self.gl.nondet.exec_prompt = mock_overturn

        self.contract.adjudicate_appeal(self.gid, "0")

        # Assertions
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "APPROVED")
        appeal = self.contract.appeals[f"{self.gid}_0"]
        self.assertEqual(appeal.status, "OVERTURNED")

        # Verify transfers: 1. Refund 200 stake to grantee, 2. Release 1000 milestone to grantee
        self.assertEqual(len(self.gl.transfers), 2)
        self.assertEqual(self.gl.transfers[0]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[0]["value"], 200)
        self.assertEqual(self.gl.transfers[1]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[1]["value"], 1000)

        # Verify reputation boost
        rep_raw = self.contract.get_reputation(self.grantee)
        rep = json.loads(rep_raw)
        self.assertGreater(rep["score"], 0)

    def test_03_adjudicate_appeal_uphold_slashes_bond_to_funder(self):
        """Scenario B: AI Senior Jury UPHOLDS rejection -> Slashes stake bond to funder + cuts milestone."""
        # Setup milestone to APPEALED with 200 GEN bond by grantee
        ms = self.contract.milestones[f"{self.gid}_0"]
        ms.status = "APPEALED"
        self.contract.milestones[f"{self.gid}_0"] = ms
        self.contract.appeals[f"{self.gid}_0"] = contract_module.Appeal(
            grant_id=self.gid,
            milestone_id="0",
            appellant=str(self.grantee),
            stake_amount=MockBigInt(200),
            justification="Frivolous appeal",
            supplemental_url="https://empty.org",
            status="PENDING",
            reason="Awaiting adjudication"
        )

        # Mock AI to return UPHOLD
        def mock_uphold(prompt, response_format="json"):
            canary = ""
            m = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
            if m:
                canary = m.group(1)
            return {
                "verdict": "UPHOLD",
                "confidence": 100,
                "canary": canary,
                "reason": "Supplemental proof is invalid and work is incomplete."
            }
        self.gl.nondet.exec_prompt = mock_uphold

        self.contract.adjudicate_appeal(self.gid, "0")

        # Assertions
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "CUT")
        appeal = self.contract.appeals[f"{self.gid}_0"]
        self.assertEqual(appeal.status, "UPHELD")

        # Verify transfers: 1. Slashed 200 stake bond transferred to FUNDER, 2. 1000 milestone escrow refunded to FUNDER
        self.assertEqual(len(self.gl.transfers), 2)
        self.assertEqual(self.gl.transfers[0]["to"], self.funder)
        self.assertEqual(self.gl.transfers[0]["value"], 200)
        self.assertEqual(self.gl.transfers[1]["to"], self.funder)
        self.assertEqual(self.gl.transfers[1]["value"], 1000)

    def test_04_reputation_tiers(self):
        """Tests that reputation scoring and tier calculation functions properly."""
        self.contract._update_reputation(str(self.grantee), 60)
        rep = json.loads(self.contract.get_reputation(self.grantee))
        self.assertEqual(rep["score"], 60)
        self.assertEqual(rep["tier"], "Gold Established")

        self.contract._update_reputation(str(self.grantee), 50)
        rep2 = json.loads(self.contract.get_reputation(self.grantee))
        self.assertEqual(rep2["score"], 110)
        self.assertEqual(rep2["tier"], "Platinum Elite")

    def test_05_awaiting_payout_cooling_off_and_finalize(self):
        """Tests that AWAITING_PAYOUT blocks premature payout, then finalizes after cooling off."""
        ms = self.contract.milestones[f"{self.gid}_0"]
        ms.status = "AWAITING_PAYOUT"
        # Set ready in future
        ms.payout_ready_at = MockBigInt(2000000000)
        ms.reason = "Awaiting payout 100% RELEASE"
        self.contract.milestones[f"{self.gid}_0"] = ms

        # Mock current time before payout_ready_at -> FAILS
        self.contract._get_current_timestamp = lambda: MockBigInt(1900000000)
        with self.assertRaises(MockUserError):
            self.contract.finalize_milestone_payout(self.gid, "0")

        # Mock current time after payout_ready_at -> SUCCEEDS
        self.contract._get_current_timestamp = lambda: MockBigInt(2000000001)
        res = self.contract.finalize_milestone_payout(self.gid, "0")
        self.assertEqual(res, "PAYOUT_FINALIZED")
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "APPROVED")
        self.assertEqual(len(self.gl.transfers), 1)
        self.assertEqual(self.gl.transfers[0]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[0]["value"], 1000)

    def test_06_awaiting_payout_disputed_by_funder_escalates(self):
        """Tests that Funder can dispute during 24h cooling off, escalating milestone."""
        ms = self.contract.milestones[f"{self.gid}_0"]
        ms.status = "AWAITING_PAYOUT"
        ms.payout_ready_at = MockBigInt(2000000000)
        self.contract.milestones[f"{self.gid}_0"] = ms

        self.contract._get_current_timestamp = lambda: MockBigInt(1900000000)
        # Stranger disputes -> FAILS
        self.gl.message.sender_address = self.stranger
        with self.assertRaises(MockUserError):
            self.contract.dispute_milestone(self.gid, "0", "Disputing")

        # Funder disputes -> SUCCEEDS
        self.gl.message.sender_address = self.funder
        res = self.contract.dispute_milestone(self.gid, "0", "Suspected plagiarism detected")
        self.assertEqual(res, "MILESTONE_DISPUTED")
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "ESCALATED")

if __name__ == "__main__":
    unittest.main(verbosity=2)
