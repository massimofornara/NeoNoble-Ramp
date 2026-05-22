import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createChart } from 'lightweight-charts';
import {
  ArrowLeft, Loader2, TrendingUp, TrendingDown, X,
  AlertTriangle, Settings2, BarChart3, LineChart, CandlestickChart,
  Activity, Layers, Search, Eye, EyeOff
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

/* XHR-based fetch wrappers — prevent "body stream already read" errors */
function xhrFetchJson(url, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'GET', url, true);
    const hdrs = options.headers || headers();
    Object.entries(hdrs).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => {
      try { resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data: JSON.parse(xhr.responseText) }); }
      catch { resolve({ ok: false, status: xhr.status, data: {} }); }
    };
    xhr.onerror = () => resolve({ ok: false, status: 0, data: {} });
    xhr.send(options.body || null);
  });
}

const PAIRS = ['BTC-EUR','ETH-EUR','BNB-EUR','NENO-EUR','SOL-EUR','XRP-EUR','ADA-EUR','DOGE-EUR'];
const INTERVALS = [
  { id: '1m', label: '1m' }, { id: '5m', label: '5m' }, { id: '15m', label: '15m' },
  { id: '1h', label: '1H' }, { id: '4h', label: '4H' }, { id: '1d', label: '1D' },
];
const CHART_TYPES = [
  { id: 'candlestick', label: 'Candele', icon: CandlestickChart },
  { id: 'line', label: 'Linea', icon: LineChart },
  { id: 'area', label: 'Area', icon: Activity },
  { id: 'bar', label: 'Barre', icon: BarChart3 },
];

const INDICATOR_DEFS = [
  { id: 'sma_20', name: 'SMA 20', group: 'Overlay', color: '#f59e0b', period: 20, type: 'sma' },
  { id: 'sma_50', name: 'SMA 50', group: 'Overlay', color: '#3b82f6', period: 50, type: 'sma' },
  { id: 'sma_200', name: 'SMA 200', group: 'Overlay', color: '#ef4444', period: 200, type: 'sma' },
  { id: 'ema_12', name: 'EMA 12', group: 'Overlay', color: '#10b981', period: 12, type: 'ema' },
  { id: 'ema_26', name: 'EMA 26', group: 'Overlay', color: '#8b5cf6', period: 26, type: 'ema' },
  { id: 'ema_50', name: 'EMA 50', group: 'Overlay', color: '#ec4899', period: 50, type: 'ema' },
  { id: 'bb_20', name: 'Bollinger Bands (20)', group: 'Overlay', color: '#6366f1', period: 20, type: 'bb' },
  { id: 'rsi_14', name: 'RSI (14)', group: 'Oscillatore', color: '#f97316', period: 14, type: 'rsi' },
  { id: 'macd', name: 'MACD (12,26,9)', group: 'Oscillatore', color: '#22d3ee', type: 'macd' },
  { id: 'volume', name: 'Volume', group: 'Volume', color: '#6366f1', type: 'volume' },
];

// ---- Indicator calculations ----
function calcSMA(data, period) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(null); continue; }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
    result.push({ time: data[i].time, value: +(sum / period).toFixed(6) });
  }
  return result.filter(Boolean);
}

function calcEMA(data, period) {
  const result = [];
  const k = 2 / (period + 1);
  let prevEma = null;
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(null); continue; }
    if (prevEma === null) {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
      prevEma = sum / period;
    } else {
      prevEma = data[i].close * k + prevEma * (1 - k);
    }
    result.push({ time: data[i].time, value: +prevEma.toFixed(6) });
  }
  return result.filter(Boolean);
}

function calcRSI(data, period) {
  const result = [];
  const gains = []; const losses = [];
  for (let i = 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close;
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? -change : 0);
  }
  let avgGain = 0, avgLoss = 0;
  for (let i = 0; i < period; i++) { avgGain += gains[i] || 0; avgLoss += losses[i] || 0; }
  avgGain /= period; avgLoss /= period;
  for (let i = 0; i < data.length; i++) {
    if (i < period) { result.push(null); continue; }
    if (i > period) {
      avgGain = (avgGain * (period - 1) + (gains[i - 1] || 0)) / period;
      avgLoss = (avgLoss * (period - 1) + (losses[i - 1] || 0)) / period;
    }
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    result.push({ time: data[i].time, value: +rsi.toFixed(2) });
  }
  return result.filter(Boolean);
}

function calcMACD(data) {
  const ema12 = calcEMA(data, 12);
  const ema26 = calcEMA(data, 26);
  const macdLine = []; const signalLine = []; const histogram = [];
  const emaMap12 = {}; const emaMap26 = {};
  ema12.forEach(e => { emaMap12[e.time] = e.value; });
  ema26.forEach(e => { emaMap26[e.time] = e.value; });
  const rawMacd = [];
  for (const d of data) {
    if (emaMap12[d.time] !== undefined && emaMap26[d.time] !== undefined) {
      rawMacd.push({ time: d.time, value: +(emaMap12[d.time] - emaMap26[d.time]).toFixed(6) });
    }
  }
  macdLine.push(...rawMacd);
  // Signal: 9-period EMA of MACD
  const k = 2 / 10; let prevSig = null;
  for (let i = 0; i < rawMacd.length; i++) {
    if (i < 8) { signalLine.push(null); continue; }
    if (prevSig === null) {
      let s = 0; for (let j = i - 8; j <= i; j++) s += rawMacd[j].value;
      prevSig = s / 9;
    } else {
      prevSig = rawMacd[i].value * k + prevSig * (1 - k);
    }
    signalLine.push({ time: rawMacd[i].time, value: +prevSig.toFixed(6) });
    histogram.push({ time: rawMacd[i].time, value: +(rawMacd[i].value - prevSig).toFixed(6), color: rawMacd[i].value - prevSig >= 0 ? '#22c55e80' : '#ef444480' });
  }
  return { macdLine, signalLine: signalLine.filter(Boolean), histogram };
}

function calcBB(data, period) {
  const sma = calcSMA(data, period);
  const smaMap = {};
  sma.forEach(s => { smaMap[s.time] = s.value; });
  const upper = []; const lower = [];
  for (let i = period - 1; i < data.length; i++) {
    const t = data[i].time;
    const mean = smaMap[t];
    if (mean === undefined) continue;
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) sumSq += Math.pow(data[j].close - mean, 2);
    const std = Math.sqrt(sumSq / period);
    upper.push({ time: t, value: +(mean + 2 * std).toFixed(6) });
    lower.push({ time: t, value: +(mean - 2 * std).toFixed(6) });
  }
  return { middle: sma, upper, lower };
}

// ==== PROFESSIONAL CHART COMPONENT ====
function ProChart({ pair, interval, chartType, activeIndicators, candles }) {
  const containerRef = useRef(null);
  const chartObjRef = useRef(null);
  const disposedRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || !candles || candles.length === 0) return;
    disposedRef.current = false;

    // Clean up previous chart
    if (chartObjRef.current) {
      try { chartObjRef.current.remove(); } catch(e) {}
      chartObjRef.current = null;
    }

    const container = containerRef.current;
    const hasOscillator = activeIndicators.some(id => {
      const def = INDICATOR_DEFS.find(d => d.id === id);
      return def && def.group === 'Oscillatore';
    });
    const chartHeight = hasOscillator ? 340 : 420;

    let chart;
    try {
      chart = createChart(container, {
        width: container.clientWidth,
        height: chartHeight,
        layout: { background: { color: '#09090b' }, textColor: '#71717a', fontFamily: "'Inter', sans-serif", fontSize: 11 },
        grid: { vertLines: { color: '#18181b' }, horzLines: { color: '#18181b' } },
        crosshair: { mode: 0, vertLine: { color: '#a78bfa40', labelBackgroundColor: '#7c3aed' }, horzLine: { color: '#a78bfa40', labelBackgroundColor: '#7c3aed' } },
        rightPriceScale: { borderColor: '#27272a', scaleMargins: { top: 0.1, bottom: 0.15 } },
        timeScale: { borderColor: '#27272a', timeVisible: true, secondsVisible: false },
        localization: { locale: 'it-IT' },
      });
    } catch (e) { console.error('Chart creation failed', e); return; }

    if (disposedRef.current) { try { chart.remove(); } catch(e) {} return; }
    chartObjRef.current = chart;

    // Main series
    try {
      if (chartType === 'candlestick') {
        const mainSeries = chart.addCandlestickSeries({
          upColor: '#22c55e', downColor: '#ef4444',
          borderUpColor: '#22c55e', borderDownColor: '#ef4444',
          wickUpColor: '#22c55e80', wickDownColor: '#ef444480',
        });
        mainSeries.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));
      } else if (chartType === 'line') {
        const mainSeries = chart.addLineSeries({ color: '#a78bfa', lineWidth: 2 });
        mainSeries.setData(candles.map(c => ({ time: c.time, value: c.close })));
      } else if (chartType === 'area') {
        const mainSeries = chart.addAreaSeries({
          topColor: '#7c3aed40', bottomColor: '#7c3aed05',
          lineColor: '#a78bfa', lineWidth: 2,
        });
        mainSeries.setData(candles.map(c => ({ time: c.time, value: c.close })));
      } else if (chartType === 'bar') {
        const mainSeries = chart.addBarSeries({ upColor: '#22c55e', downColor: '#ef4444' });
        mainSeries.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));
      }

      // Volume
      if (activeIndicators.includes('volume')) {
        const volSeries = chart.addHistogramSeries({
          color: '#6366f180', priceFormat: { type: 'volume' },
          priceScaleId: 'vol', scaleMargins: { top: 0.85, bottom: 0 },
        });
        chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
        volSeries.setData(candles.map(c => ({
          time: c.time, value: c.volume,
          color: c.close >= c.open ? '#22c55e30' : '#ef444430'
        })));
      }

      // Overlay indicators
      for (const indId of activeIndicators) {
        const def = INDICATOR_DEFS.find(d => d.id === indId);
        if (!def || def.group !== 'Overlay') continue;
        if (def.type === 'sma') {
          const s = chart.addLineSeries({ color: def.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
          s.setData(calcSMA(candles, def.period));
        } else if (def.type === 'ema') {
          const s = chart.addLineSeries({ color: def.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
          s.setData(calcEMA(candles, def.period));
        } else if (def.type === 'bb') {
          const bb = calcBB(candles, def.period);
          const sU = chart.addLineSeries({ color: def.color + '80', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
          sU.setData(bb.upper);
          const sM = chart.addLineSeries({ color: def.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
          sM.setData(bb.middle);
          const sL = chart.addLineSeries({ color: def.color + '80', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
          sL.setData(bb.lower);
        }
      }

      chart.timeScale().fitContent();
    } catch (e) { console.error('Chart series error', e); }

    const handleResize = () => {
      if (!disposedRef.current && container) {
        try { chart.applyOptions({ width: container.clientWidth }); } catch(e) {}
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      disposedRef.current = true;
      window.removeEventListener('resize', handleResize);
      try { chart.remove(); } catch(e) {}
      chartObjRef.current = null;
    };
  }, [candles, chartType, activeIndicators, pair, interval]);

  return <div ref={containerRef} data-testid="pro-chart" className="w-full" />;
}

// ==== OSCILLATOR PANEL (RSI, MACD) ====
function OscillatorPanel({ candles, activeIndicators }) {
  const rsiRef = useRef(null);
  const macdRef = useRef(null);
  const chartRefs = useRef({});
  const disposedRef = useRef(false);

  const showRSI = activeIndicators.includes('rsi_14');
  const showMACD = activeIndicators.includes('macd');

  useEffect(() => {
    if (!candles || candles.length === 0) return;
    disposedRef.current = false;

    Object.values(chartRefs.current).forEach(c => { try { c.remove(); } catch(e){} });
    chartRefs.current = {};

    if (showRSI && rsiRef.current) {
      try {
        const ch = createChart(rsiRef.current, {
          width: rsiRef.current.clientWidth, height: 120,
          layout: { background: { color: '#09090b' }, textColor: '#71717a', fontSize: 10 },
          grid: { vertLines: { color: '#18181b' }, horzLines: { color: '#18181b' } },
          rightPriceScale: { borderColor: '#27272a', scaleMargins: { top: 0.05, bottom: 0.05 } },
          timeScale: { visible: false },
          crosshair: { mode: 0 },
        });
        if (disposedRef.current) { try { ch.remove(); } catch(e) {} return; }
        const rsiData = calcRSI(candles, 14);
        const s = ch.addLineSeries({ color: '#f97316', lineWidth: 1.5, priceLineVisible: false });
        s.setData(rsiData);
        const ob = ch.addLineSeries({ color: '#ef444440', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        ob.setData(rsiData.map(d => ({ time: d.time, value: 70 })));
        const os = ch.addLineSeries({ color: '#22c55e40', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        os.setData(rsiData.map(d => ({ time: d.time, value: 30 })));
        ch.timeScale().fitContent();
        chartRefs.current.rsi = ch;
      } catch (e) { console.error('RSI chart error', e); }
    }

    if (showMACD && macdRef.current) {
      try {
        const ch = createChart(macdRef.current, {
          width: macdRef.current.clientWidth, height: 120,
          layout: { background: { color: '#09090b' }, textColor: '#71717a', fontSize: 10 },
          grid: { vertLines: { color: '#18181b' }, horzLines: { color: '#18181b' } },
          rightPriceScale: { borderColor: '#27272a', scaleMargins: { top: 0.05, bottom: 0.05 } },
          timeScale: { visible: false },
          crosshair: { mode: 0 },
        });
        if (disposedRef.current) { try { ch.remove(); } catch(e) {} return; }
        const macdData = calcMACD(candles);
        const sLine = ch.addLineSeries({ color: '#22d3ee', lineWidth: 1.5, priceLineVisible: false });
        sLine.setData(macdData.macdLine);
        const sSig = ch.addLineSeries({ color: '#f472b6', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        sSig.setData(macdData.signalLine);
        const sHist = ch.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
        sHist.setData(macdData.histogram);
        ch.timeScale().fitContent();
        chartRefs.current.macd = ch;
      } catch (e) { console.error('MACD chart error', e); }
    }

    const handleResize = () => {
      if (disposedRef.current) return;
      if (showRSI && rsiRef.current && chartRefs.current.rsi) { try { chartRefs.current.rsi.applyOptions({ width: rsiRef.current.clientWidth }); } catch(e) {} }
      if (showMACD && macdRef.current && chartRefs.current.macd) { try { chartRefs.current.macd.applyOptions({ width: macdRef.current.clientWidth }); } catch(e) {} }
    };
    window.addEventListener('resize', handleResize);
    return () => {
      disposedRef.current = true;
      window.removeEventListener('resize', handleResize);
      Object.values(chartRefs.current).forEach(c => { try { c.remove(); } catch(e){} });
      chartRefs.current = {};
    };
  }, [candles, showRSI, showMACD]);

  if (!showRSI && !showMACD) return null;

  return (
    <div className="space-y-0" data-testid="oscillator-panel">
      {showRSI && (
        <div className="border-t border-zinc-800">
          <div className="px-3 py-1 text-xs text-orange-400 font-medium bg-zinc-900/50 flex items-center gap-1">
            <Activity className="w-3 h-3" /> RSI (14)
          </div>
          <div ref={rsiRef} />
        </div>
      )}
      {showMACD && (
        <div className="border-t border-zinc-800">
          <div className="px-3 py-1 text-xs text-cyan-400 font-medium bg-zinc-900/50 flex items-center gap-1">
            <Layers className="w-3 h-3" /> MACD (12,26,9)
          </div>
          <div ref={macdRef} />
        </div>
      )}
    </div>
  );
}

// ==== INDICATOR SELECTOR ====
function IndicatorSelector({ activeIndicators, onToggle, onClose }) {
  const [search, setSearch] = useState('');
  const groups = {};
  INDICATOR_DEFS.forEach(d => {
    if (!groups[d.group]) groups[d.group] = [];
    groups[d.group].push(d);
  });
  const filtered = search ? INDICATOR_DEFS.filter(d => d.name.toLowerCase().includes(search.toLowerCase())) : null;

  return (
    <div className="absolute top-full right-0 mt-1 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 w-72 max-h-96 overflow-y-auto" data-testid="indicator-selector">
      <div className="p-2 border-b border-zinc-800 flex items-center gap-2">
        <Search className="w-3.5 h-3.5 text-zinc-500" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cerca indicatore..."
          className="flex-1 bg-transparent text-white text-xs outline-none placeholder:text-zinc-600" autoFocus />
        <button onClick={onClose}><X className="w-3.5 h-3.5 text-zinc-500 hover:text-white" /></button>
      </div>
      {filtered ? (
        <div className="p-1">
          {filtered.map(d => (
            <button key={d.id} onClick={() => onToggle(d.id)} data-testid={`ind-${d.id}`}
              className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-zinc-800 transition-colors">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                <span className="text-zinc-200">{d.name}</span>
              </div>
              {activeIndicators.includes(d.id) ? <Eye className="w-3.5 h-3.5 text-purple-400" /> : <EyeOff className="w-3.5 h-3.5 text-zinc-600" />}
            </button>
          ))}
        </div>
      ) : (
        Object.entries(groups).map(([gName, items]) => (
          <div key={gName}>
            <div className="px-3 py-1.5 text-[10px] text-zinc-500 uppercase tracking-wider font-semibold bg-zinc-800/50">{gName}</div>
            {items.map(d => (
              <button key={d.id} onClick={() => onToggle(d.id)} data-testid={`ind-${d.id}`}
                className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-zinc-800 transition-colors">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                  <span className="text-zinc-200">{d.name}</span>
                </div>
                {activeIndicators.includes(d.id) ? <Eye className="w-3.5 h-3.5 text-purple-400" /> : <EyeOff className="w-3.5 h-3.5 text-zinc-600" />}
              </button>
            ))}
          </div>
        ))
      )}
    </div>
  );
}

// ==== MAIN PAGE ====
export default function MarginTrading() {
  const navigate = useNavigate();
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);

  // Chart state
  const [pair, setPair] = useState('BTC-EUR');
  const [interval, setInterval] = useState('1h');
  const [chartType, setChartType] = useState('candlestick');
  const [activeIndicators, setActiveIndicators] = useState(['volume']);
  const [showIndicators, setShowIndicators] = useState(false);
  const [candles, setCandles] = useState([]);
  const [ticker, setTicker] = useState(null);
  const [candleLoading, setCandleLoading] = useState(false);

  // Open position form
  const [showOpen, setShowOpen] = useState(false);
  const [side, setSide] = useState('buy');
  const [qty, setQty] = useState('');
  const [leverage, setLeverage] = useState('5');
  const [sl, setSl] = useState('');
  const [tp, setTp] = useState('');
  const [opening, setOpening] = useState(false);

  // Deposit/withdraw form
  const [showDeposit, setShowDeposit] = useState(false);
  const [depAmount, setDepAmount] = useState('');
  const [depAction, setDepAction] = useState('deposit');

  // Tab state
  const [bottomTab, setBottomTab] = useState('positions');

  // Advanced orders state
  const [advOrders, setAdvOrders] = useState([]);
  const [showLimitOrder, setShowLimitOrder] = useState(false);
  const [limitPrice, setLimitPrice] = useState('');
  const [orderType, setOrderType] = useState('limit');

  const fetchData = useCallback(async () => {
    try {
      const [aData, pData, oData] = await Promise.all([
        xhrFetchJson(`${BACKEND_URL}/api/trading/margin/account`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/trading/margin/positions`, { headers: headers() }),
        xhrFetchJson(`${BACKEND_URL}/api/trading/orders/active`, { headers: headers() }),
      ]);
      setAccount(aData.data?.account);
      setPositions(pData.data?.positions || []);
      setAdvOrders(oData.data?.orders || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const fetchCandles = useCallback(async () => {
    setCandleLoading(true);
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs/${pair}/candles?interval=${interval}&limit=300`);
      setCandles(data?.candles || []);
    } catch (e) { console.error(e); }
    finally { setCandleLoading(false); }
  }, [pair, interval]);

  const fetchTicker = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/trading/pairs/${pair}/ticker`);
      setTicker(data || {});
    } catch (e) { console.error(e); }
  }, [pair]);

  useEffect(() => { fetchData(); const iv = window.setInterval(fetchData, 15000); return () => clearInterval(iv); }, [fetchData]);
  useEffect(() => { fetchCandles(); }, [fetchCandles]);
  useEffect(() => { fetchTicker(); const iv = window.setInterval(fetchTicker, 10000); return () => clearInterval(iv); }, [fetchTicker]);

  const toggleIndicator = (id) => {
    setActiveIndicators(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  };

  const createAccount = async () => {
    try {
      await xhrFetchJson(`${BACKEND_URL}/api/trading/margin/account`, { method: 'POST', headers: headers(), body: JSON.stringify({ leverage: 20 }) });
      fetchData();
    } catch (e) { console.error(e); }
  };

  const handleDeposit = async () => {
    setResult(null);
    const url = depAction === 'deposit' ? '/api/trading/margin/deposit' : '/api/trading/margin/withdraw';
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}${url}`, { method: 'POST', headers: headers(), body: JSON.stringify({ asset: 'EUR', amount: parseFloat(depAmount) }) });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore');
      setResult({ ok: true, msg: res.data?.message }); setShowDeposit(false); setDepAmount(''); fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handleOpen = async () => {
    setOpening(true); setResult(null);
    try {
      const body = { pair_id: pair, side, quantity: parseFloat(qty), leverage: parseFloat(leverage) };
      if (sl) body.stop_loss = parseFloat(sl);
      if (tp) body.take_profit = parseFloat(tp);
      const res = await xhrFetchJson(`${BACKEND_URL}/api/trading/margin/open`, { method: 'POST', headers: headers(), body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore');
      setResult({ ok: true, msg: res.data?.message }); setShowOpen(false); setQty(''); setSl(''); setTp(''); fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setOpening(false); }
  };

  const handleClose = async (posId) => {
    setResult(null);
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}/api/trading/margin/close`, { method: 'POST', headers: headers(), body: JSON.stringify({ position_id: posId }) });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore');
      setResult({ ok: true, msg: res.data?.message }); fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  const handlePlaceAdvancedOrder = async () => {
    setOpening(true); setResult(null);
    try {
      let url, body;
      if (orderType === 'limit') {
        url = `${BACKEND_URL}/api/trading/orders/limit`;
        body = { pair_id: pair, side, quantity: parseFloat(qty), limit_price: parseFloat(limitPrice), time_in_force: 'GTC' };
      } else if (orderType === 'stop') {
        url = `${BACKEND_URL}/api/trading/orders/stop`;
        body = { pair_id: pair, side, quantity: parseFloat(qty), stop_price: parseFloat(limitPrice) };
      } else if (orderType === 'trailing') {
        url = `${BACKEND_URL}/api/trading/orders/trailing-stop`;
        body = { pair_id: pair, side, quantity: parseFloat(qty), trail_percent: parseFloat(limitPrice) };
      }
      const res = await xhrFetchJson(url, { method: 'POST', headers: headers(), body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore');
      setResult({ ok: true, msg: res.data?.message }); setShowLimitOrder(false); setLimitPrice(''); setQty(''); fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setOpening(false); }
  };

  const handleCancelOrder = async (orderId) => {
    setResult(null);
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}/api/trading/orders/cancel`, { method: 'POST', headers: headers(), body: JSON.stringify({ order_id: orderId }) });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore');
      setResult({ ok: true, msg: res.data?.message }); fetchData();
    } catch (e) { setResult({ ok: false, msg: e.message }); }
  };

  if (loading) return <div className="min-h-screen bg-zinc-950 flex items-center justify-center"><Loader2 className="w-8 h-8 text-purple-500 animate-spin" /></div>;

  const openPositions = positions.filter(p => p.status === 'open');
  const closedPositions = positions.filter(p => p.status === 'closed');
  const activeOverlays = activeIndicators.filter(id => { const d = INDICATOR_DEFS.find(dd => dd.id === id); return d && d.group === 'Overlay'; });
  const lastCandle = candles.length > 0 ? candles[candles.length - 1] : null;

  return (
    <div className="min-h-screen bg-zinc-950" data-testid="margin-trading-page">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
        <div className="max-w-[1800px] mx-auto px-4 py-2 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-1.5 hover:bg-zinc-800 rounded-lg transition-colors" data-testid="back-btn">
            <ArrowLeft className="w-4 h-4 text-zinc-400" />
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-white font-bold text-base">Margin Trading</h1>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400 font-medium">PRO</span>
          </div>

          {/* Pair Selector */}
          <div className="flex items-center gap-1 ml-4">
            <select value={pair} onChange={e => setPair(e.target.value)} data-testid="pair-select"
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-white text-sm font-bold focus:outline-none focus:border-purple-500">
              {PAIRS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Ticker Info */}
          {ticker && (
            <div className="hidden md:flex items-center gap-5 ml-4 text-xs">
              <div>
                <span className="text-zinc-500">Ultimo</span>
                <div className="text-white font-bold font-mono">{ticker.last_price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
              </div>
              <div>
                <span className="text-zinc-500">24h</span>
                <div className={`font-mono font-bold ${ticker.change_24h >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {ticker.change_24h >= 0 ? '+' : ''}{ticker.change_24h?.toFixed(2)}%
                </div>
              </div>
              <div>
                <span className="text-zinc-500">Vol</span>
                <div className="text-zinc-300 font-mono">{ticker.volume_24h?.toFixed(2)}</div>
              </div>
              <div>
                <span className="text-zinc-500">Bid</span>
                <div className="text-emerald-400 font-mono">{ticker.best_bid?.toFixed(4)}</div>
              </div>
              <div>
                <span className="text-zinc-500">Ask</span>
                <div className="text-red-400 font-mono">{ticker.best_ask?.toFixed(4)}</div>
              </div>
            </div>
          )}

          {/* Account balance quick view */}
          {account && (
            <div className="ml-auto hidden lg:flex items-center gap-4 text-xs">
              <div className="text-right">
                <span className="text-zinc-500">Margine</span>
                <div className="text-white font-bold font-mono">EUR {account.margin_balance?.toFixed(2)}</div>
              </div>
              <div className="text-right">
                <span className="text-zinc-500">PnL</span>
                <div className={`font-mono font-bold ${account.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {account.unrealized_pnl >= 0 ? '+' : ''}{account.unrealized_pnl?.toFixed(2)}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Result toast */}
      {result && (
        <div className={`max-w-[1800px] mx-auto px-4 pt-2`}>
          <div className={`p-2.5 rounded-lg text-xs font-medium flex items-center gap-2 ${result.ok ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
            {result.ok ? <TrendingUp className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            {result.msg}
            <button onClick={() => setResult(null)} className="ml-auto"><X className="w-3.5 h-3.5" /></button>
          </div>
        </div>
      )}

      <div className="max-w-[1800px] mx-auto px-4 py-3">
        {/* No account */}
        {!account && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-10 text-center max-w-lg mx-auto mt-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-purple-500/20 to-violet-600/20 flex items-center justify-center">
              <TrendingUp className="w-8 h-8 text-purple-400" />
            </div>
            <h2 className="text-white font-bold text-xl mb-2">Attiva Margin Trading</h2>
            <p className="text-zinc-400 text-sm mb-6">Crea il tuo account margin per operare con leva fino a 20x su tutte le coppie</p>
            <button onClick={createAccount} data-testid="create-margin-btn"
              className="px-8 py-3 bg-gradient-to-r from-purple-500 to-violet-600 hover:from-purple-600 hover:to-violet-700 text-white rounded-xl font-semibold transition-all shadow-lg shadow-purple-500/20">
              Attiva Margin Account
            </button>
          </div>
        )}

        {account && (
          <div className="grid grid-cols-12 gap-3">
            {/* LEFT: Chart Area */}
            <div className="col-span-12 xl:col-span-9">
              {/* Chart Toolbar */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-t-xl">
                <div className="flex items-center gap-1 px-3 py-1.5 border-b border-zinc-800 flex-wrap">
                  {/* Intervals */}
                  {INTERVALS.map(iv => (
                    <button key={iv.id} onClick={() => setInterval(iv.id)} data-testid={`interval-${iv.id}`}
                      className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${interval === iv.id ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
                      {iv.label}
                    </button>
                  ))}
                  <div className="w-px h-4 bg-zinc-800 mx-1" />
                  {/* Chart Types */}
                  {CHART_TYPES.map(ct => (
                    <button key={ct.id} onClick={() => setChartType(ct.id)} data-testid={`chart-type-${ct.id}`}
                      title={ct.label}
                      className={`p-1.5 rounded transition-colors ${chartType === ct.id ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
                      <ct.icon className="w-3.5 h-3.5" />
                    </button>
                  ))}
                  <div className="w-px h-4 bg-zinc-800 mx-1" />
                  {/* Indicator Button */}
                  <div className="relative">
                    <button onClick={() => setShowIndicators(!showIndicators)} data-testid="indicators-btn"
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${showIndicators ? 'bg-purple-500/20 text-purple-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
                      <Settings2 className="w-3.5 h-3.5" /> Indicatori
                      {activeIndicators.length > 0 && <span className="bg-purple-500 text-white text-[10px] px-1.5 rounded-full">{activeIndicators.length}</span>}
                    </button>
                    {showIndicators && <IndicatorSelector activeIndicators={activeIndicators} onToggle={toggleIndicator} onClose={() => setShowIndicators(false)} />}
                  </div>

                  {/* Active indicator badges */}
                  <div className="flex items-center gap-1 ml-2 flex-wrap">
                    {activeIndicators.map(id => {
                      const def = INDICATOR_DEFS.find(d => d.id === id);
                      if (!def) return null;
                      return (
                        <span key={id} className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">
                          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: def.color }} />
                          {def.name}
                          <button onClick={() => toggleIndicator(id)}><X className="w-2.5 h-2.5 hover:text-red-400" /></button>
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* Chart */}
                <div className="relative">
                  {candleLoading && <div className="absolute inset-0 flex items-center justify-center bg-zinc-900/80 z-10"><Loader2 className="w-6 h-6 text-purple-500 animate-spin" /></div>}
                  <ProChart pair={pair} interval={interval} chartType={chartType} activeIndicators={activeIndicators} candles={candles} />
                </div>

                {/* Oscillator panels (RSI, MACD) */}
                <OscillatorPanel candles={candles} activeIndicators={activeIndicators} />
              </div>

              {/* Bottom panel: Positions / History */}
              <div className="bg-zinc-900 border border-zinc-800 border-t-0 rounded-b-xl overflow-hidden">
                <div className="flex border-b border-zinc-800">
                  {[
                    { id: 'positions', label: `Posizioni (${openPositions.length})` },
                    { id: 'orders', label: `Ordini (${advOrders.length})` },
                    { id: 'history', label: `Storico (${closedPositions.length})` },
                  ].map(t => (
                    <button key={t.id} onClick={() => setBottomTab(t.id)} data-testid={`tab-${t.id}`}
                      className={`px-4 py-2 text-xs font-medium transition-colors ${bottomTab === t.id ? 'text-purple-400 border-b-2 border-purple-500' : 'text-zinc-500 hover:text-zinc-300'}`}>
                      {t.label}
                    </button>
                  ))}
                </div>

                {bottomTab === 'positions' && (
                  openPositions.length === 0 ? (
                    <div className="py-8 text-center text-zinc-600 text-xs">Nessuna posizione aperta</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-zinc-800/50">
                          <tr>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Coppia</th>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Lato</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Qty</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Entry</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Leva</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Liq.</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">PnL</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Margine</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium"></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800/50">
                          {openPositions.map(p => (
                            <tr key={p.id} data-testid={`position-${p.id}`} className="hover:bg-zinc-800/30">
                              <td className="px-3 py-2 text-zinc-200 font-medium">{p.pair_id}</td>
                              <td className="px-3 py-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${p.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                                  {p.side === 'buy' ? 'LONG' : 'SHORT'}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{p.quantity}</td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{p.entry_price?.toLocaleString()}</td>
                              <td className="px-3 py-2 text-right text-purple-400 font-mono">{p.leverage}x</td>
                              <td className="px-3 py-2 text-right text-orange-400 font-mono">{p.liquidation_price?.toLocaleString()}</td>
                              <td className="px-3 py-2 text-right font-mono font-bold">
                                <span className={p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                  {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(2)}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right text-zinc-400 font-mono">{p.margin_used?.toFixed(2)}</td>
                              <td className="px-3 py-2 text-right">
                                <button onClick={() => handleClose(p.id)} data-testid={`close-${p.id}`}
                                  className="px-2 py-1 bg-red-500/10 text-red-400 rounded text-[10px] font-bold hover:bg-red-500/20 transition-colors">
                                  CHIUDI
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}

                {bottomTab === 'orders' && (
                  advOrders.length === 0 ? (
                    <div className="py-8 text-center text-zinc-600 text-xs">Nessun ordine attivo</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-zinc-800/50">
                          <tr>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Tipo</th>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Coppia</th>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Lato</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Qty</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Prezzo</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Stato</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium"></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800/50">
                          {advOrders.map(o => (
                            <tr key={o.id} className="hover:bg-zinc-800/30">
                              <td className="px-3 py-2">
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-400 uppercase">{o.type}</span>
                              </td>
                              <td className="px-3 py-2 text-zinc-200">{o.pair_id}</td>
                              <td className="px-3 py-2">
                                <span className={o.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>{o.side?.toUpperCase()}</span>
                              </td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{o.quantity}</td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{o.limit_price || o.stop_price || o.current_stop || '-'}</td>
                              <td className="px-3 py-2 text-right">
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${o.status === 'open' ? 'bg-emerald-500/20 text-emerald-400' : o.status === 'tracking' ? 'bg-blue-500/20 text-blue-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                                  {o.status?.toUpperCase()}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right">
                                <button onClick={() => handleCancelOrder(o.id)} className="px-2 py-1 bg-red-500/10 text-red-400 rounded text-[10px] font-bold hover:bg-red-500/20">ANNULLA</button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}

                {bottomTab === 'history' && (
                  closedPositions.length === 0 ? (
                    <div className="py-8 text-center text-zinc-600 text-xs">Nessuna posizione chiusa</div>
                  ) : (
                    <div className="overflow-x-auto max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-zinc-800/50 sticky top-0">
                          <tr>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Coppia</th>
                            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Lato</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Entry</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Exit</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Leva</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">PnL</th>
                            <th className="px-3 py-2 text-right text-zinc-500 font-medium">PnL %</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800/50">
                          {closedPositions.map(p => (
                            <tr key={p.id} className="hover:bg-zinc-800/30">
                              <td className="px-3 py-2 text-zinc-200">{p.pair_id}</td>
                              <td className="px-3 py-2">
                                <span className={`text-[10px] font-bold ${p.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}`}>{p.side.toUpperCase()}</span>
                              </td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{p.entry_price}</td>
                              <td className="px-3 py-2 text-right text-zinc-300 font-mono">{p.exit_price}</td>
                              <td className="px-3 py-2 text-right text-purple-400 font-mono">{p.leverage}x</td>
                              <td className="px-3 py-2 text-right font-mono font-bold">
                                <span className={p.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                  {p.realized_pnl >= 0 ? '+' : ''}{p.realized_pnl?.toFixed(2)}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right font-mono">
                                <span className={p.realized_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                  {p.realized_pnl_pct >= 0 ? '+' : ''}{p.realized_pnl_pct?.toFixed(1)}%
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}
              </div>
            </div>

            {/* RIGHT: Trading Panel */}
            <div className="col-span-12 xl:col-span-3 space-y-3">
              {/* Account Summary */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Account Margin</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${account.margin_level > 150 ? 'bg-emerald-500/20 text-emerald-400' : account.margin_level > 100 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}`}>
                    {account.margin_level?.toFixed(0)}%
                  </span>
                </div>
                <div className="space-y-2">
                  {[
                    { label: 'Bilancio', value: `EUR ${account.margin_balance?.toFixed(2)}`, color: 'text-white' },
                    { label: 'Equity', value: `EUR ${account.equity?.toFixed(2)}`, color: 'text-blue-400' },
                    { label: 'PnL Non Real.', value: `${account.unrealized_pnl >= 0 ? '+' : ''}${account.unrealized_pnl?.toFixed(2)}`, color: account.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400' },
                    { label: 'PnL Realizzato', value: `${(account.total_realized_pnl || 0) >= 0 ? '+' : ''}${(account.total_realized_pnl || 0).toFixed(2)}`, color: (account.total_realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400' },
                  ].map(s => (
                    <div key={s.label} className="flex items-center justify-between">
                      <span className="text-zinc-500 text-xs">{s.label}</span>
                      <span className={`font-mono text-xs font-bold ${s.color}`} data-testid={`margin-${s.label.toLowerCase().replace(/ /g,'-')}`}>{s.value}</span>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 mt-3">
                  <button onClick={() => { setShowDeposit(!showDeposit); setDepAction('deposit'); }}
                    className="flex-1 text-center py-1.5 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg text-xs font-medium hover:bg-purple-500/20 transition-colors">
                    Deposita
                  </button>
                  <button onClick={() => { setShowDeposit(!showDeposit); setDepAction('withdraw'); }}
                    className="flex-1 text-center py-1.5 bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded-lg text-xs font-medium hover:bg-orange-500/20 transition-colors">
                    Preleva
                  </button>
                </div>
              </div>

              {/* Deposit/Withdraw Inline */}
              {showDeposit && (
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 space-y-2">
                  <label className="text-zinc-400 text-xs">{depAction === 'deposit' ? 'Deposita' : 'Preleva'} EUR nel Margin</label>
                  <input type="number" step="any" value={depAmount} onChange={e => setDepAmount(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono" placeholder="0.00" />
                  <button onClick={handleDeposit} disabled={!depAmount}
                    className="w-full py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-xs font-bold disabled:opacity-50 transition-colors">Conferma</button>
                </div>
              )}

              {/* Order Form */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid="open-position-form">
                <div className="flex gap-1 mb-3">
                  <button onClick={() => setSide('buy')} data-testid="side-buy"
                    className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all ${side === 'buy' ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/20' : 'bg-zinc-800 text-zinc-400'}`}>
                    LONG
                  </button>
                  <button onClick={() => setSide('sell')} data-testid="side-sell"
                    className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all ${side === 'sell' ? 'bg-red-500 text-white shadow-lg shadow-red-500/20' : 'bg-zinc-800 text-zinc-400'}`}>
                    SHORT
                  </button>
                </div>

                <div className="space-y-2">
                  <div>
                    <label className="text-zinc-500 text-[10px] block mb-1">Quantita</label>
                    <input type="number" step="any" value={qty} onChange={e => setQty(e.target.value)} placeholder="0.01"
                      data-testid="qty-input"
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono focus:border-purple-500 focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-zinc-500 text-[10px] block mb-1">Leva</label>
                    <div className="flex gap-1">
                      {[2, 3, 5, 10, 15, 20].map(l => (
                        <button key={l} onClick={() => setLeverage(String(l))} data-testid={`lev-${l}`}
                          className={`flex-1 py-1.5 rounded text-[10px] font-bold transition-colors ${leverage === String(l) ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'bg-zinc-800 text-zinc-500 border border-transparent'}`}>
                          {l}x
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-zinc-500 text-[10px] block mb-1">Stop Loss</label>
                      <input type="number" step="any" value={sl} onChange={e => setSl(e.target.value)} placeholder="SL"
                        className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-xs font-mono" />
                    </div>
                    <div>
                      <label className="text-zinc-500 text-[10px] block mb-1">Take Profit</label>
                      <input type="number" step="any" value={tp} onChange={e => setTp(e.target.value)} placeholder="TP"
                        className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-xs font-mono" />
                    </div>
                  </div>
                  {qty && ticker && (
                    <div className="text-[10px] text-zinc-500 p-2 bg-zinc-800/50 rounded-lg space-y-0.5">
                      <div className="flex justify-between"><span>Valore nozionale</span><span className="text-zinc-300">EUR {(parseFloat(qty || 0) * (ticker.last_price || 0)).toFixed(2)}</span></div>
                      <div className="flex justify-between"><span>Margine richiesto</span><span className="text-zinc-300">EUR {(parseFloat(qty || 0) * (ticker.last_price || 0) / parseFloat(leverage || 1)).toFixed(2)}</span></div>
                    </div>
                  )}
                  <button onClick={handleOpen} disabled={opening || !qty} data-testid="confirm-open-btn"
                    className={`w-full py-2.5 rounded-lg font-bold text-sm transition-all ${side === 'buy' ? 'bg-emerald-500 hover:bg-emerald-600 shadow-lg shadow-emerald-500/20' : 'bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/20'} text-white disabled:opacity-50 disabled:shadow-none`}>
                    {opening ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : `${side === 'buy' ? 'Long' : 'Short'} ${pair} ${leverage}x`}
                  </button>

                  {/* Advanced Order Toggle */}
                  <button onClick={() => setShowLimitOrder(!showLimitOrder)} data-testid="toggle-advanced-btn"
                    className="w-full py-1.5 text-purple-400 text-[10px] font-medium hover:text-purple-300 transition-colors">
                    {showLimitOrder ? 'Nascondi' : 'Ordini Avanzati (Limit / Stop / Trailing)'}
                  </button>
                </div>

                {showLimitOrder && (
                  <div className="p-3 border-t border-zinc-800 space-y-2" data-testid="advanced-order-form">
                    <div className="flex gap-1">
                      {[{id:'limit',label:'Limit'},{id:'stop',label:'Stop'},{id:'trailing',label:'Trail'}].map(t => (
                        <button key={t.id} onClick={() => setOrderType(t.id)} data-testid={`otype-${t.id}`}
                          className={`flex-1 py-1 rounded text-[10px] font-bold ${orderType === t.id ? 'bg-purple-500/20 text-purple-400' : 'bg-zinc-800 text-zinc-500'}`}>{t.label}</button>
                      ))}
                    </div>
                    <div>
                      <label className="text-zinc-500 text-[10px] block mb-1">
                        {orderType === 'limit' ? 'Prezzo Limite' : orderType === 'stop' ? 'Prezzo Stop' : 'Trail %'}
                      </label>
                      <input type="number" step="any" value={limitPrice} onChange={e => setLimitPrice(e.target.value)}
                        placeholder={orderType === 'trailing' ? '2.0' : '0.00'}
                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono" />
                    </div>
                    <button onClick={handlePlaceAdvancedOrder} disabled={opening || !qty || !limitPrice} data-testid="place-advanced-btn"
                      className="w-full py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg font-bold text-xs disabled:opacity-50">
                      {opening ? <Loader2 className="w-3 h-3 animate-spin mx-auto" /> : `Piazza ${orderType.toUpperCase()} ${side.toUpperCase()}`}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
