import { rebuildBalancesFromJournal } from '@/lib/recovery-engine/ledgerRebuild';
import { markStaleTransactionsFailed } from '@/lib/exchange/reconciliation';
import { detectWashTrading } from '@/lib/market-protection/manipulationDetection';

export async function crashRecoveryBootstrap() {
  const stale = await markStaleTransactionsFailed();
  const ledger = await rebuildBalancesFromJournal();
  const manipulation = await detectWashTrading('NENO-USDC', 60);
  return { stale, ledger, manipulationCases: manipulation.length };
}
