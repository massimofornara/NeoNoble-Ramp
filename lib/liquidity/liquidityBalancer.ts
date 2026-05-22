import { query, writeQuery } from '@/lib/exchange/db';
import { compare, subtract } from '@/lib/exchange/money';

export async function planLiquidityRebalance(asset: string) {
  const position = (await query<{
    asset: string;
    total_assets: string;
    hot_wallet_target: string;
    cold_wallet_target: string;
  }>(
    'select asset, total_assets::text, hot_wallet_target::text, cold_wallet_target::text from treasury_positions where asset = $1',
    [asset],
  ))[0];
  if (!position) throw new Error('Treasury position not found');

  const hotWallet = (await query<{ max_online_balance: string }>(
    "select max_online_balance::text from custody_wallets where asset = $1 and tier = 'HOT' and status = 'ACTIVE' limit 1",
    [asset],
  ))[0];
  const hotBalance = hotWallet?.max_online_balance || '0';
  const actions: Array<{ actionType: string; amount: string; fromTier: string; toTier: string }> = [];

  if (compare(hotBalance, position.hot_wallet_target) > 0) {
    actions.push({ actionType: 'MOVE_TO_COLD', amount: subtract(hotBalance, position.hot_wallet_target), fromTier: 'HOT', toTier: 'COLD' });
  } else if (compare(hotBalance, position.hot_wallet_target) < 0) {
    actions.push({ actionType: 'MOVE_TO_HOT', amount: subtract(position.hot_wallet_target, hotBalance), fromTier: 'COLD', toTier: 'HOT' });
  }

  for (const action of actions) {
    await writeQuery(
      `insert into rebalancing_actions(asset, action_type, amount, from_tier, to_tier, payload)
       values ($1, $2, $3, $4, $5, $6)`,
      [asset, action.actionType, action.amount, action.fromTier, action.toTier, JSON.stringify({ source: 'liquidityBalancer' })],
    );
  }
  return actions;
}
