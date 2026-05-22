import React, { useState, useEffect } from 'react';
import { ArrowRightLeft, Loader2, Shield } from 'lucide-react';
import { useWeb3 } from '../context/Web3Context';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const NenoExchange = () => {
  const { address } = useWeb3();

  const [swapFrom, setSwapFrom] = useState('NENO');
  const [swapTo, setSwapTo] = useState('USDT');
  const [swapAmt, setSwapAmt] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRealOnChainSwap = async () => {
    if (!address) {
      alert("Connetti MetaMask per lo swap on-chain");
      return;
    }
    if (!swapAmt || parseFloat(swapAmt) <= 0) {
      alert("Inserisci una quantità valida");
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();   // ← letto una sola volta

      if (data.success) {
        alert(`✅ Swap On-Chain completato!\nTx: ${data.tx_hash}`);
        setSwapAmt("");
      } else {
        alert(`❌ ${data.error || "Swap fallito"}`);
      }
    } catch (err) {
      console.error(err);
      alert("Errore di connessione con il backend");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 bg-zinc-900 min-h-screen">
      <h1 className="text-2xl font-bold mb-6">NeoNoble Exchange</h1>

      <div className="bg-zinc-800 p-6 rounded-2xl">
        <div className="flex gap-2 mb-6">
          <button className="px-6 py-2 bg-zinc-700 rounded-xl">Acquista</button>
          <button className="px-6 py-2 bg-orange-500 rounded-xl">Vendi</button>
          <button className="px-6 py-2 bg-zinc-700 rounded-xl">Off-Ramp</button>
          <button className="px-6 py-2 bg-emerald-600 rounded-xl">Swap</button>
        </div>

        {/* Swap Section */}
        <div className="space-y-4">
          <input
            type="number"
            value={swapAmt}
            onChange={(e) => setSwapAmt(e.target.value)}
            placeholder="Quantità da scambiare"
            className="w-full p-4 bg-zinc-900 border border-zinc-700 rounded-xl text-white"
          />

          <button 
            onClick={handleRealOnChainSwap}
            disabled={loading || !swapAmt}
            className="w-full py-4 bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl font-bold text-white flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="animate-spin" /> : <><Shield /> Swap On-Chain Reale</>}
          </button>
        </div>
      </div>
    </div>
  );
};

export default NenoExchange;
