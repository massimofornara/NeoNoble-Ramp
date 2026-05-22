import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createChart } from 'lightweight-charts';
import {
  ArrowLeft, Loader2, TrendingUp, TrendingDown, PieChart,
  DollarSign, BarChart3, Calendar, ArrowUpRight, ArrowDownRight,
  Download
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

function PnLChart({ data }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !data || data.length === 0) return;
    let chart;
    try {
      chart = createChart(ref.current, {
        width: ref.current.clientWidth, height: 300,
        layout: { background: { color: '#09090b' }, textColor: '#71717a', fontSize: 11 },
        grid: { vertLines: { color: '#18181b' }, horzLines: { color: '#18181b' } },
        rightPriceScale: { borderColor: '#27272a' },
        timeScale: { borderColor: '#27272a', timeVisible: true },
      });
      const series = chart.addAreaSeries({
        topColor: '#7c3aed30', bottomColor: '#7c3aed05',
        lineColor: '#a78bfa', lineWidth: 2,
      });
      series.setData(data);
      chart.timeScale().fitContent();
    } catch(e) { console.error(e); }
    const handleResize = () => { if (ref.current && chart) try { chart.applyOptions({ width: ref.current.clientWidth }); } catch(e){} };
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); if (chart) try { chart.remove(); } catch(e){} };
  }, [data]);
  return <div ref={ref} />;
}

function AllocationChart({ allocations }) {
  if (!allocations || allocations.length === 0) return null;
  const total = allocations.reduce((s, a) => s + a.eur_value, 0);
  const colors = ['#a78bfa', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899', '#14b8a6', '#f97316'];

  let cumAngle = 0;
  const segments = allocations.map((a, i) => {
    const pct = total > 0 ? a.eur_value / total : 0;
    const startAngle = cumAngle;
    cumAngle += pct * 360;
    return { ...a, pct, startAngle, endAngle: cumAngle, color: colors[i % colors.length] };
  });

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 100 100" className="w-32 h-32">
        {segments.map((seg, i) => {
          const r = 40;
          const cx = 50, cy = 50;
          const start = (seg.startAngle - 90) * Math.PI / 180;
          const end = (seg.endAngle - 90) * Math.PI / 180;
          const largeArc = seg.pct > 0.5 ? 1 : 0;
          const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
          const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
          if (seg.pct < 0.001) return null;
          if (seg.pct > 0.999) return <circle key={i} cx={cx} cy={cy} r={r} fill={seg.color} />;
          return <path key={i} d={`M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc},1 ${x2},${y2} Z`} fill={seg.color} />;
        })}
        <circle cx="50" cy="50" r="25" fill="#09090b" />
      </svg>
      <div className="flex-1 space-y-1">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: seg.color }} />
            <span className="text-zinc-300 w-12">{seg.asset}</span>
            <span className="text-zinc-500 flex-1">{(seg.pct * 100).toFixed(1)}%</span>
            <span className="text-zinc-300 font-mono">{seg.eur_value.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PortfolioAnalytics() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [wallets, setWallets] = useState([]);
  const [totalEur, setTotalEur] = useState(0);
  const [trades, setTrades] = useState([]);
  const [marginPositions, setMarginPositions] = useState([]);
  const [pnlData, setPnlData] = useState([]);
  const [period, setPeriod] = useState('7d');
  const [riskMetrics, setRiskMetrics] = useState(null);
  const [diversification, setDiversification] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [wRes, tRes, mRes, riskRes, divRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/wallet/balances`, { headers: headers() }),
        fetch(`${BACKEND_URL}/api/trading/trades?limit=100`, { headers: headers() }),
        fetch(`${BACKEND_URL}/api/trading/margin/positions`, { headers: headers() }),
        fetch(`${BACKEND_URL}/api/analytics/advanced/portfolio-risk?days=30`, { headers: headers() }).catch(() => null),
        fetch(`${BACKEND_URL}/api/analytics/advanced/correlation?days=30`, { headers: headers() }).catch(() => null),
      ]);
      const [wData, tData, mData] = await Promise.all([wRes.json(), tRes.json(), mRes.json()]);
      setWallets(wData.wallets || []);
      setTotalEur(wData.total_eur_value || 0);
      setTrades(tData.trades || []);
      setMarginPositions(mData.positions || []);

      if (riskRes && riskRes.ok) setRiskMetrics(await riskRes.json());
      if (divRes && divRes.ok) setDiversification(await divRes.json());

      // Generate PnL curve from trades
      const sorted = (tData.trades || []).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      let cumPnl = 0;
      const pnl = sorted.map(t => {
        const pnlChange = t.pnl || (t.side === 'sell' ? t.quantity * t.price * 0.001 : -t.quantity * t.price * 0.001);
        cumPnl += pnlChange;
        const ts = Math.floor(new Date(t.created_at).getTime() / 1000);
        return { time: ts, value: cumPnl };
      });
      // Deduplicate by time
      const unique = {};
      pnl.forEach(p => { unique[p.time] = p; });
      setPnlData(Object.values(unique).sort((a, b) => a.time - b.time));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  const allocations = wallets.filter(w => w.eur_value > 0).sort((a, b) => b.eur_value - a.eur_value);
  const openMargin = marginPositions.filter(p => p.status === 'open');
  const closedMargin = marginPositions.filter(p => p.status === 'closed');
  const totalRealizedPnl = closedMargin.reduce((s, p) => s + (p.realized_pnl || 0), 0);
  const totalUnrealizedPnl = openMargin.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const winRate = closedMargin.length > 0 ? (closedMargin.filter(p => (p.realized_pnl || 0) > 0).length / closedMargin.length * 100).toFixed(1) : 0;

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="portfolio-analytics-page">
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <PieChart className="w-5 h-5 text-purple-400" />
          <h1 className="text-white font-bold text-lg">Portfolio Analytics</h1>
          <div className="ml-auto flex gap-2">
            <button onClick={() => { fetch(`${BACKEND_URL}/api/export/trades/csv`, { headers: headers() }).then(r => r.blob()).then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = 'trades.csv'; a.click(); }); }}
              className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-300 text-xs" data-testid="export-trades-btn">
              <Download className="w-3 h-3" /> Trade
            </button>
            <button onClick={() => { fetch(`${BACKEND_URL}/api/export/portfolio/csv`, { headers: headers() }).then(r => r.blob()).then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = 'portfolio.csv'; a.click(); }); }}
              className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-300 text-xs" data-testid="export-portfolio-btn">
              <Download className="w-3 h-3" /> Portfolio
            </button>
            <button onClick={() => { fetch(`${BACKEND_URL}/api/export/margin/csv`, { headers: headers() }).then(r => r.blob()).then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = 'margin.csv'; a.click(); }); }}
              className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-300 text-xs" data-testid="export-margin-btn">
              <Download className="w-3 h-3" /> Margin
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-4 space-y-4">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Valore Totale', value: totalEur.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' }), icon: DollarSign, color: 'text-white' },
            { label: 'PnL Realizzato', value: `${totalRealizedPnl >= 0 ? '+' : ''}${totalRealizedPnl.toFixed(2)} EUR`, icon: totalRealizedPnl >= 0 ? TrendingUp : TrendingDown, color: totalRealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400' },
            { label: 'PnL Non Realizzato', value: `${totalUnrealizedPnl >= 0 ? '+' : ''}${totalUnrealizedPnl.toFixed(2)} EUR`, icon: BarChart3, color: totalUnrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400' },
            { label: 'Win Rate', value: `${winRate}%`, icon: Calendar, color: 'text-purple-400' },
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

        {/* Advanced Risk Metrics */}
        {riskMetrics && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid="risk-metrics-section">
            <h3 className="text-white font-medium text-sm mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-purple-400" /> Metriche di Rischio Avanzate
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Sharpe Ratio', value: riskMetrics.sharpe_ratio != null ? riskMetrics.sharpe_ratio.toFixed(3) : 'N/A', color: riskMetrics.sharpe_ratio > 1 ? 'text-emerald-400' : riskMetrics.sharpe_ratio > 0 ? 'text-amber-400' : 'text-red-400' },
                { label: 'Sortino Ratio', value: riskMetrics.sortino_ratio != null ? riskMetrics.sortino_ratio.toFixed(3) : 'N/A', color: riskMetrics.sortino_ratio > 1 ? 'text-emerald-400' : 'text-amber-400' },
                { label: 'Max Drawdown', value: riskMetrics.max_drawdown ? `-${riskMetrics.max_drawdown.toFixed(2)} EUR` : '0', color: 'text-red-400' },
                { label: 'Volatilita Ann.', value: riskMetrics.volatility_annual ? riskMetrics.volatility_annual.toFixed(4) : '0', color: 'text-blue-400' },
                { label: 'Miglior Giorno', value: riskMetrics.best_day ? `+${riskMetrics.best_day.toFixed(2)}` : '0', color: 'text-emerald-400' },
                { label: 'Peggior Giorno', value: riskMetrics.worst_day ? `${riskMetrics.worst_day.toFixed(2)}` : '0', color: 'text-red-400' },
                { label: 'Giorni Positivi', value: riskMetrics.win_days || 0, color: 'text-emerald-400' },
                { label: 'Giorni Negativi', value: riskMetrics.loss_days || 0, color: 'text-red-400' },
              ].map(m => (
                <div key={m.label} className="bg-zinc-800/50 rounded-lg p-3" data-testid={`risk-${m.label.toLowerCase().replace(/ /g, '-')}`}>
                  <div className="text-zinc-500 text-[10px] mb-1">{m.label}</div>
                  <div className={`text-sm font-mono font-bold ${m.color}`}>{m.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Diversification Score */}
        {diversification && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid="diversification-section">
            <h3 className="text-white font-medium text-sm mb-3">Score Diversificazione</h3>
            <div className="flex items-center gap-4">
              <div className="relative w-20 h-20">
                <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                  <circle cx="50" cy="50" r="40" fill="none" stroke="#27272a" strokeWidth="8" />
                  <circle cx="50" cy="50" r="40" fill="none" stroke="#a78bfa" strokeWidth="8"
                    strokeDasharray={`${diversification.diversification_score * 2.51} 251`} strokeLinecap="round" />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center text-white font-bold text-sm">{diversification.diversification_score}%</div>
              </div>
              <div className="flex-1 space-y-1">
                <div className="text-zinc-400 text-xs">{diversification.asset_count} asset in portfolio</div>
                <div className="text-zinc-400 text-xs">HHI Index: {diversification.hhi_index}</div>
                {diversification.breakdown?.slice(0, 5).map(b => (
                  <div key={b.asset} className="flex items-center gap-2 text-xs">
                    <span className="text-zinc-300 w-12">{b.asset}</span>
                    <div className="flex-1 bg-zinc-800 rounded-full h-1.5">
                      <div className="h-full bg-purple-500 rounded-full" style={{ width: `${Math.min(b.weight, 100)}%` }} />
                    </div>
                    <span className="text-zinc-500 w-12 text-right">{b.weight}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* PnL Chart */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
            <span className="text-white font-medium text-sm">Curva PnL</span>
            <div className="flex gap-1">
              {['7d', '30d', '90d', 'all'].map(p => (
                <button key={p} onClick={() => setPeriod(p)}
                  className={`px-2.5 py-1 rounded text-xs font-medium ${period === p ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-500 hover:text-zinc-300'}`}>{p}</button>
              ))}
            </div>
          </div>
          {pnlData.length > 0 ? <PnLChart data={pnlData} /> : <div className="py-12 text-center text-zinc-500 text-sm">Nessun dato di trading disponibile</div>}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Allocation */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <h3 className="text-white font-medium text-sm mb-4">Allocazione Portfolio</h3>
            {allocations.length > 0 ? (
              <AllocationChart allocations={allocations} />
            ) : (
              <div className="text-center text-zinc-500 text-sm py-6">Nessun asset in portfolio</div>
            )}
          </div>

          {/* Recent Trades */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-zinc-800">
              <span className="text-white font-medium text-sm">Ultimi Trade ({trades.length})</span>
            </div>
            <div className="max-h-64 overflow-y-auto divide-y divide-zinc-800/50">
              {trades.slice(0, 20).map(t => (
                <div key={t.id} className="px-4 py-2 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    {t.side === 'buy' ? <ArrowDownRight className="w-3.5 h-3.5 text-emerald-400" /> : <ArrowUpRight className="w-3.5 h-3.5 text-red-400" />}
                    <span className="text-zinc-300">{t.pair_id || t.symbol}</span>
                    <span className={`font-bold ${t.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}`}>{t.side?.toUpperCase()}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-zinc-300 font-mono">{t.quantity} @ {t.price}</div>
                  </div>
                </div>
              ))}
              {trades.length === 0 && <div className="py-8 text-center text-zinc-500 text-sm">Nessun trade</div>}
            </div>
          </div>
        </div>

        {/* Open Margin Positions */}
        {openMargin.length > 0 && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-zinc-800">
              <span className="text-white font-medium text-sm">Posizioni Margin Aperte ({openMargin.length})</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-zinc-800/50">
                  <tr>
                    <th className="px-3 py-2 text-left text-zinc-500">Coppia</th>
                    <th className="px-3 py-2 text-left text-zinc-500">Lato</th>
                    <th className="px-3 py-2 text-right text-zinc-500">Leva</th>
                    <th className="px-3 py-2 text-right text-zinc-500">Entry</th>
                    <th className="px-3 py-2 text-right text-zinc-500">PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {openMargin.map(p => (
                    <tr key={p.id}>
                      <td className="px-3 py-2 text-zinc-200">{p.pair_id}</td>
                      <td className="px-3 py-2"><span className={p.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>{p.side?.toUpperCase()}</span></td>
                      <td className="px-3 py-2 text-right text-purple-400">{p.leverage}x</td>
                      <td className="px-3 py-2 text-right text-zinc-300 font-mono">{p.entry_price}</td>
                      <td className="px-3 py-2 text-right font-mono font-bold">
                        <span className={(p.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {(p.unrealized_pnl || 0) >= 0 ? '+' : ''}{(p.unrealized_pnl || 0).toFixed(2)}
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
    </div>
  );
}
