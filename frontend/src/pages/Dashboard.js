import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { rampApi } from '../api';
import TransakWidget from '../components/TransakWidget';
import NenoTradingWidget from '../components/NenoTradingWidget';
import { WalletConnectButton, ChainSelector } from '../components/WalletConnect';
import { useWeb3 } from '../context/Web3Context';
import NotificationBell from '../components/NotificationBell';
import { useBrowserPush } from '../hooks/useBrowserPush';
import {
  Coins, ArrowUpRight, ArrowDownRight, RefreshCw, History,
  Wallet, Building, LogOut, ChevronRight, Loader2, CheckCircle,
  AlertCircle, TrendingUp, CreditCard, BarChart3, Shield, ArrowRightLeft,
  PieChart, Settings, Activity, Plus
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

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

const POPULAR_CRYPTOS = ['BTC', 'ETH', 'NENO', 'USDT', 'SOL', 'BNB'];

export default function Dashboard() {
  const { user, logout, isDeveloper } = useAuth();
  const navigate = useNavigate();
  useBrowserPush();
  
  const [activeTab, setActiveTab] = useState('onramp');
  const [prices, setPrices] = useState({});
  const [transactions, setTransactions] = useState([]);
  const [loadingPrices, setLoadingPrices] = useState(true);
  
  // Custom tokens state
  const [myTokens, setMyTokens] = useState([]);
  const [loadingMyTokens, setLoadingMyTokens] = useState(true);
  const [liveBalances, setLiveBalances] = useState({});
  const balancePollRef = useRef(null);
  
  // Form states
  const [fiatAmount, setFiatAmount] = useState('');
  const [cryptoAmount, setCryptoAmount] = useState('');
  const [selectedCrypto, setSelectedCrypto] = useState('BTC');
  const [walletAddress, setWalletAddress] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  
  // Quote states
  const [quote, setQuote] = useState(null);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Transak widget states
  const [transakOpen, setTransakOpen] = useState(false);
  const [transakMode, setTransakMode] = useState('BUY');
  
  // NENO Trading widget state
  const [showNenoTrading, setShowNenoTrading] = useState(false);

  useEffect(() => {
    loadPrices();
    loadTransactions();
    loadMyTokens();
    loadLiveBalances();
    balancePollRef.current = setInterval(loadLiveBalances, 5000);
    return () => clearInterval(balancePollRef.current);
  }, []);

  const loadMyTokens = async () => {
    setLoadingMyTokens(true);
    const res = await xhrGet(`${BACKEND_URL}/api/neno-exchange/my-tokens`);
    if (res.ok) setMyTokens(res.data.tokens || []);
    setLoadingMyTokens(false);
  };

  const loadLiveBalances = async () => {
    const res = await xhrGet(`${BACKEND_URL}/api/neno-exchange/live-balances`);
    if (res.ok) setLiveBalances(res.data.balances || {});
  };

  const loadPrices = async () => {
    try {
      const data = await rampApi.getPrices();
      setPrices(data.prices || {});
    } catch (err) {
      console.error('Failed to load prices:', err);
    } finally {
      setLoadingPrices(false);
    }
  };

  const loadTransactions = async () => {
    try {
      const data = await rampApi.getTransactions();
      setTransactions(data || []);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    }
  };

  const getQuote = async () => {
    setError('');
    setQuote(null);
    setLoadingQuote(true);

    try {
      if (activeTab === 'onramp') {
        if (!fiatAmount || parseFloat(fiatAmount) <= 0) {
          throw new Error('Please enter a valid EUR amount');
        }
        const data = await rampApi.createOnrampQuote(parseFloat(fiatAmount), selectedCrypto);
        setQuote(data);
      } else {
        if (!cryptoAmount || parseFloat(cryptoAmount) <= 0) {
          throw new Error('Please enter a valid crypto amount');
        }
        const data = await rampApi.createOfframpQuote(parseFloat(cryptoAmount), selectedCrypto);
        setQuote(data);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to get quote');
    } finally {
      setLoadingQuote(false);
    }
  };

  const executeTransaction = async () => {
    setError('');
    setSuccess('');
    setExecuting(true);

    try {
      if (activeTab === 'onramp') {
        if (!walletAddress) {
          throw new Error('Please enter your wallet address');
        }
        const result = await rampApi.executeOnramp(quote.quote_id, walletAddress);
        const paymentRef = result.payment_reference || quote.payment_reference;
        const paymentAmount = result.payment_amount || quote.payment_amount || quote.fiat_amount;
        setSuccess(
          `Order confirmed! You will receive ${quote.crypto_amount?.toFixed(8)} ${quote.crypto_currency}.\n` +
          `Please complete payment of €${paymentAmount?.toLocaleString()} using reference: ${paymentRef}`
        );
      } else {
        if (!bankAccount) {
          throw new Error('Please enter your bank account IBAN');
        }
        const result = await rampApi.executeOfframp(quote.quote_id, bankAccount);
        const depositAddr = result.deposit_address || quote.deposit_address;
        setSuccess(
          `Order confirmed! Send ${quote.crypto_amount} ${quote.crypto_currency} to:\n` +
          `${depositAddr}\n` +
          `You will receive €${(quote.net_payout || (quote.fiat_amount - quote.fee_amount))?.toLocaleString('en-US', {minimumFractionDigits: 2})} after confirmation.`
        );
      }
      
      // Reset form
      setQuote(null);
      setFiatAmount('');
      setCryptoAmount('');
      setWalletAddress('');
      setBankAccount('');
      loadTransactions();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Transaction failed');
    } finally {
      setExecuting(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const formatPrice = (price) => {
    if (price >= 1000) return `€${price.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    if (price >= 1) return `€${price.toFixed(2)}`;
    return `€${price.toFixed(4)}`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Header */}
      <header className="border-b border-white/10 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center space-x-2">
              <Coins className="h-8 w-8 text-purple-400" />
              <span className="text-xl font-bold text-white">NeoNoble Ramp</span>
            </Link>
            <div className="flex items-center space-x-4">
              {/* Wallet Connect */}
              <ChainSelector />
              <WalletConnectButton />
              
              {isDeveloper && (
                <Link
                  to="/dev"
                  className="text-gray-300 hover:text-white px-3 py-2 text-sm"
                  data-testid="nav-dev-portal"
                >
                  Dev Portal
                </Link>
              )}
              <Link
                to="/admin"
                className="flex items-center gap-1 text-gray-300 hover:text-white px-3 py-2 text-sm"
                data-testid="nav-admin"
              >
                <Shield className="h-4 w-4" />
                Admin
              </Link>
              <span className="text-gray-400 text-sm">{user?.email}</span>
              <NotificationBell />
              <Link to="/settings" className="text-gray-400 hover:text-white p-2" data-testid="settings-link">
                <Settings className="h-5 w-5" />
              </Link>
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-white p-2"
                data-testid="logout-btn"
              >
                <LogOut className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Main Trading Panel */}
          <div className="lg:col-span-2">
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              {/* Tabs */}
              <div className="flex space-x-2 mb-6">
                <button
                  onClick={() => { setActiveTab('onramp'); setQuote(null); setError(''); }}
                  className={`flex-1 py-3 px-4 rounded-xl font-medium flex items-center justify-center space-x-2 transition-all ${
                    activeTab === 'onramp'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10'
                  }`}
                  data-testid="tab-onramp"
                >
                  <ArrowUpRight className="h-5 w-5" />
                  <span>Buy Crypto</span>
                </button>
                <button
                  onClick={() => { setActiveTab('offramp'); setQuote(null); setError(''); }}
                  className={`flex-1 py-3 px-4 rounded-xl font-medium flex items-center justify-center space-x-2 transition-all ${
                    activeTab === 'offramp'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10'
                  }`}
                  data-testid="tab-offramp"
                >
                  <ArrowDownRight className="h-5 w-5" />
                  <span>Sell Crypto</span>
                </button>
              </div>
              
              {/* NeoNoble Exchange — $NENO On/Off-Ramp interno */}
              <div className="mb-6 p-4 bg-gradient-to-r from-violet-600/20 to-purple-600/20 border border-violet-500/30 rounded-xl" data-testid="neno-onofframp-card">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-purple-600 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-lg shadow-violet-500/20">
                      $N
                    </div>
                    <div>
                      <h3 className="text-white font-medium">$NENO Exchange</h3>
                      <p className="text-gray-400 text-xs">Acquista, vendi e converti $NENO — On/Off-Ramp interno</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Link to="/neno-exchange" data-testid="neno-exchange-link"
                      className="px-4 py-2 bg-gradient-to-r from-purple-500 to-violet-600 hover:from-purple-600 hover:to-violet-700 text-white rounded-lg font-medium text-sm transition-colors flex items-center gap-1">
                      <ArrowRightLeft className="h-4 w-4" />
                      Apri Exchange
                    </Link>
                  </div>
                </div>
              </div>

              {/* NENO Trading Quick Access */}
              <div className="mb-6 p-4 bg-gradient-to-r from-purple-600/20 to-pink-600/20 border border-purple-500/30 rounded-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg flex items-center justify-center text-white font-bold">
                      N
                    </div>
                    <div>
                      <h3 className="text-white font-medium">$NENO Trading</h3>
                      <p className="text-gray-400 text-sm">Trade NeoNoble Token on all exchanges</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setShowNenoTrading(!showNenoTrading)}
                    className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium text-sm transition-colors flex items-center gap-1"
                    data-testid="neno-trading-toggle"
                  >
                    <BarChart3 className="h-4 w-4" />
                    {showNenoTrading ? 'Nascondi' : 'Apri Trading'}
                  </button>
                </div>
                
                {/* NENO Trading Widget Embedded */}
                {showNenoTrading && (
                  <div className="mt-4">
                    <NenoTradingWidget />
                  </div>
                )}
              </div>

              {/* Token & Subscription Quick Access */}
              <div className="mb-6 grid grid-cols-2 gap-4">
                <Link
                  to="/tokens/create"
                  className="p-4 bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 rounded-xl hover:border-cyan-400/50 transition-all group"
                  data-testid="create-custom-token-btn"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                      <Plus className="h-5 w-5 text-cyan-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-cyan-400">Crea Token Personalizzato</h3>
                      <p className="text-gray-400 text-xs">Lancia il tuo token custom</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/custom-tokens"
                  className="p-4 bg-gradient-to-r from-emerald-600/20 to-green-600/20 border border-emerald-500/30 rounded-xl hover:border-emerald-400/50 transition-all group"
                  data-testid="custom-token-market-btn"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-emerald-500/20 rounded-lg flex items-center justify-center">
                      <ArrowRightLeft className="h-5 w-5 text-emerald-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-emerald-400">Token Market</h3>
                      <p className="text-gray-400 text-xs">Compra, Vendi, Swap token</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/subscriptions"
                  className="p-4 bg-gradient-to-r from-orange-600/20 to-amber-600/20 border border-orange-500/30 rounded-xl hover:border-orange-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-orange-500/20 rounded-lg flex items-center justify-center">
                      <TrendingUp className="h-5 w-5 text-orange-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-orange-400">Abbonamenti</h3>
                      <p className="text-gray-400 text-xs">Piani Pro & Developer</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/market"
                  data-testid="market-data-link"
                  className="p-4 bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 rounded-xl hover:border-cyan-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                      <BarChart3 className="h-5 w-5 text-cyan-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-cyan-400">Mercato Crypto</h3>
                      <p className="text-gray-400 text-xs">30+ criptovalute live</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/cards"
                  data-testid="cards-link"
                  className="p-4 bg-gradient-to-r from-pink-600/20 to-rose-600/20 border border-pink-500/30 rounded-xl hover:border-pink-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-pink-500/20 rounded-lg flex items-center justify-center">
                      <CreditCard className="h-5 w-5 text-pink-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-pink-400">Carte Crypto</h3>
                      <p className="text-gray-400 text-xs">Spendi crypto ovunque</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/trade"
                  data-testid="trading-link"
                  className="p-4 bg-gradient-to-r from-amber-600/20 to-yellow-600/20 border border-amber-500/30 rounded-xl hover:border-amber-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-amber-500/20 rounded-lg flex items-center justify-center">
                      <TrendingUp className="h-5 w-5 text-amber-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-amber-400">Exchange</h3>
                      <p className="text-gray-400 text-xs">Trading con Order Book</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/margin"
                  data-testid="margin-trading-link"
                  className="p-4 bg-gradient-to-r from-red-600/20 to-orange-600/20 border border-red-500/30 rounded-xl hover:border-red-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-red-500/20 rounded-lg flex items-center justify-center">
                      <BarChart3 className="h-5 w-5 text-red-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-red-400">Margin Trading</h3>
                      <p className="text-gray-400 text-xs">Leva fino a 20x, Grafici PRO</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/wallet"
                  data-testid="wallet-banking-link"
                  className="p-4 bg-gradient-to-r from-teal-600/20 to-emerald-600/20 border border-teal-500/30 rounded-xl hover:border-teal-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-teal-500/20 rounded-lg flex items-center justify-center">
                      <Wallet className="h-5 w-5 text-teal-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-teal-400">Wallet & Banking</h3>
                      <p className="text-gray-400 text-xs">Multi-chain, IBAN, SEPA</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/developer/docs"
                  data-testid="api-docs-link"
                  className="p-4 bg-gradient-to-r from-indigo-600/20 to-violet-600/20 border border-indigo-500/30 rounded-xl hover:border-indigo-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-indigo-500/20 rounded-lg flex items-center justify-center">
                      <Shield className="h-5 w-5 text-indigo-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-indigo-400">API Developer</h3>
                      <p className="text-gray-400 text-xs">Documenti & API Keys</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/kyc"
                  data-testid="kyc-link"
                  className="p-4 bg-gradient-to-r from-teal-600/20 to-emerald-600/20 border border-teal-500/30 rounded-xl hover:border-teal-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-teal-500/20 rounded-lg flex items-center justify-center">
                      <Shield className="h-5 w-5 text-teal-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-teal-400">KYC / AML</h3>
                      <p className="text-gray-400 text-xs">Verifica identita e compliance</p>
                    </div>
                  </div>
                </Link>
                <Link
                  to="/portfolio"
                  data-testid="portfolio-link"
                  className="p-4 bg-gradient-to-r from-fuchsia-600/20 to-pink-600/20 border border-fuchsia-500/30 rounded-xl hover:border-fuchsia-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-fuchsia-500/20 rounded-lg flex items-center justify-center">
                      <PieChart className="h-5 w-5 text-fuchsia-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-fuchsia-400">Portfolio Analytics</h3>
                      <p className="text-gray-400 text-xs">Performance, PnL, Allocazione</p>
                    </div>
                  </div>
                </Link>

                {/* Real-time Portfolio Tracker */}
                <Link
                  to="/portfolio-tracker"
                  data-testid="portfolio-tracker-link"
                  className="p-4 bg-gradient-to-r from-cyan-600/20 to-teal-600/20 border border-cyan-500/30 rounded-xl hover:border-cyan-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                      <Activity className="h-5 w-5 text-cyan-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-cyan-400">Portfolio Tracker</h3>
                      <p className="text-gray-400 text-xs">Prezzi live via WebSocket</p>
                    </div>
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-cyan-400 bg-cyan-400/10 px-1.5 py-0.5 rounded">
                      <span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" /><span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500" /></span>
                      LIVE
                    </span>
                  </div>
                </Link>

                {/* DCA Trading Bot */}
                <Link
                  to="/dca"
                  data-testid="dca-bot-link"
                  className="p-4 bg-gradient-to-r from-emerald-600/20 to-green-600/20 border border-emerald-500/30 rounded-xl hover:border-emerald-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-emerald-500/20 rounded-lg flex items-center justify-center">
                      <RefreshCw className="h-5 w-5 text-emerald-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-emerald-400">DCA Bot</h3>
                      <p className="text-gray-400 text-xs">Accumulo automatico programmato</p>
                    </div>
                    <span className="ml-auto text-[10px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded font-bold">AUTO</span>
                  </div>
                </Link>

                {/* Referral Program */}
                <Link
                  to="/referral"
                  data-testid="referral-link"
                  className="p-4 bg-gradient-to-r from-amber-600/20 to-orange-600/20 border border-amber-500/30 rounded-xl hover:border-amber-400/50 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-amber-500/20 rounded-lg flex items-center justify-center">
                      <TrendingUp className="h-5 w-5 text-amber-400" />
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-amber-400">Referral</h3>
                      <p className="text-gray-400 text-xs">Invita amici, guadagna NENO</p>
                    </div>
                    <span className="ml-auto text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded font-bold">BONUS</span>
                  </div>
                </Link>
              </div>

              {/* My Custom Tokens Section */}
              <div className="mb-6 bg-white/5 border border-white/10 rounded-xl p-5" data-testid="my-custom-tokens-section">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-white flex items-center gap-2">
                    <Coins className="h-5 w-5 text-cyan-400" />
                    I Miei Token Personalizzati
                  </h3>
                  <Link
                    to="/tokens/create"
                    className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                    data-testid="create-new-token-link"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Nuovo
                  </Link>
                </div>
                {loadingMyTokens ? (
                  <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin text-cyan-400" /></div>
                ) : myTokens.length === 0 ? (
                  <div className="text-center py-4">
                    <p className="text-gray-500 text-sm mb-2">Non hai ancora creato token personalizzati.</p>
                    <Link to="/tokens/create" className="text-cyan-400 hover:underline text-sm font-medium" data-testid="create-first-token-link">
                      Crea il tuo primo token
                    </Link>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {myTokens.map(token => (
                      <div
                        key={token.symbol}
                        className="flex items-center justify-between py-3 px-4 bg-white/5 hover:bg-white/10 rounded-lg transition-colors cursor-pointer"
                        onClick={() => navigate('/custom-tokens')}
                        data-testid={`my-token-${token.symbol}`}
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                            <span className="text-cyan-400 font-mono text-xs font-bold">{token.symbol.slice(0, 3)}</span>
                          </div>
                          <div>
                            <p className="text-white text-sm font-medium">{token.name}</p>
                            <p className="text-gray-500 text-xs">{token.symbol} - Supply: {Number(token.total_supply).toLocaleString()}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-white text-sm font-medium">${token.price_usd || (token.price_eur / 0.92).toFixed(2)}</p>
                          <p className="text-gray-500 text-xs">Saldo: {(token.balance || 0).toFixed(2)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Live Balances Widget */}
              {Object.keys(liveBalances).length > 0 && (
                <div className="mb-6 bg-white/5 border border-white/10 rounded-xl p-5" data-testid="live-balances-dashboard">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <Wallet className="h-4 w-4 text-emerald-400" />
                      Bilanci in Tempo Reale
                    </h3>
                    <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded">
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                      </span>
                      LIVE
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {Object.entries(liveBalances).slice(0, 6).map(([asset, info]) => (
                      <div key={asset} className="bg-white/5 rounded-lg p-3">
                        <div className="text-gray-400 text-xs">{asset}</div>
                        <div className="text-white font-medium text-sm">{info.balance.toFixed(4)}</div>
                        <div className="text-gray-600 text-[10px]">${info.value_usd.toLocaleString()}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Error/Success Messages */}
              {error && (
                <div className="mb-4 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center space-x-2 text-red-200" data-testid="ramp-error">
                  <AlertCircle className="h-5 w-5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              {success && (
                <div className="mb-4 p-4 bg-green-500/20 border border-green-500/50 rounded-lg flex items-center space-x-2 text-green-200" data-testid="ramp-success">
                  <CheckCircle className="h-5 w-5 flex-shrink-0" />
                  <span>{success}</span>
                </div>
              )}

              {/* Crypto Selection */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-3">Select Cryptocurrency</label>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  {POPULAR_CRYPTOS.map((crypto) => (
                    <button
                      key={crypto}
                      onClick={() => { setSelectedCrypto(crypto); setQuote(null); }}
                      className={`py-2 px-3 rounded-lg font-medium text-sm transition-all ${
                        selectedCrypto === crypto
                          ? 'bg-purple-600 text-white'
                          : 'bg-white/5 text-gray-400 hover:bg-white/10'
                      }`}
                      data-testid={`crypto-${crypto}`}
                    >
                      {crypto}
                    </button>
                  ))}
                </div>
                {selectedCrypto === 'NENO' && (
                  <p className="text-xs text-purple-400 mt-2">NENO is fixed at €10,000 per token</p>
                )}
              </div>

              {/* Amount Input */}
              <div className="mb-6">
                {activeTab === 'onramp' ? (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">You Pay (EUR)</label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-lg">€</span>
                      <input
                        type="number"
                        value={fiatAmount}
                        onChange={(e) => { setFiatAmount(e.target.value); setQuote(null); }}
                        className="w-full pl-10 pr-4 py-4 bg-white/5 border border-white/10 rounded-xl text-white text-xl placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="100.00"
                        min="1"
                        data-testid="input-fiat-amount"
                      />
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">You Sell ({selectedCrypto})</label>
                    <input
                      type="number"
                      value={cryptoAmount}
                      onChange={(e) => { setCryptoAmount(e.target.value); setQuote(null); }}
                      className="w-full px-4 py-4 bg-white/5 border border-white/10 rounded-xl text-white text-xl placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      placeholder="0.001"
                      min="0"
                      step="any"
                      data-testid="input-crypto-amount"
                    />
                  </div>
                )}
              </div>

              {/* Get Quote Button */}
              {!quote && (
                <button
                  onClick={getQuote}
                  disabled={loadingQuote}
                  className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white py-4 rounded-xl font-semibold flex items-center justify-center space-x-2"
                  data-testid="get-quote-btn"
                >
                  {loadingQuote ? (
                    <><Loader2 className="h-5 w-5 animate-spin" /><span>Getting Quote...</span></>
                  ) : (
                    <><RefreshCw className="h-5 w-5" /><span>Get Quote</span></>
                  )}
                </button>
              )}

              {/* Quote Display */}
              {quote && (
                <div className="bg-white/5 rounded-xl p-4 mb-6" data-testid="quote-display">
                  <div className="flex justify-between items-center mb-4">
                    <div className="flex items-center space-x-2">
                      <span className="text-gray-400">Quote</span>
                      {quote.state && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          quote.state === 'QUOTE_CREATED' ? 'bg-blue-500/20 text-blue-400' :
                          quote.state === 'COMPLETED' ? 'bg-green-500/20 text-green-400' :
                          'bg-yellow-500/20 text-yellow-400'
                        }`}>
                          {quote.state.replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500">
                      Expires: {new Date(quote.expires_at || quote.valid_until).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-gray-400">You {activeTab === 'onramp' ? 'Pay' : 'Sell'}</span>
                      <span className="text-white font-medium">
                        {activeTab === 'onramp' 
                          ? `€${(quote.payment_amount || quote.fiat_amount)?.toLocaleString('en-US', { minimumFractionDigits: 2 })}` 
                          : `${quote.crypto_amount} ${quote.crypto_currency}`}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Exchange Rate</span>
                      <span className="text-white font-medium">1 {quote.crypto_currency} = €{quote.exchange_rate?.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Fee ({quote.fee_percentage}%)</span>
                      <span className="text-white font-medium">€{quote.fee_amount?.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="border-t border-white/10 pt-3 flex justify-between">
                      <span className="text-gray-300 font-medium">You {activeTab === 'onramp' ? 'Receive' : 'Get'}</span>
                      <span className="text-white text-lg font-bold">
                        {activeTab === 'onramp' 
                          ? `${quote.crypto_amount?.toFixed(8)} ${quote.crypto_currency}` 
                          : `€${(quote.net_payout || quote.total_fiat || (quote.fiat_amount - quote.fee_amount))?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                      </span>
                    </div>
                    {/* PoR Provider Info */}
                    {quote.provider && (
                      <p className="text-xs text-purple-400">
                        Provider: {quote.provider === 'internal_por' ? 'NeoNoble PoR Engine' : quote.provider}
                      </p>
                    )}
                    {/* Payment Reference for On-Ramp */}
                    {activeTab === 'onramp' && quote.payment_reference && (
                      <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3 mt-2">
                        <p className="text-sm text-purple-300 font-medium">Payment Reference</p>
                        <p className="text-white font-mono text-lg">{quote.payment_reference}</p>
                      </div>
                    )}
                    {/* Deposit Address for Off-Ramp */}
                    {activeTab === 'offramp' && quote.deposit_address && (
                      <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3 mt-2">
                        <p className="text-sm text-purple-300 font-medium">Deposit Address</p>
                        <p className="text-white font-mono text-xs break-all">{quote.deposit_address}</p>
                      </div>
                    )}
                    <p className="text-xs text-gray-500">
                      {quote.price_source ? `Price source: ${quote.price_source}` : 
                       quote.compliance?.por_responsible ? 'PoR handles KYC/AML' : ''}
                    </p>
                  </div>
                </div>
              )}

              {/* Destination Input & Execute */}
              {quote && (
                <div className="space-y-4">
                  {activeTab === 'onramp' ? (
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        <Wallet className="h-4 w-4 inline mr-1" /> Wallet Address
                      </label>
                      <input
                        type="text"
                        value={walletAddress}
                        onChange={(e) => setWalletAddress(e.target.value)}
                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="0x... or bc1..."
                        data-testid="input-wallet"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        <Building className="h-4 w-4 inline mr-1" /> Bank Account (IBAN)
                      </label>
                      <input
                        type="text"
                        value={bankAccount}
                        onChange={(e) => setBankAccount(e.target.value)}
                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="DE89 3704 0044 0532 0130 00"
                        data-testid="input-bank"
                      />
                    </div>
                  )}

                  <button
                    onClick={executeTransaction}
                    disabled={executing}
                    className="w-full bg-green-600 hover:bg-green-700 disabled:bg-green-600/50 text-white py-4 rounded-xl font-semibold flex items-center justify-center space-x-2"
                    data-testid="execute-btn"
                  >
                    {executing ? (
                      <><Loader2 className="h-5 w-5 animate-spin" /><span>Processing...</span></>
                    ) : (
                      <span>Confirm {activeTab === 'onramp' ? 'Purchase' : 'Sale'}</span>
                    )}
                  </button>
                  <button
                    onClick={() => setQuote(null)}
                    className="w-full text-gray-400 hover:text-white py-2"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Live Prices */}
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center">
                  <TrendingUp className="h-5 w-5 mr-2 text-purple-400" /> Live Prices
                </h3>
                <button onClick={loadPrices} className="text-gray-400 hover:text-white">
                  <RefreshCw className={`h-4 w-4 ${loadingPrices ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <div className="space-y-3">
                {POPULAR_CRYPTOS.map((crypto) => (
                  <div key={crypto} className="flex justify-between items-center">
                    <span className="text-gray-300">{crypto}</span>
                    <span className="text-white font-medium">
                      {prices[crypto] ? formatPrice(prices[crypto]) : '...'}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent Transactions */}
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-white flex items-center mb-4">
                <History className="h-5 w-5 mr-2 text-purple-400" /> Recent Transactions
              </h3>
              {transactions.length === 0 ? (
                <p className="text-gray-400 text-sm">No transactions yet</p>
              ) : (
                <div className="space-y-3">
                  {transactions.slice(0, 5).map((tx) => (
                    <div key={tx.id} className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
                      <div>
                        <p className="text-white text-sm font-medium">
                          {tx.type === 'ONRAMP' ? 'Bought' : 'Sold'} {tx.crypto_amount} {tx.crypto_currency}
                        </p>
                        <p className="text-gray-500 text-xs">{tx.reference}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${
                        tx.status === 'COMPLETED' ? 'bg-green-500/20 text-green-400' :
                        tx.status === 'PROCESSING' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {tx.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Transak Widget Modal */}
      <TransakWidget
        isOpen={transakOpen}
        onClose={() => setTransakOpen(false)}
        initialMode={transakMode}
      />
    </div>
  );
}
