# Changelog

All notable changes to the GrantAuditor project will be documented in this file.

## [v0.5.0] - 2026-08-30
### Added
- **Canary Token Defense**: Implemented a deterministic on-chain hash-based canary token generator in `adjudicate_milestone` to verify output integrity and defend against LLM prompt injections.
- **Canary Verification Tests**: Added comprehensive mock validation unit tests verifying canary mismatch detection and prompt injection mitigation in `tests/test_arbitration_flow.py`.
- **ARCHITECTURE.md**: Documented system sequence workflow and prompt safety mechanics.
- **SECURITY.md**: Detailed threat models, vulnerability mitigations, and audit checklists.

### Changed
- Standardized `validator_fn` to enforce strict canary validation before comparing semantic verdicts.
- Hardcoded fallback values to enforce `ESCALATE` verdict if canary checks fail post-consensus.
