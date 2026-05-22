import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft, Code, Copy, Check, ExternalLink,
  Globe, Key, Shield, Zap, BookOpen
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const ENDPOINTS = [
  { method: 'GET', path: '/api/public/v1/market/coins', desc: 'Dati di mercato per 30+ criptovalute', params: 'vs_currency=eur&limit=32', auth: false },
  { method: 'GET', path: '/api/public/v1/market/ticker/{pair_id}', desc: 'Ticker per una coppia di trading', params: 'pair_id=BTC-EUR', auth: false },
  { method: 'GET', path: '/api/public/v1/market/orderbook/{pair_id}', desc: 'Order book con livelli bid/ask', params: 'pair_id=BTC-EUR&depth=20', auth: false },
  { method: 'GET', path: '/api/public/v1/market/candles/{pair_id}', desc: 'Dati candlestick OHLCV', params: 'pair_id=BTC-EUR&interval=1h&limit=100', auth: false },
  { method: 'GET', path: '/api/public/v1/market/trades/{pair_id}', desc: 'Trade recenti', params: 'pair_id=BTC-EUR&limit=50', auth: false },
  { method: 'GET', path: '/api/public/v1/tokens', desc: 'Token della piattaforma', params: '', auth: false },
  { method: 'GET', path: '/api/public/v1/pairs', desc: 'Coppie di trading disponibili', params: '', auth: false },
];

const RATE_LIMITS = [
  { tier: 'Free', limit: '100 req/ora', color: 'text-gray-400' },
  { tier: 'Basic', limit: '1.000 req/ora', color: 'text-blue-400' },
  { tier: 'Pro', limit: '10.000 req/ora', color: 'text-purple-400' },
];

export default function ApiDocs() {
  const navigate = useNavigate();
  const [copied, setCopied] = useState('');

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(''), 2000);
  };

  return (
    <div className="min-h-screen bg-gray-950" data-testid="api-docs-page">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-lg">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-gray-800 rounded-lg"><ArrowLeft className="w-5 h-5 text-gray-400" /></button>
          <div className="p-2 bg-blue-500/20 rounded-lg"><Code className="w-5 h-5 text-blue-400" /></div>
          <div>
            <h1 className="text-lg font-bold text-white">API Documentation</h1>
            <p className="text-gray-400 text-xs">NeoNoble Ramp Public API v1</p>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Overview */}
        <section className="mb-10">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <Globe className="w-8 h-8 text-blue-400 mb-3" />
              <h3 className="text-white font-semibold mb-1">REST API</h3>
              <p className="text-gray-400 text-sm">Accedi a market data, order book, token e trading pairs</p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <Key className="w-8 h-8 text-purple-400 mb-3" />
              <h3 className="text-white font-semibold mb-1">Autenticazione</h3>
              <p className="text-gray-400 text-sm">Header X-API-Key con la tua chiave API</p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <Zap className="w-8 h-8 text-yellow-400 mb-3" />
              <h3 className="text-white font-semibold mb-1">Rate Limiting</h3>
              <p className="text-gray-400 text-sm">Da 100 a 10.000 req/ora in base al piano</p>
            </div>
          </div>
        </section>

        {/* Base URL */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-white mb-3">Base URL</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 flex items-center justify-between">
            <code className="text-green-400 text-sm">{BACKEND_URL}/api/public/v1</code>
            <button onClick={() => handleCopy(`${BACKEND_URL}/api/public/v1`)}
              className="p-1.5 hover:bg-gray-800 rounded transition-colors">
              {copied === `${BACKEND_URL}/api/public/v1` ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-gray-400" />}
            </button>
          </div>
        </section>

        {/* Auth */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-white mb-3">Autenticazione</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <p className="text-gray-300 text-sm mb-3">Includi la tua API key nell'header di ogni richiesta:</p>
            <div className="bg-gray-800 rounded-lg px-4 py-2 flex items-center justify-between">
              <code className="text-yellow-400 text-sm">X-API-Key: your_api_key_here</code>
              <button onClick={() => handleCopy('X-API-Key: your_api_key_here')} className="p-1.5 hover:bg-gray-700 rounded"><Copy className="w-3 h-3 text-gray-400" /></button>
            </div>
            <p className="text-gray-500 text-xs mt-2">
              Genera le tue API key nel <Link to="/dev" className="text-blue-400 hover:underline">Developer Portal</Link>
            </p>
          </div>
        </section>

        {/* Rate Limits */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-white mb-3">Rate Limits</h2>
          <div className="grid grid-cols-3 gap-3">
            {RATE_LIMITS.map(r => (
              <div key={r.tier} className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-center">
                <div className={`text-lg font-bold ${r.color}`}>{r.tier}</div>
                <div className="text-white text-sm mt-1">{r.limit}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Endpoints */}
        <section>
          <h2 className="text-lg font-semibold text-white mb-4">Endpoints</h2>
          <div className="space-y-4">
            {ENDPOINTS.map((ep, i) => (
              <EndpointCard key={i} endpoint={ep} onCopy={handleCopy} copied={copied} />
            ))}
          </div>
        </section>

        {/* Card Issuer Partners */}
        <section className="mt-12 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Card Issuing Partners</h2>
          <p className="text-gray-400 text-sm mb-4">
            Per l'emissione di carte reali Visa/Mastercard, NeoNoble Ramp e' predisposta per l'integrazione con i seguenti partner issuer:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { name: 'Marqeta', desc: 'Piattaforma leader per card issuing programmabile. Supporta carte virtuali e fisiche, controlli in tempo reale, multi-valuta.', url: 'https://www.marqeta.com', features: ['API RESTful completa', 'Carte Visa/Mastercard', 'JIT Funding', 'Controlli spesa real-time'] },
              { name: 'Stripe Issuing', desc: 'Emissione carte integrata nell\'ecosistema Stripe. Ideale per MVP rapido con infrastruttura pagamenti esistente.', url: 'https://stripe.com/issuing', features: ['Setup rapido', 'Dashboard gestione', 'Carte virtuali instant', 'Integrazione Stripe'] },
              { name: 'Wallester', desc: 'Piattaforma EU-regulated per programmi carte white-label. Supporta BIN sponsorship e compliance europea.', url: 'https://wallester.com', features: ['EU Regulated', 'White-label', 'Multi-currency', 'Compliance SEPA'] },
              { name: 'Highnote', desc: 'Piattaforma unificata per card issuing enterprise con BIN globali e compliance integrata.', url: 'https://www.highnote.com', features: ['BIN globali', 'Compliance integrata', 'Single API', 'Enterprise-grade'] },
              { name: 'Railsbank (Weavr)', desc: 'Neo-banking e card issuing con pre-built UI kits. Permette lancio rapido senza licenza bancaria propria.', url: 'https://www.weavr.io', features: ['Pre-built UI', 'No licenza richiesta', 'BaaS completo', 'Lancio rapido'] },
              { name: 'NIUM', desc: 'Infrastruttura globale per pagamenti e carte. Supporta SWIFT, API, e formati multi-payment internazionali.', url: 'https://www.nium.com', features: ['Copertura globale', 'Multi-payment', 'SWIFT integrato', 'Scalabilita\' enterprise'] },
            ].map(partner => (
              <div key={partner.name} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-white font-semibold">{partner.name}</h3>
                  <a href={partner.url} target="_blank" rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs">
                    Sito <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <p className="text-gray-400 text-sm mb-3">{partner.desc}</p>
                <div className="flex flex-wrap gap-1.5">
                  {partner.features.map(f => (
                    <span key={f} className="px-2 py-0.5 bg-gray-800 text-gray-300 rounded text-xs">{f}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function EndpointCard({ endpoint, onCopy, copied }) {
  const [expanded, setExpanded] = useState(false);
  const fullUrl = `${BACKEND_URL}${endpoint.path}${endpoint.params ? '?' + endpoint.params : ''}`;
  const curlCmd = `curl -s "${fullUrl}" -H "X-API-Key: YOUR_KEY"`;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden" data-testid={`endpoint-${endpoint.path.split('/').pop()}`}>
      <button onClick={() => setExpanded(!expanded)} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-800/50 transition-colors">
        <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs font-mono font-bold">{endpoint.method}</span>
        <code className="text-white text-sm font-mono flex-1 text-left">{endpoint.path}</code>
        <span className="text-gray-400 text-xs">{endpoint.desc}</span>
      </button>
      {expanded && (
        <div className="px-4 py-3 border-t border-gray-800 bg-gray-800/20">
          <div className="mb-2 text-gray-400 text-xs">Esempio cURL:</div>
          <div className="bg-gray-800 rounded-lg px-3 py-2 flex items-center justify-between">
            <code className="text-green-400 text-xs break-all">{curlCmd}</code>
            <button onClick={() => onCopy(curlCmd)} className="p-1 ml-2 flex-shrink-0">
              {copied === curlCmd ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3 text-gray-400" />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
