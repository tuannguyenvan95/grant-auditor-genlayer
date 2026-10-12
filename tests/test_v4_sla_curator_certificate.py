import sys
import os
import json
import pytest
import unittest
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
            self.pledges = {}
            self.grant_pledgers = {}
            self.stats_completed = {}
            self.stats_failed = {}
            self.stats_appeals_won = {}
            self.stats_appeals_lost = {}
            self.registered_users = {}
            self.milestone_deadlines = {}
            self.extension_requests = {}
            self.grant_curators = {}
            self.curator_thresholds = {}
            self.curator_endorsements = {}
            self.curator_vetoes = {}
            self.audit_certificates = {}

    class public:
        @staticmethod
        def view(fn): return fn
        @staticmethod
        def write(fn): return fn

    class message:
        value = MockBigInt(0)
        sender_address = MockAddress("0xfunder")

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
            return {"verdict": "PARTIAL", "confidence": 100, "canary": canary, "reason": "50% completed."}

    class vm:
        Return = MockReturn
        @staticmethod
        def run_nondet(leader_fn, validator_fn):
            res = leader_fn()
            ret_obj = MockReturn(res)
            assert validator_fn(ret_obj) is True
            return res

    def __init__(self):
        self.transfers = []

    def get_contract_at(self, address):
        return MockContractStub(address, self.transfers)

MockGL.public.write.payable = lambda fn: fn

mock_mod = MagicMock()
mock_gl_instance = MockGL()
mock_mod.gl = mock_gl_instance
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

class TestV4SLACuratorCertificate(unittest.TestCase):
    def setUp(self):
        self.contract = contract_module.Contract()
        self.gl = mock_gl_instance
        self.gl.transfers = []
        contract_module.gl = self.gl

        self.contract.grants = {}
        self.contract.milestones = {}
        self.contract.appeals = {}
        self.contract.reputations = {}
        self.contract.pledges = {}
        self.contract.grant_pledgers = {}
        self.contract.stats_completed = {}
        self.contract.stats_failed = {}
        self.contract.stats_appeals_won = {}
        self.contract.stats_appeals_lost = {}
        self.contract.registered_users = {}
        self.contract.milestone_deadlines = {}
        self.contract.extension_requests = {}
        self.contract.grant_curators = {}
        self.contract.curator_thresholds = {}
        self.contract.curator_endorsements = {}
        self.contract.curator_vetoes = {}
        self.contract.audit_certificates = {}
        self.contract.next_grant_id = MockBigInt(1)

        self.funder = MockAddress("0xfunder_alice")
        self.backer = MockAddress("0xbacker_bob")
        self.grantee = MockAddress("0xgrantee_charlie")
        self.curator1 = MockAddress("0xcurator_dave")
        self.curator2 = MockAddress("0xcurator_eve")
        self.gl.message.sender_address = self.funder

    def _extract_canary(self, prompt):
        import re
        match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
        return match.group(1) if match else ""

    def test_sla_deadline_configuration_and_expired_claim(self):
        """Proves that unfulfilled milestones past SLA deadline can be claimed and refunded proportionally."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(100)
        gid = self.contract.create_grant(
            self.grantee, "SLA Test Project", "https://example.com/prop", "100", "Deliverable 1"
        )

        # Backer pledges 50 GEN
        self.gl.message.sender_address = self.backer
        self.gl.message.value = MockBigInt(50)
        self.contract.pledge_grant(gid, "0")

        # Funder sets SLA deadline at timestamp 1000
        self.gl.message.sender_address = self.funder
        set_res = json.loads(self.contract.set_milestone_deadline(gid, "0", "1000"))
        self.assertEqual(set_res["status"], "DEADLINE_CONFIGURED")

        # Fast forward time to 2000 (expired)
        self.contract._get_current_timestamp = lambda: MockBigInt(2000)

        # Funder claims expired milestone escrow
        self.gl.transfers.clear()
        claim_res = json.loads(self.contract.claim_expired_milestone(gid, "0"))
        self.assertEqual(claim_res["status"], "EXPIRED_ESCROW_CLAIMED")
        self.assertEqual(claim_res["refunded_amount"], "150")

        # Verify proportional refund
        refund_alice = sum(t["value"] for t in self.gl.transfers if t["to"] == self.funder)
        refund_bob = sum(t["value"] for t in self.gl.transfers if t["to"] == self.backer)
        self.assertEqual(refund_alice, 100)
        self.assertEqual(refund_bob, 50)
        self.assertEqual(refund_alice + refund_bob, 150)

        # Verify milestone status is CUT and SLA reason recorded
        grant_data = json.loads(self.contract.get_grant(gid))
        ms0 = grant_data["milestones"][0]
        self.assertEqual(ms0["status"], "CUT")
        self.assertIn("SLA EXPIRED", ms0["reason"])
        self.assertEqual(ms0["remaining_liability"], "0")

        # Verify grant closed and audit certificate minted automatically
        self.assertEqual(grant_data["status"], "CLOSED")
        cert = grant_data["audit_certificate"]
        self.assertIsNotNone(cert)
        self.assertEqual(cert["audit_grade"], "FORFEITED_OR_CUT")
        self.assertTrue(cert["certificate_hash"].startswith("0x"))

    def test_claim_expired_milestone_premature_rejection(self):
        """Proves that attempting to claim an unexpired milestone strictly reverts."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(100)
        gid = self.contract.create_grant(
            self.grantee, "Unexpired Project", "https://example.com/prop", "100"
        )

        self.contract._get_current_timestamp = lambda: MockBigInt(1000)
        self.contract.set_milestone_deadline(gid, "0", "5000000")

        with self.assertRaises(MockUserError) as cm:
            self.contract.claim_expired_milestone(gid, "0")
        self.assertIn("has not expired yet", str(cm.exception))

    def test_builder_deadline_extension_workflow(self):
        """Proves the on-chain extension request and funder approval cycle."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(100)
        gid = self.contract.create_grant(
            self.grantee, "Extension Workflow", "https://example.com/prop", "100"
        )

        self.contract._get_current_timestamp = lambda: MockBigInt(1000)
        self.contract.set_milestone_deadline(gid, "0", "2000")

        # Grantee requests 86400s (1 day) extension
        self.gl.message.sender_address = self.grantee
        req_res = json.loads(self.contract.request_deadline_extension(gid, "0", "86400", "Pending security audit"))
        self.assertEqual(req_res["status"], "EXTENSION_REQUESTED")

        # Non-funder review should revert
        self.gl.message.sender_address = MockAddress("0xhacker")
        with self.assertRaises(MockUserError) as cm:
            self.contract.review_extension_request(gid, "0", approved=True)
        self.assertIn("Only the grant funder can review", str(cm.exception))

        # Funder approves extension
        self.gl.message.sender_address = self.funder
        rev_res = json.loads(self.contract.review_extension_request(gid, "0", approved=True))
        self.assertEqual(rev_res["status"], "EXTENSION_APPROVED")
        self.assertEqual(rev_res["new_deadline"], 2000 + 86400)

        # Query SLA status
        sla = json.loads(self.contract.get_milestone_sla(gid, "0"))
        self.assertEqual(sla["deadline"], 2000 + 86400)
        self.assertEqual(sla["extension_request"]["status"], "APPROVED")

    def test_curator_council_endorsement_and_instant_payout(self):
        """Proves Curator Council quorum waives the cooling-off window for immediate payout."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(100)
        gid = self.contract.create_grant(
            self.grantee, "Curated Grant", "https://example.com/prop", "100"
        )

        # Configure council with 2 curators and threshold 2
        self.contract.set_curator_council(gid, f"{self.curator1},{self.curator2}", "2")

        # Submit evidence
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(gid, "0", "https://example.com/ev", "Full report")

        # AI Adjudicates: PARTIAL (50% released, cooling-off window starts)
        self.contract._get_current_timestamp = lambda: MockBigInt(1000)
        self.gl.message.sender_address = self.funder
        self.contract.adjudicate_milestone(gid, "0")

        ms_data = json.loads(self.contract.get_grant(gid))["milestones"][0]
        self.assertEqual(ms_data["status"], "AWAITING_PAYOUT")
        self.assertGreater(int(ms_data["payout_ready_at"]), 1000)

        # Attempt premature finalization -> MUST REVERT
        with self.assertRaises(MockUserError) as cm:
            self.contract.finalize_milestone_payout(gid, "0")
        self.assertIn("dispute window has not elapsed yet", str(cm.exception))

        # Curator 1 endorses (1/2 endorsements - not yet quorum)
        self.gl.message.sender_address = self.curator1
        end1 = json.loads(self.contract.curator_endorse(gid, "0", "Code looks solid"))
        self.assertFalse(end1["quorum_reached"])
        self.assertFalse(end1["cooling_off_waived"])

        # Curator 2 endorses (2/2 endorsements -> QUORUM REACHED!)
        self.gl.message.sender_address = self.curator2
        end2 = json.loads(self.contract.curator_endorse(gid, "0", "Verified tests"))
        self.assertTrue(end2["quorum_reached"])
        self.assertTrue(end2["cooling_off_waived"])

        # Payout cooling-off delay is now waived -> can finalize immediately!
        self.gl.message.sender_address = self.funder
        fin_res = self.contract.finalize_milestone_payout(gid, "0")
        self.assertEqual(fin_res, "PAYOUT_FINALIZED")

        ms_final = json.loads(self.contract.get_grant(gid))["milestones"][0]
        self.assertEqual(ms_final["status"], "PARTIAL")

    def test_curator_emergency_veto(self):
        """Proves that a curator can freeze an escalated milestone upon detecting vulnerability."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(100)
        gid = self.contract.create_grant(
            self.grantee, "Veto Test", "https://example.com/prop", "100"
        )

        self.contract.set_curator_council(gid, str(self.curator1), "1")

        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(gid, "0", "https://example.com/ev", "Report")

        # Curator triggers security veto
        self.gl.message.sender_address = self.curator1
        veto_res = json.loads(self.contract.curator_veto(gid, "0", "Backdoor detected in repo dependency"))
        self.assertEqual(veto_res["status"], "CURATOR_VETOED")

        ms = json.loads(self.contract.get_grant(gid))["milestones"][0]
        self.assertEqual(ms["status"], "ESCALATED")
        self.assertIn("CURATOR VETO TRIGGERED", ms["reason"])

    def test_cryptographic_audit_certificate_provenance(self):
        """Proves immutable on-chain certificate generation with SHA-256 integrity hash."""
        self.gl.message.sender_address = self.funder
        self.gl.message.value = MockBigInt(200)
        gid = self.contract.create_grant(
            self.grantee, "Verifiable Certificate Grant", "https://example.com/prop", "100,100"
        )

        # Cancel unstarted grant to close it immediately with full refund
        self.contract.cancel_unstarted_grant(gid)

        cert_json = self.contract.get_audit_certificate(gid)
        cert = json.loads(cert_json)

        self.assertEqual(cert["grant_id"], gid)
        self.assertEqual(cert["certificate_id"], f"GA-CERT-V4-{gid}")
        self.assertTrue(cert["certificate_hash"].startswith("0x"))
        self.assertEqual(cert["audit_grade"], "FORFEITED_OR_CUT")
        self.assertEqual(cert["total_refunded_to_funders"], "200")
        self.assertEqual(cert["total_disbursed_to_grantee"], "0")
        self.assertIn("GenLayer", cert["auditor_protocol"])
