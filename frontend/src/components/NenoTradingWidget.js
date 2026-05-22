import React, { useState, useEffect, useCallback } from 'react';
import { ArrowRightLeft, Loader2, Shield, AlertTriangle } from 'lucide-react';
import { useWeb3 } from '../context/Web3Context';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const NenoTradingWidget = ({ compact = false, onOrderPlaced }) => {
  const { address, isConnected } = useWeb3();

  const [swapFrom, setSwapFrom] = useState('NENO');
  const [swapTo, setSwapTo] = useState('USDT');
  const [swapAmt, setSwapAmt] = useState('');
  const [loading, setLoading] = useState(false);
  const [quote, setQuote] = useState(null);

  // ================== SWAP ON-CHAIN REALE ==================
  const handleRealOnChainSwap = async () => {
    if (!address) {
      alert("Connetti MetaMask per eseguire lo swap on-chain");
      return;
    }
    if (!swapAmt || parseFloat(swapAmt) <= 0) {
      alert("Inserisci una quantità valida");
      return;
    }
    if (swapFrom === swapTo) {
      alert("Seleziona token diversi");
      return;
    }

    const payload = {
      user_id: "system",
      from_token: swapFrom,
      to_token: swapTo,
      amount_in: parseFloat(swapAmt),
      chain: "bsc",
      slippage: 0.8,
      user_wallet_address: address
    };

    try {
      setLoading(true);

      const response = await fetch(`${BACKEND_URL}/api/swap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${localStorage.getItem('token') || ''}`
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.success) {
        alert(`✅ Swap On-Chain completato!\n\nTx Hash: ${data.tx_hash}\nRicevuti: ${data.amount_out || '—'} ${swapTo}`);
        setSwapAmt("");
        if (onOrderPlaced) onOrderPlaced();
      } else {
        alert(`❌ Errore: ${data.error || "Swap fallito"}`);
      }
    } catch (error) {
      console.error("Errore swap on-chain:", error);
      alert("Errore di connessione con il backend. Riprova.");
    } finally {
      setLoading(false);
    }
  };

  // ================== UI ==================
  return (
    <div className={`${compact ? 'p-4' : 'p-6'} bg-zinc-900 border border-zinc-800 rounded-2xl`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Swap Rapido</h3>
        <div className="text-xs text-emerald-400 flex items-center gap-1">
          <Shield className="w-4 h-4" /> On-Chain
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-zinc-500 text-xs mb-1 block">Da</label>
            <select 
              value={swapFrom} 
              onChange={(e) => setSwapFrom(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white"
            >
              <option value="NENO">NENO</option>
              <option value="USDT">USDT</option>
              <option value="BNB">BNB</option>
              <option value="BTC">BTC</option>
            </select>
          </div>

          <div>
            <label className="text-zinc-500 text-xs mb-1 block">A</label>
            <select 
              value={swapTo} 
              onChange={(e) => setSwapTo(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white"
            >
              <option value="USDT">USDT</option>
              <option value="NENO">NENO</option>
              <option value="BNB">BNB</option>
              <option value="BTC">BTC</option>
            </select>
          </div>
        </div>

        <div>
          <label className="text-zinc-500 text-xs mb-1 block">Quantità</label>
          <input
            type="number"
            value={swapAmt}
            onChange={(e) => setSwapAmt(e.target.value)}
            placeholder="0.00"
            className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white text-lg"
          />
        </div>

        {/* Pulsante Swap On-Chain Reale */}
        <button 
          onClick={handleRealOnChainSwap}
          disabled={loading || !swapAmt || parseFloat(swapAmt) <= 0 || !address || swapFrom === swapTo}
          className="w-full py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 rounded-2xl font-bold text-white flex items-center justify-center gap-2 disabled:opacity-50 transition-all"
        >
          {loading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <>
              <Shield className="w-5 h-5" />
              Swap On-Chain Reale → {swapTo}
            </>
          )}
        </button>

        {!address && (
          <p className="text-amber-400 text-xs text-center mt-2">
            ⚠️ Connetti MetaMask per usare lo Swap On-Chain
          </p>
        )}
      </div>
    </div>
  );
};

export default NenoTradingWidget;
