const { ethers } = require('ethers');
const { getTokenConfig } = require('../blockchain/tokenRegistry.cjs');

const ERC20_ABI = [
  'function transfer(address to, uint256 value) returns (bool)',
  'function balanceOf(address account) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'event Transfer(address indexed from, address indexed to, uint256 value)',
];

class EVMChainAdapter {
  constructor(config) {
    this.config = config;
    this.provider = null;
    this.signer = null;
  }

  getRpcUrl() {
    const rpcUrl = process.env[this.config.rpcEnv] || this.config.defaultRpcUrl;
    if (!rpcUrl) {
      throw new Error(`${this.config.rpcEnv} is required for ${this.config.chainName}`);
    }
    return rpcUrl.split(',').map((url) => url.trim()).filter(Boolean)[0];
  }

  getProvider() {
    if (!this.provider) {
      this.provider = new ethers.JsonRpcProvider(this.getRpcUrl(), this.config.chainId);
    }
    return this.provider;
  }

  getPrivateKey() {
    const scopedKey = process.env[`${this.config.key}_HOT_WALLET_PRIVATE_KEY`];
    const fallback = process.env.HOT_WALLET_PRIVATE_KEY || process.env.BSC_PRIVATE_KEY;
    const privateKey = scopedKey || fallback;
    if (!privateKey) {
      throw new Error(`${this.config.key}_HOT_WALLET_PRIVATE_KEY or HOT_WALLET_PRIVATE_KEY is required`);
    }
    return privateKey;
  }

  getSigner() {
    if (!this.signer) {
      this.signer = new ethers.NonceManager(new ethers.Wallet(this.getPrivateKey(), this.getProvider()));
    }
    return this.signer;
  }

  async getHotWalletAddress() {
    const address = await this.getSigner().getAddress();
    const required = process.env.EXECUTION_WALLET_ADDRESS;
    if (required && address.toLowerCase() !== this.validateAddress(required, 'EXECUTION_WALLET_ADDRESS').toLowerCase()) {
      throw new Error(`Configured signer ${address} does not match required execution wallet`);
    }
    return address;
  }

  validateAddress(address, fieldName = 'address') {
    if (!address || !ethers.isAddress(address)) {
      throw new Error(`${fieldName} must be a valid EVM address`);
    }
    return ethers.getAddress(address);
  }

  getConfirmationsThreshold() {
    return Number.parseInt(process.env[this.config.confirmationsEnv] || '3', 10);
  }

  getFinalityThreshold() {
    return Number.parseInt(process.env[this.config.finalityEnv] || '12', 10);
  }

  async getTokenBalance(asset, address) {
    const token = getTokenConfig(asset, this.config.key);
    const contract = new ethers.Contract(token.address, ERC20_ABI, this.getProvider());
    const balance = await contract.balanceOf(this.validateAddress(address));
    return ethers.formatUnits(balance, token.decimals);
  }

  async getNativeBalance(address) {
    const balance = await this.getProvider().getBalance(this.validateAddress(address));
    return ethers.formatEther(balance);
  }

  async broadcastTokenTransfer({ asset, toAddress, amount, transactionId }) {
    if (process.env.BLOCKCHAIN_EXECUTION_MODE !== 'real') {
      throw new Error('BLOCKCHAIN_EXECUTION_MODE must be real for broadcast');
    }

    const token = getTokenConfig(asset, this.config.key);
    const signer = this.getSigner();
    const fromAddress = await this.getHotWalletAddress();
    const recipient = this.validateAddress(toAddress, 'toAddress');
    const contract = new ethers.Contract(token.address, ERC20_ABI, signer);
    const units = ethers.parseUnits(String(amount), token.decimals);

    if (units <= 0n) {
      throw new Error('Transfer amount must be greater than zero');
    }

    const balance = await contract.balanceOf(fromAddress);
    if (balance < units) {
      throw new Error(`Insufficient ${token.symbol} hot-wallet balance on ${this.config.chainName}`);
    }

    const tx = await contract.transfer(recipient, units);
    return {
      txHash: tx.hash,
      fromAddress,
      toAddress: recipient,
      rawTxData: {
        hash: tx.hash,
        nonce: tx.nonce,
        chainId: this.config.chainId,
        chainName: this.config.chainName,
        settlementLayer: this.config.settlementLayer,
        from: tx.from,
        to: tx.to,
        data: tx.data,
        value: tx.value ? tx.value.toString() : '0',
        gasLimit: tx.gasLimit ? tx.gasLimit.toString() : undefined,
        gasPrice: tx.gasPrice ? tx.gasPrice.toString() : undefined,
        transactionId,
        asset: token.symbol,
        tokenAddress: token.address,
        amount: String(amount),
      },
    };
  }

  async getTransactionStatus(txHash) {
    const provider = this.getProvider();
    const tx = await provider.getTransaction(txHash);
    const receipt = await provider.getTransactionReceipt(txHash);
    const currentBlock = await provider.getBlockNumber();

    if (!receipt) {
      return {
        txHash,
        chainStatus: tx ? 'pending' : 'not_found',
        finalityStatus: tx ? 'pending' : 'not_found',
        confirmations: 0,
        blockNumber: null,
        gasUsed: null,
        receiptStatus: null,
        chainId: this.config.chainId,
        chainName: this.config.chainName,
        settlementLayer: this.config.settlementLayer,
      };
    }

    const confirmations = Math.max(currentBlock - receipt.blockNumber + 1, 0);
    const chainStatus =
      receipt.status === 0
        ? 'failed'
        : confirmations >= this.getFinalityThreshold()
          ? 'finalized'
          : confirmations >= this.getConfirmationsThreshold()
            ? 'confirmed'
            : 'included';

    return {
      txHash,
      chainStatus,
      finalityStatus: chainStatus,
      confirmations,
      blockNumber: receipt.blockNumber,
      gasUsed: receipt.gasUsed.toString(),
      receiptStatus: receipt.status,
      chainId: this.config.chainId,
      chainName: this.config.chainName,
      settlementLayer: this.config.settlementLayer,
    };
  }
}

module.exports = {
  ERC20_ABI,
  EVMChainAdapter,
};
