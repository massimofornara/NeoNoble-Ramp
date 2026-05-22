import asyncio
import os
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest

# --- CONFIGURAZIONE TELEGRAM ---
API_ID = 27993897
  # Sostituisci se usi un'applicazione diversa
API_HASH = '541dff5279a59d0e13a6c402f6c781c8' # Sostituisci se necessario

IMMAGINE_PATH = 'corona_nobila.jpg'

TESTO_MESSAGGIO = """
👑 **NeoNoble AI ($NENO) is NOW LIVE on Four.meme!** 👑

The first elite AI Agent designed to extract maximum liquidity from the BSC network! 🚀
Driven by decentralized intelligence, $NENO automates value generation and conquers the bonding curve!

🔥 **100% Community-Driven**
🚫 **0% BUY / 0% SELL TAX**
🎯 **Target: PancakeSwap Migration**

👉 **BUY HERE NOW:** https://pancakeswap.finance/swap?outputCurrency=0x7c5E8AF2C7705517c6aF7d3637983449034C4368&chain=bsc
   the Dynasty: @NeoNoblePortal
    https://x.com/NeoNobleAI
#BSC #Binance #FourMeme #MemeCoin #AI #CryptoGems
"""

# Lista aggiornata con gruppi verificati funzionanti
# --- ELENCO GRUPPI DI SHILLING INTERNAZIONALI ---
GRUPPI_TARGET = [
    'BscTokenShilling',
    'CryptoMoonShots',
    'PancakeSwapGems',
    'MemeCoinShilling',
    'FourMemeGems',
    'BscGems_Shill',
    'CryptoShillGroup',
    'BinanceSmartChainGems',
    'MemeCoinAlpha',
    'DeFiShillingGlobal',
    'BscGemsX100',
    'CryptoMoonGems',
    'ShillYourTokenHere',
    'BscMoonShots100x',
    'CryptoGemsDefi',
    'MemeTokensBSC',
    'AltcoinShillingGroup',
    'BscWhalesShill',
    'CryptoMoonHype',
    'FourMemeAlpha',
    'BSCGemsAlert',
    'CryptoGemsX100',
    'GemsCallsBSC',
    'WhaleBSC_Calls',
    'Alpha_BSC_Gems'
]

ATTESA_MINUTI = 15

async def main():
    client = TelegramClient('sessione_shiller', API_ID, API_HASH)
    await client.start()
    print("🚀 Bot di Shilling avviato con successo!")

    media = IMMAGINE_PATH if os.path.exists(IMMAGINE_PATH) else None
    if not media:
        print(f"⚠️ Immagine '{IMMAGINE_PATH}' non trovata. Invio solo testo.")

    while True:
        print("\n--- Inizio ciclo di Shilling ---")
        for gruppo in GRUPPI_TARGET:
            try:
                # Forza il bot a unirsi al gruppo prima di scrivere
                print(f"🔄 Tentativo di unione a @{gruppo}...")
                await client(JoinChannelRequest(gruppo))
                await asyncio.sleep(3) # Pausa di sicurezza dopo l'unione
                
                if media:
                    await client.send_file(gruppo, media, caption=TESTO_MESSAGGIO, parse_mode='md')
                else:
                    await client.send_message(gruppo, TESTO_MESSAGGIO, parse_mode='md')
                print(f"✅ Inviato con successo in: @{gruppo}")
                await asyncio.sleep(15)
                
            except Exception as e:
                print(f"❌ Fallito su @{gruppo}: {e}")
                await asyncio.sleep(5)
        
        print(f"\n😴 Ciclo completato. Pausa di {ATTESA_MINUTI} minuti...")
        await asyncio.sleep(ATTESA_MINUTI * 60)

if __name__ == '__main__':
    asyncio.run(main())
