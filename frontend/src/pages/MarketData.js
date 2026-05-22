import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, TrendingDown, Search, Loader2, ArrowLeft,
  BarChart3, RefreshCw, Globe, ArrowUpRight
} from 'lucide-react';
import { xhrGet, BACKEND_URL } from '../utils/safeFetch';

function formatNumber(n) {
  if (!n && n !== 0) return '-';
  if (n >= 1e12) return `€${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `€${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `€${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `€${(n / 1e3).toFixed(1)}K`;
  return `€${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatPrice(n) {
  if (!n && n !== 0) return '-';
  if (n < 0.01) return `€${n.toFixed(6)}`;
  if (n < 1) return `€${n.toFixed(4)}`;
  return `€${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function MiniSparkline({ data, positive }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 100;
  const h = 28;
  const step = w / (data.length - 1);
  const points = data.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(' ');

  return (
    <svg width={w} height={h} className="inline-block">
      <polyline fill="none" stroke={positive ? '#22c55e' : '#ef4444'} strokeWidth="1.5" points={points} />
    </svg>
  );
}

export default function MarketData() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [coins, setCoins] = useState([]);
  const [search, setSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchData = useCallback(async (showRefresh) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await xhrGet(`${BACKEND_URL}/api/market-data/coins?vs_currency=eur&per_page=32`);
      setCoins(data.coins || []);
      setLastUpdated(new Date());
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchData(false); }, [fetchData]);

  const filtered = coins.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.symbol.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-950" data-testid="market-data-page">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
                <ArrowLeft className="w-5 h-5 text-gray-400" />
              </button>
              <div className="p-2 bg-emerald-500/20 rounded-lg">
                <BarChart3 className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">Mercato Crypto</h1>
                <p className="text-gray-400 text-xs">
                  {coins.length} criptovalute {lastUpdated && `| Aggiornato ${lastUpdated.toLocaleTimeString('it-IT')}`}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type="text" placeholder="Cerca..." value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  data-testid="market-search"
                  className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm w-52 focus:border-emerald-500 focus:outline-none" />
              </div>
              <button onClick={() => fetchData(true)} disabled={refreshing}
                data-testid="market-refresh"
                className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-400 hover:text-white transition-colors">
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
          </div>
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-800/80 sticky top-[73px]">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 w-10">#</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Nome</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400">Prezzo</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400">24h %</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 hidden md:table-cell">7d %</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 hidden lg:table-cell">Market Cap</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 hidden lg:table-cell">Volume (24h)</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 hidden xl:table-cell">7d Chart</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {filtered.map((coin) => (
                  <tr key={coin.id} className="hover:bg-gray-800/30 transition-colors cursor-pointer"
                    data-testid={`coin-row-${coin.symbol}`}>
                    <td className="px-4 py-3 text-gray-500 text-sm">{coin.market_cap_rank}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <img src={coin.image} alt={coin.symbol} className="w-7 h-7 rounded-full" loading="lazy" />
                        <div>
                          <span className="text-white font-medium text-sm">{coin.name}</span>
                          <span className="text-gray-500 text-xs ml-2">{coin.symbol}</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-white text-sm font-medium">{formatPrice(coin.current_price)}</td>
                    <td className="px-4 py-3 text-right">
                      <PriceChange value={coin.price_change_percentage_24h} />
                    </td>
                    <td className="px-4 py-3 text-right hidden md:table-cell">
                      <PriceChange value={coin.price_change_percentage_7d} />
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 text-sm hidden lg:table-cell">
                      {formatNumber(coin.market_cap)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 text-sm hidden lg:table-cell">
                      {formatNumber(coin.total_volume)}
                    </td>
                    <td className="px-4 py-3 text-right hidden xl:table-cell">
                      <MiniSparkline data={coin.sparkline_7d?.slice(-48)} positive={coin.price_change_percentage_7d >= 0} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

function PriceChange({ value }) {
  if (value === null || value === undefined) return <span className="text-gray-500 text-sm">-</span>;
  const positive = value >= 0;
  return (
    <span className={`text-sm font-medium flex items-center justify-end gap-0.5 ${positive ? 'text-green-400' : 'text-red-400'}`}>
      {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {Math.abs(value).toFixed(2)}%
    </span>
  );
}
