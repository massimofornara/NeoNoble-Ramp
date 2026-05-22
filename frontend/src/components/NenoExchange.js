import React, { useState } from 'react';

const NenoExchange = () => {
  const [activeTab, setActiveTab] = useState('swap');
  const [amount, setAmount] = useState('1.0');
  const [status, setStatus] = useState('');

  const handleSwap = async () => {
    setStatus('Esecuzione swap in corso...');

    try {
      const response = await fetch('/api/swap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: "user123",
          from_token: "NENO",
          to_token: "BTCB",
          amount_in: parseFloat(amount),
          chain: "bsc",
          slippage: 0.8,
          user_wallet_address: "0xIL_TUO_INDIRIZZO_METAMASK"   // ← Cambia con il tuo
        })
      });

      const result = await response.json();

      if (result.success) {
        setStatus(`✅ Swap completato! Tx: ${result.tx_hash}`);
      } else {
        setStatus(`❌ Errore: ${result.error}`);
      }
    } catch (err) {
      setStatus(`❌ Errore di connessione: ${err.message}`);
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 text-center">NeoNoble Exchange</h1>

      {/* Tabs */}
      <div className="flex border-b mb-6">
        <button 
          onClick={() => setActiveTab('buy')} 
          className={`flex-1 py-3 font-medium ${activeTab === 'buy' ? 'border-b-4 border-green-500 text-green-600' : 'text-gray-500'}`}>
          Acquista
        </button>
        <button 
          onClick={() => setActiveTab('sell')} 
          className={`flex-1 py-3 font-medium ${activeTab === 'sell' ? 'border-b-4 border-red-500 text-red-600' : 'text-gray-500'}`}>
          Vendi
        </button>
        <button 
          onClick={() => setActiveTab('swap')} 
          className={`flex-1 py-3 font-medium ${activeTab === 'swap' ? 'border-b-4 border-blue-500 text-blue-600' : 'text-gray-500'}`}>
          Swap On-Chain Reale
        </button>
      </div>

      {/* Tab Swap - UNICO VISIBILE E FUNZIONANTE */}
      {activeTab === 'swap' && (
        <div className="bg-white p-8 rounded-2xl shadow-lg">
          <h2 className="text-2xl font-semibold mb-6 text-center">Esegui Swap On-Chain Reale</h2>
          
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium mb-2">Quantità NENO da swappare</label>
              <input 
                type="number" 
                value={amount} 
                onChange={(e) => setAmount(e.target.value)}
                className="w-full p-4 border rounded-xl text-2xl"
                step="0.1"
              />
            </div>

            <button 
              onClick={handleSwap}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-5 rounded-2xl text-xl transition-all">
              Esegui Swap → BTCB
            </button>

            {status && (
              <div className={`p-4 rounded-xl text-center font-medium ${status.includes('✅') ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                {status}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NenoExchange;

