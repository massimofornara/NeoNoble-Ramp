const { getTransactionChainStatus } = require('../blockchain/walletService.cjs');

async function reconcileTransaction(prisma, transaction) {
  if (!transaction.txHash) {
    return {
      transactionId: transaction.id,
      status: 'missing_tx_hash',
      action: 'none',
    };
  }

  const chain = await getTransactionChainStatus(transaction.txHash);
  const mismatch =
    transaction.chainStatus !== chain.chainStatus ||
    transaction.blockNumber !== chain.blockNumber ||
    transaction.confirmations !== chain.confirmations ||
    transaction.gasUsed !== chain.gasUsed;

  if (!mismatch) {
    return {
      transactionId: transaction.id,
      status: 'matched',
      chain,
      action: 'none',
    };
  }

  await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      chainStatus: chain.chainStatus,
      blockNumber: chain.blockNumber,
      confirmations: chain.confirmations,
      gasUsed: chain.gasUsed,
    },
  });

  return {
    transactionId: transaction.id,
    status: 'corrected',
    chain,
    action: 'chain_fields_updated',
  };
}

async function reconcileUserTransactions(prisma, userId) {
  const transactions = await prisma.transaction.findMany({
    where: {
      userId,
      txHash: { not: null },
    },
    orderBy: { createdAt: 'desc' },
  });

  const results = [];
  for (const transaction of transactions) {
    results.push(await reconcileTransaction(prisma, transaction));
  }

  return {
    userId,
    checked: results.length,
    results,
  };
}

module.exports = {
  reconcileTransaction,
  reconcileUserTransactions,
};
