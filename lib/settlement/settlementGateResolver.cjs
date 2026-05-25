async function writeGateEvent(prisma, transactionId, eventType, payload) {
  if (!prisma) return;
  await prisma.transactionEvent.create({
    data: {
      transactionId,
      eventType,
      payload,
    },
  });
}

function gatePayload(liquidityPlan, bootstrapResult) {
  return {
    required: liquidityPlan.required,
    selected: liquidityPlan.selected,
    blockers: liquidityPlan.blockers,
    bootstrap: bootstrapResult
      ? {
          status: bootstrapResult.status,
          outcomes: bootstrapResult.outcomes,
          blockers: bootstrapResult.bootstrapPlan?.blockers || [],
        }
      : null,
    observedAt: new Date().toISOString(),
  };
}

async function resolveSettlementGate(prisma, transaction, liquidityPlan, bootstrapResult = null) {
  const payload = gatePayload(liquidityPlan, bootstrapResult);
  const fresh = await prisma.transaction.findUnique({ where: { id: transaction.id } });
  const rawTxData = fresh?.rawTxData || transaction.rawTxData || {};

  if (liquidityPlan.canSettle && liquidityPlan.selected) {
    const updated = await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        status: 'execution_attempted',
        step: 'settlement_source_ready',
        chainStatus: 'settlement_source_ready',
        finalityStatus: 'execution_attempted',
        settlementLayer: liquidityPlan.selected.provider,
        lastSuccessfulRail: liquidityPlan.selected.provider,
        rawTxData: {
          ...rawTxData,
          settlementGate: {
            ...payload,
            status: 'open',
          },
        },
        errorMessage: null,
      },
    });
    await writeGateEvent(prisma, transaction.id, 'settlement.gate_open', payload);
    return {
      open: true,
      status: 'open',
      transaction: updated,
      payload,
    };
  }

  const fundingRequested = bootstrapResult?.status === 'funding_requested';
  const step = fundingRequested ? 'liquidity_bootstrap_active' : 'awaiting_real_liquidity';
  const chainStatus = fundingRequested ? 'funding_requested' : 'funding_required';
  const errorMessage = fundingRequested
    ? 'liquidity bootstrap requested; awaiting provider funding proof'
    : `awaiting real liquidity: ${liquidityPlan.blockers
        .map((entry) => `${entry.provider}: ${entry.blocker}`)
        .join(' | ')}`;

  const updated = await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      status: 'execution_attempted',
      step,
      chainStatus,
      finalityStatus: 'execution_attempted',
      settlementLayer: 'liquidity_orchestrator',
      lastSuccessfulRail: 'liquidity_orchestrator',
      rawTxData: {
        ...rawTxData,
        settlementGate: {
          ...payload,
          status: fundingRequested ? 'waiting_funding' : 'blocked',
        },
      },
      errorMessage,
    },
  });

  await writeGateEvent(
    prisma,
    transaction.id,
    fundingRequested ? 'settlement.gate_waiting_funding' : 'settlement.gate_blocked',
    payload,
  );

  return {
    open: false,
    status: fundingRequested ? 'waiting_funding' : 'blocked',
    transaction: updated,
    payload,
  };
}

module.exports = {
  resolveSettlementGate,
};
