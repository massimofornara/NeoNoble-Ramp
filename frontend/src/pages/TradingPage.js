import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createChart } from 'lightweight-charts';
import {
  ArrowLeft, TrendingUp, TrendingDown, Loader2, RefreshCw,
  ArrowUpRight, ArrowDownRight, BarChart3, List
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function getAuthHeaders() {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` };
}

/* XHR-based fetch wrappers — prevent "body stream already read" errors */
function xhrFetchJson(url, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'GET', url, true);
    const hdrs = options.headers || getAuthHeaders();
    Object.entries(hdrs).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => {
      try { resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data: JSON.parse(xhr.responseText) }); }
      catch { resolve({ ok: false, status: xhr.status, data: {} }); }
    };
    xhr.onerror = () => resolve({ ok: false, status: 0, data: {} });
    xhr.send(options.body || null);
  });
}

const INTERVALS = [
  { id: '1m', label: '1m' }, { id: '5m', label: '5m' }, { id: '15m', label: '15m' },
  { id: '1h', label: '1H' }, { id: '4h', label: '4H' }, { id: '1d', label: '1D' },
];

// === CHART COMPONENT ===
function TradingChart({ pairId, interval }) {
  const chartRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 400,
      layout: { background: { color: '#0a0a0f' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: { borderColor: '#374151', timeVisible: true },
      localization: {
        locale: 'it-IT',
        dateFormat: 'dd/MM/yyyy',
      },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });
    const volumeSeries = chart.addHistogramSeries({
      color: '#6366f180', priceFormat: { type: 'volume' },
      priceScaleId: '', scaleMargins: { top: 0.85, bottom: 0 },
    });
    chartRef.current = { chart, candleSeries, volumeSeries };

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;
    (async () => {
      try {
        const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs/${pairId}/candles?interval=${interval}&limit=200`);
        const candles = (data.candles || []).map(c => ({
          time: c.time, open: c.open, high: c.high, low: c.low, close: c.close
        }));
        const volumes = (data.candles || []).map(c => ({
          time: c.time, value: c.volume,
          color: c.close >= c.open ? '#22c55e40' : '#ef444440'
        }));
        chartRef.current.candleSeries.setData(candles);
        chartRef.current.volumeSeries.setData(volumes);
      } catch (e) { console.error(e); }
    })();
  }, [pairId, interval]);

  return <div ref={containerRef} data-testid="trading-chart" />;
}

// === ORDER BOOK ===
function OrderBook({ pairId }) {
  const [orderbook, setOrderbook] = useState({ bids: [], asks: [] });

  const fetchOB = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs/${pairId}/orderbook?depth=12`);
      setOrderbook(data || { bids: [], asks: [] });
    } catch (e) { console.error(e); }
  }, [pairId]);

  useEffect(() => { fetchOB(); const iv = setInterval(fetchOB, 5000); return () => clearInterval(iv); }, [fetchOB]);

  const maxQty = Math.max(
    ...orderbook.bids.map(b => b.quantity),
    ...orderbook.asks.map(a => a.quantity), 1
  );

  return (
    <div data-testid="order-book" className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-800 flex items-center justify-between">
        <span className="text-white text-sm font-medium">Order Book</span>
      </div>
      <div className="text-xs">
        <div className="grid grid-cols-3 px-3 py-1 text-gray-500 border-b border-gray-800">
          <span>Prezzo</span><span className="text-right">Qty</span><span className="text-right">Totale</span>
        </div>
        {/* Asks (reversed) */}
        <div className="max-h-[180px] overflow-hidden flex flex-col-reverse">
          {orderbook.asks.slice(0, 10).map((a, i) => (
            <div key={`a-${i}`} className="grid grid-cols-3 px-3 py-0.5 relative">
              <div className="absolute inset-0 bg-red-500/5" style={{ width: `${(a.quantity / maxQty) * 100}%`, right: 0, left: 'auto' }} />
              <span className="text-red-400 relative z-10">{a.price.toFixed(4)}</span>
              <span className="text-gray-300 text-right relative z-10">{a.quantity.toFixed(4)}</span>
              <span className="text-gray-500 text-right relative z-10">{(a.price * a.quantity).toFixed(2)}</span>
            </div>
          ))}
        </div>
        {/* Spread */}
        <div className="px-3 py-1.5 border-y border-gray-700 bg-gray-800/50 text-center">
          <span className="text-white font-medium text-sm">
            {orderbook.bids[0] && orderbook.asks[0]
              ? ((orderbook.asks[0].price + orderbook.bids[0].price) / 2).toFixed(4)
              : '-'}
          </span>
        </div>
        {/* Bids */}
        <div className="max-h-[180px] overflow-hidden">
          {orderbook.bids.slice(0, 10).map((b, i) => (
            <div key={`b-${i}`} className="grid grid-cols-3 px-3 py-0.5 relative">
              <div className="absolute inset-0 bg-green-500/5" style={{ width: `${(b.quantity / maxQty) * 100}%`, right: 0, left: 'auto' }} />
              <span className="text-green-400 relative z-10">{b.price.toFixed(4)}</span>
              <span className="text-gray-300 text-right relative z-10">{b.quantity.toFixed(4)}</span>
              <span className="text-gray-500 text-right relative z-10">{(b.price * b.quantity).toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// === ORDER FORM ===
function OrderForm({ pairId, pair, onOrderPlaced }) {
  const [side, setSide] = useState('buy');
  const [orderType, setOrderType] = useState('market');
  const [price, setPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!quantity || parseFloat(quantity) <= 0) return;
    setLoading(true);
    setResult(null);
    try {
      const body = { pair_id: pairId, side, order_type: orderType, quantity: parseFloat(quantity) };
      if ((orderType === 'limit' || orderType === 'stop_limit') && price) body.price = parseFloat(price);
      if (['stop_loss', 'take_profit', 'stop_limit'].includes(orderType) && stopPrice) body.stop_price = parseFloat(stopPrice);
      const res = await xhrFetchJson(`${BACKEND_URL}/api/trading/orders`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body)
      });
      const data = res.data;
      if (!res.ok) throw new Error(data.detail || 'Order failed');
      setResult({ success: true, msg: data.message });
      setQuantity('');
      setPrice('');
      setStopPrice('');
      if (onOrderPlaced) onOrderPlaced();
    } catch (e) {
      setResult({ success: false, msg: e.message });
    } finally { setLoading(false); }
  };

  return (
    <div data-testid="order-form" className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex gap-1 mb-4">
        <button onClick={() => setSide('buy')} data-testid="order-buy-btn"
          className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors ${side === 'buy' ? 'bg-green-500 text-white' : 'bg-gray-800 text-gray-400'}`}>
          Buy
        </button>
        <button onClick={() => setSide('sell')} data-testid="order-sell-btn"
          className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors ${side === 'sell' ? 'bg-red-500 text-white' : 'bg-gray-800 text-gray-400'}`}>
          Sell
        </button>
      </div>

      <div className="flex gap-1 mb-4 flex-wrap">
        {['market', 'limit', 'stop_loss', 'take_profit'].map(t => (
          <button key={t} onClick={() => setOrderType(t)} data-testid={`order-type-${t}`}
            className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors min-w-[60px] ${orderType === t ? 'bg-purple-500/20 text-purple-400' : 'bg-gray-800 text-gray-400'}`}>
            {t === 'stop_loss' ? 'SL' : t === 'take_profit' ? 'TP' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        {['stop_loss', 'take_profit', 'stop_limit'].includes(orderType) && (
          <div>
            <label className="text-gray-400 text-xs mb-1 block">Trigger Price ({pair?.quote || 'EUR'})</label>
            <input type="number" step="any" value={stopPrice} onChange={(e) => setStopPrice(e.target.value)}
              placeholder="0.00" data-testid="order-stop-price-input" required
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-yellow-500 focus:outline-none" />
          </div>
        )}
        {(orderType === 'limit' || orderType === 'stop_limit') && (
          <div>
            <label className="text-gray-400 text-xs mb-1 block">Prezzo ({pair?.quote || 'EUR'})</label>
            <input type="number" step="any" value={price} onChange={(e) => setPrice(e.target.value)}
              placeholder="0.00" data-testid="order-price-input"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none" />
          </div>
        )}
        <div>
          <label className="text-gray-400 text-xs mb-1 block">Quantita' ({pair?.base || ''})</label>
          <input type="number" step="any" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)}
            placeholder="0.00" data-testid="order-quantity-input"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none" />
        </div>
        <button type="submit" disabled={loading || !quantity} data-testid="place-order-btn"
          className={`w-full py-2.5 rounded-lg font-bold text-sm transition-all ${
            side === 'buy' ? 'bg-green-500 hover:bg-green-600 text-white' : 'bg-red-500 hover:bg-red-600 text-white'
          } disabled:opacity-50`}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : `${side === 'buy' ? 'Buy' : 'Sell'} ${pair?.base || ''}`}
        </button>
      </form>

      {result && (
        <div className={`mt-3 p-2 rounded-lg text-xs ${result.success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
          {result.msg}
        </div>
      )}
    </div>
  );
}

// === RECENT TRADES ===
function RecentTrades({ pairId }) {
  const [trades, setTrades] = useState([]);

  const fetchTrades = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/trades/${pairId}?limit=20`);
      setTrades(data.trades || []);
    } catch (e) { console.error(e); }
  }, [pairId]);

  useEffect(() => { fetchTrades(); const iv = setInterval(fetchTrades, 5000); return () => clearInterval(iv); }, [fetchTrades]);

  return (
    <div data-testid="recent-trades" className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-800">
        <span className="text-white text-sm font-medium">Trade Recenti</span>
      </div>
      <div className="text-xs max-h-[200px] overflow-y-auto">
        <div className="grid grid-cols-3 px-3 py-1 text-gray-500 border-b border-gray-800">
          <span>Prezzo</span><span className="text-right">Qty</span><span className="text-right">Ora</span>
        </div>
        {trades.length === 0 ? (
          <div className="px-3 py-4 text-center text-gray-500">Nessun trade</div>
        ) : trades.map((t, i) => (
          <div key={i} className="grid grid-cols-3 px-3 py-0.5">
            <span className={t.taker_side === 'buy' ? 'text-green-400' : 'text-red-400'}>
              {t.price?.toFixed(4)}
            </span>
            <span className="text-gray-300 text-right">{t.quantity?.toFixed(4)}</span>
            <span className="text-gray-500 text-right">
              {t.created_at ? new Date(t.created_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// === MY ORDERS ===
function MyOrders({ pairId, refreshKey }) {
  const [orders, setOrders] = useState([]);

  const fetchOrders = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/orders/my?pair_id=${pairId}&limit=20`, { headers: getAuthHeaders() });
      setOrders(data.orders || []);
    } catch (e) { console.error(e); }
  }, [pairId]);

  useEffect(() => { fetchOrders(); }, [fetchOrders, refreshKey]);

  const handleCancel = async (orderId) => {
    try {
      await xhrFetchJson(`${BACKEND_URL}/api/trading/orders/cancel`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ order_id: orderId })
      });
      fetchOrders();
    } catch (e) { console.error(e); }
  };

  return (
    <div data-testid="my-orders" className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2 border-b border-gray-800">
        <span className="text-white text-sm font-medium">I Miei Ordini</span>
      </div>
      {orders.length === 0 ? (
        <div className="px-4 py-4 text-center text-gray-500 text-sm">Nessun ordine</div>
      ) : (
        <div className="overflow-x-auto text-xs">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="px-3 py-2 text-left text-gray-400">Tipo</th>
                <th className="px-3 py-2 text-left text-gray-400">Lato</th>
                <th className="px-3 py-2 text-right text-gray-400">Prezzo</th>
                <th className="px-3 py-2 text-right text-gray-400">Qty</th>
                <th className="px-3 py-2 text-right text-gray-400">Filled</th>
                <th className="px-3 py-2 text-center text-gray-400">Stato</th>
                <th className="px-3 py-2 text-right text-gray-400"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {orders.map(o => (
                <tr key={o.id}>
                  <td className="px-3 py-1.5 text-gray-300">{o.order_type}</td>
                  <td className="px-3 py-1.5">
                    <span className={o.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{o.side}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{o.price || 'Market'}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{o.quantity}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{o.filled_qty || 0}</td>
                  <td className="px-3 py-1.5 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      o.status === 'filled' ? 'bg-green-500/20 text-green-400' :
                      o.status === 'open' ? 'bg-blue-500/20 text-blue-400' :
                      o.status === 'cancelled' ? 'bg-gray-500/20 text-gray-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>{o.status}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {(o.status === 'open' || o.status === 'partially_filled' || o.status === 'pending_trigger') && (
                      <button onClick={() => handleCancel(o.id)} data-testid={`cancel-order-${o.id}`}
                        className="text-red-400 hover:text-red-300 text-xs">Cancel</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// === PAIR SELECTOR ===
function PairSelector({ pairs, selectedPair, onSelect, ticker }) {
  const [showAll, setShowAll] = useState(false);
  const selected = pairs.find(p => p.id === selectedPair);

  return (
    <div className="relative">
      <button onClick={() => setShowAll(!showAll)}
        data-testid="pair-selector"
        className="flex items-center gap-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-4 py-2 transition-colors">
        <div>
          <span className="text-white font-bold text-sm">{selected?.base}/{selected?.quote}</span>
          {ticker && (
            <span className={`ml-2 text-xs ${ticker.change_24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {ticker.change_24h >= 0 ? '+' : ''}{ticker.change_24h}%
            </span>
          )}
        </div>
        <List className="w-4 h-4 text-gray-400" />
      </button>
      {showAll && (
        <div className="absolute top-full mt-1 left-0 bg-gray-900 border border-gray-700 rounded-xl shadow-xl z-50 w-64 max-h-80 overflow-y-auto">
          {pairs.map(p => (
            <button key={p.id} onClick={() => { onSelect(p.id); setShowAll(false); }}
              data-testid={`pair-option-${p.id}`}
              className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-800 transition-colors flex items-center justify-between ${
                p.id === selectedPair ? 'bg-purple-500/10 text-purple-400' : 'text-gray-300'
              }`}>
              <span className="font-medium">{p.base}/{p.quote}</span>
              <span className="text-gray-500 text-xs">{p.base_name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


// === MAIN PAGE ===
export default function TradingPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const [pairs, setPairs] = useState([]);
  const [selectedPair, setSelectedPair] = useState(searchParams.get('pair') || 'BTC-EUR');
  const [interval, setChartInterval] = useState('1h');
  const [ticker, setTicker] = useState(null);
  const [loading, setLoading] = useState(true);
  const [orderRefresh, setOrderRefresh] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs`);
        setPairs(data.pairs || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const fetchTicker = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs/${selectedPair}/ticker`);
      setTicker(data || {});
    } catch (e) { console.error(e); }
  }, [selectedPair]);

  useEffect(() => { fetchTicker(); const iv = setInterval(fetchTicker, 10000); return () => clearInterval(iv); }, [fetchTicker]);

  const handlePairChange = (pairId) => {
    setSelectedPair(pairId);
    setSearchParams({ pair: pairId });
  };

  const currentPair = pairs.find(p => p.id === selectedPair);

  if (loading) {
    return <div className="min-h-screen bg-gray-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;
  }

  return (
    <div className="min-h-screen bg-gray-950" data-testid="trading-page">
      {/* Top Bar */}
      <div className="border-b border-gray-800 bg-gray-900/50">
        <div className="max-w-[1600px] mx-auto px-4 py-2 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-gray-800 rounded-lg">
            <ArrowLeft className="w-4 h-4 text-gray-400" />
          </button>
          <PairSelector pairs={pairs} selectedPair={selectedPair} onSelect={handlePairChange} ticker={ticker} />
          {ticker && (
            <div className="flex items-center gap-6 text-sm">
              <div>
                <span className="text-gray-400 text-xs">Ultimo</span>
                <div className="text-white font-bold">{ticker.last_price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
              </div>
              <div>
                <span className="text-gray-400 text-xs">24h Vol</span>
                <div className="text-gray-300">{ticker.volume_24h?.toFixed(2)}</div>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Bid</span>
                <div className="text-green-400">{ticker.best_bid?.toFixed(4)}</div>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Ask</span>
                <div className="text-red-400">{ticker.best_ask?.toFixed(4)}</div>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Spread</span>
                <div className="text-gray-300">{ticker.spread_pct?.toFixed(3)}%</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Layout */}
      <div className="max-w-[1600px] mx-auto px-4 py-3">
        <div className="grid grid-cols-12 gap-3">
          {/* Chart */}
          <div className="col-span-12 lg:col-span-8">
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="flex items-center gap-1 px-3 py-2 border-b border-gray-800">
                {INTERVALS.map(iv => (
                  <button key={iv.id} onClick={() => setChartInterval(iv.id)}
                    data-testid={`interval-${iv.id}`}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${interval === iv.id ? 'bg-purple-500/20 text-purple-400' : 'text-gray-400 hover:text-white'}`}>
                    {iv.label}
                  </button>
                ))}
              </div>
              <TradingChart pairId={selectedPair} interval={interval} />
            </div>

            {/* My Orders */}
            <div className="mt-3">
              <MyOrders pairId={selectedPair} refreshKey={orderRefresh} />
            </div>
          </div>

          {/* Right Panel */}
          <div className="col-span-12 lg:col-span-4 space-y-3">
            <OrderForm pairId={selectedPair} pair={currentPair} onOrderPlaced={() => setOrderRefresh(k => k + 1)} />
            <OrderBook pairId={selectedPair} />
            <RecentTrades pairId={selectedPair} />
          </div>
        </div>
      </div>
    </div>
  );
}
