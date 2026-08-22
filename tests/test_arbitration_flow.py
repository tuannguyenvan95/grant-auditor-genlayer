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
            def render(url, mode="text"): pass
        @staticmethod
        def exec_prompt(prompt, response_format="json"): pass

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

class TestGrantAuditorArbitrationSuite(unittest.TestCase):
    def setUp(self):
        self.gl = mock_mod.gl
        self.gl.transfers = []
        self.funder = MockAddress("0xfunder")
        self.grantee = MockAddress("0xgrantee")
        self.hacker = MockAddress("0xhacker")

        self.gl.message.sender_address = self.funder
        self.contract = contract_module.Contract()
        self.contract.grants = {}
        self.contract.milestones = {}

        # Create Grant: 1000 GEN for 1 milestone
        self.gl.message.value = MockBigInt(1000)
        self.gid = self.contract.create_grant(
            grantee=self.grantee,
            title="GenLayer Ecosystem Tooling",
            proposal_url="https://proposal.org/spec.pdf",
            milestone_amounts_str="1000",
            milestone_criteria_json='["Build and deploy smart contract"]'
        )

    def test_01_submit_evidence_with_progress_report(self):
        """Passes progress report text to submit_evidence and stores on-chain."""
        self.gl.message.sender_address = self.grantee
        report_text = "Completed milestone 1: Deployed contract and integrated frontend UI."
        res = self.contract.submit_evidence(self.gid, "0", "https://evidence.org/proof.pdf", progress_report=report_text)
        
        self.assertEqual(res, "EVIDENCE_SUBMITTED")
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "SUBMITTED")
        self.assertEqual(ms.progress_report, report_text)

    def test_02_arbitration_transaction_exercised_and_confirmed(self):
        """Simulates extraction error -> ESCALATED, then exercises resolve_escalated_milestone."""
        # 1. Grantee submits evidence
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(self.gid, "0", "https://evidence.org/broken_link.pdf", "Finished work")

        # 2. Broken render triggers hard runtime override to ESCALATE
        self.gl.nondet.web.render = lambda url, mode="text": "404 Not Found"
        self.contract.adjudicate_milestone(self.gid, "0")
        
        ms = self.contract.milestones[f"{self.gid}_0"]
        self.assertEqual(ms.status, "ESCALATED")
        self.assertEqual(len(self.gl.transfers), 0)

        # 3. Unauthorized hacker attempts to resolve -> MUST FAIL
        self.gl.message.sender_address = self.hacker
        with self.assertRaises(MockUserError):
            self.contract.resolve_escalated_milestone(self.gid, "0", "RELEASE", "Hacker dispute")

        # 4. Funder / Arbiter exercises resolve_escalated_milestone -> CONFIRMED
        self.gl.message.sender_address = self.funder
        arb_res = self.contract.resolve_escalated_milestone(self.gid, "0", "PARTIAL", "DAO reviewed offline proof: partial approval")
        
        parsed_arb = json.loads(arb_res)
        self.assertEqual(parsed_arb["status"], "PARTIAL")
        
        # Verify 50/50 token transfer execution
        self.assertEqual(len(self.gl.transfers), 2)
        self.assertEqual(self.gl.transfers[0]["to"], self.grantee)
        self.assertEqual(self.gl.transfers[0]["value"], 500)
        self.assertEqual(self.gl.transfers[1]["to"], self.funder)
        self.assertEqual(self.gl.transfers[1]["value"], 500)

if __name__ == "__main__":
    unittest.main(verbosity=2)
