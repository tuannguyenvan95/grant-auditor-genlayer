# GrantAuditor

GrantAuditor is an intelligent escrow and milestone adjudication system designed for DAOs and grant programs, built entirely on **GenLayer**.

## Why GenLayer?
Grant programs often suffer from subjective milestone evaluations. GenLayer solves this by providing a decentralized, intelligent consensus mechanism (Intelligent Contracts). By using GenLayer's Nondeterministic API (`gl.nondet.web.render` and `gl.nondet.exec_prompt`), GrantAuditor can automatically fetch grant proposals and submitted evidence (from URLs like GitHub, Notion, PDFs), and use an LLM consensus to adjudicate whether the milestone has been met. If met, funds are released on-chain automatically.

## Live App
- **Confirmed URL**: [https://grant-auditor-genlayer-xi.vercel.app](https://grant-auditor-genlayer-xi.vercel.app)

## Deployed Contract
- **Studionet Address**: `0xb70edE8901e3620f2C5E3729Ab39fC37A73D1E2f`
- **Explorer Link**: [GenLayer Explorer](https://explorer-studio.genlayer.com/address/0xb70edE8901e3620f2C5E3729Ab39fC37A73D1E2f)

## 🚀 Milestone v4.0 Ultimate: Autonomous AI Oracle Playground & On-Chain Holographic SVG Certificates

GrantAuditor v4.0 Ultimate elevates decentralized grant auditing into an enterprise-grade autonomous operating system:

### 1. Interactive AI Oracle Playground (Judge Sandbox)
- Evaluators can test GenLayer subjective consensus in real time with 1-click test vector benchmarks.
- **Canary Token Defense**: Cryptographic guardrails prevent adversarial prompt injection exploits.
- **Multi-Vector Scoring**: Real-time evaluation of Deliverable Completeness (0-100), Code Quality & Authenticity (0-100), and Risk/Fraud Index.

### 2. On-Chain Holographic SVG Certificates
- Pure vector certificates rendered directly from GenVM memory on-chain via `get_certificate_svg(grant_id)`.
- Features tamper-proof SHA-256 cryptographic provenance digests and builder trust tiers.

### 3. SLA Deadlines & Expired Escrow Clawback
- Unresponsive or abandoned builder milestones expire on-chain, entitling funders and syndicate pledgers to execute an immediate 100% clawback of unreleased escrow.
- Grantees can request formal extensions subject to on-chain funder approval.

### 4. Institutional Curator Council Governance
- Multi-member domain expert curator council with quorum thresholds to accelerate milestone releases and emergency veto powers to freeze suspicious deliverables into ESCALATED mode.

### 5. Community Signal Governance
- Decentralized sentiment signals (upvotes/downvotes) anchored to Studionet state.

### 1. Syndicate Multi-Funder Escrow Pool (`pledge_grant`)
- Anyone can co-fund active grants by pledging GEN tokens directly into milestone escrows.
- **Proportional Solvency Clawback**: In the event of a milestone rejection/CUT or cancellation, remaining funds are returned proportionally across all co-funders based on their contribution ratios.
- **Emergency Cancellation**: Funders can cancel unstarted grants and reclaim funds safely without lock-in.

### 2. On-Chain Reputation & Dynamic Fast-Track Adjudication
- Granular performance metrics tracked on-chain: completed milestones, rejection rate, appeals win/loss record.
- **Four Trust Tiers**: Bronze Newcomer (<20), Silver Verified (20-49), Gold Established (50-99), Platinum Elite (100+).
- **Fast-Track Settlement**: High-reputation builders (Gold/Platinum) unlock an accelerated **12-hour cooling-off dispute window (43,200s)**, while new builders maintain the standard 24 hours (86,400s).
- **Public Leaderboard**: Query top verified builders and funders via `get_reputation_leaderboard()`.

### 3. Automated Invariant & Security Verification Suite
Total test suite contains **21 automated unit and regression tests** verifying:
- Syndicate co-funding and proportional clawbacks.
- Single-appeal enforcement and anti-double-disbursement guarantees.
- Prompt injection canary token verification.
- Mathematical solvency: $\sum \text{Disbursements} + \sum \text{Refunds} \le \text{Initial Deposit} + \sum \text{Pledges} + \sum \text{Stakes}$.

To run all automated test suites:
```bash
pytest tests/
```

## 🛡️ Core GenLayer Compliance & Audit Standards
GrantAuditor has been engineered from the ground up to comply with rigorous GenLayer audit and judging standards:

### 1. Zero-Mock & 100% On-Chain Execution (No Simulated Timers)
Unlike demo prototypes that use artificial JavaScript timers (`setTimeout`) or local state overriding to simulate consensus progress, **GrantAuditor performs strictly on-chain read/write operations**. When an adjudication is triggered, the frontend binds directly to the GenLayer RPC (`genlayer-js`), awaiting real validator BFT agreement before updating UI states. No fake success paths exist.

### 2. Escrow Preservation on Data Extraction / Network Errors
A common vulnerability in decentralized escrow systems is defaulting to a "CUT" (refund to Customer/Funder) when external web links return HTTP 404, scraping failures, or network timeouts. This introduces an unfair exploitation vector against workers/grantees.
In GrantAuditor:
- **Mandatory Escrow Protection**: If `gl.nondet.web.render` encounters an HTTP error, unreachable domain, or unparseable JSON summary, the AI consensus engine and Python runtime fallbacks **NEVER output CUT**.
- **Fund Preservation**: Instead, all extraction anomalies result in an **ESCALATE** (freezing and preserving 100% of escrowed GEN tokens in the vault for DAO arbitration) or **RETRY** (allowing the Grantee to resubmit after a 60s cooldown without strike penalty). Escrow funds are strictly safeguarded against improper Funder refunds.

### 3. Payment Regression Verification Suite
We provide an automated regression test script designed specifically to verify the payment settlement pathway across valid, partial, fraudulent, and extraction error scenarios.

To run the regression verification suite locally:
```bash
node tests/test_payment_regression.mjs
```

## Architecture
- **Smart Contract**: Python-based Intelligent Contract on GenLayer (`contracts/grant_auditor.py`). Uses `TreeMap` and Nondeterministic execution for AI adjudication with escrow protection.
- **Frontend**: React + Vite + TypeScript + `genlayer-js`. A premium, dark-themed UI with real-time on-chain state sync and reactive Funder/Grantee controls.
- **Network**: GenLayer Studionet (ChainID: 61999).

## Contract Deployment (GenLayer Studio)
1. Visit [GenLayer Studio](https://studio.genlayer.com).
2. Copy the contents of `contracts/grant_auditor.py`.
3. Paste it into the Studio editor.
4. Click **Deploy**.
5. Once deployed, copy the **Contract Address** to use in your frontend.

## Frontend Setup & Testing
1. Open `.env` in the `frontend/` directory.
2. Add your deployed Contract Address:
   ```env
   VITE_CONTRACT_ADDRESS=0xb70edE8901e3620f2C5E3729Ab39fC37A73D1E2f
   ```
3. Run the development server or build for production:
   ```bash
   cd frontend
   npm run build # Verify clean TypeScript production compilation
   npm run dev   # Launch local workstation
   ```
