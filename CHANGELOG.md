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
- **24-Hour Dispute Cooling-Off Window (Steward Escrow Standard)**:
  - Added `AWAITING_PAYOUT` state on `RELEASE` / `PARTIAL` verdicts with `payout_ready_at` lock.
  - Implemented `@gl.public.write def finalize_milestone_payout(...)` to disburse funds only after the 24h cooling window.
  - Implemented `@gl.public.write def dispute_milestone(...)` enabling Funders to halt payout during cooling-off and escalate to DAO.
- **Untruncated Evidence Processing**:
  - Removed all `[:2000]` character slicing in `adjudicate_milestone` and `adjudicate_appeal`, feeding untruncated full texts into AI prompts per Steward Pavel Kolosov & Joaquín's guidelines.
- **Artifact Hash Pinning**:
  - Added `evidence_hash` support on `Milestone` and `submit_evidence` for immutable Git commit / SHA-256 digest validation.
- **Frontend Enhancements**:
  - Added 24H Cooling-off window panel with Finalize Payout and Dispute buttons.
  - Added Artifact Pinning field in milestone submission console.
- **Testing**:
  - Added 8 automated unit test suites covering Overturn, Uphold/Slash, Bond Validation, Reputation Tiers, 24H Cooling-off Window, and Funder Dispute.

## [v0.5.0] - 2026-08-30
### Added
- **Canary Token Defense**: Implemented a deterministic on-chain hash-based canary token generator in `adjudicate_milestone` to verify output integrity and defend against LLM prompt injections.
- **Canary Verification Tests**: Added comprehensive mock validation unit tests verifying canary mismatch detection and prompt injection mitigation in `tests/test_arbitration_flow.py`.
- **ARCHITECTURE.md**: Documented system sequence workflow and prompt safety mechanics.
- **SECURITY.md**: Detailed threat models, vulnerability mitigations, and audit checklists.

### Changed
- Standardized `validator_fn` to enforce strict canary validation before comparing semantic verdicts.
- Hardcoded fallback values to enforce `ESCALATE` verdict if canary checks fail post-consensus.
