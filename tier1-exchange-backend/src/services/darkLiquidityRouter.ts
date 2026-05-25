import { HiddenLiquidityPool } from "./hiddenLiquidityPool.js";
import { InstitutionalMakerGateway } from "./institutionalMakerGateway.js";

export class DarkLiquidityRouter {
  constructor(
    private readonly pool = new HiddenLiquidityPool(),
    private readonly gateway = new InstitutionalMakerGateway(),
  ) {}

  route(asset: string, amount: string): Record<string, unknown> {
    const providers = this.gateway.segment(this.pool.providers(asset), amount);
    return {
      enabled: providers.length > 0,
      eligibleProviders: providers.filter((provider) => provider.eligible),
      segmentedVenue: "dark-liquidity",
      mandatory: Number(amount) >= Number(process.env.DARK_LIQUIDITY_MANDATORY_SIZE ?? 100_000),
    };
  }
}
