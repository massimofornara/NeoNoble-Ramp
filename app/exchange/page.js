'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Landmark } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PortfolioDashboard } from '@/components/PortfolioDashboard';
import { ExchangeSwapPanel } from '@/components/ExchangeSwapPanel';
import { TransactionHistory } from '@/components/TransactionHistory';
import { BuyNENOButton } from '@/components/BuyNENOButton';
import { SellNENOButton } from '@/components/SellNENOButton';

export default function ExchangePage() {
  const [user, setUser] = useState(null);

  useEffect(() => {
    const userData = localStorage.getItem('user_data');
    setUser(userData ? JSON.parse(userData) : { id: 'demo-user', email: 'demo@neonoble.local' });
  }, []);

  const userId = useMemo(() => user?.id || user?.email || 'demo-user', [user]);

  return (
    <div className="min-h-screen bg-[#05070f] px-4 py-8 text-white">
      <main className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between gap-4">
          <Button asChild variant="outline" className="border-white/15 bg-transparent text-white hover:bg-white/10">
            <Link href="/ramp">
              <ArrowLeft className="h-4 w-4" />
              Fiat ramp
            </Link>
          </Button>
          <div className="flex gap-2">
            <BuyNENOButton partnerCustomerId={userId} />
            <SellNENOButton partnerCustomerId={userId} />
          </div>
        </div>

        <section className="rounded-md border border-cyan-300/20 bg-white/[0.035] p-6">
          <div className="inline-flex items-center gap-2 rounded-md border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs text-cyan-100">
            <Landmark className="h-3.5 w-3.5" />
            NeoNoble Exchange Core
          </div>
          <h1 className="mt-4 text-4xl font-semibold tracking-normal">Ledger-first exchange dashboard</h1>
        </section>

        <PortfolioDashboard userId={userId} />
        <ExchangeSwapPanel userId={userId} />
        <TransactionHistory userId={userId} />
      </main>
    </div>
  );
}
