# Token Factory Deployment

MetaSwapV3 includes a production EVM token factory contract at `contracts/evm/MetaSwapV3TokenFactory.sol`.

To deploy factory contracts to Ethereum, BNB Chain, Base and Polygon mainnet:

```powershell
$env:DEPLOYER_PRIVATE_KEY="0x..."
npm run deploy:token-factories
```

Requirements:

- `.env.production` must contain mainnet `*_RPC_URLS`.
- `DEPLOYER_PRIVATE_KEY` must control a funded deployer wallet on each EVM chain.
- The deployer becomes the factory owner.

The script writes:

- `ETHEREUM_TOKEN_FACTORY_ADDRESS`
- `BNB_TOKEN_FACTORY_ADDRESS`
- `BASE_TOKEN_FACTORY_ADDRESS`
- `POLYGON_TOKEN_FACTORY_ADDRESS`
- `SOLANA_TOKEN_FACTORY_ADDRESS`

Solana uses the canonical SPL Token Program ID unless a proprietary program ID is already present.
