import { query, writeQuery } from '@/lib/exchange/db';
import { compare, subtract } from '@/lib/exchange/money';

export async function upsertTreasuryPosition(input: {
  asset: string;
  totalAssets: string;
  hotWalletTarget: string;
  coldWalletTarget: string;
  maxExposure: string;
  insuranceFundBalance?: string;
}) {
  await writeQuery(
    `insert into treasury_positions(asset, total_assets, hot_wallet_target, cold_wallet_target, max_exposure, insurance_fund_balance)
     values ($1, $2, $3, $4, $5, $6)
     on conflict(asset) do update set
       total_assets = excluded.total_assets,
       hot_wallet_target = excluded.hot_wallet_target,
       cold_wallet_target = excluded.cold_wallet_target,
       max_exposure = excluded.max_exposure,
       insurance_fund_balance = excluded.insurance_fund_balance,
       updated_at = now()`,
    [input.asset, input.totalAssets, input.hotWalletTarget, input.coldWalletTarget, input.maxExposure, input.insuranceFundBalance || '0'],
  );
}

export async function exposureReport() {
  const rows = await query<{
    asset: string;
    total_assets: string;
    max_exposure: string;
    insurance_fund_balance: string;
  }>('select asset, total_assets::text, max_exposure::text, insurance_fund_balance::text from treasury_positions order by asset');

  return rows.map((row) => ({
    asset: row.asset,
    totalAssets: row.total_assets,
    maxExposure: row.max_exposure,
    excessExposure: compare(row.total_assets, row.max_exposure) > 0 ? subtract(row.total_assets, row.max_exposure) : '0',
    insuranceFundBalance: row.insurance_fund_balance,
    breached: compare(row.total_assets, row.max_exposure) > 0,
  }));
}
