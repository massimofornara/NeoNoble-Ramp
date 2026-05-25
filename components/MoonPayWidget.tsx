'use client';

import { useCallback, useEffect, useState } from 'react';
import { CircleDollarSign, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from '@/hooks/use-toast';

type MoonPayAction = {
  provider: 'moonpay';
  type: 'widget';
  flow: 'buy' | 'sell' | 'swap' | 'swapsCustomerSetup';
  environment: 'sandbox' | 'production';
  sdkUrl: string;
  widgetUrl?: string;
  params: Record<string, string | number | boolean | undefined>;
};

type MoonPayWidgetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: MoonPayAction | null;
  title?: string;
  description?: string;
};

declare global {
  interface Window {
    MoonPayWebSdk?: {
      init: (config: Record<string, unknown>) => {
        show: () => void;
        generateUrlForSigning?: () => string;
        updateSignature?: (signature: string) => void;
      };
    };
  }
}

function loadMoonPayScript(src: string) {
  return new Promise<void>((resolve, reject) => {
    if (window.MoonPayWebSdk) {
      resolve();
      return;
    }

    const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error('MoonPay SDK failed to load')), { once: true });
      return;
    }

    const script = document.createElement('script');
    script.defer = true;
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('MoonPay SDK failed to load'));
    document.head.appendChild(script);
  });
}

export function MoonPayWidget({
  open,
  onOpenChange,
  action,
  title = 'MoonPay fallback rail',
  description = 'Provider-backed liquidity execution via MoonPay.',
}: MoonPayWidgetProps) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'open' | 'failed'>('idle');
  const [error, setError] = useState('');

  const launch = useCallback(async () => {
    if (!action) return;
    setStatus('loading');
    setError('');

    try {
      await loadMoonPayScript(action.sdkUrl);
      if (!window.MoonPayWebSdk) throw new Error('MoonPayWebSdk is not available');

      const widget = window.MoonPayWebSdk.init({
        flow: action.flow,
        environment: action.environment,
        variant: 'overlay',
        useWarnBeforeRefresh: false,
        params: action.params,
        handlers: {
          onTransactionCompleted(props: unknown) {
            toast({ title: 'MoonPay transaction update', description: 'Provider webhook will settle the ledger.' });
            return props;
          },
          onCloseOverlay() {
            onOpenChange(false);
          },
        },
      });

      if (widget.generateUrlForSigning && widget.updateSignature) {
        const urlForSignature = widget.generateUrlForSigning();
        const signatureResponse = await fetch('/api/moonpay/sign-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urlForSignature }),
        });
        if (signatureResponse.ok) {
          const payload = (await signatureResponse.json()) as { signature?: string };
          if (payload.signature) widget.updateSignature(payload.signature);
        }
      }

      widget.show();
      setStatus('open');
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'MoonPay unavailable';
      setStatus('failed');
      setError(message);
      toast({ title: 'MoonPay fallback non disponibile', description: message, variant: 'destructive' });
    }
  }, [action, onOpenChange]);

  useEffect(() => {
    if (open) void launch();
  }, [launch, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px] border-fuchsia-400/30 bg-[#05070f] text-white shadow-2xl shadow-fuchsia-500/15">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <CircleDollarSign className="h-5 w-5 text-fuchsia-300" />
            {title}
          </DialogTitle>
          <DialogDescription className="text-slate-300">{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-md border border-white/10 bg-black/30 px-4 py-3 text-sm text-slate-200">
            Provider: <span className="font-mono text-fuchsia-200">MoonPay</span>
            <span className="px-2 text-slate-600">/</span>
            Flow: <span className="font-mono text-cyan-200">{action?.flow || 'n/a'}</span>
          </div>

          {status === 'loading' ? (
            <div className="flex items-center gap-2 rounded-md border border-cyan-400/20 bg-cyan-400/5 px-4 py-3 text-cyan-100">
              <Loader2 className="h-4 w-4 animate-spin" />
              Caricamento MoonPay SDK
            </div>
          ) : null}

          {error ? (
            <div className="flex items-center gap-2 rounded-md border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              <XCircle className="h-4 w-4" />
              {error}
            </div>
          ) : null}

          <Button
            className="h-10 w-full border border-fuchsia-300/30 bg-fuchsia-300 text-black hover:bg-fuchsia-200"
            onClick={() => void launch()}
            disabled={!action || status === 'loading'}
          >
            Apri MoonPay
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
