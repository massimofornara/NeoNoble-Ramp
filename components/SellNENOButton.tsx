'use client';

import { useMemo, useState } from 'react';
import { Landmark } from 'lucide-react';
import { Button } from '@/components/ui/button';
import TransakWidget from '@/components/TransakWidget';

export function SellNENOButton({ partnerCustomerId }: { partnerCustomerId?: string }) {
  const [open, setOpen] = useState(false);
  const partnerOrderId = useMemo(() => `sell-neno-${crypto.randomUUID()}`, []);

  return (
    <>
      <Button className="h-11 border border-fuchsia-300/40 bg-fuchsia-400 text-black hover:bg-fuchsia-300" onClick={() => setOpen(true)}>
        <Landmark className="h-4 w-4" />
        Vendi NENO
      </Button>
      <TransakWidget
        open={open}
        onOpenChange={setOpen}
        productsAvailed="SELL"
        title="Vendi NENO"
        description="NENO to fiat con off-ramp Transak. SELL deve essere abilitato nel Partner Portal."
        cryptoCurrency="NENO"
        cryptoCurrencyList={['NENO']}
        network="bsc"
        networks={['bsc']}
        fiatCurrency="EUR"
        partnerCustomerId={partnerCustomerId}
        partnerOrderId={partnerOrderId}
        exchangeScreenTitle="Vendi NENO su NeoNoble"
        redirectURL={typeof window !== 'undefined' ? `${window.location.origin}/ramp?flow=sell` : undefined}
      />
    </>
  );
}
