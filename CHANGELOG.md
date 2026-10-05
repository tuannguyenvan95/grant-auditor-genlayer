# Changelog

All notable changes to the GrantAuditor project will be documented in this file.

## [v3.0.0] - 2026-10-05
### Added
- **Syndicate Multi-Funder Escrow Pool (`contracts/grant_auditor.py`)**:
  - Implemented `@gl.public.write.payable def pledge_grant(grant_id, milestone_id)` allowing multiple co-funders, angel sponsors, and community members to pool GEN into any active grant milestone.
  - Implemented `_refund_milestone_escrow` with mathematical **Proportional Clawback**: in case of milestone rejection/CUT or cancellation, remaining escrow is distributed proportionally across all contributors according to their pledge shares without rounding loss.
  - Implemented `@gl.public.write def cancel_unstarted_grant(grant_id)` enabling safe escrow reclamation with proportional refunds if deliverables have not yet commenced.
  - Implemented `@gl.public.view def get_grant_pledges(grant_id)` inspecting all syndicate co-funders, contributions, and share percentages.
- **On-Chain Reputation & Trust Tier Engine (`contracts/grant_auditor.py`)**:
  - Added granular performance attribution: `stats_completed`, `stats_failed`, `stats_appeals_won`, `stats_appeals_lost`, and `registered_users`.
  - Implemented **Dynamic Fast-Track Adjudication**: Grantees with Gold Established ($\ge 50$ pts) or Platinum Elite ($\ge 100$ pts) trust tiers automatically unlock an accelerated **12-hour cooling-off window (43,200s)**, while Bronze/Silver tiers maintain the standard 24 hours (86,400s).
  - Implemented `@gl.public.view def get_reputation_profile(user_address)` returning complete builder dossier (score, tier, fast-track eligibility, completion rate, win rate).
  - Implemented `@gl.public.view def get_reputation_leaderboard()` returning top 20 ranked builders and funders on-chain.
- **Milestone v3 Verification Suite (`tests/test_v3_syndicate_reputation.py`)**:
  - Added 5 comprehensive automated test suites verifying:
    1. Multi-funder syndicate pooling and pool inspector (`test_syndicate_pledge_and_accounting`).
    2. Proportional clawback on CUT to multiple co-funders (`test_syndicate_proportional_clawback_on_cut`).
    3. Unstarted grant cancellation and proportional refunds (`test_cancel_unstarted_grant_proportional_refund`).
    4. Dynamic 12h Fast-Track cooling-off window vs 24h standard window (`test_dynamic_fast_track_cooling_window`).
    5. Builder dossier analytics and on-chain leaderboard queries (`test_reputation_dossier_and_leaderboard`).
  - Total test suite expanded to 21/21 passing tests (100% pass rate in 0.13s).
- **Frontend Workstation Enhancements (`frontend/src/App.tsx`)**:
  - Added Syndicate Co-Funding Modal with tranche selection and real-time contribution share calculation.
  - Added On-Chain Leaderboard & Trust Tier Drawer displaying ranks, scores, badges, and fast-track statuses.
  - Added dynamic `⚡ AWAITING PAYOUT (FAST-TRACK 12H)` badge on qualifying milestones.
  - Added Emergency Grant Cancellation for unstarted grants with automatic pool recovery.

## [v0.6.2] - 2026-09-21
### Added
- **Formal Invariant & Solvency Test Suite (`tests/test_liability_invariants.py`)**:
  - Added 5 comprehensive contract test suites verifying mathematical solvency:
    1. Partial release (50%) followed by appeal `OVERTURN` (Grantee wins): pays only remaining 50% liability + refunds stake; prevents double-disbursement.
    2. Partial release (50%) followed by appeal `UPHELD` (Appeal rejected): refunds remaining 50% liability to funder + slashes stake to funder.
    3. Single appeal per milestone enforcement: rejects repeated appeal attempts with `UserError`.
    4. Multi-milestone grant lifecycle solvency: proves total payouts strictly never exceed total funding + stakes across all milestone combinations.
    5. Cooling-off window finalization without appeal: refunds remaining 50% liability to funder after 24h.
  - Assertions prove $\sum \text{Payouts} \le \text{Total Funding} + \sum \text{Stakes}$.

### Changed
- **Anti-Double-Disbursement & Liability Tracking (`contracts/grant_auditor.py`)**:
  - Added `disbursed_to_grantee: bigint`, `disbursed_to_funder: bigint`, and `appeal_count: bigint` to `Milestone` storage schema.
  - In `adjudicate_appeal`, when verdict is `OVERTURN`, contract releases *only* the remaining undisbursed liability (`ms.amount - ms.disbursed_to_grantee`), strictly preventing already-paid milestone value from being disbursed again.
  - When verdict is `UPHELD`, contract refunds *only* the remaining undisbursed liability (`ms.amount - ms.disbursed_to_grantee - ms.disbursed_to_funder`).
- **Reserved Liability Through Appeal Window**:
  - In `adjudicate_milestone` upon `PARTIAL` verdict, the undisputed 50% tranche is released to grantee while the remaining 50% liability is strictly reserved in escrow through the 24h dispute/appeal window.
  - If no appeal is filed, `finalize_milestone_payout` refunds the reserved 50% liability to the funder.
- **Single Appeal Per Milestone**:
  - Enforced in `file_appeal`: each milestone can only be appealed once. Any repeat attempt reverts with `UserError`.

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
