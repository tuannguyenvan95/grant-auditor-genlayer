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
            return {"verdict": "RELEASE", "confidence": 100, "canary": canary, "reason": "100% completed"}

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

class TestV3SyndicateReputation(unittest.TestCase):
    def setUp(self):
        self.contract = contract_module.Contract()
        self.gl = mock_mod.gl
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
        self.contract.next_grant_id = MockBigInt(1)

        self.funder = MockAddress("0xfunder_alice")
        self.co_funder = MockAddress("0xfunder_bob")
        self.grantee = MockAddress("0xgrantee_charlie")
        self.gl.message.sender_address = self.funder

    def _extract_canary(self, prompt):
        import re
        match = re.search(r'"canary":\s*"([^"]+)"', str(prompt))
        return match.group(1) if match else ""

    def test_syndicate_pledge_and_accounting(self):
        """Verifies multi-party syndicate pooling: lead funder creates grant, co-funder pledges extra GEN."""
        # Alice creates grant: 100 GEN
        self.gl.message.value = MockBigInt(100)
        self.gl.message.sender_address = self.funder
        gid = self.contract.create_grant(
            self.grantee, "Syndicate Grant", "https://example.com/prop", "100", "Deliverable 1"
        )
        self.assertEqual(gid, "1")

        # Bob pledges 50 GEN to Milestone 0
        self.gl.message.value = MockBigInt(50)
        self.gl.message.sender_address = self.co_funder
        pledge_res = json.loads(self.contract.pledge_grant(gid, "0"))
        self.assertEqual(pledge_res["status"], "PLEDGE_RECORDED")
        self.assertEqual(pledge_res["new_milestone_amount"], "150")
        self.assertEqual(pledge_res["new_grant_total"], "150")

        # Check syndicate pool inspector
        pool_data = json.loads(self.contract.get_grant_pledges(gid))
        self.assertEqual(pool_data["total_amount"], "150")
        self.assertEqual(pool_data["pledgers_count"], 2)
        # Alice has 100 (66.67%), Bob has 50 (33.33%)
        pledges = pool_data["pledges"]
        self.assertEqual(pledges[0]["funder"], str(self.funder).lower())
        self.assertEqual(pledges[0]["amount"], "100")
        self.assertEqual(pledges[1]["funder"], str(self.co_funder).lower())
        self.assertEqual(pledges[1]["amount"], "50")

    def test_syndicate_proportional_clawback_on_cut(self):
        """Proves that on CUT, remaining escrow is refunded proportionately to all co-funders."""
        # Alice: 100 GEN, Bob: 100 GEN. Total = 200 GEN
        self.gl.message.value = MockBigInt(100)
        self.gl.message.sender_address = self.funder
        gid = self.contract.create_grant(
            self.grantee, "DeFi Protocol", "https://example.com/prop", "100", "M1"
        )

        self.gl.message.value = MockBigInt(100)
        self.gl.message.sender_address = self.co_funder
        self.contract.pledge_grant(gid, "0")

        # Charlie submits 3 failing attempts
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "CUT", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "Unacceptable deliverables"
        }

        for attempt in range(1, 4):
            self.gl.message.sender_address = self.grantee
            self.contract.submit_evidence(gid, "0", "https://evidence.com/fail", f"Attempt {attempt}")
            self.gl.message.sender_address = self.funder
            self.contract.adjudicate_milestone(gid, "0")

        ms = self.contract.milestones[f"{gid}_0"]
        self.assertEqual(ms.status, "CUT")

        # Solvency verification: total refunds equal exactly 200 GEN
        self.assertEqual(len(self.gl.transfers), 2)
        refund_alice = next(t["value"] for t in self.gl.transfers if t["to"] == self.funder)
        refund_bob = next(t["value"] for t in self.gl.transfers if t["to"] == self.co_funder)
        self.assertEqual(refund_alice, 100)
        self.assertEqual(refund_bob, 100)
        self.assertEqual(refund_alice + refund_bob, 200)

    def test_cancel_unstarted_grant_proportional_refund(self):
        """Proves funder can cancel unstarted grant with proportional refunds to co-funders."""
        # Alice: 150 GEN, Bob: 50 GEN. Total = 200 GEN
        self.gl.message.value = MockBigInt(150)
        self.gl.message.sender_address = self.funder
        gid = self.contract.create_grant(
            self.grantee, "Unstarted Project", "https://example.com/prop", "150", "M1"
        )

        self.gl.message.value = MockBigInt(50)
        self.gl.message.sender_address = self.co_funder
        self.contract.pledge_grant(gid, "0")

        # Alice cancels grant before Charlie submits
        self.gl.message.sender_address = self.funder
        cancel_res = self.contract.cancel_unstarted_grant(gid)
        self.assertEqual(cancel_res, "GRANT_CANCELLED")

        grant = self.contract.grants[gid]
        self.assertEqual(grant.status, "CLOSED")

        # Refunds: 150 to Alice, 50 to Bob
        refund_alice = next(t["value"] for t in self.gl.transfers if t["to"] == self.funder)
        refund_bob = next(t["value"] for t in self.gl.transfers if t["to"] == self.co_funder)
        self.assertEqual(refund_alice, 150)
        self.assertEqual(refund_bob, 50)
        self.assertEqual(sum(t["value"] for t in self.gl.transfers), 200)

    def test_dynamic_fast_track_cooling_window(self):
        """Proves that Gold/Platinum builders receive a 12h Fast-Track window instead of standard 24h."""
        # 1. Standard builder (<50 score)
        self.gl.message.value = MockBigInt(100)
        self.gl.message.sender_address = self.funder
        gid1 = self.contract.create_grant(
            self.grantee, "Normal Project", "https://example.com/prop", "100", "M1"
        )
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(gid1, "0", "https://evidence.com/ok", "Done")

        now_base = MockBigInt(1700000000)
        self.contract._get_current_timestamp = lambda: now_base
        contract_module.gl.nondet.exec_prompt = lambda prompt, response_format="json": {
            "verdict": "RELEASE", "confidence": 100, "canary": self._extract_canary(prompt), "reason": "All good"
        }
        self.contract.adjudicate_milestone(gid1, "0")
        ms1 = self.contract.milestones[f"{gid1}_0"]
        # Standard cooling window = 86400 seconds (24 hours)
        self.assertEqual(ms1.payout_ready_at - now_base, 86400)
        self.assertIn("24H DISPUTE WINDOW", ms1.reason)

        # 2. Boost grantee to Gold Established (>= 50 score)
        self.contract._update_reputation(str(self.grantee), 60)
        rep = json.loads(self.contract.get_reputation(str(self.grantee)))
        self.assertEqual(rep["tier"], "Gold Established")

        # Fast-track grant adjudication
        self.gl.message.value = MockBigInt(100)
        self.gl.message.sender_address = self.funder
        gid2 = self.contract.create_grant(
            self.grantee, "Gold Project", "https://example.com/prop", "100", "M1"
        )
        self.gl.message.sender_address = self.grantee
        self.contract.submit_evidence(gid2, "0", "https://evidence.com/ok2", "Done again")
        self.contract.adjudicate_milestone(gid2, "0")
        ms2 = self.contract.milestones[f"{gid2}_0"]
        # Fast-track cooling window = 43200 seconds (12 hours)
        self.assertEqual(ms2.payout_ready_at - now_base, 43200)
        self.assertIn("FAST-TRACK 12H DISPUTE WINDOW", ms2.reason)

    def test_reputation_dossier_and_leaderboard(self):
        """Verifies full builder dossier and on-chain leaderboard queries."""
        # Set up test reputations
        self.contract._update_reputation("0xalice", 80)
        self.contract._update_reputation("0xbob", 120)
        self.contract._inc_stat("completed", "0xbob")
        self.contract._inc_stat("completed", "0xbob")
        self.contract._inc_stat("appeals_won", "0xbob")

        profile_bob = json.loads(self.contract.get_reputation_profile("0xbob"))
        self.assertEqual(profile_bob["tier"], "Platinum Elite")
        self.assertTrue(profile_bob["fast_track_eligible"])
        self.assertEqual(profile_bob["milestones_completed"], 2)
        self.assertEqual(profile_bob["appeals_won"], 1)
        self.assertEqual(profile_bob["reliability_index"], 100.0)

        # Leaderboard should have Bob (120) first, Alice (80) second
        leaderboard = json.loads(self.contract.get_reputation_leaderboard())
        self.assertTrue(len(leaderboard) >= 2)
        self.assertEqual(leaderboard[0]["address"], "0xbob")
        self.assertEqual(leaderboard[0]["score"], 120)
        self.assertEqual(leaderboard[1]["address"], "0xalice")
        self.assertEqual(leaderboard[1]["score"], 80)
