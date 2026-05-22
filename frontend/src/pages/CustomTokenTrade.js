import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowRightLeft, Coins, TrendingUp, TrendingDown,
  Loader2, RefreshCw, AlertCircle, CheckCircle, Wallet, ArrowDown
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

/* XHR helpers */
function xhrGet(url) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    const token = localStorage.getItem('token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.onload = () => {
      try { resolve({ ok: xhr.status >= 200 && xhr.status < 300, data: JSON.parse(xhr.responseText) }); }
      catch { resolve({ ok: false, data: {} }); }
    };
    xhr.onerror = () => resolve({ ok: false, data: {} });
    xhr.send();
  });
}

function xhrPost(url, body) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    const token = localStorage.getItem('token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = { detail: `Errore ${xhr.status}` }; }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, data });
    };
    xhr.onerror = () => resolve({ ok: false, data: { detail: 'Connessione di rete fallita' } });
    xhr.send(JSON.stringify(body));
  });
}

const PAY_ASSETS = ['EUR', 'USDT', 'BTC', 'ETH', 'BNB', 'NENO'];

export default function CustomTokenTrade() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('buy');
  const [customTokens, setCustomTokens] = useState([]);
  const [selectedToken, setSelectedToken] = useState(null);
  const [amount, setAmount] = useState('');
  const [payAsset, setPayAsset] = useState('EUR');
  const [loading, setLoading] = useState(false);
  const [loadingTokens, setLoadingTokens] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [balances, setBalances] = useState({});
  const [swapFrom, setSwapFrom] = useState('');
  const [swapTo, setSwapTo] = useState('');
  const [swapAmount, setSwapAmount] = useState('');
  const [swapQuote, setSwapQuote] = useState(null);
  const pollRef = useRef(null);

  const loadTokens = useCallback(async () => {
    const res = await xhrGet(`${BACKEND_URL}/api/neno-exchange/custom-tokens`);
    if (res.ok) {
      setCustomTokens(res.data.tokens || []);
      if (!selectedToken && res.data.tokens?.length > 0) {
        setSelectedToken(res.data.tokens[0]);
      }
    }
    setLoadingTokens(false);
  }, [selectedToken]);

  const loadBalances = useCallback(async () => {
    const res = await xhrGet(`${BACKEND_URL}/api/neno-exchange/live-balances`);
    if (res.ok) setBalances(res.data.balances || {});
  }, []);

  useEffect(() => {
    loadTokens();
    loadBalances();
    pollRef.current = setInterval(loadBalances, 5000);
    return () => clearInterval(pollRef.current);
  }, [loadTokens, loadBalances]);

  const handleTrade = async () => {
    if (!selectedToken || !amount || parseFloat(amount) <= 0) {
      setError('Inserisci un importo valido');
      return;
    }
    setLoading(true);
    setError('');
    setSuccess('');

    const endpoint = tab === 'buy' ? 'buy-custom-token' : 'sell-custom-token';
    const body = tab === 'buy'
      ? { symbol: selectedToken.symbol, amount: parseFloat(amount), pay_asset: payAsset }
      : { symbol: selectedToken.symbol, amount: parseFloat(amount), receive_asset: payAsset };

    const res = await xhrPost(`${BACKEND_URL}/api/neno-exchange/${endpoint}`, body);

    if (res.ok) {
      setSuccess(res.data.message);
      setAmount('');
      loadBalances();
      loadTokens();
    } else {
      setError(res.data.detail || `Errore ${tab}`);
    }
    setLoading(false);
  };

  const handleSwap = async () => {
    if (!swapFrom || !swapTo || !swapAmount || parseFloat(swapAmount) <= 0) {
      setError('Compila tutti i campi dello swap');
      return;
    }
    if (swapFrom === swapTo) {
      setError('Seleziona due asset diversi');
      return;
    }
    setLoading(true);
    setError('');
    setSuccess('');

    const res = await xhrPost(`${BACKEND_URL}/api/neno-exchange/swap`, {
      from_asset: swapFrom,
      to_asset: swapTo,
      amount: parseFloat(swapAmount),
    });

    if (res.ok) {
      setSuccess(res.data.message);
      setSwapAmount('');
      setSwapQuote(null);
      loadBalances();
    } else {
      setError(res.data.detail || 'Errore swap');
    }
    setLoading(false);
  };

  const loadSwapQuote = useCallback(async () => {
    if (!swapFrom || !swapTo || !swapAmount || parseFloat(swapAmount) <= 0 || swapFrom === swapTo) {
      setSwapQuote(null);
      return;
    }
    const res = await xhrGet(
      `${BACKEND_URL}/api/neno-exchange/swap-quote?from_asset=${swapFrom}&to_asset=${swapTo}&amount=${swapAmount}`
    );
    if (res.ok) setSwapQuote(res.data);
  }, [swapFrom, swapTo, swapAmount]);

  useEffect(() => {
    const timer = setTimeout(loadSwapQuote, 500);
    return () => clearTimeout(timer);
  }, [loadSwapQuote]);

  const allAssets = [...PAY_ASSETS, ...customTokens.map(t => t.symbol)];

  const getBalance = (asset) => balances[asset]?.balance || 0;

  const estimateBuyCost = () => {
    if (!selectedToken || !amount || parseFloat(amount) <= 0) return null;
    const tokenPriceEur = selectedToken.price_eur || 0;
    const payPriceMap = { EUR: 1, USDT: 0.92, BTC: 60787, ETH: 1769, BNB: 555.36, NENO: 10000 };
    const payPrice = payPriceMap[payAsset] || 1;
    const totalEur = parseFloat(amount) * tokenPriceEur;
    const fee = totalEur * 0.003;
    return { cost: ((totalEur + fee) / payPrice).toFixed(8), fee: (fee / payPrice).toFixed(8) };
  };

  const estimateSellReceive = () => {
    if (!selectedToken || !amount || parseFloat(amount) <= 0) return null;
    const tokenPriceEur = selectedToken.price_eur || 0;
    const payPriceMap = { EUR: 1, USDT: 0.92, BTC: 60787, ETH: 1769, BNB: 555.36, NENO: 10000 };
    const payPrice = payPriceMap[payAsset] || 1;
    const totalEur = parseFloat(amount) * tokenPriceEur;
    const fee = totalEur * 0.003;
    return { receive: ((totalEur - fee) / payPrice).toFixed(8), fee: (fee / payPrice).toFixed(8) };
  };

  return (
    <div className="min-h-screen bg-[#0a0b14]">
      <header className="border-b border-[#1e2035] bg-[#0d0e18]/80 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-[#1a1b2e] rounded-lg transition-colors" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg">
              <ArrowRightLeft className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Custom Token Market</h1>
              <p className="text-gray-500 text-xs">Compra, Vendi e Scambia Token Personalizzati</p>
            </div>
          </div>
          <button onClick={() => { loadTokens(); loadBalances(); }} className="ml-auto p-2 hover:bg-[#1a1b2e] rounded-lg" data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Tabs */}
        <div className="flex gap-2 bg-[#12131f] rounded-xl p-1" data-testid="trade-tabs">
          {[
            { id: 'buy', label: 'Compra', icon: TrendingUp, color: 'emerald' },
            { id: 'sell', label: 'Vendi', icon: TrendingDown, color: 'red' },
            { id: 'swap', label: 'Swap', icon: ArrowRightLeft, color: 'cyan' },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setError(''); setSuccess(''); }}
              className={`flex-1 py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-all text-sm ${
                tab === t.id
                  ? t.color === 'emerald' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : t.color === 'red' ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              data-testid={`tab-${t.id}`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Messages */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3" data-testid="trade-error">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 flex items-center gap-3" data-testid="trade-success">
            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <p className="text-emerald-400 text-sm">{success}</p>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Main Trading Panel */}
          <div className="lg:col-span-2 space-y-5">
            {tab !== 'swap' ? (
              /* Buy / Sell Panel */
              <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-6 space-y-5">
                <h3 className="text-base font-semibold text-white">
                  {tab === 'buy' ? 'Compra Token' : 'Vendi Token'}
                </h3>

                {loadingTokens ? (
                  <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-cyan-400" /></div>
                ) : customTokens.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-gray-500">Nessun token personalizzato disponibile.</p>
                    <button onClick={() => navigate('/tokens/create')} className="mt-3 text-cyan-400 hover:underline text-sm" data-testid="create-first-token">
                      Crea il primo token
                    </button>
                  </div>
                ) : (
                  <>
                    {/* Token selector */}
                    <div>
                      <label className="block text-sm text-gray-400 mb-2">Seleziona Token</label>
                      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2" data-testid="token-selector">
                        {customTokens.map(t => (
                          <button
                            key={t.symbol}
                            onClick={() => setSelectedToken(t)}
                            className={`p-3 rounded-lg border transition-all text-center ${
                              selectedToken?.symbol === t.symbol
                                ? 'border-cyan-500/50 bg-cyan-500/10'
                                : 'border-[#1e2035] bg-[#0a0b14] hover:border-[#2a2d45]'
                            }`}
                            data-testid={`select-token-${t.symbol}`}
                          >
                            <div className="text-white font-mono font-bold text-sm">{t.symbol}</div>
                            <div className="text-gray-500 text-xs mt-0.5">${t.price_usd || (t.price_eur / 0.92).toFixed(2)}</div>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Amount */}
                    <div>
                      <label className="block text-sm text-gray-400 mb-2">
                        {tab === 'buy' ? 'Quantita\' da comprare' : 'Quantita\' da vendere'}
                      </label>
                      <div className="relative">
                        <input
                          type="number" value={amount} onChange={e => setAmount(e.target.value)}
                          placeholder="0.00" min="0" step="any"
                          className="w-full px-4 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white text-lg placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none"
                          data-testid="trade-amount-input"
                        />
                        <span className="absolute right-4 top-1/2 -translate-y-1/2 text-cyan-400 font-mono text-sm">
                          {selectedToken?.symbol || '---'}
                        </span>
                      </div>
                      {tab === 'sell' && selectedToken && (
                        <p className="text-xs text-gray-500 mt-1">
                          Saldo: {getBalance(selectedToken.symbol).toFixed(4)} {selectedToken.symbol}
                        </p>
                      )}
                    </div>

                    {/* Pay/Receive asset */}
                    <div>
                      <label className="block text-sm text-gray-400 mb-2">
                        {tab === 'buy' ? 'Paga con' : 'Ricevi in'}
                      </label>
                      <div className="flex flex-wrap gap-2" data-testid="pay-asset-selector">
                        {PAY_ASSETS.map(a => (
                          <button
                            key={a}
                            onClick={() => setPayAsset(a)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                              payAsset === a
                                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                                : 'bg-[#0a0b14] text-gray-500 border border-[#1e2035] hover:text-gray-300'
                            }`}
                            data-testid={`pay-asset-${a}`}
                          >
                            {a}
                            <span className="text-[10px] ml-1 text-gray-600">{getBalance(a).toFixed(4)}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Estimate */}
                    {selectedToken && amount && parseFloat(amount) > 0 && (
                      <div className="bg-[#0a0b14] rounded-lg p-4 space-y-2 text-sm" data-testid="trade-estimate">
                        {tab === 'buy' ? (
                          <>
                            <div className="flex justify-between">
                              <span className="text-gray-500">Costo stimato</span>
                              <span className="text-white">{estimateBuyCost()?.cost} {payAsset}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-gray-500">Fee (0.3%)</span>
                              <span className="text-gray-400">{estimateBuyCost()?.fee} {payAsset}</span>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="flex justify-between">
                              <span className="text-gray-500">Riceverai circa</span>
                              <span className="text-white">{estimateSellReceive()?.receive} {payAsset}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-gray-500">Fee (0.3%)</span>
                              <span className="text-gray-400">{estimateSellReceive()?.fee} {payAsset}</span>
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {/* Execute */}
                    <button
                      onClick={handleTrade} disabled={loading || !selectedToken || !amount}
                      className={`w-full py-3.5 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-40 ${
                        tab === 'buy'
                          ? 'bg-gradient-to-r from-emerald-500 to-green-600 hover:from-emerald-600 hover:to-green-700 text-white shadow-lg shadow-emerald-500/20'
                          : 'bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white shadow-lg shadow-red-500/20'
                      }`}
                      data-testid="execute-trade-btn"
                    >
                      {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : tab === 'buy' ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                      {loading ? 'Esecuzione...' : tab === 'buy' ? `Compra ${selectedToken?.symbol || ''}` : `Vendi ${selectedToken?.symbol || ''}`}
                    </button>
                  </>
                )}
              </div>
            ) : (
              /* Swap Panel */
              <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-6 space-y-5">
                <h3 className="text-base font-semibold text-white">Swap Token</h3>
                <p className="text-gray-500 text-xs">Scambia qualsiasi coppia di token (custom e nativi) tramite il bridge NENO</p>

                {/* From */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Da</label>
                  <div className="flex gap-2">
                    <select
                      value={swapFrom}
                      onChange={e => setSwapFrom(e.target.value)}
                      className="flex-1 px-3 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white focus:border-cyan-500/50 focus:outline-none"
                      data-testid="swap-from-select"
                    >
                      <option value="">Seleziona asset</option>
                      {allAssets.map(a => (
                        <option key={a} value={a}>{a} ({getBalance(a).toFixed(4)})</option>
                      ))}
                    </select>
                    <input
                      type="number" value={swapAmount} onChange={e => setSwapAmount(e.target.value)}
                      placeholder="Importo" min="0" step="any"
                      className="w-36 px-3 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none"
                      data-testid="swap-amount-input"
                    />
                  </div>
                </div>

                <div className="flex justify-center">
                  <button
                    onClick={() => { const tmp = swapFrom; setSwapFrom(swapTo); setSwapTo(tmp); }}
                    className="p-2 bg-[#1a1b2e] hover:bg-[#22243a] rounded-full transition-colors"
                    data-testid="swap-direction-btn"
                  >
                    <ArrowDown className="w-5 h-5 text-cyan-400" />
                  </button>
                </div>

                {/* To */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">A</label>
                  <select
                    value={swapTo}
                    onChange={e => setSwapTo(e.target.value)}
                    className="w-full px-3 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white focus:border-cyan-500/50 focus:outline-none"
                    data-testid="swap-to-select"
                  >
                    <option value="">Seleziona asset</option>
                    {allAssets.filter(a => a !== swapFrom).map(a => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>

                {/* Quote */}
                {swapQuote && (
                  <div className="bg-[#0a0b14] rounded-lg p-4 space-y-2 text-sm" data-testid="swap-quote">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Riceverai</span>
                      <span className="text-white font-bold">{swapQuote.receive_amount} {swapTo}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Tasso</span>
                      <span className="text-gray-400">1 {swapFrom} = {swapQuote.rate} {swapTo}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Fee</span>
                      <span className="text-gray-400">{swapQuote.fee_pct}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Slippage stimato</span>
                      <span className="text-yellow-400">~0.1%</span>
                    </div>
                  </div>
                )}

                <button
                  onClick={handleSwap} disabled={loading || !swapFrom || !swapTo || !swapAmount}
                  className="w-full py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white rounded-xl font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-40 shadow-lg shadow-cyan-500/20"
                  data-testid="execute-swap-btn"
                >
                  {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <ArrowRightLeft className="w-5 h-5" />}
                  {loading ? 'Swap in corso...' : 'Esegui Swap'}
                </button>
              </div>
            )}
          </div>

          {/* Sidebar - Live Balances */}
          <div className="space-y-5">
            <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-5" data-testid="live-balances-panel">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Wallet className="w-4 h-4 text-cyan-400" />
                  Bilanci Live
                </h3>
                <span className="flex items-center gap-1 text-[10px] text-cyan-400 bg-cyan-400/10 px-1.5 py-0.5 rounded">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500" />
                  </span>
                  LIVE
                </span>
              </div>
              <div className="space-y-2">
                {Object.keys(balances).length === 0 ? (
                  <p className="text-gray-600 text-xs">Nessun saldo disponibile</p>
                ) : (
                  Object.entries(balances).map(([asset, info]) => (
                    <div key={asset} className="flex justify-between items-center py-1.5 border-b border-[#1e2035]/50 last:border-0">
                      <div>
                        <span className={`text-sm font-medium ${info.is_custom ? 'text-cyan-400' : 'text-white'}`}>{asset}</span>
                        {info.is_custom && <span className="ml-1 text-[10px] text-gray-600">custom</span>}
                      </div>
                      <div className="text-right">
                        <div className="text-white text-sm">{info.balance.toFixed(4)}</div>
                        <div className="text-gray-600 text-[10px]">${info.value_usd.toLocaleString()}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Token Info */}
            {selectedToken && tab !== 'swap' && (
              <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-5" data-testid="token-info-panel">
                <h3 className="text-sm font-semibold text-white mb-3">
                  <Coins className="w-4 h-4 text-cyan-400 inline mr-1" />
                  {selectedToken.name}
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Simbolo</span>
                    <span className="text-cyan-400 font-mono">{selectedToken.symbol}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Prezzo</span>
                    <span className="text-white">${selectedToken.price_usd || (selectedToken.price_eur / 0.92).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Supply</span>
                    <span className="text-white">{Number(selectedToken.total_supply).toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Il tuo saldo</span>
                    <span className="text-emerald-400 font-bold">{getBalance(selectedToken.symbol).toFixed(4)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* All Custom Tokens */}
            <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-5" data-testid="all-custom-tokens-sidebar">
              <h3 className="text-sm font-semibold text-white mb-3">Token Disponibili</h3>
              {customTokens.length === 0 ? (
                <p className="text-gray-600 text-xs">Nessun token</p>
              ) : (
                <div className="space-y-2">
                  {customTokens.map(t => (
                    <div key={t.symbol} className="flex justify-between items-center py-1.5 border-b border-[#1e2035]/50 last:border-0">
                      <div>
                        <span className="text-white text-sm font-medium">{t.symbol}</span>
                        <span className="text-gray-600 text-xs ml-1">{t.name}</span>
                      </div>
                      <span className="text-emerald-400 text-sm">${t.price_usd || (t.price_eur / 0.92).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
