'use client';

import { useMemo, useState } from 'react';
import { CreditCard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import TransakWidget from '@/components/TransakWidget';

export function BuyNENOButton({
  partnerCustomerId,
  walletAddress,
}: {
  partnerCustomerId?: string;
  walletAddress?: string;
}) {
  const [open, setOpen] = useState(false);
  const partnerOrderId = useMemo(() => `buy-neno-${crypto.randomUUID()}`, []);

  return (
    <>
      <Button className="h-11 bg-cyan-300 text-black hover:bg-cyan-200" onClick={() => setOpen(true)}>
        <CreditCard className="h-4 w-4" />
        Compra NENO
      </Button>
      <TransakWidget
        open={open}
        onOpenChange={setOpen}
        productsAvailed="BUY"
        title="Compra NENO"
        description="Fiat to NENO con KYC embedded e wallet precompilato."
        cryptoCurrency="NENO"
        cryptoCurrencyList={['NENO']}
        network="bsc"
        networks={['bsc']}
        fiatCurrency="EUR"
        partnerCustomerId={partnerCustomerId}
        partnerOrderId={partnerOrderId}
        lockWallet
        exchangeScreenTitle="Compra NENO su NeoNoble"
        redirectURL={typeof window !== 'undefined' ? `${window.location.origin}/ramp?flow=buy` : undefined}
        {...(walletAddress ? { walletAddress } : {})}
      />
    </>
  );
}
