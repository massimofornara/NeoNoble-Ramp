import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Wallet, ArrowLeft, RefreshCw, Loader2, ArrowRightLeft,
  CreditCard, Building, Link2, Unlink, Globe, ChevronDown,
  ArrowUpRight, ArrowDownRight, Copy, Check, Layers, Search, Sparkles
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const hdr = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

/* Safe fetch wrapper — prevents "body stream already read" by using clone() */
async function safeFetch(url, opts = {}) {
  try {
    const res = await fetch(url, opts);
    const clone = res.clone();
    try { return await clone.json(); } catch { return {}; }
  } catch { return {}; }
}

async function safePost(url, body) {
  try {
    const res = await fetch(url, { method: 'POST', headers: hdr(), body: JSON.stringify(body) });
    const data = await res.clone().json().catch(() => ({}));
    return { ok: res.ok, data };
  } catch (e) { return { ok: false, data: { detail: e.message } }; }
}

const CHAIN_ICONS = { ethereum: '/eth.svg', bsc: '/bnb.svg', polygon: '/matic.svg' };
const CHAIN_COLORS = { ethereum: '#627EEA', bsc: '#F3BA2F', polygon: '#8247E5' };

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="ml-1 text-gray-400 hover:text-white">
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

export default function WalletPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState('platform');
  const [wallets, setWallets] = useState([]);
  const [totalEur, setTotalEur] = useState(0);
  const [chains, setChains] = useState([]);
  const [onchainWallets, setOnchainWallets] = useState([]);
  const [ibans, setIbans] = useState([]);
  const [settlements, setSettlements] = useState([]);
  const [bankingTxs, setBankingTxs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  // Unified wallet state
  const [unifiedAssets, setUnifiedAssets] = useState([]);
  const [unifiedTotal, setUnifiedTotal] = useState(0);
  const [unifiedLoading, setUnifiedLoading] = useState(false);

  // Token discovery state
  const [discoveredTokens, setDiscoveredTokens] = useState([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoverChain, setDiscoverChain] = useState('ethereum');

  // Convert form
  const [showConvert, setShowConvert] = useState(false);
  const [convertFrom, setConvertFrom] = useState('BTC');
  const [convertTo, setConvertTo] = useState('EUR');
  const [convertAmount, setConvertAmount] = useState('');
  const [convertResult, setConvertResult] = useState(null);
  const [convertLoading, setConvertLoading] = useState(false);

  // Link wallet form
  const [showLink, setShowLink] = useState(false);
  const [linkAddress, setLinkAddress] = useState('');
  const [linkChain, setLinkChain] = useState('bsc');
  const [linkLoading, setLinkLoading] = useState(false);

  // IBAN form
  const [showIbanForm, setShowIbanForm] = useState(false);
  const [ibanName, setIbanName] = useState('');

  // SEPA Withdraw
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawIban, setWithdrawIban] = useState('');
  const [withdrawName, setWithdrawName] = useState('');

  const fetchAll = useCallback(async () => {
    try {
      const [wData, cData, ocData, ibData, sData, btData] = await Promise.all([
        safeFetch(`${BACKEND_URL}/api/wallet/balances`, { headers: hdr() }),
        safeFetch(`${BACKEND_URL}/api/multichain/chains`),
        safeFetch(`${BACKEND_URL}/api/multichain/balances`, { headers: hdr() }),
        safeFetch(`${BACKEND_URL}/api/banking/iban`, { headers: hdr() }),
        safeFetch(`${BACKEND_URL}/api/wallet/settlements?limit=10`, { headers: hdr() }),
        safeFetch(`${BACKEND_URL}/api/banking/transactions?limit=10`, { headers: hdr() }),
      ]);
      setWallets(wData.wallets || []);
      setTotalEur(wData.total_eur_value || 0);
      setChains(cData.chains || []);
      setOnchainWallets(ocData.wallets || []);
      setIbans(ibData.ibans || []);
      setSettlements(sData.settlements || []);
      setBankingTxs(btData.transactions || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fetchUnifiedWallet = useCallback(async () => {
    setUnifiedLoading(true);
    try {
      const data = await safeFetch(`${BACKEND_URL}/api/multichain/unified-wallet`, { headers: hdr() });
      setUnifiedAssets(data.assets || []);
      setUnifiedTotal(data.total_eur_value || 0);
    } catch (e) { console.error(e); }
    finally { setUnifiedLoading(false); }
  }, []);

  useEffect(() => { if (tab === 'unified') fetchUnifiedWallet(); }, [tab, fetchUnifiedWallet]);

  const handleDiscoverTokens = async (chain) => {
    setDiscovering(true);
    try {
      const data = await safeFetch(`${BACKEND_URL}/api/multichain/discover-tokens`, {
        method: 'POST', headers: hdr(), body: JSON.stringify({ chain })
      });
      setDiscoveredTokens(data.discovered_tokens || []);
    } catch (e) { console.error(e); }
    finally { setDiscovering(false); }
  };

  const handleConvert = async (e) => {
    e.preventDefault();
    setConvertLoading(true); setConvertResult(null);
    try {
      const { ok, data } = await safePost(`${BACKEND_URL}/api/wallet/convert`, { from_asset: convertFrom, to_asset: convertTo, amount: parseFloat(convertAmount) });
      if (!ok) throw new Error(data.detail || 'Conversion failed');
      setConvertResult({ success: true, data });
      setConvertAmount('');
      fetchAll();
    } catch (e) { setConvertResult({ success: false, msg: e.message }); }
    finally { setConvertLoading(false); }
  };

  const handleLinkWallet = async (e) => {
    e.preventDefault();
    setLinkLoading(true);
    try {
      const { ok, data } = await safePost(`${BACKEND_URL}/api/multichain/link`, { address: linkAddress, chain: linkChain });
      if (!ok) throw new Error(data.detail || 'Link failed');
      setShowLink(false); setLinkAddress('');
      fetchAll();
    } catch (e) { alert(e.message); }
    finally { setLinkLoading(false); }
  };

  const handleSyncChain = async (chain) => {
    setSyncing(true);
    try {
      await safeFetch(`${BACKEND_URL}/api/multichain/sync`, {
        method: 'POST', headers: hdr(),
        body: JSON.stringify({ chain })
      });
      fetchAll();
    } catch (e) { console.error(e); }
    finally { setSyncing(false); }
  };

  const handleAssignIban = async () => {
    try {
      await safePost(`${BACKEND_URL}/api/banking/iban/assign`, { currency: 'EUR', beneficiary_name: ibanName || undefined });
      setShowIbanForm(false); setIbanName('');
      fetchAll();
    } catch (e) { console.error(e); }
  };

  const handleWithdraw = async (e) => {
    e.preventDefault();
    try {
      const { ok, data } = await safePost(`${BACKEND_URL}/api/banking/sepa/withdraw`, { amount: parseFloat(withdrawAmount), destination_iban: withdrawIban, beneficiary_name: withdrawName });
      if (!ok) throw new Error(data.detail);
      setShowWithdraw(false); setWithdrawAmount(''); setWithdrawIban(''); setWithdrawName('');
      fetchAll();
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="min-h-screen bg-gray-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  const TABS = [
    { id: 'platform', label: 'Wallet', icon: Wallet },
    { id: 'unified', label: 'Unificato', icon: Layers },
    { id: 'onchain', label: 'On-Chain', icon: Globe },
    { id: 'banking', label: 'Banking', icon: Building },
  ];

  return (
    <div className="min-h-screen bg-gray-950" data-testid="wallet-page">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-900/50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-gray-800 rounded-lg"><ArrowLeft className="w-4 h-4 text-gray-400" /></button>
            <h1 className="text-white font-bold text-lg">Wallet & Banking</h1>
          </div>
          <div className="text-right">
            <div className="text-gray-400 text-xs">Valore Totale</div>
            <div className="text-white font-bold text-xl" data-testid="total-value">{totalEur.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-6xl mx-auto px-4 pt-4">
        <div className="flex gap-1 bg-gray-900 rounded-xl p-1 mb-4 w-fit">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t.id ? 'bg-purple-500/20 text-purple-400' : 'text-gray-400 hover:text-white'}`}>
              <t.icon className="w-4 h-4" />{t.label}
            </button>
          ))}
        </div>

        {/* PLATFORM WALLET TAB */}
        {tab === 'platform' && (
          <div className="space-y-4">
            <div className="flex gap-2 mb-4">
              <button onClick={() => setShowConvert(!showConvert)} data-testid="convert-btn"
                className="flex items-center gap-2 bg-purple-500/10 text-purple-400 border border-purple-500/30 px-4 py-2 rounded-lg text-sm hover:bg-purple-500/20">
                <ArrowRightLeft className="w-4 h-4" />Converti
              </button>
              <button onClick={() => navigate('/cards')} className="flex items-center gap-2 bg-blue-500/10 text-blue-400 border border-blue-500/30 px-4 py-2 rounded-lg text-sm hover:bg-blue-500/20">
                <CreditCard className="w-4 h-4" />Carte
              </button>
            </div>

            {showConvert && (
              <form onSubmit={handleConvert} data-testid="convert-form" className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-gray-400 text-xs block mb-1">Da</label>
                    <select value={convertFrom} onChange={e => setConvertFrom(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                      {['BTC','ETH','NENO','USDT','EUR','SOL','BNB','XRP','ADA','DOGE'].map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-gray-400 text-xs block mb-1">A</label>
                    <select value={convertTo} onChange={e => setConvertTo(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                      {['EUR','USDT','BTC','ETH','NENO','USD','SOL','BNB'].map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-gray-400 text-xs block mb-1">Importo</label>
                    <input type="number" step="any" value={convertAmount} onChange={e => setConvertAmount(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" placeholder="0.00" />
                  </div>
                </div>
                <button type="submit" disabled={convertLoading || !convertAmount} data-testid="convert-submit"
                  className="bg-purple-500 hover:bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
                  {convertLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Converti'}
                </button>
                {convertResult && (
                  <div className={`p-2 rounded-lg text-xs ${convertResult.success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                    {convertResult.success ? `Convertito: ${convertResult.data.to_amount_net} ${convertResult.data.to_asset} (fee: ${convertResult.data.fee_amount})` : convertResult.msg}
                  </div>
                )}
              </form>
            )}

            {/* Balances Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="wallet-balances">
              {wallets.map(w => (
                <div key={w.asset} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-bold text-sm">{w.asset}</span>
                    <span className="text-gray-400 text-xs">{w.eur_value?.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</span>
                  </div>
                  <div className="text-white text-lg font-mono">{w.balance?.toFixed(w.asset === 'EUR' ? 2 : 6)}</div>
                </div>
              ))}
              {wallets.length === 0 && <div className="col-span-3 text-center text-gray-500 py-8">Nessun saldo disponibile</div>}
            </div>

            {/* Recent Settlements */}
            {settlements.length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-800"><span className="text-white font-medium text-sm">Settlement Recenti</span></div>
                <div className="divide-y divide-gray-800/50">
                  {settlements.slice(0, 5).map(s => (
                    <div key={s.id} className="px-4 py-2 flex items-center justify-between text-xs">
                      <div>
                        <span className="text-gray-300">{s.from_amount} {s.from_asset}</span>
                        <span className="text-gray-500 mx-1">&rarr;</span>
                        <span className="text-green-400">{s.to_amount_net} {s.to_asset}</span>
                      </div>
                      <span className="text-gray-500">{s.type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* UNIFIED WALLET TAB */}
        {tab === 'unified' && (
          <div className="space-y-4" data-testid="unified-wallet-tab">
            <div className="flex items-center justify-between mb-2">
              <div>
                <h2 className="text-white font-bold text-lg">Wallet Unificato</h2>
                <p className="text-gray-500 text-xs">Bilanci interni + on-chain sincronizzati</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-gray-400 text-[10px] uppercase tracking-wider">Totale EUR</div>
                  <div className="text-white font-bold text-xl font-mono" data-testid="unified-total">
                    {unifiedLoading ? '...' : unifiedTotal.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}
                  </div>
                </div>
                <button onClick={fetchUnifiedWallet} disabled={unifiedLoading}
                  className="p-2 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg hover:bg-purple-500/20 transition-colors">
                  <RefreshCw className={`w-4 h-4 ${unifiedLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {unifiedLoading ? (
              <div className="py-12 text-center"><Loader2 className="w-6 h-6 text-purple-500 animate-spin mx-auto" /></div>
            ) : unifiedAssets.length === 0 ? (
              <div className="py-12 text-center text-gray-500 text-sm">Nessun asset trovato. Deposita fondi o collega un wallet on-chain.</div>
            ) : (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-800/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-gray-400 font-medium text-xs">Asset</th>
                        <th className="px-4 py-3 text-right text-gray-400 font-medium text-xs">Interno</th>
                        <th className="px-4 py-3 text-right text-gray-400 font-medium text-xs">Esterno (On-Chain)</th>
                        <th className="px-4 py-3 text-right text-gray-400 font-medium text-xs">Totale</th>
                        <th className="px-4 py-3 text-right text-gray-400 font-medium text-xs">Valore EUR</th>
                        <th className="px-4 py-3 text-center text-gray-400 font-medium text-xs">Fonte</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/50">
                      {unifiedAssets.map(a => (
                        <tr key={a.asset} className="hover:bg-gray-800/30" data-testid={`unified-asset-${a.asset}`}>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500/30 to-violet-600/30 flex items-center justify-center text-white font-bold text-[10px]">
                                {a.asset.slice(0, 2)}
                              </div>
                              <span className="text-white font-medium">{a.asset}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right text-gray-300 font-mono text-xs">{a.internal_balance > 0 ? a.internal_balance.toFixed(6) : '-'}</td>
                          <td className="px-4 py-3 text-right text-cyan-400 font-mono text-xs">{a.external_balance > 0 ? a.external_balance.toFixed(6) : '-'}</td>
                          <td className="px-4 py-3 text-right text-white font-mono font-bold text-xs">{a.total_balance?.toFixed(6)}</td>
                          <td className="px-4 py-3 text-right text-green-400 font-mono text-xs">{a.eur_value?.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                              a.source === 'both' ? 'bg-purple-500/20 text-purple-400' :
                              a.source === 'external' ? 'bg-cyan-500/20 text-cyan-400' :
                              'bg-gray-500/20 text-gray-400'
                            }`}>
                              {a.source === 'both' ? 'Sync' : a.source === 'external' ? 'On-Chain' : 'Piattaforma'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ON-CHAIN TAB */}
        {tab === 'onchain' && (
          <div className="space-y-4">
            <div className="flex gap-2 mb-4 flex-wrap">
              <button onClick={() => setShowLink(!showLink)} data-testid="link-wallet-btn"
                className="flex items-center gap-2 bg-green-500/10 text-green-400 border border-green-500/30 px-4 py-2 rounded-lg text-sm hover:bg-green-500/20">
                <Link2 className="w-4 h-4" />Collega Wallet
              </button>
              <div className="flex items-center gap-2">
                <select value={discoverChain} onChange={e => setDiscoverChain(e.target.value)}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                  {chains.map(c => <option key={c.key} value={c.key}>{c.name}</option>)}
                </select>
                <button onClick={() => handleDiscoverTokens(discoverChain)} disabled={discovering} data-testid="discover-tokens-btn"
                  className="flex items-center gap-2 bg-violet-500/10 text-violet-400 border border-violet-500/30 px-4 py-2 rounded-lg text-sm hover:bg-violet-500/20 disabled:opacity-50">
                  {discovering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  Scopri Token
                </button>
              </div>
            </div>

            {showLink && (
              <form onSubmit={handleLinkWallet} data-testid="link-form" className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-gray-400 text-xs block mb-1">Indirizzo Wallet</label>
                    <input type="text" value={linkAddress} onChange={e => setLinkAddress(e.target.value)} placeholder="0x..."
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm font-mono" />
                  </div>
                  <div>
                    <label className="text-gray-400 text-xs block mb-1">Chain</label>
                    <select value={linkChain} onChange={e => setLinkChain(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                      {chains.map(c => <option key={c.key} value={c.key}>{c.name} ({c.symbol})</option>)}
                    </select>
                  </div>
                </div>
                <button type="submit" disabled={linkLoading || !linkAddress} data-testid="link-submit"
                  className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
                  {linkLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Collega e Sincronizza'}
                </button>
              </form>
            )}

            {/* Discovered Tokens */}
            {discoveredTokens.length > 0 && (
              <div className="bg-gray-900 border border-violet-500/20 rounded-xl overflow-hidden" data-testid="discovered-tokens">
                <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-violet-400" />
                  <span className="text-white font-medium text-sm">Token Scoperti ({discoveredTokens.length})</span>
                </div>
                <div className="divide-y divide-gray-800/50">
                  {discoveredTokens.map((t, i) => (
                    <div key={i} className="px-4 py-2.5 flex items-center justify-between text-sm">
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-full bg-violet-500/20 flex items-center justify-center text-violet-400 text-[10px] font-bold">
                          {t.symbol?.slice(0, 2)}
                        </div>
                        <div>
                          <div className="text-white font-medium text-xs">{t.symbol}</div>
                          <div className="text-gray-500 text-[10px] font-mono truncate max-w-[200px]">{t.token_address}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white font-mono text-xs">{t.balance > 0 ? t.balance.toFixed(6) : '0'}</div>
                        {t.custom && <span className="text-[10px] text-violet-400">Custom</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Chain Status */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="chain-status">
              {chains.map(c => (
                <div key={c.key} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ backgroundColor: (CHAIN_COLORS[c.key] || '#666') + '20', color: CHAIN_COLORS[c.key] }}>
                        {c.symbol.slice(0, 2)}
                      </div>
                      <div>
                        <div className="text-white font-medium text-sm">{c.name}</div>
                        <div className="text-gray-500 text-xs">Chain ID: {c.chain_id}</div>
                      </div>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${c.connected ? 'bg-green-400' : 'bg-gray-600'}`} />
                  </div>
                  {onchainWallets.filter(w => w.chain === c.key).map(w => (
                    <div key={w.chain} className="mt-2 pt-2 border-t border-gray-800">
                      <div className="text-xs text-gray-400 font-mono truncate">{w.address}</div>
                      <div className="flex items-center justify-between mt-1">
                        <span className="text-white font-mono text-sm">{w.native_balance} {w.native_symbol}</span>
                        <button onClick={() => handleSyncChain(c.key)} className="text-purple-400 text-xs flex items-center gap-1 hover:text-purple-300">
                          <RefreshCw className={`w-3 h-3 ${syncing ? 'animate-spin' : ''}`} />Sync
                        </button>
                      </div>
                      {w.tokens?.filter(t => t.balance > 0).map(t => (
                        <div key={t.symbol} className="flex justify-between mt-1 text-xs">
                          <span className="text-gray-400">{t.symbol}</span>
                          <span className="text-gray-300 font-mono">{t.balance}</span>
                        </div>
                      ))}
                      <div className="text-xs text-gray-500 mt-1">{w.synced ? 'Sincronizzato' : 'Non sincronizzato'} - {w.last_sync ? new Date(w.last_sync).toLocaleString('it-IT') : ''}</div>
                    </div>
                  ))}
                  {!onchainWallets.some(w => w.chain === c.key) && (
                    <div className="mt-2 pt-2 border-t border-gray-800 text-center text-gray-500 text-xs py-2">Nessun wallet collegato</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* BANKING TAB */}
        {tab === 'banking' && (
          <div className="space-y-4">
            <div className="flex gap-2 mb-4">
              {ibans.length === 0 && (
                <button onClick={() => setShowIbanForm(true)} data-testid="assign-iban-btn"
                  className="flex items-center gap-2 bg-blue-500/10 text-blue-400 border border-blue-500/30 px-4 py-2 rounded-lg text-sm hover:bg-blue-500/20">
                  <Building className="w-4 h-4" />Ottieni IBAN
                </button>
              )}
              <button onClick={() => setShowWithdraw(true)} data-testid="withdraw-btn"
                className="flex items-center gap-2 bg-orange-500/10 text-orange-400 border border-orange-500/30 px-4 py-2 rounded-lg text-sm hover:bg-orange-500/20">
                <ArrowUpRight className="w-4 h-4" />Prelievo SEPA
              </button>
            </div>

            {showIbanForm && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                <input type="text" value={ibanName} onChange={e => setIbanName(e.target.value)} placeholder="Nome beneficiario"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
                <button onClick={handleAssignIban} data-testid="iban-submit"
                  className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium">Assegna IBAN Virtuale</button>
              </div>
            )}

            {showWithdraw && (
              <form onSubmit={handleWithdraw} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3" data-testid="withdraw-form">
                <div className="grid grid-cols-3 gap-3">
                  <input type="number" step="0.01" value={withdrawAmount} onChange={e => setWithdrawAmount(e.target.value)}
                    placeholder="Importo EUR" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
                  <input type="text" value={withdrawIban} onChange={e => setWithdrawIban(e.target.value)}
                    placeholder="IBAN destinazione" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm font-mono" />
                  <input type="text" value={withdrawName} onChange={e => setWithdrawName(e.target.value)}
                    placeholder="Nome beneficiario" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
                </div>
                <button type="submit" disabled={!withdrawAmount || !withdrawIban || !withdrawName}
                  className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">Invia Bonifico</button>
              </form>
            )}

            {/* IBAN Cards */}
            {ibans.length > 0 && (
              <div className="space-y-3" data-testid="iban-list">
                {ibans.map(ib => (
                  <div key={ib.id} className="bg-gradient-to-r from-gray-900 to-blue-900/20 border border-blue-500/20 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-blue-400 text-xs font-medium uppercase tracking-wide">IBAN Virtuale</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${ib.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>{ib.status}</span>
                    </div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-white font-mono text-lg tracking-wider">{ib.iban}</span>
                      <CopyBtn text={ib.iban} />
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-xs mt-3">
                      <div><span className="text-gray-500">BIC</span><div className="text-gray-300 font-mono">{ib.bic}</div></div>
                      <div><span className="text-gray-500">Banca</span><div className="text-gray-300">{ib.bank_name}</div></div>
                      <div><span className="text-gray-500">Beneficiario</span><div className="text-gray-300">{ib.beneficiary_name}</div></div>
                    </div>
                    <div className="flex gap-6 mt-3 pt-3 border-t border-gray-800 text-xs">
                      <div><span className="text-gray-500">Depositi</span><span className="text-green-400 ml-1">{ib.total_deposited?.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</span></div>
                      <div><span className="text-gray-500">Prelievi</span><span className="text-orange-400 ml-1">{ib.total_withdrawn?.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Banking Transactions */}
            {bankingTxs.length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-800"><span className="text-white font-medium text-sm">Transazioni Bancarie</span></div>
                <div className="divide-y divide-gray-800/50">
                  {bankingTxs.map(t => (
                    <div key={t.id} className="px-4 py-2.5 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        {t.type === 'sepa_deposit' ? <ArrowDownRight className="w-4 h-4 text-green-400" /> : <ArrowUpRight className="w-4 h-4 text-orange-400" />}
                        <div>
                          <div className="text-gray-300">{t.type === 'sepa_deposit' ? 'Deposito SEPA' : 'Prelievo SEPA'}</div>
                          <div className="text-gray-500">{t.reference}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={t.type === 'sepa_deposit' ? 'text-green-400' : 'text-orange-400'}>
                          {t.type === 'sepa_deposit' ? '+' : '-'}{t.amount?.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}
                        </div>
                        <div className={`text-xs ${t.status === 'completed' ? 'text-green-500' : 'text-yellow-500'}`}>{t.status}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
