import { bytesToHex, keccak256 } from "../crypto/keccak256.js";

export class TokenDeploymentService {
  constructor({ blockchainAdapters, eventBus }) {
    this.blockchainAdapters = blockchainAdapters;
    this.eventBus = eventBus;
  }

  async prepare(request) {
    const {
      chain,
      ownerAddress = request.address,
      name,
      symbol,
      maxSupply,
      decimals = 18
    } = request;
    const missing = [];
    if (!chain) missing.push("chain");
    if (!ownerAddress) missing.push("ownerAddress");
    if (!name) missing.push("name");
    if (!symbol) missing.push("symbol");
    if (maxSupply === undefined || maxSupply === null || maxSupply === "") missing.push("maxSupply");
    if (missing.length) {
      throw new Error(`Missing token deployment fields: ${missing.join(", ")}`);
    }
    const adapter = this.blockchainAdapters[chain];
    if (!adapter?.configured()) throw new Error(`RPC is required for ${chain}`);
    const transaction = chain === "solana"
      ? this.solanaInstruction({ adapter, ownerAddress, name, symbol, maxSupply, decimals })
      : await this.evmTransaction({ adapter, ownerAddress, name, symbol, maxSupply, decimals });
    this.eventBus.publish("TokenDeploymentPrepared", { chain, ownerAddress, symbol, transaction });
    return transaction;
  }

  async evmTransaction({ adapter, ownerAddress, name, symbol, maxSupply, decimals }) {
    if (!adapter.tokenFactoryAddress) throw new Error("EVM token factory contract address is required");
    const data = encodeFunctionCall("deployToken(string,string,uint256,uint8,address)", [
      { type: "string", value: name },
      { type: "string", value: symbol },
      { type: "uint256", value: BigInt(maxSupply) * 10n ** BigInt(decimals) },
      { type: "uint8", value: BigInt(decimals) },
      { type: "address", value: ownerAddress }
    ]);
    const tx = { from: ownerAddress, to: adapter.tokenFactoryAddress, data, value: "0x0" };
    const gas = await adapter.estimateGas(tx);
    return { chainId: adapter.chainId, type: "evm_factory_call", transaction: { ...tx, gas } };
  }

  solanaInstruction({ adapter, ownerAddress, name, symbol, maxSupply, decimals }) {
    if (!adapter.tokenFactoryAddress) throw new Error("Solana token program address is required");
    return {
      chainId: adapter.chainId,
      type: "solana_program_instruction",
      programId: adapter.tokenFactoryAddress,
      payer: ownerAddress,
      instruction: {
        action: "create_mint",
        name,
        symbol,
        maxSupply,
        decimals,
        mintAuthority: ownerAddress,
        freezeAuthority: ownerAddress
      }
    };
  }
}

function encodeFunctionCall(signature, args) {
  const selector = bytesToHex(keccak256(signature).slice(0, 4));
  const heads = [];
  const tails = [];
  let dynamicOffset = 32 * args.length;
  for (const arg of args) {
    if (arg.type === "string") {
      const encoded = encodeString(arg.value);
      heads.push(word(dynamicOffset));
      tails.push(encoded);
      dynamicOffset += encoded.length / 2;
    } else {
      heads.push(encodeStatic(arg));
    }
  }
  return `0x${selector}${heads.join("")}${tails.join("")}`;
}

function encodeStatic(arg) {
  if (arg.type.startsWith("uint")) return word(arg.value);
  if (arg.type === "address") return arg.value.toLowerCase().replace("0x", "").padStart(64, "0");
  throw new Error(`Unsupported ABI type ${arg.type}`);
}

function encodeString(value) {
  const bytes = new TextEncoder().encode(value);
  const length = word(bytes.length);
  const body = bytesToHex(bytes).padEnd(Math.ceil(bytes.length / 32) * 64, "0");
  return `${length}${body}`;
}

function word(value) {
  return BigInt(value).toString(16).padStart(64, "0");
}
