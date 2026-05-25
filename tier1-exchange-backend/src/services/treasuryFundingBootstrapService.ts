import { Contract, JsonRpcProvider, Wallet, parseUnits } from "ethers";
import { AssetRegistry } from "./assetRegistry.js";
import { TreasuryOnChainService } from "./treasuryOnChainService.js";

const ERC20_ABI = ["function transfer(address to,uint256 amount) returns (bool)"];

export interface TreasuryTopUpAction {
  asset: string;
  chainName: string;
  kind: "erc20" | "native-gas";
  fromConfigured: boolean;
  to: string;
  amount: string;
  reason: string;
  executable: boolean;
}

export class TreasuryFundingBootstrapService {
  constructor(
    private readonly registry = new AssetRegistry(),
    private readonly onChain = new TreasuryOnChainService(registry),
  ) {}

  async plan(): Promise<Record<string, unknown>> {
    const treasury = process.env.TREASURY_ADDRESS ?? "";
    const balances = await this.onChain.balances(treasury);
    const balanceRows = Array.isArray((balances as { balances?: unknown }).balances) ? ((balances as { balances: Array<Record<string, unknown>> }).balances) : [];
    const gasRows = Array.isArray((balances as { nativeGas?: unknown }).nativeGas) ? ((balances as { nativeGas: Array<Record<string, unknown>> }).nativeGas) : [];
    const topUps: TreasuryTopUpAction[] = [];
    for (const row of balanceRows) {
      const required = Number(row.requiredForBatch ?? 0);
      const balance = Number(row.balance ?? 0);
      if (required > balance) {
        topUps.push({
          asset: String(row.asset),
          chainName: String(row.chainName),
          kind: "erc20",
          fromConfigured: this.sourceConfigured(String(row.chainName)),
          to: treasury,
          amount: String(required - balance),
          reason: `balance ${balance} below required ${required}`,
          executable: this.sourceConfigured(String(row.chainName)) && String(row.asset) !== "ETH",
        });
      }
    }
    for (const row of gasRows) {
      const required = Number(row.requiredReserve ?? 0);
      const balance = Number(row.balance ?? 0);
      if (required > balance) {
        topUps.push({
          asset: String(row.asset),
          chainName: String(row.chainName),
          kind: "native-gas",
          fromConfigured: this.sourceConfigured(String(row.chainName)),
          to: treasury,
          amount: String(required - balance),
          reason: `gas reserve ${balance} below required ${required}`,
          executable: this.sourceConfigured(String(row.chainName)),
        });
      }
    }
    return {
      mode: "real-source-treasury-bootstrap",
      executeEnabled: process.env.TREASURY_BOOTSTRAP_EXECUTE === "1",
      sourceConfigured: {
        bsc: this.sourceConfigured("bsc"),
        ethereum: this.sourceConfigured("ethereum"),
      },
      balances,
      topUps,
      healthyAfterBootstrap: topUps.length === 0,
    };
  }

  async executeIfEnabled(): Promise<Record<string, unknown>> {
    const plan = await this.plan();
    if (process.env.TREASURY_BOOTSTRAP_EXECUTE !== "1") {
      return { ...plan, executed: false, reason: "TREASURY_BOOTSTRAP_EXECUTE is not enabled" };
    }
    const actions = (plan as { topUps: TreasuryTopUpAction[] }).topUps.filter((action) => action.executable);
    const receipts: Array<Record<string, unknown>> = [];
    for (const action of actions) {
      receipts.push(await this.execute(action));
    }
    return { ...plan, executed: receipts.length > 0, receipts };
  }

  private async execute(action: TreasuryTopUpAction): Promise<Record<string, unknown>> {
    const wallet = fundingWallet(action.chainName);
    if (action.kind === "native-gas") {
      const tx = await wallet.sendTransaction({ to: action.to, value: parseUnits(action.amount, 18) });
      return { asset: action.asset, chainName: action.chainName, txHash: tx.hash, kind: action.kind };
    }
    const asset = this.registry.require(action.asset);
    if (!asset.checksumAddress) throw new Error(`${asset.symbol} cannot be ERC20-funded because it is native`);
    const contract = new Contract(asset.checksumAddress, ERC20_ABI, wallet);
    const tx = await contract.transfer(action.to, parseUnits(action.amount, asset.decimals));
    return { asset: action.asset, chainName: action.chainName, txHash: tx.hash, kind: action.kind };
  }

  private sourceConfigured(chainName: string): boolean {
    const prefix = chainName.toUpperCase();
    return Boolean(process.env[`${prefix}_FUNDING_SOURCE_PRIVATE_KEY`] && process.env[`${prefix}_RPC_URL`]);
  }
}

function fundingWallet(chainName: string): Wallet {
  const prefix = chainName.toUpperCase();
  const rpcUrl = process.env[`${prefix}_RPC_URL`];
  const privateKey = process.env[`${prefix}_FUNDING_SOURCE_PRIVATE_KEY`];
  if (!rpcUrl || !privateKey) throw new Error(`${prefix}_RPC_URL and ${prefix}_FUNDING_SOURCE_PRIVATE_KEY are required for treasury bootstrap execution`);
  const chainId = chainName === "ethereum" ? Number(process.env.ETHEREUM_CHAIN_ID ?? 1) : Number(process.env.BSC_CHAIN_ID ?? 56);
  return new Wallet(privateKey, new JsonRpcProvider(rpcUrl, chainId));
}
