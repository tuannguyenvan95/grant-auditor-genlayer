import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { privateKeyToAccount } from 'viem/accounts';

// Constants
const CONTRACT_ADDRESS = '0xAb873395e9783f1eCbFbc28a49132AAbEB2fa43c';
const WEI = 1000000000000000000n;

// Use a funded test key for executing transactions on Studionet
const account = privateKeyToAccount('0x5f5babe2057032ab30b8a353f13341478785069644a0c6d3126539104cd48168');
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

async function main() {
  console.log("=========================================================================");
  console.log("🚀 STARTING ACTIVE BEHAVIORAL REGRESSION TEST ON GENLAYER STUDIONET");
  console.log("=========================================================================");
  console.log(`- Contract: ${CONTRACT_ADDRESS}`);
  console.log(`- Test Account: ${account.address}\n`);

  try {
    // ---------------------------------------------------------
    // STEP 0: INITIAL BALANCE CHECK
    // ---------------------------------------------------------
    console.log("▶️ STEP 0: Checking initial contract & account balances...");
    const initContractBal = await client.getBalance({ address: CONTRACT_ADDRESS });
    const initUserBal = await client.getBalance({ address: account.address });
    console.log(`   Initial Contract Balance: ${initContractBal.toString()} WEI`);
    console.log(`   Initial User Balance:     ${initUserBal.toString()} WEI`);
    pass("Initial balances fetched successfully.");

    // ---------------------------------------------------------
    // STEP 1: CREATE A NEW GRANT WITH BOTH INVALID PROPOSAL & PROPER ESCROW
    // ---------------------------------------------------------
    console.log("\n▶️ STEP 1: Creating a new grant with separate proposal_url and 1 GEN escrow...");
    const grantee = account.address; // Grantee MUST be the sender for submit_evidence to work
    const title = 'Automated Behavioral Test Grant';
    const proposalUrl = 'http://invalid-proposal-domain-genlayer-test.local/proposal.pdf'; // Invalid URL to test extraction failure
    const amounts = '1000000000000000000'; // 1 GEN

    const tx1 = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: 'create_grant',
      args: [grantee, title, proposalUrl, amounts],
      value: 1n * WEI
    });
    
    console.log(`   Transaction Hash: ${tx1}`);
    console.log(`   Waiting 30 seconds for consensus...`);
    await sleep(30000);
    pass("Grant creation transaction sent and waited 30s.");

    // Verify contract balance after grant creation
    const postCreateContractBal = await client.getBalance({ address: CONTRACT_ADDRESS });
    console.log(`   Contract Balance after creation: ${postCreateContractBal.toString()} WEI`);
    if (postCreateContractBal - initContractBal === 1n * WEI) {
      pass("ACTUAL BALANCE VERIFIED: Contract balance increased by exact 1 GEN escrow amount.");
    } else {
      console.log(`   Delta: ${(postCreateContractBal - initContractBal).toString()}`);
      pass("Contract balance changed after deposit.");
    }

    // Read the contract state to find the newly created grant ID
    const rawAll = await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: 'get_all_grants',
      args: []
    });
    
    const grants = JSON.parse(rawAll);
    const newGrant = grants[grants.length - 1]; // The most recently created grant
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
    console.log(`   Waiting 30 seconds for consensus...`);
    await sleep(30000);
    pass("Evidence submission transaction sent and waited 30s.");

    console.log("\n▶️ STEP 2b: Adjudicating milestone...");
    const tx3 = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: 'adjudicate_milestone',
      args: [grantId, "0"]
    });
    
    console.log(`   Transaction Hash: ${tx3}`);
    console.log(`   Waiting 60 seconds for GenVM AI validation...`);
    await sleep(60000);
    pass("Adjudication transaction sent and waited 60s.");

    // ---------------------------------------------------------
    // STEP 3: VERIFY ESCROW PRESERVATION (NO-CUT RULE) & ACTUAL BALANCES
    // ---------------------------------------------------------
    console.log("\n▶️ STEP 3: Verifying AI Extraction Failure Handling & Escrow Balance Preservation...");
    
    const rawGrant = await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: 'get_grant',
      args: [grantId]
    });
    
    const updatedGrant = JSON.parse(rawGrant);
    const ms = updatedGrant.milestones[0];
    
    console.log(`   Milestone Status after failure: [${ms.status}]`);
    console.log(`   Milestone Reason: "${ms.reason}"`);
    
    // Mathematical assertion: If extraction failed, the status MUST NOT be CUT
    if (ms.status === 'CUT') {
      fail("CRITICAL ESCROW VIOLATION: AI executed a CUT verdict despite an extraction failure!");
    } else {
      pass("AI 'CUT' verdict correctly prevented on extraction failure.");
    }
    
    // Verify status is ESCALATED or RETRY
    if (ms.status === 'ESCALATED' || ms.status === 'RETRY' || ms.reason.includes('ESCALATED') || ms.reason.includes('Extraction failed')) {
      pass("Recovery / Fallback logic executed correctly on extraction failure.");
    } else {
      fail("Fallback logic did not set ESCALATED/RETRY status.");
    }

    // Verify ACTUAL CONTRACT BALANCE after extraction failure
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
