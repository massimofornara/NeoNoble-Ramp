const { getTransactionStatusOnChain } = require('./walletService.cjs');
const { createPayoutRequest } = require('../settlement/settlementService.cjs');
const { publishTransactionEvent } = require('../events/eventBus.cjs');

function isChainFinal(status) {
  return status.chainStatus === 'finalized' || status.confirmations >= Number.parseInt(process.env.BSC_FINALITY_CONFIRMATIONS || '12', 10);
}

function isChainConfirmed(status) {
  return status.chainStatus === 'confirmed' || status.chainStatus === 'finalized';
}

async function updateBroadcastedTransaction(prisma, transaction) {
  const chain = await getTransactionStatusOnChain(transaction.txHash, transaction.chainName || transaction.network || 'BSC');

  if (chain.chainStatus === 'not_found' || chain.chainStatus === 'pending') {
    await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        chainStatus: chain.chainStatus,
        finalityStatus: 'settlement_pending',
        confirmations: chain.confirmations,
      },
    });
    return { changed: false, chain };
  }

  if (chain.chainStatus === 'failed') {
    await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        status: 'failed_unrecoverable',
        step: 'chain_failed',
        chainStatus: 'failed',
        finalityStatus: 'failed_unrecoverable',
        blockNumber: chain.blockNumber,
        gasUsed: chain.gasUsed,
        confirmations: chain.confirmations,
        errorMessage: 'Transaction receipt status is failed',
      },
    });
    await publishTransactionEvent(transaction.id, 'transaction.failed', chain);
    return { changed: true, chain };
  }

  const update = {
    chainStatus: chain.chainStatus,
    finalityStatus: 'settlement_pending',
    chainId: chain.chainId,
    chainName: chain.chainName,
    settlementLayer: chain.settlementLayer,
    blockNumber: chain.blockNumber,
    gasUsed: chain.gasUsed,
    confirmations: chain.confirmations,
  };

  if (
    isChainConfirmed(chain) &&
    ['settlement_pending', 'execution_successful', 'execution_attempted', 'broadcasted'].includes(transaction.status)
  ) {
    update.status = 'settlement_pending';
    update.step = 'chain_confirmed';
  }

  if (isChainFinal(chain)) {
    if (transaction.type === 'offramp' && String(transaction.fiatCurrency || '').toUpperCase() !== 'USDT') {
      const payout = await createPayoutRequest(transaction);
      update.status = 'settlement_pending';
      update.step = 'payout_requested';
      update.settlementId = payout.settlementId;
      update.paymentReference = payout.paymentReference;
      await publishTransactionEvent(transaction.id, 'settlement.requested', payout);
    } else {
      update.status = 'settlement_confirmed';
      update.step = 'finalized';
      update.settlementId = transaction.settlementId || `chain:${transaction.txHash}`;
      update.finalityStatus = 'finalized';
      update.lastSuccessfulRail = 'onchain';
    }
  }

  await prisma.transaction.update({
    where: { id: transaction.id },
    data: update,
  });

  if (update.step === 'chain_confirmed') {
    await publishTransactionEvent(transaction.id, 'transaction.confirmed', chain);
  }

  if (update.step === 'payout_requested') {
    await publishTransactionEvent(transaction.id, 'settlement.pending', {
      ...chain,
      settlementId: update.settlementId,
    });
  }

  if (update.status === 'settlement_confirmed') {
    await publishTransactionEvent(transaction.id, 'settlement.confirmed', {
      ...chain,
      settlementId: update.settlementId,
    });
  }

  return { changed: true, chain };
}

module.exports = {
  updateBroadcastedTransaction,
};
