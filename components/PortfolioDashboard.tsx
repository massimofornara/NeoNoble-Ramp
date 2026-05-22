'use client';

import { useEffect, useState } from 'react';
import { Activity, ShieldAlert, WalletCards } from 'lucide-react';

type Portfolio = {
  balances: Array<{ asset: string; available: string; held: string }>;
  transactions: Array<{ id: string; transaction_type: string; state: string; created_at: string }>;
  risk: Array<{ risk_type: string; severity: string; score: number; blocked: boolean }>;
};

export function PortfolioDashboard({ userId }: { userId: string }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`/api/exchange/portfolio?userId=${encodeURIComponent(userId)}`, { cache: 'no-store' });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Portfolio unavailable');
        setPortfolio(payload);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Portfolio unavailable');
      }
    };
    void load();
    const interval = window.setInterval(load, 10000);
    return () => window.clearInterval(interval);
  }, [userId]);

  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
      <div className="rounded-md border border-cyan-300/20 bg-white/[0.035] p-5">
        <div className="mb-4 flex items-center gap-2">
          <WalletCards className="h-5 w-5 text-cyan-200" />
          <h2 className="text-lg font-semibold">Portfolio</h2>
        </div>
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
        <div className="grid gap-3 sm:grid-cols-2">
          {(portfolio?.balances || []).map((balance) => (
            <div key={balance.asset} className="rounded-md border border-white/10 bg-black/30 p-4">
              <div className="font-mono text-cyan-100">{balance.asset}</div>
              <div className="mt-2 text-sm text-slate-300">Available: {balance.available}</div>
              <div className="text-sm text-slate-500">Held: {balance.held}</div>
            </div>
          ))}
          {portfolio && portfolio.balances.length === 0 ? <p className="text-sm text-slate-400">No internal ledger balances yet.</p> : null}
        </div>
      </div>

      <div className="rounded-md border border-white/10 bg-white/[0.035] p-5">
        <div className="mb-4 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-fuchsia-200" />
          <h2 className="text-lg font-semibold">Risk status</h2>
        </div>
        <div className="space-y-2">
          {(portfolio?.risk || []).slice(0, 5).map((risk, index) => (
            <div key={`${risk.risk_type}-${index}`} className="rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm">
              <div className="flex items-center justify-between">
                <span>{risk.risk_type}</span>
                <span className={risk.blocked ? 'text-red-300' : 'text-emerald-300'}>{risk.severity}</span>
              </div>
              <div className="text-slate-500">Score {risk.score}</div>
            </div>
          ))}
          {!portfolio?.risk?.length ? (
            <div className="flex items-center gap-2 text-sm text-emerald-300">
              <Activity className="h-4 w-4" />
              No active risk flags
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
