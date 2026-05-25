import { decimalToUnits, unitsToDecimal } from "../core/store.js";
import { PriceOracleService, type PriceSnapshot } from "./priceOracleService.js";

const SCALE = 8;
const NENO_USDT_RATE = process.env.NENO_USDT_RATE ?? "20000";
const WBNB_USDT_PRICE = process.env.WBNB_USDT_PRICE ?? "1000";

export interface ValuationMetadata {
  sourceAsset: string;
  sourceAmount: string;
  sourceValuationUSDT: string;
  exchangeRate: string;
  oracle: {
    pair: string;
    price: string;
    mode: "deterministic-local" | "external" | "ledger-fixed-rate";
    source?: string;
    capturedAt?: string;
    replayKey?: string;
  };
  targetAsset: string;
  targetAmount: string;
}

export class ValuationService {
  constructor(private readonly oracle = new PriceOracleService()) {}

  nenoToUsdt(amount: string): string {
    return multiplyDecimal(amount, NENO_USDT_RATE);
  }

  async swapNenoToWbnbWithOracle(amount: string): Promise<ValuationMetadata> {
    return this.swapNenoToWbnbFromSnapshot(amount, await this.oracle.wbnbUsdtSnapshot());
  }

  async swapNenoToAsset(amount: string, targetAsset: string): Promise<ValuationMetadata> {
    const normalized = targetAsset.toUpperCase();
    if (normalized === "WBNB") return this.swapNenoToWbnbWithOracle(amount);
    if (normalized === "ETH" || normalized === "WETH" || normalized === "BTC" || normalized === "WBTC") {
      const oracleAsset = normalized === "WETH" ? "ETH" : normalized === "WBTC" ? "BTC" : normalized;
      const sourceValuationUSDT = this.nenoToUsdt(amount);
      const snapshot = await this.oracle.assetUsdtSnapshot(oracleAsset);
      return {
        sourceAsset: "NENO",
        sourceAmount: amount,
        sourceValuationUSDT,
        exchangeRate: `1 NENO = ${NENO_USDT_RATE} USDT`,
        oracle: {
          pair: `${oracleAsset}/USDT`,
          price: snapshot.price,
          mode: snapshot.source === "deterministic" ? "deterministic-local" : "external",
          source: snapshot.source,
          capturedAt: snapshot.capturedAt,
          replayKey: snapshot.replayKey,
        },
        targetAsset: normalized,
        targetAmount: divideDecimal(sourceValuationUSDT, snapshot.price),
      };
    }
    if (normalized === "USDT" || normalized === "USDC") {
      const targetAmount = this.nenoToUsdt(amount);
      return {
        sourceAsset: "NENO",
        sourceAmount: amount,
        sourceValuationUSDT: targetAmount,
        exchangeRate: `1 NENO = ${NENO_USDT_RATE} ${normalized}`,
        oracle: {
          pair: `NENO/${normalized}`,
          price: NENO_USDT_RATE,
          mode: "ledger-fixed-rate",
        },
        targetAsset: normalized,
        targetAmount,
      };
    }
    throw new Error(`Unsupported NENO swap valuation target: ${targetAsset}`);
  }

  swapNenoToWbnb(amount: string): ValuationMetadata {
    return this.swapNenoToWbnbFromSnapshot(amount, {
      pair: "WBNB/USDT",
      price: WBNB_USDT_PRICE,
      source: process.env.WBNB_PRICE_FEED_URL ? "coingecko" : "deterministic",
      capturedAt: new Date().toISOString(),
      replayKey: "static-env-price",
      raw: {},
    });
  }

  private swapNenoToWbnbFromSnapshot(amount: string, snapshot: PriceSnapshot): ValuationMetadata {
    const sourceValuationUSDT = this.nenoToUsdt(amount);
    const targetAmount = divideDecimal(sourceValuationUSDT, snapshot.price);
    return {
      sourceAsset: "NENO",
      sourceAmount: amount,
      sourceValuationUSDT,
      exchangeRate: `1 NENO = ${NENO_USDT_RATE} USDT`,
      oracle: {
        pair: snapshot.pair,
        price: snapshot.price,
        mode: snapshot.source === "deterministic" ? "deterministic-local" : "external",
        source: snapshot.source,
        capturedAt: snapshot.capturedAt,
        replayKey: snapshot.replayKey,
      },
      targetAsset: "WBNB",
      targetAmount,
    };
  }

  offrampNenoToFiatEquivalent(amount: string, rate: string, targetAsset: string): ValuationMetadata {
    const sourceValuationUSDT = multiplyDecimal(amount, rate);
    return {
      sourceAsset: "NENO",
      sourceAmount: amount,
      sourceValuationUSDT,
      exchangeRate: `1 NENO = ${rate} ${targetAsset}`,
      oracle: {
        pair: `NENO/${targetAsset}`,
        price: rate,
        mode: "ledger-fixed-rate",
      },
      targetAsset,
      targetAmount: sourceValuationUSDT,
    };
  }
}

export function multiplyDecimal(left: string, right: string): string {
  const leftUnits = decimalToUnits(left, SCALE);
  const rightUnits = decimalToUnits(right, SCALE);
  return unitsToDecimal((leftUnits * rightUnits) / 10n ** BigInt(SCALE), SCALE);
}

export function divideDecimal(left: string, right: string): string {
  const leftUnits = decimalToUnits(left, SCALE);
  const rightUnits = decimalToUnits(right, SCALE);
  if (rightUnits === 0n) throw new Error("Division by zero in deterministic valuation");
  return unitsToDecimal((leftUnits * 10n ** BigInt(SCALE)) / rightUnits, SCALE);
}
