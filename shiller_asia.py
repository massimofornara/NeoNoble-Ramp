import asyncio
import os
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError

# --- CONFIGURAZIONE TELEGRAM ---
API_ID = 27993897
API_HASH = '541dff5279a59d0e13a6c402f6c781c8'

IMMAGINE_PATH = 'corona_nobila.jpg'

# Testo ottimizzato con fuso orario globale e richiamo ai mercati orientali
TESTO_MESSAGGIO = """
🚀 **NeoNoble AI ($NENO) - The Elite AI Agent is LIVE on Four.meme!** 🚀

Designed to extract maximum liquidity from the BSC network. 💎
Driven by decentralized intelligence, $NENO conquers the bonding curve!

🔥 **Asian & Global Whales Entering Now**
🚫 **0% BUY / 0% SELL TAX (No Dev Dump)**
🎯 **Target: Immediate PancakeSwap Migration**

     https://pancakeswap.finance/swap?outputCurrency=0x7c5E8AF2C7705517c6aF7d3637983449034C4368&chain=bsc
     Global Portal: @NeoNoblePortal
     https://x.com/NeoNobleAI
#BSC #Binance #FourMeme #MemeCoin #CryptoAlpha #CNGems #CryptoChina
"""

# Lista di canali, gruppi di discussione Alpha e mercati asiatici/globali
GRUPPI_TARGET = [
    'FourMemeCN',          # Canale/Gruppo Cinese ufficiale o correlato Four.meme
    'BscGemsChina',        # Community BSC orientata al mercato asiatico
     'CryptoAlphaAsia',     # Chiamate Alpha Asia
    'MemeCoinChina',       # Trader di meme orientali
    'FourMemeGlobal',      # Hub globale
    'BscWhalesCalls',      # Gruppo di shilling per investitori BSC grandi
    'PancakeSwapChina',    # Discussioni PancakeSwap orientate a est
    'BinanceChainCN',      # Community Binance Smart Chain in lingua
    'CryptoMoonCalls',     # Segnali e Shilling globale
    'BscGems100xCalls'     # Gemme BSC ad alto potenziale
]

ATTESA_MINUTI = 20  # Pausa leggermente più lunga per i mercati asiatici per evitare restrizioni rigide

async def main():
    client = TelegramClient('sessione_shiller_asia', API_ID, API_HASH)
    await client.start()
    print("🚀 Bot di Shilling Asia/Global avviato con successo!")

    media = IMMAGINE_PATH if os.path.exists(IMMAGINE_PATH) else None
    if not media:
        print(f"⚠️ Immagine '{IMMAGINE_PATH}' non trovata nella cartella attuale. Invio solo testo.")

    while True:
        print("\n--- Inizio ciclo di Shilling Asia/Global ---")
        for gruppo in GRUPPI_TARGET:
            try:
                print(f"🔄 Tentativo di ingresso automatico in @{gruppo}...")
                await client(JoinChannelRequest(gruppo))
                await asyncio.sleep(4)  # Pausa precauzionale post-ingresso
                
                if media:
                    await client.send_file(gruppo, media, caption=TESTO_MESSAGGIO, parse_mode='md')
                else:
                    await client.send_message(gruppo, TESTO_MESSAGGIO, parse_mode='md')
                print(f"✅ Inviato con successo in: @{gruppo}")
                await asyncio.sleep(20)  # Pausa tra un gruppo e l'altro per sicurezza antispam
                
            except FloodWaitError as e:
                print(f"⚠️ Telegram richiede di attendere. Pausa forzata di {e.seconds} secondi...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"❌ Impossibile procedere su @{gruppo}: {e}")
                await asyncio.sleep(5)
        
        print(f"\n😴 Ciclo notturno completato. Pausa di {ATTESA_MINUTI} minuti...")
        await asyncio.sleep(ATTESA_MINUTI * 60)

if __name__ == '__main__':
    asyncio.run(main())
