'use client';

import { useMemo, useState } from 'react';
import { Repeat2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from '@/hooks/use-toast';
import { MoonPayWidget } from '@/components/MoonPayWidget';

export function ExchangeSwapPanel({ userId }: { userId: string }) {
  const [fromAsset, setFromAsset] = useState('NENO');
  const [toAsset, setToAsset] = useState('USDT');
  const [amount, setAmount] = useState('1');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [limitPrice, setLimitPrice] = useState('');
  const [maxSlippageBps, setMaxSlippageBps] = useState(100);
  const [quote, setQuote] = useState<any>(null);
  const [moonPayAction, setMoonPayAction] = useState<any>(null);
  const [moonPayOpen, setMoonPayOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const idempotencyKey = useMemo(() => `swap-${crypto.randomUUID()}`, []);

  const getQuote = async () => {
    const response = await fetch(`/api/exchange/swap?fromAsset=${fromAsset}&toAsset=${toAsset}&amount=${amount}&maxSlippageBps=${maxSlippageBps}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Quote failed');
    setQuote(payload);
  };

  const execute = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/swap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId,
          fromToken: fromAsset,
          toToken: toAsset,
          cryptoAmount: amount,
          orderType,
          limitPrice,
          maxSlippageBps,
          idempotencyKey,
          network: 'BSC',
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Swap failed');
      if (payload.executionRoute?.provider === 'moonpay') {
        setMoonPayAction(payload.executionRoute);
        setMoonPayOpen(true);
        toast({ title: 'Fallback provider attivato', description: 'MoonPay gestira liquidita e conferma via webhook.' });
      } else {
        toast({ title: 'Swap in coda', description: payload.transactionId });
      }
    } catch (caught) {
      toast({ title: 'Swap blocked', description: caught instanceof Error ? caught.message : 'Swap failed', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-md border border-emerald-300/20 bg-white/[0.035] p-5">
      <div className="mb-4 flex items-center gap-2">
        <Repeat2 className="h-5 w-5 text-emerald-200" />
        <h2 className="text-lg font-semibold">Internal swap engine</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <input className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" value={fromAsset} onChange={(event) => setFromAsset(event.target.value.toUpperCase())} />
        <input className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" value={toAsset} onChange={(event) => setToAsset(event.target.value.toUpperCase())} />
        <input className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" value={amount} onChange={(event) => setAmount(event.target.value)} />
        <select className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" value={orderType} onChange={(event) => setOrderType(event.target.value as 'MARKET' | 'LIMIT')}>
          <option value="MARKET">MARKET</option>
          <option value="LIMIT">LIMIT</option>
        </select>
        <input className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} placeholder="Limit price" disabled={orderType === 'MARKET'} />
        <input className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm" type="number" value={maxSlippageBps} onChange={(event) => setMaxSlippageBps(Number(event.target.value))} />
      </div>
      {quote ? (
        <div className="mt-4 rounded-md border border-white/10 bg-black/30 p-3 text-sm text-slate-200">
          Output {quote.amountOut} {toAsset} at price {quote.price}; spread {quote.spreadBps}bps, slippage {quote.slippageBps}bps.
        </div>
      ) : null}
      <div className="mt-4 flex gap-2">
        <Button className="bg-emerald-300 text-black hover:bg-emerald-200" onClick={() => void getQuote()}>Quote</Button>
        <Button className="bg-cyan-300 text-black hover:bg-cyan-200" onClick={() => void execute()} disabled={loading}>{loading ? 'Settling' : 'Execute'}</Button>
      </div>
      <MoonPayWidget
        open={moonPayOpen}
        onOpenChange={setMoonPayOpen}
        action={moonPayAction}
        title="Liquidity fallback"
        description="On-chain USDT liquidity is unavailable; execution switches to MoonPay provider-backed liquidity."
      />
    </section>
  );
}
