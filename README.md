# GrantAuditor

GrantAuditor is an intelligent escrow and milestone adjudication system designed for DAOs and grant programs, built entirely on **GenLayer**.

## Why GenLayer?
Grant programs often suffer from subjective milestone evaluations. GenLayer solves this by providing a decentralized, intelligent consensus mechanism (Intelligent Contracts). By using GenLayer's Nondeterministic API (`gl.nondet.web.render` and `gl.nondet.exec_prompt`), GrantAuditor can automatically fetch grant proposals and submitted evidence (from URLs like GitHub, Notion, PDFs), and use an LLM consensus to adjudicate whether the milestone has been met. If met, funds are released on-chain automatically.

## Live App
- **Confirmed URL**: [https://grant-auditor-genlayer.vercel.app](https://grant-auditor-genlayer.vercel.app)

## Deployed Contract
- **Studionet Address**: `0x94Ea7A141f70D66BB24C56A9c4B4197fFb7c5030`
- **Explorer Link**: [GenLayer Explorer](https://genlayer-explorer.vercel.app/address/0x94Ea7A141f70D66BB24C56A9c4B4197fFb7c5030)

## Architecture
- **Smart Contract**: Python-based Intelligent Contract on GenLayer. It uses `TreeMap` and `DynArray` for storage, and Nondeterministic execution for AI adjudication.
- **Frontend**: React + Vite + TypeScript + `genlayer-js`. A premium, dark-themed UI with glassmorphism and Framer Motion animations.
- **Network**: GenLayer Studionet (ChainID: 61999).

## Contract Deployment (GenLayer Studio)
1. Visit [GenLayer Studio](https://studio.genlayer.com).
2. Copy the contents of `contracts/grant_auditor.py`.
3. Paste it into the Studio editor.
4. Click **Deploy**.
5. Once deployed, copy the **Contract Address**.

## Funding Your Wallet
To create a grant, you need GEN tokens on studionet.
1. Open the **Accounts** panel in GenLayer Studio.
2. Ensure your MetaMask wallet is connected to studionet.
3. Fund your wallet using the built-in faucet/funding options in the Studio.

## Frontend Setup
1. Open `.env` in the `frontend/` directory.
2. Add your Contract Address:
   ```env
   VITE_CONTRACT_ADDRESS=0x94Ea7A141f70D66BB24C56A9c4B4197fFb7c5030
   ```
3. Run the development server:
   ```bash
   cd frontend
   npm run dev
   ```
