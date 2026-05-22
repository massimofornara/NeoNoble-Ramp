import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Users, Gift, Copy, Check, Trophy, Share2,
  Loader2, ChevronRight, Sparkles
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

function xhrFetchJson(url, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'GET', url, true);
    const hdrs = options.headers || headers();
    Object.entries(hdrs).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => {
      try { resolve({ ok: xhr.status >= 200 && xhr.status < 300, data: JSON.parse(xhr.responseText) }); }
      catch { resolve({ ok: false, data: {} }); }
    };
    xhr.onerror = () => resolve({ ok: false, data: {} });
    xhr.send(options.body || null);
  });
}

export default function ReferralPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [viralStats, setViralStats] = useState(null);
  const [rewards, setRewards] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [code, setCode] = useState('');
  const [applyCode, setApplyCode] = useState('');
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState('');
  const [copied, setCopied] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [codeRes, statsRes, lbRes, viralRes, rewardsRes] = await Promise.all([
        xhrFetchJson(`${BACKEND_URL}/api/referral/code`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/referral/stats`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/referral/leaderboard`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/referral/viral-stats`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/growth/my-rewards`, { headers: headers() }),
      ]);
      setCode(codeRes.data?.code || '');
      setStats(statsRes.data);
      setLeaderboard(lbRes.data?.leaderboard || []);
      setViralStats(viralRes.data);
      setRewards(rewardsRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApply = async () => {
    if (!applyCode.trim()) return;
    setApplying(true);
    setApplyMsg('');
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}/api/referral/apply`, {
        method: 'POST', headers: headers(),
        body: JSON.stringify({ code: applyCode.trim() }),
      });
      if (res.ok) {
        setApplyMsg(res.data?.message || 'Codice applicato!');
        setApplyCode('');
        fetchData();
      } else {
        setApplyMsg(res.data?.detail || 'Errore');
      }
    } catch (e) { setApplyMsg('Errore di connessione'); }
    finally { setApplying(false); }
  };

  const shareLink = () => {
    const url = `${window.location.origin}/signup?ref=${code}`;
    if (navigator.share) {
      navigator.share({ title: 'NeoNoble Ramp', text: `Unisciti a NeoNoble Ramp con il mio codice referral ${code}!`, url });
    } else {
      navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="referral-page">
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg" data-testid="referral-back-btn">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <Users className="w-5 h-5 text-purple-400" />
          <h1 className="text-white font-bold text-lg">Programma Referral</h1>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Hero Card */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-purple-900/40 via-zinc-900 to-zinc-900 border border-purple-500/20 p-6">
          <div className="absolute top-0 right-0 w-64 h-64 bg-purple-500/5 rounded-full blur-3xl" />
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-5 h-5 text-amber-400" />
              <span className="text-amber-400 text-sm font-semibold">Guadagna NENO</span>
            </div>
            <h2 className="text-white text-2xl font-bold mb-2">Invita amici, guadagna bonus</h2>
            <p className="text-zinc-400 text-sm max-w-lg">Per ogni amico che si registra con il tuo codice, ricevi {stats?.referral_bonus || 0.001} NENO. Il tuo amico riceve {stats?.welcome_bonus || 0.0005} NENO di benvenuto.</p>
          </div>
        </div>

        {/* My Code + Apply Code */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h3 className="text-white font-medium text-sm mb-3">Il Tuo Codice Referral</h3>
            <div className="flex items-center gap-2 mb-4">
              <div className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 font-mono text-lg text-purple-400 tracking-widest text-center" data-testid="referral-code">
                {code}
              </div>
              <button onClick={copyCode} className="p-3 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors" data-testid="copy-code-btn">
                {copied ? <Check className="w-4 h-4 text-white" /> : <Copy className="w-4 h-4 text-white" />}
              </button>
            </div>
            <button onClick={shareLink} className="w-full flex items-center justify-center gap-2 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-300 text-sm transition-colors" data-testid="share-link-btn">
              <Share2 className="w-4 h-4" /> Condividi Link
            </button>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h3 className="text-white font-medium text-sm mb-3">Hai un codice referral?</h3>
            <div className="flex items-center gap-2 mb-3">
              <input
                value={applyCode}
                onChange={e => setApplyCode(e.target.value.toUpperCase())}
                placeholder="Inserisci codice"
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 text-white font-mono tracking-widest text-center placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                data-testid="apply-code-input"
              />
              <button
                onClick={handleApply}
                disabled={applying || !applyCode.trim()}
                className="px-4 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-colors"
                data-testid="apply-code-btn"
              >
                {applying ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Applica'}
              </button>
            </div>
            {applyMsg && <p className="text-sm text-center text-zinc-400">{applyMsg}</p>}
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Referral Totali', value: stats?.total_referrals || 0, icon: Users, color: 'text-purple-400' },
            { label: 'NENO Guadagnati', value: `${(stats?.total_bonus_earned || 0).toFixed(4)}`, icon: Gift, color: 'text-amber-400' },
            { label: 'Bonus Referrer', value: `${stats?.referral_bonus || 0.001} NENO`, icon: Sparkles, color: 'text-emerald-400' },
            { label: 'Bonus Trading', value: `${stats?.trade_bonus || 0.0005} NENO`, icon: Trophy, color: 'text-blue-400' },
          ].map(s => (
            <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid={`stat-${s.label.toLowerCase().replace(/ /g, '-')}`}>
              <div className="flex items-center gap-2 mb-2">
                <s.icon className={`w-4 h-4 ${s.color}`} />
                <span className="text-zinc-500 text-xs">{s.label}</span>
              </div>
              <div className={`text-lg font-bold font-mono ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </div>

        {/* My Referrals */}
        {stats?.referrals?.length > 0 && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-zinc-800">
              <span className="text-white font-medium text-sm">I Miei Referral ({stats.referrals.length})</span>
            </div>
            <div className="divide-y divide-zinc-800/50">
              {stats.referrals.map((r, i) => (
                <div key={r.id || i} className="px-4 py-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center text-purple-400 font-bold">{i + 1}</div>
                    <div>
                      <div className="text-zinc-300">{r.referred_user_id?.slice(0, 8)}...</div>
                      <div className="text-zinc-600">{r.created_at?.slice(0, 10)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${r.referrer_bonus_paid ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700 text-zinc-400'}`}>
                      {r.referrer_bonus_paid ? 'Bonus pagato' : 'Pending'}
                    </span>
                    {r.trade_bonus_paid && <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/20 text-blue-400">Trade bonus</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Viral Loop Stats */}
        {viralStats && (
          <div className="bg-gradient-to-br from-purple-900/20 to-zinc-900 border border-purple-500/20 rounded-xl p-5" data-testid="viral-stats">
            <h3 className="text-sm font-bold text-purple-400 mb-3 flex items-center gap-1.5">
              <Share2 className="w-4 h-4" /> Viral Loop — Il Tuo Network
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Volume Network</div>
                <div className="text-lg font-bold text-white font-mono">{viralStats.network_volume_eur?.toLocaleString()} EUR</div>
              </div>
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Trade Network</div>
                <div className="text-lg font-bold text-cyan-400">{viralStats.network_trades}</div>
              </div>
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Guadagno Proiettato</div>
                <div className="text-lg font-bold text-emerald-400 font-mono">{viralStats.projected_monthly_eur} EUR/mese</div>
              </div>
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Moltiplicatore Virale</div>
                <div className="text-lg font-bold text-amber-400">x{viralStats.viral_multiplier}</div>
              </div>
            </div>
            {viralStats.funnel && (
              <div className="mt-3 flex gap-2 text-[10px]">
                <span className="bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded-full">Invitati: {viralStats.funnel.invited}</span>
                <span className="bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-full">Attivi: {viralStats.funnel.active}</span>
                <span className="bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded-full">Spendenti: {viralStats.funnel.spending}</span>
              </div>
            )}
          </div>
        )}

        {/* Rewards Summary */}
        {rewards && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5" data-testid="rewards-summary">
            <h3 className="text-sm font-bold text-amber-400 mb-3">I Tuoi Premi Totali</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Cashback Totale</div>
                <div className="text-lg font-bold text-emerald-400 font-mono">{rewards.cashback?.total_earned || 0} EUR</div>
              </div>
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Referral Earnings</div>
                <div className="text-lg font-bold text-purple-400 font-mono">{rewards.referral_earnings?.total || 0}</div>
              </div>
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <div className="text-zinc-500">Tier</div>
                <div className="text-lg font-bold" style={{ color: rewards.tier?.color || '#a3a3a3' }}>{rewards.tier?.current_tier}</div>
                <div className="text-zinc-600">Cashback: {rewards.tier?.cashback_pct}</div>
              </div>
            </div>
            {rewards.tier?.next_tier && (
              <div className="mt-3">
                <div className="text-[10px] text-zinc-500 mb-1">
                  Prossimo tier: {rewards.tier.next_tier} (min {rewards.tier.next_tier_min?.toLocaleString()} EUR/mese)
                </div>
                <div className="w-full bg-zinc-800 rounded-full h-1.5">
                  <div className="bg-emerald-500 h-full rounded-full transition-all" style={{ width: `${Math.min(rewards.tier.progress_to_next, 100)}%` }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Leaderboard */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
            <Trophy className="w-4 h-4 text-amber-400" />
            <span className="text-white font-medium text-sm">Classifica Top Referrer</span>
          </div>
          <div className="divide-y divide-zinc-800/50">
            {leaderboard.length === 0 && <div className="py-8 text-center text-zinc-500 text-sm">Nessun referral ancora</div>}
            {leaderboard.map((l, i) => (
              <div key={i} className="px-4 py-3 flex items-center justify-between text-xs">
                <div className="flex items-center gap-3">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${i === 0 ? 'bg-amber-500/20 text-amber-400' : i === 1 ? 'bg-zinc-400/20 text-zinc-300' : i === 2 ? 'bg-orange-500/20 text-orange-400' : 'bg-zinc-800 text-zinc-500'}`}>
                    {i + 1}
                  </div>
                  <span className="text-zinc-300 font-mono">{l.username || l.code}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-zinc-500">{l.total_referrals} referral</span>
                  <span className="text-amber-400 font-mono font-bold">{l.total_bonus_earned?.toFixed(4)} NENO</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
