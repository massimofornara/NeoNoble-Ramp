from typing import Optional, List
from decimal import Decimal
import logging
import time
from web3 import Web3
from web3.exceptions import ContractLogicError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SwapRequest(BaseModel):
    user_id: str
    from_token: str                    # indirizzo contratto o "NENO"
    to_token: str                      # indirizzo contratto
    amount_in: Decimal
    chain: str = "bsc"
    slippage: float = 0.8              # percentuale
    user_wallet_address: str           # wallet che deve ricevere i token

class SwapResult(BaseModel):
    success: bool
    tx_hash: Optional[str] = None
    amount_out: Optional[Decimal] = None
    error: Optional[str] = None
    message: Optional[str] = None

class SwapEngine:
    # PancakeSwap V2 Router su BSC Mainnet
    PANCAKE_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

    def __init__(self):
        self.rpc_url = "https://bsc-dataseed.binance.org/"
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        # Hot wallet della piattaforma (usa variabili d'ambiente in produzione!)
        self.hot_wallet_address = "0xYOUR_HOT_WALLET_ADDRESS_HERE"
        self.hot_wallet_private_key = "0xYOUR_PRIVATE_KEY_HERE"

        # Indirizzo WBNB (usato come intermediario quando non c'è liquidità diretta)
        self.wbnb_address = "0xbb4CdB9CBd36B01bD1c0A0C9b3f4f6f2f5a1f5a1"

    async def execute_swap(self, request: SwapRequest) -> SwapResult:
        try:
            if not self.w3.is_connected():
                raise Exception("Non connesso alla BSC RPC")

            # 1. Ottieni decimali
            from_decimals = await self._get_decimals(request.from_token)
            to_decimals = await self._get_decimals(request.to_token)

            amount_in_wei = int(request.amount_in * Decimal(10 ** from_decimals))

            # 2. Costruisci path: from → WBNB → to (per massimizzare probabilità di esecuzione)
            path: List[str] = [request.from_token, self.wbnb_address, request.to_token]

            # 3. Calcola amount out minimo con slippage
            router = self.w3.eth.contract(address=self.PANCAKE_ROUTER, abi=self._get_router_abi())
            
            try:
                amounts_out = router.functions.getAmountsOut(
                    amount_in_wei, path
                ).call()
                estimated_out = Decimal(amounts_out[-1]) / Decimal(10 ** to_decimals)
            except ContractLogicError:
                # Se non c'è liquidità diretta, usiamo una stima conservativa
                estimated_out = request.amount_in * Decimal("0.92")  # 8% di perdita stimata

            amount_out_min = int(estimated_out * Decimal(10 ** to_decimals) * Decimal(1 - request.slippage / 100))

            # 4. Esegui lo swap reale tramite Pancake Router
            nonce = self.w3.eth.get_transaction_count(self.hot_wallet_address)
            gas_price = self.w3.eth.gas_price

            # Approva il token di input (se necessario)
            await self._approve_token(request.from_token, amount_in_wei)

            # Swap
            swap_tx = router.functions.swapExactTokensForTokens(
                amount_in_wei,
                amount_out_min,
                path,
                request.user_wallet_address,   # ← i token vanno direttamente all'utente
                int(time.time()) + 1200        # deadline 20 minuti
            ).build_transaction({
                'from': self.hot_wallet_address,
                'gas': 500000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })

            # Firma e invia
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.hot_wallet_private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Attendi conferma
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt.status == 1:
                logger.info(f"Swap on-chain riuscito! Tx: {tx_hash.hex()}")
                return SwapResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    amount_out=estimated_out,
                    message="Swap eseguito su PancakeSwap e inviato all'utente"
                )
            else:
                raise Exception("Transazione fallita on-chain")

        except Exception as e:
            logger.error(f"Errore execute_swap: {str(e)}", exc_info=True)
            return SwapResult(
                success=False,
                error=str(e),
                message="Swap fallito. Controlla liquidità o saldo hot wallet."
            )

    async def _get_decimals(self, token_address: str) -> int:
        try:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=[{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]
            )
            return token_contract.functions.decimals().call()
        except:
            return 18  # default per la maggior parte dei token

    async def _approve_token(self, token_address: str, amount: int):
        """Approva il Pancake Router a spendere i token dall'hot wallet"""
        try:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=[{"constant":False,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]
            )

            allowance = token_contract.functions.allowance(self.hot_wallet_address, self.PANCAKE_ROUTER).call()
            if allowance < amount:
                approve_tx = token_contract.functions.approve(
                    self.PANCAKE_ROUTER, amount
                ).build_transaction({
                    'from': self.hot_wallet_address,
                    'gas': 100000,
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.hot_wallet_address),
                })

                signed = self.w3.eth.account.sign_transaction(approve_tx, self.hot_wallet_private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                logger.info(f"Approvazione eseguita per {token_address}")
        except Exception as e:
            logger.warning(f"Errore approvazione token: {e}")

    def _get_router_abi(self):
        return [
            {"inputs":[{"name":"amountIn","type":"uint256"},{"name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},
            {"inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}
        ]
