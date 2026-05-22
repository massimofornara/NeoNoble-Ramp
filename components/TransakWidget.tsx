'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Transak, type TransakConfig } from '@transak/ui-js-sdk';
import Pusher from 'pusher-js';
import { Activity, CheckCircle2, Loader2, ShieldCheck, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from '@/hooks/use-toast';
import type { TransakProducts, TransakSessionResponse, TransakOrder } from '@/types/transak';

type WidgetStatus =
  | 'idle'
  | 'connecting_wallet'
  | 'creating_session'
  | 'widget_open'
  | 'order_created'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'closed';

export type TransakWidgetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productsAvailed: TransakProducts;
  title: string;
  description: string;
  cryptoCurrency?: string;
  cryptoCurrencyList?: string[];
  network?: string;
  networks?: string[];
  fiatCurrency?: string;
  fiatAmount?: number;
  cryptoAmount?: number;
  paymentMethod?: string;
  partnerCustomerId?: string;
  partnerOrderId?: string;
  walletAddress?: string;
  lockWallet?: boolean;
  redirectURL?: string;
  exchangeScreenTitle?: string;
  onStatusChange?: (order: TransakOrder | null, status: WidgetStatus) => void;
};

declare global {
  interface Window {
    ethereum?: {
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
    };
  }
}

const SDK_EVENTS = [
  'TRANSAK_WIDGET_INITIALISED',
  'TRANSAK_WIDGET_OPEN',
  'TRANSAK_ORDER_CREATED',
  'TRANSAK_ORDER_SUCCESSFUL',
  'TRANSAK_ORDER_CANCELLED',
  'TRANSAK_ORDER_FAILED',
  'TRANSAK_WIDGET_CLOSE',
] as const;

const ORDER_EVENTS = [
  'ORDER_CREATED',
  'ORDER_PAYMENT_VERIFYING',
  'ORDER_PROCESSING',
  'ORDER_COMPLETED',
  'ORDER_FAILED',
  'ORDER_CANCELLED',
  'ORDER_REFUNDED',
  'ORDER_EXPIRED',
] as const;

function statusLabel(status: WidgetStatus) {
  return {
    idle: 'Pronto',
    connecting_wallet: 'Connessione wallet',
    creating_session: 'Sessione Transak',
    widget_open: 'Widget aperto',
    order_created: 'Ordine creato',
    processing: 'Ordine in elaborazione',
    completed: 'Ordine completato',
    failed: 'Ordine fallito',
    closed: 'Widget chiuso',
  }[status];
}

function isTerminal(status?: string) {
  return status === 'COMPLETED' || status === 'FAILED' || status === 'CANCELLED' || status === 'EXPIRED';
}

export default function TransakWidget({
  open,
  onOpenChange,
  productsAvailed,
  title,
  description,
  cryptoCurrency = 'NENO',
  cryptoCurrencyList,
  network = 'bsc',
  networks,
  fiatCurrency = 'EUR',
  fiatAmount,
  cryptoAmount,
  paymentMethod,
  partnerCustomerId,
  partnerOrderId,
  walletAddress: initialWalletAddress = '',
  lockWallet = true,
  redirectURL,
  exchangeScreenTitle,
  onStatusChange,
}: TransakWidgetProps) {
  const [walletAddress, setWalletAddress] = useState<string>(initialWalletAddress);
  const [session, setSession] = useState<TransakSessionResponse | null>(null);
  const [status, setStatus] = useState<WidgetStatus>('idle');
  const [order, setOrder] = useState<TransakOrder | null>(null);
  const [error, setError] = useState<string>('');
  const transakRef = useRef<Transak | null>(null);

  const requestBody = useMemo(
    () => ({
      productsAvailed,
      walletAddress: walletAddress || undefined,
      fiatCurrency,
      cryptoCurrency,
      network,
      networks,
      fiatAmount,
      cryptoAmount,
      paymentMethod,
      cryptoCurrencyList,
      disableWalletAddressForm: lockWallet && Boolean(walletAddress),
      partnerCustomerId,
      partnerOrderId,
      redirectURL,
      exchangeScreenTitle,
      colorMode: 'DARK',
      themeColor: '#00f5d4',
    }),
    [
      productsAvailed,
      walletAddress,
      fiatCurrency,
      cryptoCurrency,
      network,
      networks,
      fiatAmount,
      cryptoAmount,
      paymentMethod,
      cryptoCurrencyList,
      lockWallet,
      partnerCustomerId,
      partnerOrderId,
      redirectURL,
      exchangeScreenTitle,
    ],
  );

  const connectWallet = useCallback(async () => {
    if (walletAddress) return walletAddress;
    if (!window.ethereum) return '';

    setStatus('connecting_wallet');
    const accounts = (await window.ethereum.request({ method: 'eth_requestAccounts' })) as string[];
    const firstAccount = Array.isArray(accounts) ? accounts[0] : '';
    if (firstAccount) setWalletAddress(firstAccount);
    return firstAccount || '';
  }, [walletAddress]);

  useEffect(() => {
    if (initialWalletAddress) setWalletAddress(initialWalletAddress);
  }, [initialWalletAddress]);

  const pollStatus = useCallback(async (currentSession: TransakSessionResponse) => {
    const response = await fetch(`/api/transak/status?partnerOrderId=${encodeURIComponent(currentSession.partnerOrderId)}`, {
      cache: 'no-store',
    });
    if (!response.ok) return;
    const payload = (await response.json()) as { data: TransakOrder | null };
    if (!payload.data) return;

    setOrder(payload.data);
    const nextStatus = payload.data.status === 'COMPLETED' ? 'completed' : isTerminal(payload.data.status) ? 'failed' : 'processing';
    setStatus(nextStatus);
    onStatusChange?.(payload.data, nextStatus);
  }, [onStatusChange]);

  const launch = useCallback(async () => {
    setError('');
    try {
      const connectedWallet = productsAvailed.includes('BUY') ? await connectWallet() : walletAddress;
      setStatus('creating_session');

      const response = await fetch('/api/transak/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...requestBody, walletAddress: connectedWallet || undefined }),
      });
      const payload = (await response.json()) as TransakSessionResponse | { error?: string };
      if (!response.ok || !('widgetUrl' in payload)) {
        throw new Error('error' in payload && payload.error ? payload.error : 'Unable to create Transak session');
      }

      setSession(payload);
      const transakConfig: TransakConfig = { widgetUrl: payload.widgetUrl };
      const transak = new Transak(transakConfig);
      transakRef.current = transak;

      (Transak.on as unknown as (eventName: string, handler: (eventData: unknown) => void) => void)('*', (eventData: unknown) => {
        const typed = eventData as { eventName?: string; event_id?: string; data?: TransakOrder };
        const eventName = typed.eventName || typed.event_id || '';
        if (!eventName) return;

        if (eventName === 'TRANSAK_WIDGET_OPEN') setStatus('widget_open');
        if (eventName === 'TRANSAK_ORDER_CREATED') {
          setStatus('order_created');
          setOrder(typed.data || null);
          toast({ title: 'Ordine Transak creato', description: payload.partnerOrderId });
        }
        if (eventName === 'TRANSAK_ORDER_SUCCESSFUL') {
          setStatus('completed');
          setOrder(typed.data || null);
          toast({ title: 'Ordine completato', description: 'Transak ha marcato il flusso come concluso.' });
          transak.close();
        }
        if (eventName === 'TRANSAK_ORDER_CANCELLED' || eventName === 'TRANSAK_ORDER_FAILED') {
          setStatus('failed');
          setOrder(typed.data || null);
          toast({ title: 'Ordine non completato', description: eventName, variant: 'destructive' });
        }
        if (eventName === 'TRANSAK_WIDGET_CLOSE') {
          setStatus('closed');
          onOpenChange(false);
        }
        onStatusChange?.(typed.data || null, status);
      });

      transak.init();
      setStatus('widget_open');
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Errore Transak';
      setError(message);
      setStatus('failed');
      toast({ title: 'Transak non disponibile', description: message, variant: 'destructive' });
    }
  }, [connectWallet, lockWallet, onOpenChange, onStatusChange, productsAvailed, requestBody, status, walletAddress]);

  useEffect(() => {
    if (!open) return;
    void launch();
    return () => {
      transakRef.current?.close();
      transakRef.current = null;
    };
  }, [open, launch]);

  useEffect(() => {
    if (!session) return;

    const pusher = new Pusher(session.pusher.appKey, { cluster: session.pusher.cluster });
    const channel = pusher.subscribe(session.pusher.channel);

    ORDER_EVENTS.forEach((eventName) => {
      channel.bind(eventName, (data: TransakOrder) => {
        setOrder(data);
        const nextStatus = eventName === 'ORDER_COMPLETED' || data.status === 'COMPLETED'
          ? 'completed'
          : eventName === 'ORDER_FAILED' || eventName === 'ORDER_CANCELLED' || eventName === 'ORDER_EXPIRED'
            ? 'failed'
            : 'processing';
        setStatus(nextStatus);
        onStatusChange?.(data, nextStatus);
      });
    });

    const interval = window.setInterval(() => {
      if (!order?.status || !isTerminal(order.status)) void pollStatus(session);
    }, 10_000);

    return () => {
      window.clearInterval(interval);
      channel.unbind_all();
      pusher.unsubscribe(session.pusher.channel);
      pusher.disconnect();
    };
  }, [onStatusChange, order?.status, pollStatus, session]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px] border-cyan-400/30 bg-[#05070f] text-white shadow-2xl shadow-cyan-500/15">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <ShieldCheck className="h-5 w-5 text-cyan-300" />
            {title}
          </DialogTitle>
          <DialogDescription className="text-slate-300">{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 rounded-md border border-white/10 bg-white/[0.03] p-4 sm:grid-cols-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500">Asset</div>
              <div className="font-mono text-sm text-cyan-200">{cryptoCurrency}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500">Network</div>
              <div className="font-mono text-sm text-emerald-200">{network}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500">Mode</div>
              <div className="font-mono text-sm text-fuchsia-200">{productsAvailed}</div>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md border border-white/10 bg-black/30 px-4 py-3">
            <div className="flex items-center gap-2">
              {status === 'failed' ? (
                <XCircle className="h-4 w-4 text-red-400" />
              ) : status === 'completed' ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <Activity className="h-4 w-4 text-cyan-300" />
              )}
              <span className="text-sm text-slate-200">{statusLabel(status)}</span>
            </div>
            {status === 'creating_session' || status === 'connecting_wallet' ? (
              <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
            ) : null}
          </div>

          {walletAddress ? (
            <div className="truncate rounded-md border border-emerald-400/20 bg-emerald-400/5 px-3 py-2 font-mono text-xs text-emerald-200">
              {walletAddress}
            </div>
          ) : null}

          {order?.status ? (
            <div className="rounded-md border border-cyan-400/20 bg-cyan-400/5 px-3 py-2 text-sm text-cyan-100">
              Transak status: <span className="font-mono">{order.status}</span>
            </div>
          ) : null}

          {error ? (
            <div className="rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">{error}</div>
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              className="h-10 flex-1 border border-cyan-300/30 bg-cyan-300 text-black hover:bg-cyan-200"
              onClick={() => void launch()}
              disabled={status === 'creating_session' || status === 'connecting_wallet'}
            >
              Riapri sessione
            </Button>
            <Button
              variant="outline"
              className="h-10 flex-1 border-white/15 bg-transparent text-white hover:bg-white/10"
              onClick={() => onOpenChange(false)}
            >
              Chiudi
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
