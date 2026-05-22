import { randomUUID } from "node:crypto";
import { createPublicKey, verify } from "node:crypto";
import { recoverPersonalSignAddress } from "../crypto/evm-signature.js";

const EVM_CHAINS = new Set(["ethereum", "bnb", "polygon", "base"]);

export class WalletService {
  constructor({ eventBus, store }) {
    this.eventBus = eventBus;
    this.store = store;
    this.challenges = new Map();
    this.sessions = new Map();
    for (const challenge of this.store?.loadWalletChallenges?.() ?? []) this.challenges.set(challenge.id, challenge);
    for (const session of this.store?.loadWalletSessions?.() ?? []) this.sessions.set(session.id, session);
  }

  createChallenge({ userId, address, chain, walletType = "walletconnect" }) {
    const nonce = randomUUID();
    const normalizedChain = chain.toLowerCase();
    const message = [
      "MetaSwap V3 wallet authentication",
      `User: ${userId}`,
      `Address: ${address}`,
      `Chain: ${normalizedChain}`,
      `Nonce: ${nonce}`,
      `Issued At: ${new Date().toISOString()}`
    ].join("\n");
    const challenge = {
      id: randomUUID(),
      userId,
      address,
      chain: normalizedChain,
      walletType,
      nonce,
      message,
      expiresAt: Date.now() + 5 * 60_000
    };
    this.challenges.set(challenge.id, challenge);
    this.store?.saveWalletChallenge?.(challenge);
    this.eventBus.publish("WalletChallengeCreated", { challengeId: challenge.id, userId, address, chain: normalizedChain, walletType });
    return challenge;
  }

  verifyChallenge({ challengeId, signature, publicKey }) {
    const challenge = this.challenges.get(challengeId);
    if (!challenge) throw new Error("Unknown wallet challenge");
    if (Date.now() > challenge.expiresAt) throw new Error("Wallet challenge expired");
    const verifiedAddress = EVM_CHAINS.has(challenge.chain)
      ? recoverPersonalSignAddress(challenge.message, signature)
      : verifySolanaSignature({ message: challenge.message, signature, publicKey, expectedAddress: challenge.address });
    if (verifiedAddress.toLowerCase() !== challenge.address.toLowerCase()) throw new Error("Wallet signature address mismatch");
    const session = {
      id: randomUUID(),
      userId: challenge.userId,
      address: challenge.address,
      chain: challenge.chain,
      walletType: challenge.walletType,
      status: "active",
      createdAt: new Date().toISOString()
    };
    this.sessions.set(session.id, session);
    this.store?.saveWalletSession?.(session);
    this.eventBus.publish("WalletSessionVerified", session);
    return session;
  }

  sessionsForUser(userId) {
    return [...this.sessions.values()].filter((session) => session.userId === userId && session.status === "active");
  }

  getSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (!session || session.status !== "active") throw new Error("Active wallet session not found");
    return session;
  }

  tokenImportMetadata(asset, chain) {
    const address = asset.contracts?.[chain];
    if (!address) throw new Error(`Asset ${asset.symbol} is not deployed on ${chain}`);
    return {
      chain,
      evm: {
        method: "wallet_watchAsset",
        params: {
          type: "ERC20",
          options: {
            address,
            symbol: asset.symbol,
            decimals: asset.decimals ?? 18,
            image: asset.logoUri ?? undefined
          }
        }
      },
      asset: {
        symbol: asset.symbol,
        name: asset.name,
        address,
        decimals: asset.decimals ?? 18
      }
    };
  }
}

function verifySolanaSignature({ message, signature, publicKey, expectedAddress }) {
  if (!publicKey) throw new Error("Solana public key is required");
  if (publicKey !== expectedAddress) throw new Error("Solana public key mismatch");
  const raw = base58Decode(publicKey);
  if (raw.length !== 32) throw new Error("Invalid Solana public key");
  const derPrefix = Buffer.from("302a300506032b6570032100", "hex");
  const key = createPublicKey({ key: Buffer.concat([derPrefix, Buffer.from(raw)]), format: "der", type: "spki" });
  const ok = verify(null, Buffer.from(message), key, Buffer.from(signature, "base64"));
  if (!ok) throw new Error("Invalid Solana signature");
  return expectedAddress;
}

function base58Decode(value) {
  const alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  let number = 0n;
  for (const char of value) {
    const index = alphabet.indexOf(char);
    if (index < 0) throw new Error("Invalid base58 character");
    number = number * 58n + BigInt(index);
  }
  const bytes = [];
  while (number > 0n) {
    bytes.unshift(Number(number & 0xffn));
    number >>= 8n;
  }
  for (const char of value) {
    if (char === "1") bytes.unshift(0);
    else break;
  }
  return Uint8Array.from(bytes);
}
