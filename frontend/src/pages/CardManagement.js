import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  CreditCard, Plus, Loader2, ArrowLeft, Snowflake,
  ArrowUpRight, Wallet, X, AlertCircle, Check,
  Shield, Eye, EyeOff, Lock, Unlock
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function getAuthHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  };
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

const STATUS_COLORS = {
  active: 'bg-green-500/20 text-green-400 border-green-500/30',
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  pending_shipment: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  frozen: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  cancelled: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const NETWORK_STYLES = {
  visa: { color: 'from-blue-600 to-blue-900', label: 'VISA' },
  mastercard: { color: 'from-red-600 to-orange-700', label: 'MASTERCARD' },
};

const CRYPTO_OPTIONS = [
  { symbol: 'BTC', name: 'Bitcoin' },
  { symbol: 'ETH', name: 'Ethereum' },
  { symbol: 'NENO', name: 'NeoNoble' },
  { symbol: 'USDT', name: 'Tether' },
  { symbol: 'SOL', name: 'Solana' },
  { symbol: 'BNB', name: 'BNB' },
];

export default function CardManagement() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showTopUp, setShowTopUp] = useState(null);
  const [showReveal, setShowReveal] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [selectedCard, setSelectedCard] = useState(null);
  const [txLoading, setTxLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchCards = useCallback(async () => {
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/cards/my-cards`, { headers: getAuthHeaders() });
      setCards(data.cards || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchCards(); }, [fetchCards]);

  const loadTransactions = async (cardId) => {
    setTxLoading(true);
    setSelectedCard(cardId);
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/cards/${cardId}/transactions`, { headers: getAuthHeaders() });
      setTransactions(data.transactions || []);
    } catch (e) { console.error(e); }
    finally { setTxLoading(false); }
  };

  const handleFreeze = async (cardId) => {
    setActionLoading(cardId);
    try {
      const { data } = await xhrFetchJson(`${BACKEND_URL}/api/cards/${cardId}/freeze`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({})
      });
      setSuccess(data.message);
      await fetchCards();
    } catch (e) { setError(e.message); }
    finally { setActionLoading(null); setTimeout(() => setSuccess(''), 3000); }
  };

  const handleCancel = async (cardId) => {
    if (!window.confirm('Sei sicuro di voler cancellare questa carta permanentemente?')) return;
    setActionLoading(cardId);
    try {
      await xhrFetchJson(`${BACKEND_URL}/api/cards/${cardId}/cancel`, {
        method: 'POST', headers: getAuthHeaders()
      });
      setSuccess('Carta cancellata');
      await fetchCards();
    } catch (e) { setError(e.message); }
    finally { setActionLoading(null); setTimeout(() => setSuccess(''), 3000); }
  };

  const activeCards = cards.filter(c => c.status !== 'cancelled');

  return (
    <div className="min-h-screen bg-gray-950" data-testid="card-management-page">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
                <ArrowLeft className="w-5 h-5 text-gray-400" />
              </button>
              <div className="p-2 bg-pink-500/20 rounded-lg">
                <CreditCard className="w-5 h-5 text-pink-400" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">Carte Crypto</h1>
                <p className="text-gray-400 text-xs">Carte virtuali e fisiche per spendere le tue crypto</p>
              </div>
            </div>
            <button onClick={() => setShowCreate(true)}
              data-testid="create-card-btn"
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-pink-500 to-purple-500 hover:from-pink-600 hover:to-purple-600 text-white rounded-lg font-medium text-sm transition-all">
              <Plus className="w-4 h-4" /> Nuova Carta
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {/* Messages */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400" /><p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2">
            <Check className="w-4 h-4 text-green-400" /><p className="text-green-400 text-sm">{success}</p>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-pink-500 animate-spin" />
          </div>
        ) : activeCards.length === 0 ? (
          <div className="text-center py-20">
            <CreditCard className="w-14 h-14 text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">Nessuna Carta</h3>
            <p className="text-gray-400 mb-6 text-sm">Crea la tua prima carta per spendere crypto ovunque</p>
            <button onClick={() => setShowCreate(true)}
              className="px-5 py-2.5 bg-pink-500 hover:bg-pink-600 text-white rounded-lg font-medium text-sm transition-colors">
              Crea Carta Virtuale
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Cards Column */}
            <div className="space-y-4">
              <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Le Tue Carte</h2>
              {activeCards.map(card => (
                <CardVisual key={card.id} card={card}
                  isSelected={selectedCard === card.id}
                  onSelect={() => loadTransactions(card.id)}
                  onFreeze={() => handleFreeze(card.id)}
                  onCancel={() => handleCancel(card.id)}
                  onTopUp={() => setShowTopUp(card)}
                  onReveal={() => setShowReveal(card)}
                  actionLoading={actionLoading === card.id} />
              ))}
            </div>

            {/* Transactions Column */}
            <div>
              <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">Transazioni</h2>
              {!selectedCard ? (
                <div className="text-center py-12 text-gray-500 text-sm">Seleziona una carta per vedere le transazioni</div>
              ) : txLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-pink-500 animate-spin" /></div>
              ) : transactions.length === 0 ? (
                <div className="text-center py-12 text-gray-500 text-sm">Nessuna transazione</div>
              ) : (
                <div className="space-y-2">
                  {transactions.map(tx => (
                    <div key={tx.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`p-1.5 rounded-lg ${tx.type === 'top_up' ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                            {tx.type === 'top_up' ? <ArrowUpRight className="w-3.5 h-3.5 text-green-400" /> : <CreditCard className="w-3.5 h-3.5 text-red-400" />}
                          </div>
                          <div>
                            <div className="text-white text-sm font-medium">{tx.type === 'top_up' ? 'Top-Up' : 'Pagamento'}</div>
                            <div className="text-gray-500 text-xs">{tx.crypto_amount} {tx.crypto_asset} @ €{tx.conversion_rate?.toLocaleString()}</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`font-medium text-sm ${tx.type === 'top_up' ? 'text-green-400' : 'text-red-400'}`}>
                            {tx.type === 'top_up' ? '+' : '-'}€{tx.fiat_amount?.toFixed(2)}
                          </div>
                          <div className="text-gray-500 text-xs">
                            {tx.created_at ? new Date(tx.created_at).toLocaleDateString('it-IT') : ''}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Create Card Modal */}
      {showCreate && <CreateCardModal onClose={() => setShowCreate(false)} onSuccess={() => { setShowCreate(false); fetchCards(); setSuccess('Carta creata con successo!'); setTimeout(() => setSuccess(''), 3000); }} />}

      {/* Top-Up Modal */}
      {showTopUp && <TopUpModal card={showTopUp} onClose={() => setShowTopUp(null)} onSuccess={() => { setShowTopUp(null); fetchCards(); if (selectedCard) loadTransactions(selectedCard); setSuccess('Top-up completato!'); setTimeout(() => setSuccess(''), 3000); }} />}
      {showReveal && <CardRevealModal card={showReveal} onClose={() => setShowReveal(null)} />}
    </div>
  );
}

function CardVisual({ card, isSelected, onSelect, onFreeze, onCancel, onTopUp, onReveal, actionLoading }) {
  const network = NETWORK_STYLES[card.card_network] || NETWORK_STYLES.visa;
  const statusBadge = STATUS_COLORS[card.status] || STATUS_COLORS.active;

  return (
    <div className={`rounded-xl overflow-hidden transition-all cursor-pointer ${isSelected ? 'ring-2 ring-pink-500' : ''}`}
      onClick={onSelect} data-testid={`card-${card.id}`}>
      {/* Card Visual */}
      <div className={`bg-gradient-to-br ${network.color} p-5 relative`}>
        <div className="flex items-center justify-between mb-6">
          <span className={`px-2 py-0.5 rounded text-xs font-medium border ${statusBadge}`}>{card.status}</span>
          <span className="text-white/70 text-xs font-mono uppercase">{network.label}</span>
        </div>
        <div className="text-white font-mono text-lg tracking-widest mb-4">{card.card_number_masked}</div>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-white/60 text-xs">Saldo</div>
            <div className="text-white text-xl font-bold">€{(card.balance || 0).toFixed(2)}</div>
          </div>
          <div className="text-right">
            <div className="text-white/60 text-xs">{card.card_type === 'virtual' ? 'Virtuale' : 'Fisica'}</div>
            <div className="text-white/70 text-xs">
              Scade {card.expires_at ? new Date(card.expires_at).toLocaleDateString('it-IT', { month: '2-digit', year: '2-digit' }) : 'N/A'}
            </div>
          </div>
        </div>
      </div>
      {/* Actions */}
      <div className="bg-gray-900 border border-gray-800 border-t-0 rounded-b-xl p-3">
        {/* Shipping info for physical cards */}
        {card.card_type === 'physical' && card.tracking_number && (
          <div className="mb-2 p-2 bg-yellow-500/5 border border-yellow-500/20 rounded-lg text-xs" data-testid={`shipping-${card.id}`}>
            <div className="flex justify-between items-center">
              <span className="text-yellow-400 font-medium">Spedizione: {card.shipping_status || 'processing'}</span>
              <span className="text-gray-400 font-mono">{card.tracking_number}</span>
            </div>
            {card.estimated_delivery && <div className="text-gray-500 mt-0.5">Consegna: {card.estimated_delivery}</div>}
          </div>
        )}
        <div className="flex gap-2">
        <button onClick={(e) => { e.stopPropagation(); onReveal(); }}
          data-testid={`reveal-card-${card.id}`}
          className="flex-1 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors">
          <Eye className="w-3 h-3" /> Reveal
        </button>
        <button onClick={(e) => { e.stopPropagation(); onTopUp(); }}
          data-testid={`topup-card-${card.id}`}
          className="flex-1 py-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors">
          <Wallet className="w-3 h-3" /> Top-Up
        </button>
        <button onClick={(e) => { e.stopPropagation(); onFreeze(); }} disabled={actionLoading}
          data-testid={`freeze-card-${card.id}`}
          className="flex-1 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors">
          {card.status === 'frozen' ? <><Unlock className="w-3 h-3" /> Sblocca</> : <><Snowflake className="w-3 h-3" /> Congela</>}
        </button>
        <button onClick={(e) => { e.stopPropagation(); onCancel(); }} disabled={actionLoading}
          className="py-1.5 px-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg text-xs transition-colors">
          <X className="w-3 h-3" />
        </button>
        </div>
      </div>
    </div>
  );
}

function CreateCardModal({ onClose, onSuccess }) {
  const [cardType, setCardType] = useState('virtual');
  const [network, setNetwork] = useState('visa');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [address, setAddress] = useState({ line1: '', city: '', zip: '', country: 'IT' });

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      const body = { card_type: cardType, card_network: network, currency: 'EUR' };
      if (cardType === 'physical') {
        if (!address.line1 || !address.city || !address.zip) {
          throw new Error('Compila tutti i campi dell\'indirizzo');
        }
        body.shipping_address = address;
      }
      const res = await xhrFetchJson(`${BACKEND_URL}/api/cards/create`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body)
      });
      if (!res.ok) {
        throw new Error(res.data?.detail || 'Errore nella creazione');
      }
      onSuccess();
    } catch (e) { setError(e.message); }
    finally { setCreating(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-md w-full" data-testid="create-card-modal">
        <h3 className="text-lg font-bold text-white mb-4">Nuova Carta</h3>

        {error && <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">{error}</div>}

        <div className="space-y-4 mb-6">
          <div>
            <label className="text-gray-400 text-sm mb-2 block">Tipo Carta</label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { id: 'virtual', label: 'Virtuale', desc: 'Gratis - Pagamenti online', fee: '€0' },
                { id: 'physical', label: 'Fisica', desc: 'POS, ATM, spedizione', fee: '€9.99 + €14.99 spedizione' },
              ].map(t => (
                <button key={t.id} onClick={() => setCardType(t.id)}
                  className={`p-3 rounded-xl border text-left transition-all ${cardType === t.id ? 'border-pink-500 bg-pink-500/10' : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'}`}>
                  <div className="text-white font-medium text-sm">{t.label}</div>
                  <div className="text-gray-400 text-xs">{t.desc}</div>
                  <div className="text-pink-400 text-xs mt-1">{t.fee}</div>
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-gray-400 text-sm mb-2 block">Circuito</label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { id: 'visa', label: 'Visa' },
                { id: 'mastercard', label: 'Mastercard' },
              ].map(n => (
                <button key={n.id} onClick={() => setNetwork(n.id)}
                  className={`p-3 rounded-xl border text-center transition-all ${network === n.id ? 'border-pink-500 bg-pink-500/10' : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'}`}>
                  <div className="text-white font-medium text-sm">{n.label}</div>
                </button>
              ))}
            </div>
          </div>

          {cardType === 'physical' && (
            <div data-testid="shipping-address-form">
              <label className="text-gray-400 text-sm mb-2 block">Indirizzo di Spedizione</label>
              <div className="space-y-2">
                <input type="text" placeholder="Via e numero civico" value={address.line1}
                  onChange={e => setAddress({...address, line1: e.target.value})}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-pink-500 focus:outline-none" />
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" placeholder="Citta'" value={address.city}
                    onChange={e => setAddress({...address, city: e.target.value})}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-pink-500 focus:outline-none" />
                  <input type="text" placeholder="CAP" value={address.zip}
                    onChange={e => setAddress({...address, zip: e.target.value})}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-pink-500 focus:outline-none" />
                </div>
                <select value={address.country} onChange={e => setAddress({...address, country: e.target.value})}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm">
                  <option value="IT">Italia</option><option value="DE">Germania</option><option value="FR">Francia</option>
                  <option value="ES">Spagna</option><option value="GB">Regno Unito</option><option value="US">Stati Uniti</option>
                  <option value="CH">Svizzera</option><option value="AT">Austria</option>
                </select>
              </div>
            </div>
          )}
        </div>

        <button onClick={handleCreate} disabled={creating}
          data-testid="confirm-create-card"
          className="w-full py-2.5 bg-gradient-to-r from-pink-500 to-purple-500 hover:from-pink-600 hover:to-purple-600 text-white rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2">
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Crea Carta</>}
        </button>
        <button onClick={onClose} className="w-full mt-2 py-2 text-gray-400 hover:text-white text-sm transition-colors">Annulla</button>
      </div>
    </div>
  );
}

function TopUpModal({ card, onClose, onSuccess }) {
  const [asset, setAsset] = useState('BTC');
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleTopUp = async () => {
    if (!amount || parseFloat(amount) <= 0) return;
    setLoading(true);
    setError('');
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}/api/cards/${card.id}/top-up`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ amount_crypto: parseFloat(amount), crypto_asset: asset })
      });
      if (!res.ok) {
        throw new Error(res.data?.detail || 'Errore nel top-up');
      }
      onSuccess();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-md w-full" data-testid="topup-modal">
        <h3 className="text-lg font-bold text-white mb-1">Top-Up Carta</h3>
        <p className="text-gray-400 text-sm mb-4">{card.card_number_masked} | Saldo: €{(card.balance || 0).toFixed(2)}</p>

        {error && <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">{error}</div>}

        <div className="space-y-4 mb-6">
          <div>
            <label className="text-gray-400 text-sm mb-2 block">Asset Crypto</label>
            <div className="grid grid-cols-3 gap-2">
              {CRYPTO_OPTIONS.map(c => (
                <button key={c.symbol} onClick={() => setAsset(c.symbol)}
                  className={`p-2 rounded-lg border text-center text-sm transition-all ${asset === c.symbol ? 'border-green-500 bg-green-500/10 text-green-400' : 'border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600'}`}>
                  {c.symbol}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-gray-400 text-sm mb-2 block">Importo ({asset})</label>
            <input type="number" step="0.0001" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              data-testid="topup-amount"
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-green-500 focus:outline-none" />
          </div>
        </div>

        <button onClick={handleTopUp} disabled={loading || !amount}
          data-testid="confirm-topup"
          className="w-full py-2.5 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Conferma Top-Up</>}
        </button>
        <button onClick={onClose} className="w-full mt-2 py-2 text-gray-400 hover:text-white text-sm transition-colors">Annulla</button>
      </div>
    </div>
  );
}

function CardRevealModal({ card, onClose }) {
  const [otpCode, setOtpCode] = useState('');
  const [revealed, setRevealed] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);

  useEffect(() => {
    if (countdown > 0) {
      const t = setTimeout(() => setCountdown(c => c - 1), 1000);
      return () => clearTimeout(t);
    } else if (countdown === 0 && revealed) {
      setRevealed(null);
    }
  }, [countdown, revealed]);

  const handleReveal = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await xhrFetchJson(`${BACKEND_URL}/api/card-engine/reveal`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ card_id: card.id, otp_code: otpCode, otp_verified: otpCode.length === 6 })
      });
      if (!res.ok) throw new Error(res.data?.detail || 'Errore nel reveal');
      setRevealed(res.data);
      setCountdown(res.data.expires_in_seconds || 60);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" data-testid="reveal-modal">
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Lock className="w-5 h-5 text-amber-400" /> Secure Card Reveal
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        {!revealed ? (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">Inserisci il codice 2FA a 6 cifre per vedere i dati completi della carta.</p>
            <div>
              <label className="text-gray-400 text-sm mb-1 block">Codice 2FA (OTP)</label>
              <input type="text" maxLength={6} value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                data-testid="otp-input"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white text-center tracking-[0.5em] text-xl font-mono focus:border-amber-500 focus:outline-none" />
            </div>
            {error && <div className="text-red-400 text-sm bg-red-500/10 rounded-lg p-2">{error}</div>}
            <button onClick={handleReveal} disabled={loading || otpCode.length !== 6}
              data-testid="confirm-reveal"
              className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white rounded-lg font-bold text-sm transition-all disabled:opacity-50">
              {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Rivela Carta'}
            </button>
          </div>
        ) : (
          <div className="space-y-4" data-testid="revealed-card-data">
            <div className="bg-gradient-to-br from-amber-900/30 to-orange-900/30 border border-amber-500/30 rounded-xl p-4 space-y-3">
              <div>
                <div className="text-[10px] text-amber-400/70 mb-0.5">Numero Carta (PAN)</div>
                <div className="text-white font-mono text-lg tracking-widest" data-testid="revealed-pan">
                  {revealed.pan?.replace(/(\d{4})/g, '$1 ').trim()}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[10px] text-amber-400/70 mb-0.5">CVV</div>
                  <div className="text-white font-mono text-lg" data-testid="revealed-cvv">{revealed.cvv}</div>
                </div>
                <div>
                  <div className="text-[10px] text-amber-400/70 mb-0.5">Scadenza</div>
                  <div className="text-white font-mono text-lg" data-testid="revealed-expiry">{revealed.expiry}</div>
                </div>
              </div>
              <div className="text-[10px] text-amber-400/70">
                Titolare: <span className="text-white">{revealed.cardholder}</span>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-amber-400">Dati visibili per {countdown}s</span>
              <span className="text-zinc-500">Provider: {revealed.provider}</span>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5">
              <div className="bg-amber-500 h-full rounded-full transition-all" style={{ width: `${(countdown / 60) * 100}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

