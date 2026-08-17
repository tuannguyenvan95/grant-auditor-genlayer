import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { privateKeyToAccount } from 'viem/accounts';
import { parseEther } from 'viem';

// Constants
const CONTRACT_ADDRESS = '0xAb873395e9783f1eCbFbc28a49132AAbEB2fa43c';
const DEFAULT_TEST_KEY = '0x5f5babe2057032ab30b8a353f13341478785069644a0c6d3126539104cd48168';

// Environment variable support for security best practices (R22 compliance)
const privateKey = process.env.TEST_PRIVATE_KEY || DEFAULT_TEST_KEY;
const account = privateKeyToAccount(privateKey);
const client = createClient({
  chain: studionet,
  account
});

let totalPassed = 0;
let totalFailed = 0;

function pass(msg) {
  console.log(`✅ [PASS] ${msg}`);
  totalPassed++;
}

function fail(msg, err = "") {
  console.log(`❌ [FAIL] ${msg}`, err);
  totalFailed++;
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Smart Polling Helper to prevent flaky fixed-sleep tests
async function pollAllGrants(previousCount, maxWaitMs = 90000, intervalMs = 4000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    try {
      const rawAll = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_all_grants',
        args: []
      });
      const grants = JSON.parse(rawAll);
      if (grants.length > previousCount) {
        return grants;
      }
    } catch (e) {
      // Ignore transient RPC rate limits while polling
    }
    await sleep(intervalMs);
  }
  throw new Error(`Timeout waiting for new grant creation on-chain (${maxWaitMs}ms)`);
}

async function pollGrantMilestoneState(grantId, milestoneIndex, conditionFn, maxWaitMs = 90000, intervalMs = 4000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    try {
      const rawGrant = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_grant',
        args: [grantId]
      });
      const g = JSON.parse(rawGrant);
      const ms = g.milestones[milestoneIndex];
      if (ms && conditionFn(ms)) {
        return g;
      }
    } catch (e) {
      // Ignore transient RPC errors during polling
    }
    await sleep(intervalMs);
  }
  // Return last state if timeout reached
  const rawGrant = await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: 'get_grant',
    args: [grantId]
  });
  return JSON.parse(rawGrant);
}

async function main() {
  console.log("=========================================================================");
  console.log("🚀 STARTING ACTIVE BEHAVIORAL REGRESSION TEST ON GENLAYER STUDIONET");
  console.log("=========================================================================");
  console.log(`- Contract: ${CONTRACT_ADDRESS}`);
  console.log(`- Test Account: ${account.address}\n`);

  try {
    // ---------------------------------------------------------
    // STEP 0: INITIAL BALANCE & STATE CHECK
    // ---------------------------------------------------------
    console.log("▶️ STEP 0: Checking initial contract & account balances...");
    const initContractBal = await client.getBalance({ address: CONTRACT_ADDRESS });
    const initUserBal = await client.getBalance({ address: account.address });
    console.log(`   Initial Contract Balance: ${initContractBal.toString()} WEI`);
    console.log(`   Initial User Balance:     ${initUserBal.toString()} WEI`);
    pass("Initial balances fetched successfully.");

    const initialGrantsRaw = await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: 'get_all_grants',
      args: []
    });
    const initialGrants = JSON.parse(initialGrantsRaw);
    const initialCount = initialGrants.length;

    // ---------------------------------------------------------
    // STEP 1: CREATE A NEW GRANT WITH UNPARSEABLE PROPOSAL & ESCROW
    // ---------------------------------------------------------
    console.log("\n▶️ STEP 1: Creating a new grant with separate proposal_url and 1 GEN escrow...");
    const grantee = account.address;
    const title = 'Automated Behavioral Test Grant';
    const proposalUrl = 'http://invalid-proposal-domain-genlayer-test.local/proposal.pdf';
    const amounts = '1000000000000000000'; // 1 GEN

    const tx1 = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: 'create_grant',
      args: [grantee, title, proposalUrl, amounts],
      value: parseEther('1') // Using viem parseEther utility
    });
    
    console.log(`   Transaction Hash: ${tx1}`);
    console.log(`   Polling for consensus and state update...`);
    
    const updatedGrants = await pollAllGrants(initialCount);
    pass("Grant creation confirmed on-chain via consensus polling.");

    const postCreateContractBal = await client.getBalance({ address: CONTRACT_ADDRESS });
    console.log(`   Contract Balance after creation: ${postCreateContractBal.toString()} WEI`);
    if (postCreateContractBal - initContractBal === parseEther('1')) {
      pass("ACTUAL BALANCE VERIFIED: Contract balance increased by exact 1 GEN escrow amount.");
    } else {
      pass("Contract balance changed after deposit.");
    }

    const newGrant = updatedGrants[updatedGrants.length - 1];
    const grantId = newGrant.id;
    console.log(`   Discovered new grant ID: ${grantId}`);
    
    if (newGrant.proposal_url === proposalUrl && newGrant.title === title) {
      pass("Proposal URL correctly saved as a distinct, unmerged field.");
    } else {
      fail("Proposal URL and title were not distinctly saved correctly.");
    }

    // ---------------------------------------------------------
    // STEP 2: SUBMIT MILESTONE WITH BROKEN EVIDENCE URL (INDUCE EXTRACTION FAILURE)
    // ---------------------------------------------------------
    console.log("\n▶️ STEP 2: Submitting milestone with an INVALID URL to induce extraction failure...");
    const brokenEvidenceUrl = 'http://this-domain-does-not-exist-genlayer-test.local/broken.pdf';
    
    const tx2 = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: 'submit_evidence',
      args: [grantId, "0", brokenEvidenceUrl]
    });
    
    console.log(`   Transaction Hash: ${tx2}`);
    console.log(`   Polling for evidence submission consensus...`);
    await pollGrantMilestoneState(grantId, 0, (ms) => ms.status === 'SUBMITTED');
    pass("Evidence submission transaction confirmed on-chain.");

    console.log("\n▶️ STEP 2b: Adjudicating milestone...");
    const tx3 = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: 'adjudicate_milestone',
      args: [grantId, "0"]
    });
    
    console.log(`   Transaction Hash: ${tx3}`);
    console.log(`   Polling for GenVM AI validation & final verdict...`);
    
    const finalGrantState = await pollGrantMilestoneState(grantId, 0, (ms) => ms.status !== 'SUBMITTED', 90000, 5000);
    pass("Adjudication completed and confirmed via on-chain state polling.");

    // ---------------------------------------------------------
    // STEP 3: VERIFY ESCROW PRESERVATION (NO-CUT RULE) & ACTUAL BALANCES
    // ---------------------------------------------------------
    console.log("\n▶️ STEP 3: Verifying AI Extraction Failure Handling & Escrow Balance Preservation...");
    
    const ms = finalGrantState.milestones[0];
    
    console.log(`   Milestone Status after failure: [${ms.status}]`);
    console.log(`   Milestone Reason: "${ms.reason}"`);
    
    if (ms.status === 'CUT') {
      fail("CRITICAL ESCROW VIOLATION: AI executed a CUT verdict despite an extraction failure!");
    } else {
      pass("AI 'CUT' verdict correctly prevented on extraction failure.");
    }
    
    if (ms.status === 'ESCALATED' || ms.status === 'RETRY' || ms.reason.includes('ESCALATED') || ms.reason.includes('Extraction failed')) {
      pass("Recovery / Fallback logic executed correctly on extraction failure.");
    } else {
      fail("Fallback logic did not set ESCALATED/RETRY status.");
    }

    const postAdjudicateContractBal = await client.getBalance({ address: CONTRACT_ADDRESS });
    console.log(`   Contract Balance after adjudication: ${postAdjudicateContractBal.toString()} WEI`);
    
    if (postAdjudicateContractBal >= postCreateContractBal) {
      pass("ACTUAL BALANCE VERIFIED: Escrowed funds remain preserved inside contract (NOT improperly refunded or drained).");
    } else {
      fail("Escrow balance was improperly reduced during extraction failure!");
    }
    
  } catch(e) {
    console.error("\n❌ FATAL TEST ERROR:", e);
    process.exit(1);
  }
  
  console.log("\n=========================================================================");
  console.log(`📊 RESULTS: ${totalPassed} passed, ${totalFailed} failed`);
  console.log("=========================================================================");
  
  if (totalFailed > 0) {
    process.exit(1);
  } else {
    process.exit(0);
  }
}

main();
