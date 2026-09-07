# Changelog

All notable changes to the GrantAuditor project will be documented in this file.

## [v0.6.0] - 2026-09-07
### Added
- **Stake-Based Appeal Protocol (Category 3b Major Feature)**:
  - Added `@allow_storage @dataclass class Appeal` storing appellant, staked bond, justification, and supplemental evidence.
  - Implemented `@gl.public.write.payable def file_appeal(...)` allowing grantees or funders to stake a GEN bond and break inactive funder escrow deadlocks on disputed/escalated milestones.
  - Implemented `@gl.public.write def adjudicate_appeal(...)` invoking a Senior AI Appellate Jury via GenVM consensus to re-evaluate evidence and either `OVERTURN` (refund 100% bond + release escrow) or `UPHOLD` (slash bond to counterparty).
- **On-Chain Dynamic Reputation Engine (Category 3c Major Feature)**:
  - Added `reputations: TreeMap[str, bigint]` tracking real-time credit scores and tiers (Platinum Elite, Gold Established, Silver Verified, Bronze Newcomer).
  - Automatically awards positive reputation for successful deliveries and slashes points for frivolous disputes.
  - Implemented `@gl.public.view def get_reputation(...)` and `@gl.public.view def get_appeal(...)`.
- **Frontend Appeal & Reputation UI**:
  - Added on-chain Reputation Badges for Funder DAO and Grantee Recipient cards.
  - Added Senior AI Appellate Court resolution panel and inline Staked Appeal submission form.
- **Testing**:
  - Added `tests/test_appeal_flow.py` with 4 new automated unit test suites covering Overturn, Uphold/Slash, Bond Validation, and Tier Escalation.

## [v0.5.0] - 2026-08-30
### Added
- **Canary Token Defense**: Implemented a deterministic on-chain hash-based canary token generator in `adjudicate_milestone` to verify output integrity and defend against LLM prompt injections.
- **Canary Verification Tests**: Added comprehensive mock validation unit tests verifying canary mismatch detection and prompt injection mitigation in `tests/test_arbitration_flow.py`.
- **ARCHITECTURE.md**: Documented system sequence workflow and prompt safety mechanics.
- **SECURITY.md**: Detailed threat models, vulnerability mitigations, and audit checklists.

### Changed
- Standardized `validator_fn` to enforce strict canary validation before comparing semantic verdicts.
- Hardcoded fallback values to enforce `ESCALATE` verdict if canary checks fail post-consensus.
