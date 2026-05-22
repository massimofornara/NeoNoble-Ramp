'use client';

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SellNENOButton } from '@/components/SellNENOButton';

export default function NenoSellPage() {
  return (
    <div className="min-h-screen bg-[#05070f] px-4 py-10 text-white">
      <main className="mx-auto max-w-3xl space-y-6">
        <Button asChild variant="outline" className="border-white/15 bg-transparent text-white hover:bg-white/10">
          <Link href="/ramp">
            <ArrowLeft className="h-4 w-4" />
            Ramp
          </Link>
        </Button>
        <section className="rounded-md border border-fuchsia-300/20 bg-white/[0.035] p-6">
          <h1 className="text-3xl font-semibold tracking-normal">Vendi NENO</h1>
          <div className="mt-6">
            <SellNENOButton />
          </div>
        </section>
      </main>
    </div>
  );
}
