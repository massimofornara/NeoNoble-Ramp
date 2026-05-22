'use client';

import { useMemo, useState } from 'react';
import { Repeat2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import TransakWidget from '@/components/TransakWidget';

export function SwapNENOButton({ partnerCustomerId }: { partnerCustomerId?: string }) {
  const [open, setOpen] = useState(false);
  const partnerOrderId = useMemo(() => `multi-neno-${crypto.randomUUID()}`, []);

  return (
    <>
      <Button className="h-11 border border-emerald-300/40 bg-emerald-300 text-black hover:bg-emerald-200" onClick={() => setOpen(true)}>
        <Repeat2 className="h-4 w-4" />
        NENO multi-asset
      </Button>
      <TransakWidget
        open={open}
        onOpenChange={setOpen}
        productsAvailed="BUY,SELL"
        title="NENO multi-asset"
        description="Transak supporta ufficialmente BUY e SELL. Il cambio crypto-to-crypto puro resta gestito dal motore swap NeoNoble."
        cryptoCurrency="NENO"
        cryptoCurrencyList={['NENO', 'ETH', 'USDT', 'USDC', 'BNB']}
        network="bsc"
        networks={['bsc', 'ethereum', 'polygon']}
        fiatCurrency="EUR"
        partnerCustomerId={partnerCustomerId}
        partnerOrderId={partnerOrderId}
        exchangeScreenTitle="NeoNoble multi-asset ramp"
        redirectURL={typeof window !== 'undefined' ? `${window.location.origin}/ramp?flow=multi` : undefined}
      />
    </>
  );
}
