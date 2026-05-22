import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Coins, ArrowLeft, Check, AlertCircle, Loader2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

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
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
    };
    xhr.onerror = () => resolve({ ok: false, status: 0, data: { detail: 'Connessione di rete fallita' } });
    xhr.send(JSON.stringify(body));
  });
}

export default function TokenCreation() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [createdToken, setCreatedToken] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    symbol: '',
    total_supply: '',
    price_usd: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    if (name === 'symbol') {
      setFormData(prev => ({ ...prev, [name]: value.toUpperCase().slice(0, 8) }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (!formData.name.trim()) { setError('Inserisci il nome del token'); setLoading(false); return; }
    if (formData.symbol.length < 2 || formData.symbol.length > 8) { setError('Il simbolo deve essere tra 2 e 8 caratteri'); setLoading(false); return; }
    if (!formData.total_supply || parseFloat(formData.total_supply) <= 0) { setError('Inserisci una supply valida'); setLoading(false); return; }
    if (!formData.price_usd || parseFloat(formData.price_usd) <= 0) { setError('Inserisci un prezzo USD valido'); setLoading(false); return; }

    const payload = {
      name: formData.name.trim(),
      symbol: formData.symbol.trim(),
      total_supply: parseFloat(formData.total_supply),
      price_usd: Math.round(parseFloat(formData.price_usd) * 100) / 100,
    };

    const res = await xhrPost(`${BACKEND_URL}/api/neno-exchange/create-token`, payload);

    if (res.ok) {
      setCreatedToken(res.data.token);
      setSuccess(true);
    } else {
      setError(res.data.detail || 'Errore nella creazione del token');
    }
    setLoading(false);
  };

  if (success && createdToken) {
    return (
      <div className="min-h-screen bg-[#0a0b14] flex items-center justify-center p-4">
        <div className="bg-[#12131f] border border-[#1e2035] rounded-2xl p-8 max-w-md w-full text-center" data-testid="token-created-success">
          <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
            <Check className="w-8 h-8 text-emerald-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Token Creato!</h2>
          <p className="text-gray-400 mb-6">
            <span className="text-cyan-400 font-bold">{createdToken.symbol}</span> creato con successo. L'intera supply e' stata accreditata al tuo wallet.
          </p>
          <div className="bg-[#0d0e18] rounded-xl p-4 mb-6 text-left space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-500 text-sm">Nome</span>
              <span className="text-white font-medium">{createdToken.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 text-sm">Simbolo</span>
              <span className="text-cyan-400 font-mono font-bold">{createdToken.symbol}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 text-sm">Supply Totale</span>
              <span className="text-white">{Number(createdToken.total_supply).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 text-sm">Prezzo</span>
              <span className="text-emerald-400 font-bold">${createdToken.price_usd}</span>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex-1 px-4 py-3 bg-[#1a1b2e] hover:bg-[#22243a] text-white rounded-xl transition-colors font-medium"
              data-testid="back-to-dashboard-btn"
            >
              Dashboard
            </button>
            <button
              onClick={() => navigate('/custom-tokens')}
              className="flex-1 px-4 py-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white rounded-xl transition-colors font-medium"
              data-testid="go-to-trade-btn"
            >
              Compra / Vendi
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0b14]">
      <header className="border-b border-[#1e2035] bg-[#0d0e18]/80 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="p-2 hover:bg-[#1a1b2e] rounded-lg transition-colors" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg">
              <Coins className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Crea Token Personalizzato</h1>
              <p className="text-gray-500 text-xs">Lancia il tuo token su NeoNoble Ramp</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8">
        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3" data-testid="create-token-error">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <div className="bg-[#12131f] border border-[#1e2035] rounded-xl p-6 space-y-5">
            <h2 className="text-base font-semibold text-white">Dettagli Token</h2>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Nome Token *</label>
              <input
                type="text" name="name" value={formData.name} onChange={handleChange} required
                placeholder="Es. NeoToken Gold"
                className="w-full px-4 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none transition-colors"
                data-testid="token-name-input"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Simbolo (max 8 caratteri) *</label>
              <input
                type="text" name="symbol" value={formData.symbol} onChange={handleChange} required
                maxLength={8} placeholder="Es. NTG"
                className="w-full px-4 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white uppercase font-mono placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none transition-colors tracking-wider"
                data-testid="token-symbol-input"
              />
              <p className="text-xs text-gray-600 mt-1">{formData.symbol.length}/8 caratteri</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Supply Iniziale *</label>
                <input
                  type="number" name="total_supply" value={formData.total_supply} onChange={handleChange} required
                  min="1" step="1" placeholder="1000000"
                  className="w-full px-4 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none transition-colors"
                  data-testid="token-supply-input"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Prezzo USD (2 decimali) *</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 font-medium">$</span>
                  <input
                    type="number" name="price_usd" value={formData.price_usd} onChange={handleChange} required
                    min="0.01" step="0.01" placeholder="1.00"
                    className="w-full pl-8 pr-4 py-3 bg-[#0a0b14] border border-[#1e2035] rounded-lg text-white placeholder-gray-600 focus:border-cyan-500/50 focus:outline-none transition-colors"
                    data-testid="token-price-input"
                  />
                </div>
              </div>
            </div>
          </div>

          {formData.name && formData.symbol && formData.total_supply && formData.price_usd && (
            <div className="bg-[#12131f] border border-cyan-500/20 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-cyan-400 mb-3">Riepilogo</h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Market Cap</span>
                  <span className="text-white font-medium">
                    ${(parseFloat(formData.total_supply || 0) * parseFloat(formData.price_usd || 0)).toLocaleString(undefined, {maximumFractionDigits: 2})}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Token</span>
                  <span className="text-cyan-400 font-mono">{formData.symbol || '---'}</span>
                </div>
              </div>
            </div>
          )}

          <button
            type="submit" disabled={loading}
            className="w-full py-4 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-semibold rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20"
            data-testid="create-token-submit-btn"
          >
            {loading ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> Creazione in corso...</>
            ) : (
              <><Coins className="w-5 h-5" /> Crea Token</>
            )}
          </button>
        </form>
      </main>
    </div>
  );
}
