import React, { useCallback, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { X, ExternalLink, Loader2, ArrowRight } from 'lucide-react';

const TRANSAK_API_KEY = process.env.REACT_APP_TRANSAK_API_KEY || '5911d9ec-46b5-48b0-a4c8-0b67aa60baae';
const TRANSAK_BASE = 'https://global-stg.transak.com';

/**
 * Transak On/Off-Ramp Widget — popup-based integration.
 *
 * Opens Transak in a popup window (recommended pattern for KYC flows).
 * Bypasses X-Frame-Options restrictions.
 * Default crypto: BNB on BSC. Users convert BNB → NENO on the platform.
 */
export default function TransakWidget({ isOpen, onClose, initialMode = 'BUY' }) {
  const { user } = useAuth();
  const [launched, setLaunched] = useState(false);

  const buildUrl = useCallback(() => {
    const params = new URLSearchParams({
      apiKey: TRANSAK_API_KEY,
      productsAvailed: initialMode,
      defaultCryptoCurrency: 'BNB',
      cryptoCurrencyList: 'BNB,ETH,USDT,USDC,BTC,MATIC',
      network: 'bsc',
      defaultNetwork: 'bsc',
      networks: 'bsc,ethereum,polygon',
      defaultFiatCurrency: 'EUR',
      themeColor: '7c3aed',
      colorMode: 'DARK',
      hideMenu: 'true',
      exchangeScreenTitle: initialMode === 'BUY' ? 'Buy Crypto — NeoNoble Ramp' : 'Sell Crypto — NeoNoble Ramp',
      referrerDomain: window.location.origin,
    });
    if (user?.email) params.set('email', user.email);
    return `${TRANSAK_BASE}?${params.toString()}`;
  }, [initialMode, user]);

  const handleLaunch = useCallback(() => {
    const url = buildUrl();
    const w = 480;
    const h = 680;
    const left = (window.screen.width - w) / 2;
    const top = (window.screen.height - h) / 2;
    window.open(
      url,
      'transak_widget',
      `width=${w},height=${h},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,resizable=yes`
    );
    setLaunched(true);
  }, [buildUrl]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl overflow-hidden shadow-2xl"
        data-testid="transak-widget-modal">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <span className="text-white font-semibold">
            {initialMode === 'BUY' ? 'Acquista Crypto' : 'Vendi Crypto'}
          </span>
          <button onClick={onClose} data-testid="transak-close-btn"
            className="p-1.5 hover:bg-gray-800 rounded-lg transition-colors">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-5">
          {/* Transak Logo */}
          <div className="flex items-center justify-center py-3">
            <div className="bg-gradient-to-r from-blue-500 to-purple-600 text-white font-bold text-2xl px-6 py-3 rounded-xl shadow-lg shadow-purple-500/20">
              Transak
            </div>
          </div>

          {/* Info */}
          <div className="space-y-3 text-center">
            <h3 className="text-white font-medium">
              {initialMode === 'BUY'
                ? 'Acquista crypto con carta o bonifico'
                : 'Vendi crypto e ricevi EUR'}
            </h3>
            <p className="text-gray-400 text-sm">
              {initialMode === 'BUY'
                ? 'Acquista BNB, ETH, USDT o BTC via Transak. Poi converti in $NENO dalla sezione Wallet della piattaforma.'
                : 'Vendi i tuoi crypto e ricevi EUR direttamente sul tuo conto bancario.'}
            </p>
          </div>

          {/* Supported assets */}
          <div className="bg-gray-800/50 rounded-xl p-3">
            <div className="text-gray-400 text-xs mb-2 text-center">Crypto disponibili</div>
            <div className="flex justify-center gap-2 flex-wrap">
              {['BNB', 'ETH', 'USDT', 'BTC', 'USDC', 'MATIC'].map(c => (
                <span key={c} className="px-3 py-1 bg-gray-700/50 text-gray-300 rounded-full text-xs font-mono">{c}</span>
              ))}
            </div>
          </div>

          {/* Conversion flow info */}
          <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-3">
            <div className="flex items-center justify-center gap-2 text-xs text-purple-300">
              <span className="font-medium">Transak</span>
              <ArrowRight className="w-3 h-3" />
              <span>BNB / ETH</span>
              <ArrowRight className="w-3 h-3" />
              <span className="font-medium">Converti in $NENO</span>
            </div>
          </div>

          {/* Launch button */}
          {!launched ? (
            <button onClick={handleLaunch} data-testid="transak-launch-btn"
              className="w-full py-3 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-purple-500/20">
              <ExternalLink className="w-4 h-4" />
              {initialMode === 'BUY' ? 'Apri Transak — Acquista' : 'Apri Transak — Vendi'}
            </button>
          ) : (
            <div className="text-center space-y-3">
              <div className="flex items-center justify-center gap-2 text-green-400 text-sm">
                <Loader2 className="w-4 h-4 animate-spin" />
                Transak aperto in una nuova finestra
              </div>
              <button onClick={handleLaunch} className="text-purple-400 text-xs hover:text-purple-300 underline">
                Riapri Transak
              </button>
            </div>
          )}

          {/* Payment methods */}
          <div className="flex items-center justify-center gap-3 pt-2 opacity-60">
            <span className="text-gray-500 text-[10px]">Visa</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-500 text-[10px]">Mastercard</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-500 text-[10px]">SEPA</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-500 text-[10px]">Apple Pay</span>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-gray-800 text-center">
          <span className="text-gray-500 text-[10px]">
            Powered by Transak — Sicuro & Regolamentato — 170+ Paesi supportati
          </span>
        </div>
      </div>
    </div>
  );
}
