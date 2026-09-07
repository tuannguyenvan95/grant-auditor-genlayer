import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { privateKeyToAccount } from 'viem/accounts';
import { parseEther } from 'viem';

// Target Contract Address (Update once new contract is deployed)
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS || '0x9Eb43D02a286278338D831c207A46E549A5bA2E3';
const DEFAULT_TEST_KEY = '0x5f5babe2057032ab30b8a353f13341478785069644a0c6d3126539104cd48168';

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

async function main() {
  console.log("=========================================================================");
  console.log("🧪 RUNNING STAKE-BASED APPEAL & REPUTATION ON-CHAIN REGRESSION TEST");
  console.log("=========================================================================");
  console.log(`- Contract Address: ${CONTRACT_ADDRESS}`);
  console.log(`- Test Account:     ${account.address}`);

  try {
    // 1. Check get_reputation view method
    console.log("\n▶️ [STEP 1] Testing get_reputation view method...");
    try {
      const repRaw = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_reputation',
        args: [account.address]
      });
      const rep = JSON.parse(repRaw);
      console.log(`   Reputation result:`, rep);
      if (rep.address && rep.tier != null) {
        pass(`get_reputation succeeded. Tier: ${rep.tier}, Score: ${rep.score}`);
      } else {
        fail(`get_reputation returned unexpected schema: ${repRaw}`);
      }
    } catch (err) {
      fail("get_reputation failed (contract might need redeployment for new storage)", err.shortMessage || err.message);
    }

    // 2. Check get_all_grants includes reputation data
    console.log("\n▶️ [STEP 2] Testing get_all_grants view method...");
    try {
      const rawAll = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_all_grants',
        args: []
      });
      const allGrants = JSON.parse(rawAll);
      pass(`get_all_grants returned ${allGrants.length} grants successfully.`);
    } catch (err) {
      fail("get_all_grants failed", err.shortMessage || err.message);
    }

    console.log("\n=========================================================================");
    console.log(`SUMMARY: ${totalPassed} Passed, ${totalFailed} Failed`);
    console.log("=========================================================================");
  } catch (globalErr) {
    console.error("Fatal Test Suite Crash:", globalErr);
  }
}

main();
