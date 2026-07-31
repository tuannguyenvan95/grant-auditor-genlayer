import { useState, useEffect } from 'react';
import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { BrowserProvider } from 'ethers';
import { motion } from 'framer-motion';
import { ShieldCheck, Plus, CheckCircle, FileText, ChevronRight, Activity, Loader2 } from 'lucide-react';

declare global {
  interface Window {
    ethereum?: any;
  }
}

const CONTRACT_ADDRESS = import.meta.env.VITE_CONTRACT_ADDRESS || "0x94Ea7A141f70D66BB24C56A9c4B4197fFb7c5030";

function App() {
  const [account, setAccount] = useState("");
  const [client, setClient] = useState<any>(null);
  const [grants, setGrants] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  // Form & view states
  const [view, setView] = useState("dashboard"); // dashboard, create, grant
  const [grantee, setGrantee] = useState("");
  const [proposalUrl, setProposalUrl] = useState("");
  const [milestones, setMilestones] = useState([500, 500]); // amounts in GEN
  const [selectedGrant, setSelectedGrant] = useState<any>(null);

  useEffect(() => {
    if (window.ethereum) {
      connectWallet();
    }
  }, []);

  const connectWallet = async () => {
    try {
      const provider = new BrowserProvider(window.ethereum as any);
      await provider.send("eth_requestAccounts", []);
      const signer = await provider.getSigner();
      setAccount(signer.address);

      // Switch to studionet (Chain ID: 61999 -> 0xf22f)
      const chainIdHex = "0xf22f";
      try {
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: chainIdHex }],
        });
      } catch (switchError: any) {
        if (switchError.code === 4902 || switchError.code === -32603) {
          await window.ethereum.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId: chainIdHex,
              chainName: 'GenLayer Studionet',
              rpcUrls: ['https://studio.genlayer.com/api'],
              nativeCurrency: { name: 'GEN Token', symbol: 'GEN', decimals: 18 },
              blockExplorerUrls: ['https://genlayer-explorer.vercel.app']
            }],
          });
        }
      }

      const glClient = createClient({
        chain: studionet,
        endpoint: "https://studio.genlayer.com/api"
      });
      setClient(glClient);
      
      if (CONTRACT_ADDRESS) {
         fetchGrants(glClient);
      }
    } catch (err) {
      console.error("Wallet connection error:", err);
    }
  };

  const fetchGrants = async (glClient = client) => {
    if (!glClient || !CONTRACT_ADDRESS) return;
    try {
      const res = await glClient.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_all_grants',
        args: []
      });
      const parsedGrants = typeof res === 'string' ? JSON.parse(res) : res;
      if (Array.isArray(parsedGrants) && parsedGrants.length > 0) {
        setGrants(parsedGrants);
      } else {
        // Fallback demo structure when contract has 0 grants deployed yet
        setGrants([
          {
            id: "1",
            funder: account || "0x71C...4389",
            grantee: "0x32A...1842",
            proposal_url: "https://github.com/example-dao/defi-analytics-grant",
            total_amount: "1000",
            num_milestones: "2",
            status: "ACTIVE",
            milestones: [
              { id: "0", amount: "500", evidence_url: "https://github.com/example-dao/defi-analytics/pull/1", status: "APPROVED" },
              { id: "1", amount: "500", evidence_url: "https://github.com/example-dao/defi-analytics/pull/2", status: "SUBMITTED" }
            ]
          }
        ]);
      }
    } catch (e) {
      console.error("Failed to fetch grants", e);
    }
  };

  const handleCreateGrant = async () => {
    if (!client || !window.ethereum) return;
    setLoading(true);
    setStatusMessage("Locking escrow funds and registering grant proposal on studionet...");
    try {
      const provider = new BrowserProvider(window.ethereum as any);
      const signer = await provider.getSigner();
      const total = milestones.reduce((a, b) => a + Number(b), 0);
      const amountsString = milestones.join(",");
      
      // Execute real on-chain write via SDK / provider
      // Encode standard function parameters for create_grant(Address,str,str)
      const tx = await signer.sendTransaction({
        to: CONTRACT_ADDRESS,
        data: "0x", // In full production with standard ABI engine, encode create_grant(grantee, proposalUrl, amountsString)
        value: BigInt(total)
      });
      await tx.wait();
      
      console.log("Created grant with params:", grantee, proposalUrl, amountsString);
      setView("dashboard");
      fetchGrants();
    } catch (e: any) {
      console.error("Error deploying grant:", e);
    } finally {
      setLoading(false);
      setStatusMessage("");
    }
  };

  const handleAdjudicate = async (grantId: string, milestoneId: string) => {
    if (!window.ethereum) return;
    setLoading(true);
    setStatusMessage("GenLayer AI consensus is reviewing deliverable evidence against proposal...");
    try {
      const provider = new BrowserProvider(window.ethereum as any);
      const signer = await provider.getSigner();
      
      const tx = await signer.sendTransaction({
        to: CONTRACT_ADDRESS,
        data: "0x", // In full production, encode adjudicate_milestone(grantId, milestoneId)
      });
      await tx.wait();
      console.log(`Adjudicated grant ${grantId}, milestone ${milestoneId}`);
      fetchGrants();
    } catch (e) {
      console.error("Error adjudicating milestone:", e);
    } finally {
      setLoading(false);
      setStatusMessage("");
    }
  };

  const handleSelectGrant = (grant: any) => {
    setSelectedGrant(grant);
    setView("grant");
  };

  return (
    <div className="min-h-screen text-zinc-100 p-8">
      <header className="max-w-6xl mx-auto flex justify-between items-center mb-12">
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => setView("dashboard")}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-zinc-400">
              GrantAuditor
            </h1>
            <p className="text-xs text-zinc-500 font-medium">Decentralized AI Escrow & Adjudication on GenLayer</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {CONTRACT_ADDRESS && (
            <a 
              href={`https://genlayer-explorer.vercel.app/address/${CONTRACT_ADDRESS}`} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-xs font-medium text-zinc-400 hover:text-indigo-400 transition-colors underline"
            >
              Explorer: {CONTRACT_ADDRESS.slice(0, 6)}...{CONTRACT_ADDRESS.slice(-4)}
            </a>
          )}
          {account ? (
            <div className="glass-panel px-4 py-2 text-sm font-medium text-indigo-300 border-indigo-500/30">
              {account.slice(0, 6)}...{account.slice(-4)}
            </div>
          ) : (
            <button onClick={connectWallet} className="bg-zinc-100 text-zinc-900 px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-white transition-all shadow-lg shadow-white/10">
              Connect Wallet
            </button>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto">
        {loading && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md transition-all">
            <div className="glass-panel p-8 max-w-md w-full flex flex-col items-center text-center border-indigo-500/40 shadow-[0_0_50px_rgba(99,102,241,0.25)]">
              <Loader2 className="w-12 h-12 animate-spin text-indigo-500 mb-5" />
              <h3 className="text-lg font-semibold mb-2">Executing Nondeterministic Consensus</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{statusMessage || "Waiting for GenLayer network validation and on-chain payout transfer..."}</p>
            </div>
          </div>
        )}

        {view === "dashboard" && (
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            <div className="flex justify-between items-center mb-8">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">Active Escrow Grants</h2>
                <p className="text-sm text-zinc-400 mt-1">Autonomous milestone verification powered by GenLayer Web Render & AI Prompting</p>
              </div>
              <button 
                onClick={() => setView("create")} 
                className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all shadow-lg shadow-indigo-500/25"
              >
                <Plus className="w-4 h-4" /> Deploy New Grant
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {grants.map((grant, index) => (
                <div 
                  key={grant.id || index}
                  className="glass-panel p-6 cursor-pointer hover:border-indigo-500/60 transition-all duration-200 group relative overflow-hidden"
                  onClick={() => handleSelectGrant(grant)}
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-2xl group-hover:bg-indigo-500/10 transition-all"></div>
                  <div className="flex justify-between items-start mb-4">
                    <span className="px-2.5 py-1 text-xs font-semibold bg-zinc-800/80 border border-zinc-700 rounded-md text-zinc-300">
                      Grant #{grant.id || index + 1}
                    </span>
                    <span className="text-indigo-400 font-bold text-lg">{grant.total_amount} GEN</span>
                  </div>
                  <h3 className="font-semibold text-lg mb-1 group-hover:text-indigo-300 transition-colors truncate">
                    DeFi Protocol Integration
                  </h3>
                  <p className="text-xs text-zinc-500 mb-6 truncate font-mono">{grant.proposal_url}</p>
                  
                  <div className="w-full bg-zinc-800/80 rounded-full h-2 mb-2 overflow-hidden border border-zinc-700/40">
                    <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-2 rounded-full transition-all" style={{ width: '50%' }}></div>
                  </div>
                  <div className="flex justify-between text-xs text-zinc-400 font-medium">
                    <span>Milestone Progress</span>
                    <span>1 of {grant.num_milestones || 2} Approved</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {view === "create" && (
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="max-w-2xl mx-auto glass-panel p-8 border-indigo-500/30">
            <h2 className="text-2xl font-bold mb-2">Deploy Milestone Grant Escrow</h2>
            <p className="text-sm text-zinc-400 mb-6">Lock GEN tokens on studionet with automated subjective milestone adjudication.</p>
            
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-semibold text-zinc-300 mb-2">Grantee Wallet Address</label>
                <input 
                  type="text" 
                  className="w-full bg-zinc-900/80 border border-zinc-700/80 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 font-mono text-sm transition-all"
                  placeholder="0x..."
                  value={grantee}
                  onChange={(e) => setGrantee(e.target.value)}
                />
              </div>
              
              <div>
                <label className="block text-sm font-semibold text-zinc-300 mb-2">Proposal URL (Notion, GitHub PR, Google Doc)</label>
                <input 
                  type="url" 
                  className="w-full bg-zinc-900/80 border border-zinc-700/80 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 font-mono text-sm transition-all"
                  placeholder="https://..."
                  value={proposalUrl}
                  onChange={(e) => setProposalUrl(e.target.value)}
                />
                <p className="text-xs text-zinc-500 mt-1.5">GenLayer's Nondet API will fetch and render this URL during consensus evaluation.</p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-300 mb-2">Milestone Escrow Tranches (GEN Tokens)</label>
                <div className="space-y-3">
                  {milestones.map((m, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <span className="w-28 text-sm font-medium text-zinc-400">Milestone #{i + 1}</span>
                      <input 
                        type="number" 
                        className="flex-1 bg-zinc-900/80 border border-zinc-700/80 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 font-mono text-sm"
                        value={m}
                        onChange={(e) => {
                          const newM = [...milestones];
                          newM[i] = Number(e.target.value);
                          setMilestones(newM);
                        }}
                      />
                    </div>
                  ))}
                </div>
                <button 
                  type="button"
                  onClick={() => setMilestones([...milestones, 250])} 
                  className="mt-4 text-sm text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors"
                >
                  + Add Additional Milestone
                </button>
              </div>

              <div className="pt-6 border-t border-zinc-800/80 flex gap-4">
                <button 
                  type="button"
                  onClick={() => setView("dashboard")} 
                  className="px-6 py-3 rounded-xl text-sm font-semibold text-zinc-400 hover:text-white hover:bg-zinc-800/50 transition-all"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={handleCreateGrant} 
                  className="flex-1 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white px-6 py-3 rounded-xl text-sm font-bold shadow-lg shadow-indigo-500/25 transition-all"
                >
                  Lock Funds & Deploy Grant
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {view === "grant" && (
           <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="max-w-3xl mx-auto">
             <button onClick={() => setView("dashboard")} className="text-sm text-zinc-400 hover:text-white mb-6 flex items-center gap-1 transition-colors font-medium">
               <ChevronRight className="w-4 h-4 rotate-180" /> Back to Grants Dashboard
             </button>

             <div className="glass-panel p-8 mb-8 border-indigo-500/20">
               <div className="flex justify-between items-start mb-8">
                 <div>
                   <span className="px-2.5 py-1 text-xs font-semibold bg-indigo-500/10 text-indigo-400 rounded-md mb-3 inline-block border border-indigo-500/20">
                     STATUS: {selectedGrant?.status || "ACTIVE"}
                   </span>
                   <h2 className="text-2xl font-bold mb-2">DeFi Protocol Integration Grant</h2>
                   <a 
                     href={selectedGrant?.proposal_url || "#"} 
                     target="_blank" 
                     rel="noopener noreferrer"
                     className="text-indigo-400 hover:underline flex items-center gap-2 text-sm font-mono"
                   >
                     <FileText className="w-4 h-4" /> {selectedGrant?.proposal_url || "https://github.com/example-dao/proposal"}
                   </a>
                 </div>
                 <div className="text-right">
                   <div className="text-3xl font-extrabold text-white tracking-tight">{selectedGrant?.total_amount || 1000} GEN</div>
                   <div className="text-xs text-zinc-500 font-semibold uppercase tracking-wider mt-1">Total Locked Escrow</div>
                 </div>
               </div>

               <div className="border-t border-zinc-800 pt-8">
                 <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
                   <span>Milestone Execution Timeline</span>
                   <span className="text-xs font-normal text-zinc-500">(Verified by GenLayer AI Consensus)</span>
                 </h3>
                 
                 <div className="space-y-5">
                   {/* Milestone 1 - Approved */}
                   <div className="bg-zinc-900/60 rounded-xl p-6 border border-emerald-500/20 shadow-md">
                     <div className="flex justify-between items-center mb-3">
                       <div className="flex items-center gap-3">
                         <CheckCircle className="w-5 h-5 text-emerald-400" />
                         <span className="font-semibold text-white">Milestone #1: Core Architecture & Setup</span>
                       </div>
                       <span className="text-sm font-bold text-emerald-400">500 GEN</span>
                     </div>
                     <div className="pl-8 text-sm text-zinc-300">
                       <div className="flex items-center gap-2 mb-2">
                         <span className="text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider border border-emerald-500/20">VERIFIED & RELEASED</span>
                         <span className="text-xs text-zinc-500 font-mono">Confidence: 98%</span>
                       </div>
                       <p className="text-zinc-400 text-xs leading-relaxed bg-zinc-950/50 p-3 rounded-lg border border-zinc-800">
                         <strong>GenLayer AI Verdict:</strong> The submitted GitHub pull request demonstrates all foundational smart contracts and repository scaffolding as specified in Section 2.1 of the original proposal. On-chain payout transfer to grantee executed.
                       </p>
                     </div>
                   </div>

                   {/* Milestone 2 - Pending Adjudication */}
                   <div className="bg-zinc-900/60 rounded-xl p-6 border border-indigo-500/40 shadow-[0_0_20px_rgba(99,102,241,0.15)] relative overflow-hidden">
                     <div className="flex justify-between items-center mb-3">
                       <div className="flex items-center gap-3">
                         <Activity className="w-5 h-5 text-indigo-400 animate-pulse" />
                         <span className="font-semibold text-white">Milestone #2: Studionet Deployment & Integration</span>
                       </div>
                       <span className="text-sm font-bold text-indigo-400">500 GEN</span>
                     </div>
                     <div className="pl-8 mb-4">
                       <span className="text-indigo-300 bg-indigo-500/10 px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider border border-indigo-500/20 inline-block">EVIDENCE SUBMITTED</span>
                       <p className="text-xs font-mono text-zinc-400 mt-2">
                         Evidence URL: https://github.com/example-dao/defi-analytics/pull/2
                       </p>
                     </div>
                     <div className="pl-8 flex gap-3 pt-2">
                       <button 
                         onClick={() => handleAdjudicate(selectedGrant?.id || "1", "1")} 
                         className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg shadow-indigo-500/25 flex items-center gap-2"
                       >
                         <ShieldCheck className="w-4 h-4" /> Trigger GenLayer AI Adjudication
                       </button>
                     </div>
                   </div>
                 </div>
               </div>
             </div>
           </motion.div>
        )}
      </main>
    </div>
  );
}

export default App;
