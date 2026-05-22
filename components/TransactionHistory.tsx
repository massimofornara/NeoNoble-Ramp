'use client';

import { useEffect, useState } from 'react';

export function TransactionHistory({ userId }: { userId: string }) {
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    const load = async () => {
      const response = await fetch(`/api/exchange/transactions?userId=${encodeURIComponent(userId)}`, { cache: 'no-store' });
      const payload = await response.json();
      if (response.ok) setRows(payload.data || []);
    };
    void load();
    const interval = window.setInterval(load, 15000);
    return () => window.clearInterval(interval);
  }, [userId]);

  return (
    <section className="rounded-md border border-white/10 bg-white/[0.035] p-5">
      <h2 className="mb-4 text-lg font-semibold">Immutable transaction history</h2>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.id} className="rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-cyan-100">{row.transaction_type}</span>
              <span className="text-emerald-200">{row.state}</span>
            </div>
            <div className="mt-1 truncate text-xs text-slate-500">{row.id}</div>
          </div>
        ))}
        {rows.length === 0 ? <p className="text-sm text-slate-400">No settled internal ledger transactions yet.</p> : null}
      </div>
    </section>
  );
}
