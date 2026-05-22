import React, { useState, useEffect, useCallback } from 'react';
import { Shield, TrendingUp, Building, Activity, Globe, BarChart3, RefreshCw, ExternalLink, Lock, AlertTriangle, CheckCircle, Coins, Zap, ArrowRightLeft, Banknote, Users, Target, CreditCard } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function xhrFetch(url, opts = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(opts.method || 'GET', url);
    Object.entries(opts.headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => { try { resolve(JSON.parse(xhr.responseText)); } catch { resolve({}); } };
    xhr.onerror = () => resolve({});
    xhr.send(opts.body || null);
  });
}

const StatCard = ({ label, value, sub, icon: Icon, color = 'emerald' }) => (
  <div className={`bg-zinc-900/80 border border-${color}-500/20 rounded-xl p-4`} data-testid={`stat-${label.toLowerCase().replace(/\s/g,'-')}`}>
    <div className="flex items-center justify-between mb-2">
      <span className="text-zinc-500 text-xs uppercase tracking-wider">{label}</span>
      {Icon && <Icon className={`w-4 h-4 text-${color}-500`} />}
    </div>
    <div className={`text-xl font-bold text-${color}-400`}>{value}</div>
    {sub && <div className="text-[10px] text-zinc-600 mt-1">{sub}</div>}
  </div>
);

function PipelineStatusPanel() {
  const [status, setStatus] = useState(null);
  const [fundResult, setFundResult] = useState(null);
  const [payoutCheckResult, setPayoutCheckResult] = useState(null);
  const hdrs = { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` };

  const fetchStatus = useCallback(async () => {
    const data = await xhrFetch(`${API}/api/pipeline/status`, { headers: hdrs });
    if (data.running !== undefined) setStatus(data);
  }, []);

  useEffect(() => { fetchStatus(); const iv = setInterval(fetchStatus, 30000); return () => clearInterval(iv); }, [fetchStatus]);

  const triggerAutoFund = async () => {
    setFundResult(null);
    const data = await xhrFetch(`${API}/api/pipeline/auto-fund`, { method: 'POST', headers: hdrs });
    setFundResult(data);
    fetchStatus();
  };

  const triggerPayoutCheck = async () => {
    setPayoutCheckResult(null);
    const data = await xhrFetch(`${API}/api/pipeline/auto-payout-check`, { method: 'POST', headers: hdrs });
    setPayoutCheckResult(data);
    fetchStatus();
  };

  if (!status) return null;

  return (
    <div className="bg-zinc-900/80 border border-purple-500/20 rounded-xl p-5" data-testid="pipeline-panel">
      <h3 className="text-sm font-bold text-purple-400 mb-3 flex items-center gap-1.5">
        <Zap className="w-4 h-4" /> Autonomous Financial Pipeline
        <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${status.running ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
          {status.running ? 'ATTIVO' : 'FERMO'}
        </span>
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3 text-xs">
        <div className="bg-zinc-800/50 rounded-lg p-2">
          <div className="text-zinc-500">Stripe EUR</div>
          <div className="text-sm font-bold text-emerald-400 font-mono">{status.stripe_balance_eur?.toFixed(2)}</div>
        </div>
        <div className="bg-zinc-800/50 rounded-lg p-2">
          <div className="text-zinc-500">Cicli</div>
          <div className="text-sm font-bold text-white">{status.cycle_count}</div>
        </div>
        <div className="bg-zinc-800/50 rounded-lg p-2">
          <div className="text-zinc-500">Depositi</div>
          <div className="text-sm font-bold text-cyan-400">{status.deposits?.total || 0}</div>
        </div>
        <div className="bg-zinc-800/50 rounded-lg p-2">
          <div className="text-zinc-500">Payouts Auto</div>
          <div className="text-sm font-bold text-amber-400">{status.payouts?.total || 0}</div>
        </div>
        <div className="bg-zinc-800/50 rounded-lg p-2">
          <div className="text-zinc-500">Threshold</div>
          <div className="text-sm font-bold text-zinc-300">{status.auto_payout_threshold_eur} EUR</div>
        </div>
      </div>
      <div className="flex gap-2 mb-3">
        <button onClick={triggerAutoFund}
          data-testid="auto-fund-btn"
          className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded-lg font-bold transition">
          Auto-Fund
        </button>
        <button onClick={triggerPayoutCheck}
          data-testid="auto-payout-btn"
          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg font-bold transition">
          Check & Auto-Payout
        </button>
        <button onClick={fetchStatus}
          className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-xs rounded-lg transition flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>
      {fundResult && (
        <div className={`mb-2 p-2 rounded text-[10px] ${fundResult.funded ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>
          {fundResult.funded ? `Funded: ${fundResult.amount_eur} EUR via ${fundResult.method}` : fundResult.reason || fundResult.action || 'Nessuna revenue da finanziare'}
        </div>
      )}
      {payoutCheckResult && (
        <div className={`p-2 rounded text-[10px] ${payoutCheckResult.executed ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>
          {payoutCheckResult.executed
            ? `Payout eseguito: ${payoutCheckResult.payout_id} | ${payoutCheckResult.amount_eur} EUR`
            : `${payoutCheckResult.reason}: Balance ${payoutCheckResult.balance_eur?.toFixed(2) || '0'} EUR < Threshold ${status.auto_payout_threshold_eur} EUR`}
        </div>
      )}
      <div className="text-[9px] text-zinc-600 mt-2">
        Pipeline: UI → Deposit (Stripe) → Fee Extraction → Revenue → Auto-Payout (SEPA) | Webhook: payment_intent.succeeded + payout.paid + balance.available
      </div>
    </div>
  );
}

function GrowthDashboardPanel() {
  const [data, setData] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [daily, setDaily] = useState([]);
  const hdrs = { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` };

  useEffect(() => {
    Promise.all([
      xhrFetch(`${API}/api/growth/dashboard`, { headers: hdrs }),
      xhrFetch(`${API}/api/growth/revenue`, { headers: hdrs }),
      xhrFetch(`${API}/api/growth/revenue/daily?days=7`, { headers: hdrs }),
    ]).then(([d, r, dy]) => { setData(d); setRevenue(r); setDaily(dy || []); });
  }, []);

  if (!data) return <div className="text-zinc-500 text-sm">Caricamento Growth Dashboard...</div>;

  const f = data.funnel || {};
  const ret = data.retention || {};
  const arpu = data.revenue_per_user || {};

  return (
    <div className="space-y-4" data-testid="growth-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 mb-1">Utenti Totali</div>
          <div className="text-xl font-bold text-emerald-400" data-testid="total-users">{f.total_users || ret.total_users || 0}</div>
        </div>
        <div className="bg-zinc-900/80 border border-cyan-500/20 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 mb-1">DAU / MAU</div>
          <div className="text-xl font-bold text-cyan-400">{ret.dau || 0} / {ret.mau || 0}</div>
          <div className="text-[10px] text-zinc-600">Ratio: {ret.dau_mau_ratio || 0}%</div>
        </div>
        <div className="bg-zinc-900/80 border border-amber-500/20 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 mb-1">ARPU</div>
          <div className="text-xl font-bold text-amber-400">{arpu.arpu_eur || 0} EUR</div>
        </div>
        <div className="bg-zinc-900/80 border border-purple-500/20 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 mb-1">Volume Totale</div>
          <div className="text-xl font-bold text-purple-400">{(arpu.total_volume || 0).toLocaleString()} EUR</div>
        </div>
      </div>

      <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4">
        <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5">
          <Target className="w-4 h-4" /> Funnel di Acquisizione
        </h3>
        <div className="space-y-2">
          {(f.steps || []).map((s, i) => (
            <div key={s.step} className="flex items-center gap-3">
              <div className="w-28 text-xs text-zinc-400 capitalize">{s.step.replace('_', ' ')}</div>
              <div className="flex-1 bg-zinc-800 rounded-full h-5 overflow-hidden">
                <div className="h-full bg-gradient-to-r from-emerald-600 to-cyan-500 rounded-full transition-all"
                  style={{ width: `${Math.max(s.pct, 2)}%` }} />
              </div>
              <div className="w-16 text-right text-xs font-mono text-zinc-300">{s.count} ({s.pct}%)</div>
            </div>
          ))}
        </div>
      </div>

      {revenue && (
        <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4">
          <h3 className="text-sm font-bold text-amber-400 mb-3">Revenue Breakdown ({revenue.period_days}d)</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
            <div><span className="text-zinc-500">Trading Fees:</span> <span className="text-white font-mono">{revenue.trading?.fees_earned || 0} EUR</span></div>
            <div><span className="text-zinc-500">Spread Revenue:</span> <span className="text-white font-mono">{revenue.trading?.spread_revenue || 0} EUR</span></div>
            <div><span className="text-zinc-500">Card Revenue:</span> <span className="text-white font-mono">{revenue.cards?.total_card_revenue || 0} EUR</span></div>
            <div><span className="text-zinc-500">Volume:</span> <span className="text-white font-mono">{revenue.trading?.volume?.toLocaleString() || 0} EUR</span></div>
            <div><span className="text-zinc-500">Net Revenue:</span> <span className="font-bold text-emerald-400 font-mono">{revenue.net_revenue_eur || 0} EUR</span></div>
            <div><span className="text-zinc-500">Referral Costs:</span> <span className="text-red-400 font-mono">-{revenue.costs?.referral_bonuses || 0}</span></div>
          </div>
        </div>
      )}

      {daily.length > 0 && (
        <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4">
          <h3 className="text-sm font-bold text-cyan-400 mb-3">Revenue Giornaliero (7d)</h3>
          <div className="flex items-end gap-1 h-24">
            {daily.map((d, i) => {
              const maxVol = Math.max(...daily.map(x => x.volume || 1));
              const h = Math.max(((d.volume || 0) / maxVol) * 100, 4);
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full bg-emerald-600/70 rounded-t" style={{ height: `${h}%` }} title={`${d.date}: ${d.volume} EUR`} />
                  <div className="text-[8px] text-zinc-600">{d.date?.slice(5)}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function MonetizationPanel() {
  const [cardStats, setCardStats] = useState(null);
  const [arpu, setArpu] = useState(null);
  const hdrs = { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` };

  useEffect(() => {
    Promise.all([
      xhrFetch(`${API}/api/card-engine/monetization`, { headers: hdrs }),
      xhrFetch(`${API}/api/growth/arpu`, { headers: hdrs }),
    ]).then(([c, a]) => { setCardStats(c); setArpu(a); });
  }, []);

  return (
    <div className="space-y-4" data-testid="monetization-tab">
      <div className="bg-zinc-900/80 border border-amber-500/20 rounded-xl p-5">
        <h3 className="text-sm font-bold text-amber-400 mb-4 flex items-center gap-1.5">
          <CreditCard className="w-4 h-4" /> Card Monetization Engine
        </h3>
        {cardStats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-zinc-800/50 rounded-lg p-3">
              <div className="text-zinc-500">Carte Attive</div>
              <div className="text-lg font-bold text-white">{cardStats.total_cards_active}</div>
            </div>
            <div className="bg-zinc-800/50 rounded-lg p-3">
              <div className="text-zinc-500">Volume Carte</div>
              <div className="text-lg font-bold text-white">{cardStats.total_volume?.toLocaleString()} EUR</div>
            </div>
            <div className="bg-zinc-800/50 rounded-lg p-3">
              <div className="text-zinc-500">Interchange</div>
              <div className="text-lg font-bold text-emerald-400">{cardStats.total_interchange_revenue} EUR</div>
            </div>
            <div className="bg-zinc-800/50 rounded-lg p-3">
              <div className="text-zinc-500">FX Revenue</div>
              <div className="text-lg font-bold text-cyan-400">{cardStats.total_fx_revenue} EUR</div>
            </div>
          </div>
        ) : <div className="text-zinc-600 text-xs">Caricamento...</div>}

        {cardStats?.revenue_streams && (
          <div className="mt-4 grid grid-cols-2 gap-2 text-[10px]">
            {Object.entries(cardStats.revenue_streams).map(([k, v]) => (
              <div key={k} className="flex justify-between bg-zinc-800/30 rounded px-2 py-1">
                <span className="text-zinc-500 capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="text-zinc-300 font-mono">{v}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {arpu && (
        <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4">
          <h3 className="text-sm font-bold text-purple-400 mb-3">Revenue Per User (ARPU)</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
            <div><span className="text-zinc-500">ARPU:</span> <span className="text-white font-bold">{arpu.arpu_eur} EUR</span></div>
            <div><span className="text-zinc-500">Volume/Utente:</span> <span className="text-white">{arpu.avg_volume_per_user} EUR</span></div>
            <div><span className="text-zinc-500">Revenue Totale:</span> <span className="text-emerald-400 font-bold">{arpu.total_revenue_eur} EUR</span></div>
          </div>
          <div className="mt-3 text-[10px] text-zinc-600">
            GA4: {arpu.external_tracking?.ga4 ? 'Attivo' : 'Non configurato'} | Meta Pixel: {arpu.external_tracking?.meta_pixel ? 'Attivo' : 'Non configurato'}
          </div>
        </div>
      )}

      <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4">
        <h3 className="text-sm font-bold text-zinc-400 mb-2">Modello di Scaling Revenue</h3>
        <div className="text-xs text-zinc-500 space-y-1">
          <div className="flex items-center gap-2"><Users className="w-3 h-3" /> Piu utenti → piu transazioni → piu spread → piu profitto</div>
          <div>Revenue Sources: Interchange (1.5%) + FX (0.5%) + Trading Spread + Card Fees + Yield</div>
          <div>Provider: <span className="text-emerald-400 font-mono">{cardStats?.provider || 'internal'}</span> (plug-and-play per Marqeta/NIUM/Adyen)</div>
        </div>
      </div>
    </div>
  );
}

function RevenueWithdrawPanel() {
  const [amount, setAmount] = useState('');
  const [destType, setDestType] = useState('sepa');
  const [iban, setIban] = useState('');
  const [wallet, setWallet] = useState('');
  const [beneficiary, setBeneficiary] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);

  const hdrs = { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` };

  const fetchHistory = useCallback(async () => {
    try {
      const data = await xhrFetch(`${API}/api/cashout/revenue-history`, { headers: hdrs });
      setHistory(data.withdrawals || []);
    } catch {}
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handleWithdraw = async () => {
    setLoading(true); setResult(null);
    try {
      const body = { amount: parseFloat(amount), currency: 'EUR', destination_type: destType };
      if (destType === 'crypto') body.destination_wallet = wallet;
      else { body.destination_iban = iban; body.beneficiary_name = beneficiary; }
      const data = await xhrFetch(`${API}/api/cashout/revenue-withdraw`, {
        method: 'POST', headers: hdrs, body: JSON.stringify(body)
      });
      if (data.success) {
        setResult({ ok: true, msg: data.message, payout_id: data.payout_id, tx_hash: data.tx_hash, explorer: data.explorer });
        setAmount(''); fetchHistory();
      } else {
        setResult({ ok: false, msg: data.detail || 'Errore nel prelievo revenue' });
      }
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setLoading(false); }
  };

  const [stripeBalance, setStripeBalance] = useState(null);
  const [topupAmount, setTopupAmount] = useState('50');
  const [topupLoading, setTopupLoading] = useState(false);
  const [payoutAmount, setPayoutAmount] = useState('5');
  const [payoutLoading, setPayoutLoading] = useState(false);
  const [payoutResult, setPayoutResult] = useState(null);

  const fetchStripeBalance = useCallback(async () => {
    try {
      const data = await xhrFetch(`${API}/api/cashout/stripe-balance`, { headers: hdrs });
      setStripeBalance(data);
    } catch {}
  }, []);

  useEffect(() => { fetchStripeBalance(); }, [fetchStripeBalance]);

  const handleStripeTopup = async () => {
    setTopupLoading(true);
    try {
      const data = await xhrFetch(`${API}/api/cashout/stripe-topup`, {
        method: 'POST', headers: hdrs, body: JSON.stringify({ amount_eur: parseFloat(topupAmount) })
      });
      if (data.checkout_url) {
        window.open(data.checkout_url, '_blank');
      }
    } catch {}
    finally { setTopupLoading(false); }
  };

  const handleSepaPayout = async () => {
    setPayoutLoading(true); setPayoutResult(null);
    try {
      const data = await xhrFetch(`${API}/api/cashout/sepa-payout`, {
        method: 'POST', headers: hdrs,
        body: JSON.stringify({ amount_eur: parseFloat(payoutAmount), description: 'NeoNoble Revenue SEPA Payout' })
      });
      setPayoutResult(data);
      if (data.success) fetchStripeBalance();
    } catch (e) { setPayoutResult({ success: false, message: e.message }); }
    finally { setPayoutLoading(false); }
  };

  return (
    <div className="space-y-4" data-testid="revenue-tab">
      {/* Stripe Balance + SEPA Payout */}
      <div className="bg-zinc-900/80 border border-cyan-500/20 rounded-xl p-5" data-testid="stripe-section">
        <h3 className="text-sm font-bold text-cyan-400 mb-4 flex items-center gap-1.5">
          <Banknote className="w-4 h-4" /> Stripe — Saldo & SEPA Payout
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <div className="text-[10px] text-zinc-500">EUR Disponibile</div>
            <div className="text-lg font-bold text-emerald-400 font-mono" data-testid="stripe-eur-available">
              {stripeBalance ? `€${stripeBalance.available?.EUR?.toFixed(2) || '0.00'}` : '...'}
            </div>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <div className="text-[10px] text-zinc-500">EUR Pending</div>
            <div className="text-lg font-bold text-amber-400 font-mono">
              {stripeBalance ? `€${stripeBalance.pending?.EUR?.toFixed(2) || '0.00'}` : '...'}
            </div>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <div className="text-[10px] text-zinc-500">Payout Ready</div>
            <div className={`text-lg font-bold ${stripeBalance?.payout_ready ? 'text-emerald-400' : 'text-red-400'}`}>
              {stripeBalance?.payout_ready ? 'SI' : 'NO'}
            </div>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3 flex flex-col">
            <div className="text-[10px] text-zinc-500 mb-1">Top-Up Stripe</div>
            <div className="flex gap-1">
              <input type="number" value={topupAmount} onChange={e => setTopupAmount(e.target.value)}
                className="flex-1 bg-zinc-700 border border-zinc-600 rounded px-2 py-1 text-xs text-white font-mono min-w-0" />
              <button onClick={handleStripeTopup} disabled={topupLoading}
                data-testid="stripe-topup-btn"
                className="px-2 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs rounded font-bold disabled:opacity-50">
                {topupLoading ? '...' : 'Pay'}
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <div>
            <label className="text-[10px] text-zinc-500 mb-1 block">Importo SEPA Payout (EUR)</label>
            <input type="number" value={payoutAmount} onChange={e => setPayoutAmount(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
              data-testid="sepa-payout-amount" />
          </div>
          <button onClick={handleSepaPayout} disabled={payoutLoading || !stripeBalance?.payout_ready}
            data-testid="sepa-payout-btn"
            className="py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold rounded-lg disabled:opacity-50 transition">
            {payoutLoading ? 'Esecuzione...' : 'Esegui SEPA Payout'}
          </button>
          <button onClick={fetchStripeBalance}
            className="py-2.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded-lg transition flex items-center justify-center gap-1">
            <RefreshCw className="w-3 h-3" /> Aggiorna Saldo
          </button>
        </div>

        {payoutResult && (
          <div className={`mt-3 p-3 rounded-lg text-xs ${payoutResult.success ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400' : 'bg-red-500/10 border border-red-500/30 text-red-400'}`} data-testid="payout-result">
            {payoutResult.success ? (
              <>
                <div className="font-bold">{payoutResult.message}</div>
                <div className="font-mono mt-1">Payout ID: {payoutResult.payout_id}</div>
                <div>Status: {payoutResult.status} → {payoutResult.status_flow}</div>
                {payoutResult.arrival_date && <div>Arrivo: {payoutResult.arrival_date}</div>}
              </>
            ) : (
              <>
                <div>{payoutResult.message}</div>
                {payoutResult.fix && <div className="mt-1 text-amber-400">{payoutResult.fix}</div>}
              </>
            )}
          </div>
        )}
      </div>

      {/* Autonomous Pipeline Status */}
      <PipelineStatusPanel />

      <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-5" data-testid="revenue-withdraw-panel">
        <h3 className="text-sm font-bold text-emerald-400 mb-4 flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4" /> Revenue Withdrawal — Prelievo Profitti
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-zinc-400 mb-1 block">Importo (EUR)</label>
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white"
              placeholder="0.00" data-testid="revenue-amount-input" />
          </div>
          <div>
            <label className="text-xs text-zinc-400 mb-1 block">Tipo Destinazione</label>
            <select value={destType} onChange={e => setDestType(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white" data-testid="revenue-dest-type">
              <option value="sepa">SEPA</option>
              <option value="swift">SWIFT</option>
              <option value="crypto">Crypto Wallet</option>
            </select>
          </div>
        </div>
        {destType !== 'crypto' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">IBAN Destinazione</label>
              <input type="text" value={iban} onChange={e => setIban(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
                placeholder="IT60X0542811101000000123456" data-testid="revenue-iban-input" />
            </div>
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Beneficiario</label>
              <input type="text" value={beneficiary} onChange={e => setBeneficiary(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white"
                placeholder="NeoNoble Holdings SA" data-testid="revenue-beneficiary-input" />
            </div>
          </div>
        ) : (
          <div className="mb-4">
            <label className="text-xs text-zinc-400 mb-1 block">Wallet Destinazione</label>
            <input type="text" value={wallet} onChange={e => setWallet(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
              placeholder="0x..." data-testid="revenue-wallet-input" />
          </div>
        )}
        <button onClick={handleWithdraw} disabled={loading || !amount}
          className="w-full md:w-auto px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold rounded-lg disabled:opacity-50 transition"
          data-testid="revenue-withdraw-btn">
          {loading ? 'Esecuzione...' : 'Preleva Revenue'}
        </button>
        {result && (
          <div className={`mt-4 p-3 rounded-lg text-sm ${result.ok ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400' : 'bg-red-500/10 border border-red-500/30 text-red-400'}`} data-testid="revenue-result">
            <div>{result.msg}</div>
            {result.payout_id && <div className="text-xs mt-1 font-mono">Payout ID: {result.payout_id}</div>}
            {result.tx_hash && <div className="text-xs mt-1 font-mono">TX: <a href={result.explorer} target="_blank" rel="noopener noreferrer" className="underline">{result.tx_hash.slice(0, 20)}...</a></div>}
          </div>
        )}
      </div>
      <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4" data-testid="revenue-history-panel">
        <h3 className="text-sm font-bold text-zinc-300 mb-3">Storico Prelievi Revenue</h3>
        {history.length === 0 ? (
          <div className="text-xs text-zinc-600">Nessun prelievo revenue ancora</div>
        ) : (
          <div className="space-y-2">
            {history.map((w, i) => (
              <div key={w.id || i} className="bg-zinc-800/50 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <div className="text-xs text-white font-mono">{w.amount} {w.currency} → {w.destination_type}</div>
                  <div className="text-[10px] text-zinc-500">{w.created_at?.slice(0, 19)} | {w.admin_email}</div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                  w.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                }`}>{w.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const [financials, setFinancials] = useState(null);
  const [pnl, setPnl] = useState(null);
  const [structure, setStructure] = useState(null);
  const [safeguarding, setSafeguarding] = useState(null);
  const [bankingRails, setBankingRails] = useState(null);
  const [securityStatus, setSecurityStatus] = useState(null);
  const [treasuryCheck, setTreasuryCheck] = useState(null);
  const [recentTxs, setRecentTxs] = useState([]);
  const [realTreasury, setRealTreasury] = useState(null);
  const [virtualMetrics, setVirtualMetrics] = useState(null);
  const [circleBalances, setCircleBalances] = useState(null);
  const [circleAutoOp, setCircleAutoOp] = useState(null);
  const [circleSegregation, setCircleSegregation] = useState(null);
  const [circleFailSafe, setCircleFailSafe] = useState(null);
  const [cashoutStatus, setCashoutStatus] = useState(null);
  const [cashoutReport, setCashoutReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');

  const headers = useCallback(() => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const h = headers();
    try {
      const [fin, p, str, saf, br, sec, tc, txs, rt, vm, cb, cao, csg, cfs, cstat, crpt] = await Promise.all([
        xhrFetch(`${API}/api/institutional/financials`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/institutional/pnl?period_hours=24`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/institutional/structure`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/institutional/compliance/safeguarding`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/institutional/banking-rails`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/neno-exchange/security-status`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/institutional/risk/treasury-check/NENO?amount=1`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/neno-exchange/transactions?limit=10`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/strategic/real-treasury`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/strategic/virtual-metrics`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/circle/wallets/balances`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/circle/auto-op/status`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/circle/segregation/summary`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/circle/fail-safe/report`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/cashout/status`, { headers: h }).catch(() => null),
        xhrFetch(`${API}/api/cashout/report`, { headers: h }).catch(() => null),
      ]);
      setFinancials(fin); setPnl(p); setStructure(str); setSafeguarding(saf);
      setBankingRails(br); setSecurityStatus(sec); setTreasuryCheck(tc);
      setRecentTxs(txs?.transactions || []);
      setRealTreasury(rt); setVirtualMetrics(vm);
      setCircleBalances(cb); setCircleAutoOp(cao);
      setCircleSegregation(csg); setCircleFailSafe(cfs);
      setCashoutStatus(cstat); setCashoutReport(crpt);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [headers]);

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 30000); return () => clearInterval(i); }, [fetchAll]);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'revenue', label: 'Revenue', icon: TrendingUp },
    { id: 'growth', label: 'Growth', icon: Target },
    { id: 'monetization', label: 'Monetization', icon: CreditCard },
    { id: 'cashout', label: 'Cashout Engine', icon: Banknote },
    { id: 'circle-usdc', label: 'Circle USDC', icon: Coins },
    { id: 'real-virtual', label: 'Real vs Virtual', icon: Shield },
    { id: 'treasury', label: 'Treasury & Risk', icon: Lock },
    { id: 'rails', label: 'Banking Rails', icon: Globe },
    { id: 'executions', label: 'Execution Logs', icon: Activity },
  ];

  return (
    <div className="min-h-screen bg-zinc-950 text-white" data-testid="admin-dashboard">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
              Admin Command Center
            </h1>
            <p className="text-zinc-500 text-sm">NeoNoble Ramp — IPO-Ready Fintech Platform</p>
          </div>
          <button onClick={fetchAll} className="p-2 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition" data-testid="refresh-btn">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-xl p-1" data-testid="tab-nav">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition ${
                tab === t.id ? 'bg-emerald-500/20 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'
              }`} data-testid={`tab-${t.id}`}>
              <t.icon className="w-3.5 h-3.5" /> {t.label}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div className="space-y-4">
            {/* System Status Banner */}
            <div className="bg-zinc-900/80 border border-emerald-500/30 rounded-xl p-3" data-testid="system-status-banner">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[10px] font-bold text-emerald-400">REAL MODE</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Zap className="w-3 h-3 text-cyan-400" />
                    <span className="text-[10px] text-cyan-400">Cashout Engine: {cashoutStatus?.running ? 'ACTIVE' : 'OFF'}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ArrowRightLeft className="w-3 h-3 text-blue-400" />
                    <span className="text-[10px] text-blue-400">Instant Withdraw: ACTIVE</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Coins className="w-3 h-3 text-amber-400" />
                    <span className="text-[10px] text-amber-400">Auto-Op Loop: {circleAutoOp?.running ? 'ACTIVE' : 'OFF'}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {cashoutReport?.hot_wallet?.neno > 0 && (
                    <span className="text-[9px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">{cashoutReport?.hot_wallet?.neno?.toFixed(4)} NENO</span>
                  )}
                  <span className="text-[9px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">{cashoutReport?.usdc_total?.toFixed(2) || '0.00'} USDC</span>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Volume Totale" value={`EUR ${(financials?.kpis?.total_volume_eur || 0).toLocaleString()}`} icon={TrendingUp} />
              <StatCard label="Transazioni" value={financials?.kpis?.total_transactions || 0} icon={Activity} color="cyan" />
              <StatCard label="Utenti" value={financials?.kpis?.total_users || 0} icon={Building} color="blue" />
              <StatCard label="Revenue/User" value={`EUR ${financials?.kpis?.revenue_per_user_eur || 0}`} icon={BarChart3} color="amber" />
            </div>
            {pnl && (
              <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4">
                <h3 className="text-sm font-bold text-emerald-400 mb-3">PnL (24h)</h3>
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center">
                    <div className="text-lg font-bold text-emerald-400">EUR {pnl.trading_fees?.total_eur || 0}</div>
                    <div className="text-[10px] text-zinc-500">Trading Fees ({pnl.trading_fees?.count || 0} trades)</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-cyan-400">EUR {pnl.spread_revenue?.total_eur || 0}</div>
                    <div className="text-[10px] text-zinc-500">Spread Revenue</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-amber-400">EUR {pnl.total_revenue_eur || 0}</div>
                    <div className="text-[10px] text-zinc-500">Revenue Totale</div>
                  </div>
                </div>
              </div>
            )}
            {safeguarding && (
              <div className="bg-zinc-900/80 border border-blue-500/20 rounded-xl p-4">
                <h3 className="text-sm font-bold text-blue-400 mb-2">Safeguarding EMI</h3>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-base font-bold text-white">EUR {(safeguarding.total_client_funds_eur || 0).toLocaleString()}</div>
                    <div className="text-[10px] text-zinc-500">Fondi Clienti</div>
                  </div>
                  <div>
                    <div className="text-base font-bold text-white">EUR {(safeguarding.treasury_eur || 0).toLocaleString()}</div>
                    <div className="text-[10px] text-zinc-500">Treasury</div>
                  </div>
                  <div>
                    <div className={`text-base font-bold ${safeguarding.coverage_pct >= 100 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {safeguarding.coverage_pct}%
                    </div>
                    <div className="text-[10px] text-zinc-500">Coverage</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}


        {tab === 'revenue' && <RevenueWithdrawPanel />}

        {tab === 'growth' && <GrowthDashboardPanel />}

        {tab === 'monetization' && <MonetizationPanel />}

        {tab === 'cashout' && (
          <div className="space-y-4" data-testid="cashout-tab">
            {/* Engine Status */}
            <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4" data-testid="cashout-engine-panel">
              <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5">
                <Banknote className="w-4 h-4" /> Autonomous Profit Extraction Engine
                {cashoutStatus?.running && <span className="ml-2 text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full animate-pulse">ACTIVE</span>}
              </h3>
              {cashoutStatus && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                    <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                      <div className="text-base font-bold text-emerald-400">{cashoutStatus.cycle_count}</div>
                      <div className="text-[10px] text-zinc-500">Cicli</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                      <div className="text-base font-bold text-cyan-400">{cashoutStatus.cumulative?.extracted_usdc?.toFixed(6)}</div>
                      <div className="text-[10px] text-zinc-500">USDC Estratti</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                      <div className="text-base font-bold text-amber-400">{cashoutStatus.cumulative?.extracted_eur?.toFixed(2)}</div>
                      <div className="text-[10px] text-zinc-500">EUR Estratti</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                      <div className="text-base font-bold text-white">{cashoutStatus.cumulative?.cashouts_executed}</div>
                      <div className="text-[10px] text-zinc-500">Cashout Eseguiti</div>
                    </div>
                  </div>
                  <div className="flex gap-3 text-[10px] text-zinc-500">
                    <span>Intervallo: {cashoutStatus.interval_seconds}s</span>
                    <span>Buffer TREASURY: {cashoutStatus.treasury_buffer_pct}%</span>
                    <span>Min USDC: {cashoutStatus.min_cashout_usdc}</span>
                    <span>Min EUR: {cashoutStatus.min_cashout_eur}</span>
                  </div>
                </>
              )}
            </div>

            {/* EUR Accounts */}
            <div className="bg-zinc-900/80 border border-blue-500/20 rounded-xl p-4" data-testid="eur-accounts-panel">
              <h3 className="text-sm font-bold text-blue-400 mb-3 flex items-center gap-1.5"><ArrowRightLeft className="w-4 h-4" /> Conti EUR (SEPA/SWIFT)</h3>
              {cashoutStatus?.eur_accounts && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(cashoutStatus.eur_accounts).map(([key, acc]) => (
                    <div key={key} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3" data-testid={`eur-account-${key}`}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-bold text-blue-400">{key}</span>
                        <span className="text-[9px] bg-zinc-700/50 text-zinc-400 px-1.5 py-0.5 rounded">{acc.bic}</span>
                      </div>
                      <div className="text-xs text-white font-mono">{acc.iban}</div>
                      <div className="text-[10px] text-zinc-500 mt-1">{acc.beneficiary}</div>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div className="bg-zinc-800/30 rounded p-1.5">
                  <div className="text-[10px] text-emerald-400">SEPA Instant</div>
                  <div className="text-[9px] text-zinc-500">&lt; 5,000 EUR</div>
                </div>
                <div className="bg-zinc-800/30 rounded p-1.5">
                  <div className="text-[10px] text-blue-400">SEPA Standard</div>
                  <div className="text-[9px] text-zinc-500">5k — 100k EUR</div>
                </div>
                <div className="bg-zinc-800/30 rounded p-1.5">
                  <div className="text-[10px] text-amber-400">SWIFT</div>
                  <div className="text-[9px] text-zinc-500">&gt; 100k EUR</div>
                </div>
              </div>
            </div>

            {/* Report Summary */}
            {cashoutReport && (
              <div className="bg-zinc-900/80 border border-cyan-500/20 rounded-xl p-4" data-testid="cashout-report-panel">
                <h3 className="text-sm font-bold text-cyan-400 mb-3">Report Completo</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-cyan-400">{cashoutReport.usdc_total?.toFixed(6)}</div>
                    <div className="text-[10px] text-zinc-500">USDC On-Chain</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-emerald-400">{cashoutReport.hot_wallet?.neno?.toFixed(4) || '0'}</div>
                    <div className="text-[10px] text-zinc-500">NENO Hot Wallet</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-amber-400">{cashoutReport.hot_wallet?.bnb?.toFixed(6) || '0'}</div>
                    <div className="text-[10px] text-zinc-500">BNB Hot Wallet</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-blue-400">{cashoutReport.conversion_opportunities}</div>
                    <div className="text-[10px] text-zinc-500">Conversioni Disponibili</div>
                  </div>
                </div>
                {cashoutReport.usdc_wallets && (
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    {Object.entries(cashoutReport.usdc_wallets).map(([role, bal]) => (
                      <div key={role} className="bg-zinc-800/30 rounded p-1.5 text-center">
                        <div className="text-[10px] text-zinc-400 uppercase">{role}</div>
                        <div className="text-xs font-bold text-white">{bal?.toFixed(6)} USDC</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Recent Cashouts */}
            {cashoutStatus?.recent_cashouts?.length > 0 && (
              <div className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-4" data-testid="recent-cashouts-panel">
                <h3 className="text-sm font-bold text-zinc-400 mb-3">Cashout Recenti</h3>
                <div className="space-y-1.5">
                  {cashoutStatus.recent_cashouts.slice(0, 10).map((co, i) => (
                    <div key={i} className="flex items-center justify-between bg-zinc-800/30 rounded p-2 text-[10px]">
                      <span className={`font-bold ${co.type?.includes('sepa') ? 'text-blue-400' : co.type?.includes('swift') ? 'text-amber-400' : 'text-cyan-400'}`}>
                        {co.type?.replace(/_/g, ' ').toUpperCase()}
                      </span>
                      <span className="text-white font-mono">{co.amount} {co.currency || co.asset || 'USDC'}</span>
                      <span className={`px-1.5 py-0.5 rounded ${co.status === 'confirmed' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                        {co.status}
                      </span>
                      <span className="text-zinc-600">{co.created_at?.slice(0, 16)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'circle-usdc' && (
          <div className="space-y-4" data-testid="circle-usdc-tab">
            {/* Wallet Balances */}
            <div className="bg-zinc-900/80 border border-cyan-500/20 rounded-xl p-4" data-testid="circle-wallets-panel">
              <h3 className="text-sm font-bold text-cyan-400 mb-3 flex items-center gap-1.5"><Coins className="w-4 h-4" /> Wallet Segregati USDC (On-Chain Verificato)</h3>
              {circleBalances?.wallets ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {Object.entries(circleBalances.wallets).map(([role, data]) => (
                    <div key={role} className={`bg-zinc-800/50 border rounded-lg p-3 ${
                      role === 'client' ? 'border-blue-500/30' : role === 'treasury' ? 'border-emerald-500/30' : 'border-amber-500/30'
                    }`} data-testid={`circle-wallet-${role}`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-xs font-bold uppercase ${
                          role === 'client' ? 'text-blue-400' : role === 'treasury' ? 'text-emerald-400' : 'text-amber-400'
                        }`}>{role}</span>
                        {data.verified ? <CheckCircle className="w-3 h-3 text-emerald-500" /> : <AlertTriangle className="w-3 h-3 text-red-500" />}
                      </div>
                      <div className="text-xl font-bold text-white font-mono">{data.balance?.toFixed(6) || '0.000000'} USDC</div>
                      <div className="text-[9px] text-zinc-600 mt-1 font-mono truncate">{data.address}</div>
                      <div className="text-[9px] text-zinc-600">Chain: {data.chain} | Block: {data.block || 'N/A'}</div>
                    </div>
                  ))}
                </div>
              ) : <div className="text-xs text-zinc-500">Caricamento...</div>}
              {circleBalances && (
                <div className="mt-3 bg-zinc-800/30 rounded-lg p-2 flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Totale USDC On-Chain</span>
                  <span className="text-sm font-bold text-cyan-400">{circleBalances.total_usdc?.toFixed(6) || '0.000000'} USDC</span>
                </div>
              )}
            </div>

            {/* Auto-Operation Loop */}
            <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4" data-testid="auto-op-panel">
              <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5">
                <Zap className="w-4 h-4" /> Auto-Operation Loop
                {circleAutoOp?.running && <span className="ml-2 text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full animate-pulse">ACTIVE</span>}
              </h3>
              {circleAutoOp && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-emerald-400">{circleAutoOp.cycle_count}</div>
                    <div className="text-[10px] text-zinc-500">Cicli Completati</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-cyan-400">{circleAutoOp.operations_executed}</div>
                    <div className="text-[10px] text-zinc-500">Operazioni Eseguite</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-red-400">{circleAutoOp.operations_blocked}</div>
                    <div className="text-[10px] text-zinc-500">Operazioni Bloccate</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-amber-400">{circleAutoOp.total_pnl_usdc?.toFixed(6)}</div>
                    <div className="text-[10px] text-zinc-500">PnL Reale (USDC)</div>
                  </div>
                </div>
              )}
              {circleAutoOp?.fail_safes && (
                <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(circleAutoOp.fail_safes).map(([key, val]) => (
                    <div key={key} className="bg-zinc-800/30 rounded p-1.5 flex items-center gap-1">
                      {val === true ? <CheckCircle className="w-3 h-3 text-emerald-500 flex-shrink-0" /> : <span className="text-[9px] text-zinc-400">{val}</span>}
                      <span className="text-[9px] text-zinc-500">{key.replace(/_/g, ' ')}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Segregation Summary */}
            <div className="bg-zinc-900/80 border border-blue-500/20 rounded-xl p-4" data-testid="segregation-panel">
              <h3 className="text-sm font-bold text-blue-400 mb-3">Wallet Segregation</h3>
              {circleSegregation && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-white">{circleSegregation.total_movements}</div>
                    <div className="text-[10px] text-zinc-500">Movimenti Totali</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-emerald-400">{circleSegregation.confirmed}</div>
                    <div className="text-[10px] text-zinc-500">Confermati</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                    <div className="text-base font-bold text-amber-400">{circleSegregation.pending}</div>
                    <div className="text-[10px] text-zinc-500">In Attesa</div>
                  </div>
                </div>
              )}
            </div>

            {/* Fail-Safe Report */}
            {circleFailSafe && (
              <div className="bg-zinc-900/80 border border-red-500/20 rounded-xl p-4" data-testid="fail-safe-panel">
                <h3 className="text-sm font-bold text-red-400 mb-3 flex items-center gap-1.5"><Lock className="w-4 h-4" /> Fail-Safe & Reality Check</h3>
                <div className="grid grid-cols-2 gap-2">
                  {circleFailSafe.rules && Object.entries(circleFailSafe.rules).map(([rule, active]) => (
                    <div key={rule} className="flex items-center gap-2 bg-zinc-800/50 rounded-lg p-2">
                      {active ? <CheckCircle className="w-3 h-3 text-emerald-500" /> : <AlertTriangle className="w-3 h-3 text-red-500" />}
                      <span className="text-[10px] text-zinc-400">{rule.replace(/_/g, ' ')}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-[10px] text-zinc-600">
                  Cicli totali: {circleFailSafe.statistics?.total_cycles} | Operazioni bloccate: {circleFailSafe.statistics?.blocked_operations}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'real-virtual' && (
          <div className="space-y-4">
            <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4" data-testid="real-treasury-panel">
              <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5"><CheckCircle className="w-4 h-4" /> Treasury REALE (On-Chain Verificato)</h3>
              {realTreasury && (
                <>
                  <div className="text-xl font-bold text-emerald-400 mb-3">EUR {(realTreasury.total_eur_value || 0).toLocaleString()}</div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {realTreasury.assets && Object.entries(realTreasury.assets).map(([asset, data]) => (
                      <div key={asset} className="bg-zinc-800/50 rounded-lg p-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-white">{asset}</span>
                          {data.verified ? <CheckCircle className="w-3 h-3 text-emerald-500" /> : <AlertTriangle className="w-3 h-3 text-red-500" />}
                        </div>
                        <div className="text-sm font-mono text-emerald-400">{data.balance}</div>
                        <div className="text-[9px] text-zinc-600">{data.source}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 text-[10px] text-zinc-600">
                    Hot wallet: {realTreasury.hot_wallet} | Block: {realTreasury.block_number} | Fee reali guadagnate: EUR {realTreasury.real_revenue?.total_fees_earned || 0} ({realTreasury.real_revenue?.real_trade_count || 0} trade)
                  </div>
                </>
              )}
            </div>

            <div className="bg-zinc-900/80 border border-amber-500/20 rounded-xl p-4" data-testid="virtual-metrics-panel">
              <h3 className="text-sm font-bold text-amber-400 mb-3 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" /> Metriche VIRTUALI (NON sono denaro reale)</h3>
              {virtualMetrics && (
                <>
                  <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-2 mb-3 text-[10px] text-amber-500">
                    {virtualMetrics.warning}
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <div className="text-base font-bold text-emerald-400">EUR {(virtualMetrics.real_executed_volume_eur || 0).toLocaleString()}</div>
                      <div className="text-[10px] text-zinc-500">Volume Reale</div>
                    </div>
                    <div>
                      <div className="text-base font-bold text-amber-400">EUR {(virtualMetrics.virtual_demand_volume_eur || 0).toLocaleString()}</div>
                      <div className="text-[10px] text-zinc-500">Volume Virtuale</div>
                    </div>
                    <div>
                      <div className="text-base font-bold text-cyan-400">{virtualMetrics.conversion_rate_pct}%</div>
                      <div className="text-[10px] text-zinc-500">Conversion Rate</div>
                    </div>
                  </div>
                  <div className="mt-3 bg-zinc-800/50 rounded-lg p-2">
                    <div className="text-[10px] text-zinc-400 font-mono">
                      virtual demand → trading reale → fee/spread → treasury reale → payout
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-1">
                      Reali: {virtualMetrics.real_transactions} tx | Virtuali: {virtualMetrics.virtual_transactions} tx | Totali: {virtualMetrics.total_transactions}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'treasury' && (
          <div className="space-y-4">
            {securityStatus && (
              <div className="bg-zinc-900/80 border border-emerald-500/20 rounded-xl p-4">
                <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-1.5"><Lock className="w-4 h-4" /> Security Caps</h3>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                    <div className="text-base font-bold text-white">EUR {securityStatus.treasury_caps?.max_single_tx_eur?.toLocaleString()}</div>
                    <div className="text-[10px] text-zinc-500">Max/Transazione</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                    <div className="text-base font-bold text-white">EUR {securityStatus.treasury_caps?.max_daily_eur?.toLocaleString()}</div>
                    <div className="text-[10px] text-zinc-500">Max/Giorno</div>
                  </div>
                  <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                    <div className="text-base font-bold text-white">{securityStatus.treasury_caps?.max_neno_per_tx} NENO</div>
                    <div className="text-[10px] text-zinc-500">Max NENO/TX</div>
                  </div>
                </div>
                <div className="mt-3 text-[10px] text-zinc-600">
                  Rate limit: {securityStatus.rate_limit?.max_exec_ops_per_min} ops/min | Assets on-chain: {securityStatus.supported_onchain_assets?.join(', ')}
                </div>
              </div>
            )}
            {treasuryCheck && (
              <div className="bg-zinc-900/80 border border-cyan-500/20 rounded-xl p-4">
                <h3 className="text-sm font-bold text-cyan-400 mb-2">Treasury On-Chain (NENO)</h3>
                <div className="flex items-center gap-2">
                  {treasuryCheck.sufficient ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <AlertTriangle className="w-4 h-4 text-red-500" />}
                  <span className="font-mono text-sm">{treasuryCheck.on_chain} NENO on-chain</span>
                </div>
                <div className="text-[10px] text-zinc-600 mt-1">Contract: {treasuryCheck.contract}</div>
              </div>
            )}
          </div>
        )}

        {tab === 'structure' && structure && (
          <div className="space-y-4">
            <div className="bg-zinc-900/80 border border-amber-500/20 rounded-xl p-4">
              <h3 className="text-sm font-bold text-amber-400 mb-3">Holding — {structure.holding?.name}</h3>
              <div className="text-xs text-zinc-400 mb-2">Giurisdizione: {structure.holding?.jurisdiction} | Status: <span className="text-emerald-400">{structure.holding?.status}</span></div>
              <div className="space-y-2">
                {structure.subsidiaries?.map((s, i) => (
                  <div key={i} className="bg-zinc-800/50 rounded-lg p-3">
                    <div className="text-xs font-bold text-white">{s.name}</div>
                    <div className="text-[10px] text-zinc-500">{s.jurisdiction} — {s.function}</div>
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {s.licenses?.map((l, j) => (
                        <span key={j} className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">{l}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-zinc-900/80 border border-blue-500/20 rounded-xl p-4">
              <h3 className="text-sm font-bold text-blue-400 mb-2">Governance</h3>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>Board Seats: {structure.governance?.board_seats}</div>
                <div>Independent Directors: {structure.governance?.independent_directors}</div>
                <div>Audit Committee: {structure.governance?.audit_committee ? 'Active' : 'N/A'}</div>
                <div>Risk Committee: {structure.governance?.risk_committee ? 'Active' : 'N/A'}</div>
                <div>Standard: {structure.governance?.reporting_standard}</div>
                <div>External Auditor: {structure.governance?.external_auditor}</div>
              </div>
            </div>
          </div>
        )}

        {tab === 'rails' && bankingRails && (
          <div className="space-y-3">
            {Object.entries(bankingRails).filter(([k]) => !['cards','clearing_systems'].includes(k)).map(([key, val]) => (
              <div key={key} className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-white uppercase">{key.replace('_',' ')}</div>
                  <div className="text-[10px] text-zinc-500">{val.type} | {val.coverage || val.currency || ''}</div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                  val.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                }`}>{val.status}</span>
              </div>
            ))}
            <h3 className="text-xs font-bold text-zinc-400 mt-4">Payment Networks</h3>
            {bankingRails.cards && Object.entries(bankingRails.cards).map(([key, val]) => (
              <div key={key} className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-3 flex items-center justify-between">
                <div className="text-xs font-bold text-white uppercase">{key}</div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400">{val.status}</span>
              </div>
            ))}
            <h3 className="text-xs font-bold text-zinc-400 mt-4">Clearing Systems</h3>
            {bankingRails.clearing_systems && Object.entries(bankingRails.clearing_systems).map(([key, val]) => (
              <div key={key} className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-white uppercase">{key}</div>
                  <div className="text-[10px] text-zinc-500">{val.type} | {val.currency}</div>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400">{val.status}</span>
              </div>
            ))}
          </div>
        )}

        {tab === 'executions' && (
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-emerald-400 mb-2">Execution Logs Recenti</h3>
            {recentTxs.length === 0 && <div className="text-xs text-zinc-500">Nessuna transazione recente</div>}
            {recentTxs.map((tx, i) => (
              <div key={tx.id || i} className="bg-zinc-900/80 border border-zinc-700/30 rounded-xl p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                      tx.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                      tx.status === 'pending_execution' ? 'bg-orange-500/20 text-orange-400' :
                      tx.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                      'bg-zinc-500/20 text-zinc-400'
                    }`}>{tx.status}</span>
                    <span className="text-xs text-white font-mono">{tx.type}</span>
                  </div>
                  <span className="text-[10px] text-zinc-600">{tx.created_at?.slice(0, 19)}</span>
                </div>
                <div className="mt-1 text-[10px] text-zinc-400">
                  {tx.eur_value && <span>EUR {tx.eur_value} | </span>}
                  {tx.execution_mode && <span>Mode: {tx.execution_mode} | </span>}
                  {tx.delivery_tx_hash && (
                    <a href={`https://bscscan.com/tx/${tx.delivery_tx_hash}`} target="_blank" rel="noopener noreferrer"
                       className="text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-0.5">
                      TX: {tx.delivery_tx_hash.slice(0, 12)}... <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
