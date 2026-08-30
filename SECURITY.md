# Security Policy and Threat Model

This document outlines the security architecture, threat model, and safety guardrails engineered into the GrantAuditor Intelligent Contract.

## Threat Model

| Threat | Target | Mitigations |
| :--- | :--- | :--- |
| **Prompt Injection** | LLM consensus verdict | **Canary Token Defense**: Generates a deterministic on-chain hash per milestone attempt. LLM must repeat this token. Mismatches force immediate `ESCALATE` status, preserving escrow. |
| **Unusable Render Abuse** | Malicious CUT / Refund trigger | **Escrow Preservation Rule**: If proposal or evidence renders return 404, 500, or fail extraction, the contract automatically blocks the consensus verdict and overrides status to `ESCALATED`. |
| **Double Payout** | Escrowed funds in contract | **Terminal State Gating**: Once milestone is resolved (`APPROVED`, `PARTIAL`, `CUT`), state variable prevents any duplicate adjudication calls. |
| **Oracle Latency Manipulation** | Non-deterministic state | **Optimistic Democracy**: Multi-validator LLM consensus verifies and votes on the leader's proposed outcome, preventing individual validator collusion. |

## Audit Checklist
- [x] All addresses case-normalized with `.lower()`.
- [x] `u256` explicitly cast in all `emit_transfer` calls.
- [x] Storage attributes avoid bare `int` types, utilizing `bigint` and sized integers.
- [x] `validator_fn` compares semantic verdict equality instead of text matching.
- [x] Maximum attempts capped at 3 to prevent contract spam.
