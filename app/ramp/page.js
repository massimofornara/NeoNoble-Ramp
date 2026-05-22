'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, Radio, ShieldCheck, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BuyNENOButton } from '@/components/BuyNENOButton';
import { SellNENOButton } from '@/components/SellNENOButton';
import { SwapNENOButton } from '@/components/SwapNENOButton';

export default function RampHome() {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [walletAddress, setWalletAddress] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('user_token');
    const userData = localStorage.getItem('user_data');

    if (!token || !userData) {
      router.push('/auth');
      return;
    }

    setUser(JSON.parse(userData));
  }, [router]);

  const partnerCustomerId = useMemo(() => {
    if (!user) return undefined;
    return user.id || user.email || undefined;
  }, [user]);

  const connectWallet = async () => {
    if (!window.ethereum) return;
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    if (Array.isArray(accounts) && accounts[0]) setWalletAddress(accounts[0]);
  };

  const handleLogout = () => {
    localStorage.removeItem('user_token');
    localStorage.removeItem('user_data');
    router.push('/auth');
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-[#05070f] text-white flex items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-2 border-cyan-300 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#05070f] text-white">
      <header className="border-b border-cyan-300/15 bg-black/40 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-md border border-cyan-300/40 bg-cyan-300/10">
              <Radio className="h-5 w-5 text-cyan-200" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-normal">NeoNoble Ramp</h1>
              <p className="text-xs text-slate-400">{user.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="border-white/15 bg-transparent text-white hover:bg-white/10" onClick={connectWallet}>
              <Wallet className="h-4 w-4" />
              Wallet
            </Button>
            <Button variant="outline" size="icon" className="border-white/15 bg-transparent text-white hover:bg-white/10" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10">
        <section className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-6">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 rounded-md border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs text-emerald-200">
                <ShieldCheck className="h-3.5 w-3.5" />
                Transak embedded
              </div>
              <h2 className="max-w-3xl text-4xl font-semibold tracking-normal text-white sm:text-5xl">
                NENO fiat rail, live inside NeoNoble.
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase text-slate-500">Fiat</div>
                <div className="mt-1 font-mono text-cyan-200">EUR</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase text-slate-500">Token</div>
                <div className="mt-1 font-mono text-fuchsia-200">NENO</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase text-slate-500">Network</div>
                <div className="mt-1 font-mono text-emerald-200">BSC</div>
              </div>
            </div>

            {walletAddress ? (
              <div className="truncate rounded-md border border-cyan-300/20 bg-cyan-300/5 px-4 py-3 font-mono text-xs text-cyan-100">
                {walletAddress}
              </div>
            ) : null}

            <div className="flex flex-col gap-3 sm:flex-row">
              <BuyNENOButton partnerCustomerId={partnerCustomerId} walletAddress={walletAddress} />
              <SellNENOButton partnerCustomerId={partnerCustomerId} />
              <SwapNENOButton partnerCustomerId={partnerCustomerId} />
            </div>
          </div>

          <div className="rounded-md border border-white/10 bg-white/[0.035] p-5">
            <div className="grid gap-3">
              {[
                ['KYC', 'Embedded'],
                ['Status', 'Pusher + polling'],
                ['Webhook', 'JWT verified'],
                ['Runtime', process.env.NEXT_PUBLIC_TRANSAK_ENVIRONMENT || 'STAGING'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between rounded-md border border-white/10 bg-black/30 px-4 py-3">
                  <span className="text-sm text-slate-400">{label}</span>
                  <span className="font-mono text-sm text-white">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
