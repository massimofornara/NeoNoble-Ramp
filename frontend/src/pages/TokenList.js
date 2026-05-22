import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Coins, Plus, Search, Loader2, ChevronRight,
  ListChecks, Check, Clock, X, AlertCircle
} from 'lucide-react';
import { xhrGet, xhrPost, BACKEND_URL } from '../utils/safeFetch';

const STATUS_BADGES = {
  pending: { color: 'bg-yellow-500/20 text-yellow-400', label: 'In Attesa' },
  approved: { color: 'bg-green-500/20 text-green-400', label: 'Approvato' },
  rejected: { color: 'bg-red-500/20 text-red-400', label: 'Rifiutato' },
  live: { color: 'bg-emerald-500/20 text-emerald-400', label: 'Live' },
  paused: { color: 'bg-gray-500/20 text-gray-400', label: 'In Pausa' },
};

const CHAIN_LABELS = {
  ethereum: 'Ethereum', bsc: 'BNB Chain', polygon: 'Polygon',
  arbitrum: 'Arbitrum', base: 'Base',
};

export default function TokenList() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [loading, setLoading] = useState(true);
  const [tokens, setTokens] = useState([]);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [listingModal, setListingModal] = useState(null);
  const [listingLoading, setListingLoading] = useState(false);
  const [listingError, setListingError] = useState('');
  const [listingSuccess, setListingSuccess] = useState('');

  const fetchTokens = useCallback(async () => {
    setLoading(true);
    try {
      let url = `${BACKEND_URL}/api/tokens/list?page_size=50`;
      if (filter === 'my') url += `&creator_id=${user?.id}`;
      else if (filter !== 'all') url += `&status=${filter}`;
      const data = await xhrGet(url);
      setTokens(data.tokens || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [filter, user?.id]);

  useEffect(() => { fetchTokens(); }, [filter]);

  const handleRequestListing = async (tokenId, listingType) => {
    setListingLoading(true); setListingError(''); setListingSuccess('');
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/tokens/listings/create`, {
        token_id: tokenId, listing_type: listingType, requested_pairs: ['EUR', 'USD', 'USDT'],
      });
      if (!ok) throw new Error(data.detail || 'Errore nella richiesta listing');
      setListingSuccess(`Listing richiesto con successo! Fee: €${data.listing_fee}`);
      setTimeout(() => { setListingModal(null); setListingSuccess(''); }, 2000);
    } catch (e) {
      setListingError(e.message);
    } finally {
      setListingLoading(false);
    }
  };

  const filteredTokens = tokens.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.symbol.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-950" data-testid="token-list-page">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <Coins className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">Token Marketplace</h1>
                <p className="text-gray-400 text-sm">Esplora e gestisci token</p>
              </div>
            </div>
            <button onClick={() => navigate('/tokens/create')}
              data-testid="create-token-nav-btn"
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium text-sm transition-all">
              <Plus className="w-4 h-4" /> Crea Token
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input type="text" placeholder="Cerca token..." value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none" />
          </div>
          <div className="flex gap-2">
            {[
              { id: 'all', label: 'Tutti' },
              { id: 'my', label: 'I Miei' },
              { id: 'live', label: 'Live' },
              { id: 'pending', label: 'In Attesa' },
            ].map(f => (
              <button key={f.id} onClick={() => setFilter(f.id)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === f.id ? 'bg-purple-500 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}>{f.label}</button>
            ))}
          </div>
        </div>

        {/* Token Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
          </div>
        ) : filteredTokens.length === 0 ? (
          <div className="text-center py-20">
            <Coins className="w-14 h-14 text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">Nessun Token</h3>
            <p className="text-gray-400 mb-6 text-sm">
              {filter === 'my' ? "Non hai ancora creato nessun token." : "Nessun token trovato."}
            </p>
            <button onClick={() => navigate('/tokens/create')}
              className="px-5 py-2.5 bg-purple-500 hover:bg-purple-600 text-white rounded-lg font-medium text-sm transition-colors">
              Crea il tuo primo Token
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTokens.map(t => (
              <TokenCard key={t.id} token={t} onRequestListing={() => setListingModal(t)} />
            ))}
          </div>
        )}
      </main>

      {/* Listing Request Modal */}
      {listingModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-md w-full" data-testid="listing-modal">
            <h3 className="text-lg font-bold text-white mb-2">Richiedi Listing</h3>
            <p className="text-gray-400 text-sm mb-4">
              Token: <span className="text-purple-400 font-medium">{listingModal.name} (${listingModal.symbol})</span>
            </p>

            {listingError && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <p className="text-red-400 text-sm">{listingError}</p>
              </div>
            )}
            {listingSuccess && (
              <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2">
                <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                <p className="text-green-400 text-sm">{listingSuccess}</p>
              </div>
            )}

            <div className="space-y-3 mb-6">
              {[
                { type: 'standard', name: 'Standard', fee: '€500', desc: 'Listing base con 3 trading pairs' },
                { type: 'premium', name: 'Premium', fee: '€2.000', desc: 'Visibilità avanzata + supporto dedicato' },
                { type: 'featured', name: 'Featured', fee: '€5.000', desc: 'Massima visibilità + promozione' },
              ].map(opt => (
                <button key={opt.type} onClick={() => handleRequestListing(listingModal.id, opt.type)}
                  disabled={listingLoading}
                  data-testid={`listing-type-${opt.type}`}
                  className="w-full p-4 bg-gray-800/50 hover:bg-gray-800 border border-gray-700 hover:border-purple-500/50 rounded-xl text-left transition-all">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-white font-medium">{opt.name}</span>
                    <span className="text-purple-400 font-bold">{opt.fee}</span>
                  </div>
                  <p className="text-gray-400 text-xs">{opt.desc}</p>
                </button>
              ))}
            </div>

            <div className="text-gray-500 text-xs mb-4">
              Pairs incluse: EUR, USD, USDT. Il pagamento sara' richiesto dopo l'approvazione admin.
            </div>

            <button onClick={() => { setListingModal(null); setListingError(''); setListingSuccess(''); }}
              className="w-full py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">
              Annulla
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function TokenCard({ token, onRequestListing }) {
  const status = STATUS_BADGES[token.status] || STATUS_BADGES.pending;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-all"
      data-testid={`token-card-${token.symbol}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">{token.symbol.charAt(0)}</span>
          </div>
          <div>
            <h3 className="text-white font-semibold text-sm">{token.name}</h3>
            <p className="text-gray-500 text-xs">${token.symbol}</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${status.color}`}>
          {status.label}
        </span>
      </div>

      <div className="space-y-1.5 mb-4">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Prezzo</span>
          <span className="text-white">€{token.current_price?.toLocaleString()}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Supply</span>
          <span className="text-white">{token.total_supply?.toLocaleString()}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Chain</span>
          <span className="text-white">{CHAIN_LABELS[token.chain] || token.chain}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Trading Pairs</span>
          <span className="text-white">{token.trading_pairs_count || 0}</span>
        </div>
      </div>

      {/* Actions based on status */}
      <div className="pt-3 border-t border-gray-800">
        {(token.status === 'approved' || token.status === 'live') && (
          <button onClick={(e) => { e.stopPropagation(); onRequestListing(); }}
            data-testid={`request-listing-${token.symbol}`}
            className="w-full py-2 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1.5">
            <ListChecks className="w-3.5 h-3.5" /> Richiedi Listing
          </button>
        )}
        {token.status === 'pending' && (
          <div className="flex items-center justify-center gap-1.5 text-yellow-400 text-sm">
            <Clock className="w-3.5 h-3.5" /> In attesa di approvazione
          </div>
        )}
        {token.status === 'rejected' && (
          <div className="flex items-center justify-center gap-1.5 text-red-400 text-sm">
            <X className="w-3.5 h-3.5" /> Rifiutato
          </div>
        )}
      </div>
    </div>
  );
}
