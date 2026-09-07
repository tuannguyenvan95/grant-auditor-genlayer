# Security Policy and Threat Model

This document outlines the security architecture, threat model, and safety guardrails engineered into the GrantAuditor Intelligent Contract on GenLayer.

## 1. Threat Model & Mitigations

| Threat | Target | Mitigations |
| :--- | :--- | :--- |
| **Prompt Injection** | LLM consensus verdict | **Canary Token Defense**: Generates a deterministic on-chain hash per milestone attempt: `sha256(canary_grant_milestone_attempt)`. LLM must repeat this token. Mismatches force immediate `ESCALATE` (or `UPHOLD`) status, preserving escrowed funds. |
| **Unusable Render Abuse** | Malicious CUT / Refund trigger | **Escrow Preservation Rule**: If proposal or evidence renders return 404, 500, or fail extraction, the contract automatically blocks any `CUT` verdict and overrides status to `ESCALATED`. |
| **Double Payout / Drain** | Escrowed funds in contract | **Terminal State Gating**: Once a milestone is terminal (`APPROVED`, `PARTIAL`, `CUT`), state guards prevent any duplicate adjudication or transfer execution. |
| **Oracle Latency Manipulation** | Non-deterministic state | **Optimistic Democracy**: Multi-validator LLM consensus verifies and votes on the leader's proposed outcome, preventing individual validator collusion. |
| **Inactive Funder Escrow Deadlock** | Frozen funds on `ESCALATED` milestones | **Stake-Based Appeal Protocol**: Grantees or funders can file an on-chain appeal by locking a GEN bond, convening the Senior AI Appellate Court to break deadlocks without waiting for inactive multisig signers. |
| **Frivolous Appeal / Sybil Griefing** | Malicious delay of contract settlement | **Bond Slasher Mechanism**: If an appeal is deemed invalid or frivolous by the Senior AI Jury (`UPHOLD`), 100% of the appellant's staked bond is slashed and paid to the counterparty as compensation for delay, along with reputation penalties. |
| **State Variable Loss in GenVM Sandbox** | Closure-captured mutations | **Serializable Dict Return**: All mutable extraction states (`extraction_errors`) are explicitly passed through the nondeterministic return dictionary instead of captured closures. |

---

## 2. Smart Contract Audit Checklist
- [x] All addresses case-normalized with `.lower()`.
- [x] `u256` explicitly cast in all `emit_transfer` payouts.
- [x] Storage attributes avoid bare `int` types, utilizing `bigint`, `TreeMap`, and sized integers.
- [x] Storage dictionaries (`appeals`, `reputations`, `milestones`, `grants`) never reassigned in `__init__`.
- [x] `validator_fn` enforces canary token validation and semantic consensus equality.
- [x] Maximum attempts capped at 3 to prevent contract spam.
- [x] Non-zero stake bond strictly enforced in `file_appeal`.
- [x] Reputation changes bounded with `max(0, ...)` to prevent negative underflows.
