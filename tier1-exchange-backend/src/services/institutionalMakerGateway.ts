import type { HiddenLiquidity } from "./hiddenLiquidityPool.js";

export class InstitutionalMakerGateway {
  segment(providers: HiddenLiquidity[], amount: string): Array<HiddenLiquidity & { eligible: boolean }> {
    const value = Number(amount);
    return providers.map((provider) => ({
      ...provider,
      eligible: value >= Number(provider.minSize) && (Number(provider.maxSize) === 0 || value <= Number(provider.maxSize)),
    }));
  }
}
