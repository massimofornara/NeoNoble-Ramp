import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Activity, TrendingUp, TrendingDown, Wifi, WifiOff,
  RefreshCw, DollarSign, BarChart3, Layers, Zap
} from 'lucide-react';
import PriceAlerts from '../components/PriceAlerts';
import { useBrowserPush } from '../hooks/useBrowserPush';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function PortfolioTracker() {
  const navigate = useNavigate();
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [reconnecting, setReconnecting] = useState(false);
  const reconnectTimerRef = useRef(null);

  // Activate browser push notifications
  useBrowserPush();

  const connectWs = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const wsUrl = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    const ws = new WebSocket(`${wsUrl}/api/ws/portfolio/${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setReconnecting(false);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'portfolio_update') {
          setData(msg.data);
          setHistory(prev => {
            const next = [...prev, { total: msg.data.total_eur, ts: new Date() }];
            return next.length > 60 ? next.slice(-60) : next;
          });
        }
      } catch (e) { console.error('WS parse error', e); }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect
      if (!reconnectTimerRef.current) {
        setReconnecting(true);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connectWs();
        }, 3000);
      }
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [connectWs]);

  // Mini sparkline SVG
  const Sparkline = ({ points, color }) => {
    if (!points || points.length < 2) return null;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;
    const w = 120;
    const h = 36;
    const pathData = points
      .map((v, i) => `${(i / (points.length - 1)) * w},${h - ((v - min) / range) * h}`)
      .join(' L ');
    return (
      <svg width={w} height={h} className="overflow-visible">
        <polyline points={pathData} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  };

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-white" data-testid="portfolio-tracker-page">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-white/5 bg-[#0a0b0f]/90 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-14 gap-3">
          <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-white" data-testid="tracker-back-btn">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <Activity className="h-5 w-5 text-cyan-400" />
          <span className="font-semibold text-sm tracking-wide">PORTFOLIO TRACKER</span>
          <span className="text-[10px] text-cyan-400/70 font-mono ml-1">LIVE</span>
          <div className="ml-auto flex items-center gap-3">
            {connected ? (
              <span className="flex items-center gap-1 text-emerald-400 text-xs">
                <Wifi className="h-3 w-3" /> <span className="hidden sm:inline">Connesso</span>
                <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" /></span>
              </span>
            ) : reconnecting ? (
              <span className="flex items-center gap-1 text-amber-400 text-xs"><RefreshCw className="h-3 w-3 animate-spin" /> Riconnessione...</span>
            ) : (
              <span className="flex items-center gap-1 text-red-400 text-xs"><WifiOff className="h-3 w-3" /> Disconnesso</span>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {!data ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <RefreshCw className="h-8 w-8 animate-spin mb-3 text-cyan-400/50" />
            <p className="text-sm">In attesa dei dati dal WebSocket...</p>
          </div>
        ) : (
          <>
            {/* Main Value */}
            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4" data-testid="portfolio-total">
              <div>
                <p className="text-gray-500 text-xs uppercase tracking-wider mb-1">Valore Totale Portfolio</p>
                <h2 className="text-4xl sm:text-5xl font-bold tabular-nums tracking-tight">
                  {new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(data.total_eur)}
                </h2>
              </div>
              <div className={`flex items-center gap-1 text-sm font-medium ${data.total_24h_change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {data.total_24h_change_pct >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                {data.total_24h_change_pct >= 0 ? '+' : ''}{data.total_24h_change_pct.toFixed(2)}%
              </div>
              {data.margin_positions_count > 0 && (
                <div className="flex items-center gap-1 text-xs text-amber-400 bg-amber-400/10 px-2 py-1 rounded" data-testid="margin-badge">
                  <Zap className="h-3 w-3" /> {data.margin_positions_count} margin · PnL: {data.margin_unrealized_pnl >= 0 ? '+' : ''}{data.margin_unrealized_pnl.toFixed(2)}
                </div>
              )}
            </div>

            {/* Mini chart */}
            {history.length > 3 && (
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4" data-testid="portfolio-chart">
                <p className="text-gray-500 text-[10px] uppercase tracking-wider mb-2">Andamento sessione</p>
                <Sparkline
                  points={history.map(h => h.total)}
                  color={history[history.length - 1].total >= history[0].total ? '#34d399' : '#f87171'}
                />
              </div>
            )}

            {/* Asset Grid */}
            <div data-testid="assets-grid">
              <div className="flex items-center gap-2 mb-3">
                <Layers className="h-4 w-4 text-gray-600" />
                <span className="text-xs text-gray-500 uppercase tracking-wider">Asset ({data.assets.length})</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.assets.map((a, i) => (
                  <div key={a.asset}
                    className="bg-white/[0.03] border border-white/5 rounded-xl p-4 hover:border-white/10 transition-colors"
                    data-testid={`asset-card-${a.asset.toLowerCase()}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center text-xs font-bold text-white">
                          {a.asset.substring(0, 2)}
                        </div>
                        <div>
                          <p className="font-medium text-sm">{a.asset}</p>
                          <p className="text-gray-500 text-[10px] tabular-nums">{a.balance.toFixed(a.asset === 'EUR' || a.asset === 'USD' ? 2 : 6)}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium tabular-nums">{new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(a.eur_value)}</p>
                        <p className={`text-[10px] tabular-nums ${a.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {a.change_pct >= 0 ? '+' : ''}{a.change_pct.toFixed(3)}%
                        </p>
                      </div>
                    </div>
                    {/* Price bar */}
                    <div className="flex items-center justify-between text-[10px] text-gray-600 mt-1">
                      <span>Prezzo: {new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(a.price)}</span>
                      <span>{data.total_eur > 0 ? ((a.eur_value / data.total_eur) * 100).toFixed(1) : 0}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Price Alerts */}
            <PriceAlerts />

            {/* Live Prices Ticker */}
            <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4" data-testid="live-prices-ticker">
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 className="h-4 w-4 text-gray-600" />
                <span className="text-xs text-gray-500 uppercase tracking-wider">Tutti i prezzi live</span>
                <span className="text-[10px] text-cyan-400/50 font-mono ml-auto">{new Date(data.timestamp).toLocaleTimeString('it-IT')}</span>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-1">
                {Object.entries(data.prices)
                  .filter(([k]) => !['EUR', 'USDT', 'USDC'].includes(k))
                  .sort(([, a], [, b]) => b - a)
                  .map(([asset, price]) => (
                    <span key={asset} className="text-xs text-gray-400 tabular-nums">
                      <span className="text-gray-300 font-medium">{asset}</span>{' '}
                      {new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: price < 1 ? 4 : 2 }).format(price)}
                    </span>
                  ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
