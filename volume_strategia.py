import time
import requests
import urllib3
import random
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAZIONE ---
TOKEN_NENO = "0x7c5E8AF2C7705517c6aF7d3637983449034C4368"
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# Legge i wallet usando nomi di chiavi logici dalle variabili d'ambiente
WALLETS = [
    os.environ.get("WALLET_ACCOUNT_1"),
    os.environ.get("WALLET_ACCOUNT_2"),
    os.environ.get("WALLET_ACCOUNT_3")
]

if any(w is None for w in WALLETS):
    print("❌ ERRORE: Uno o più wallet non sono caricati nelle variabili d'ambiente!")
    print("Assicurati di aver eseguito i comandi 'export' nel terminale.")
    exit(1)

def esegui_acquisto_diretto(wallet_address, importo_bnb):
    url = "https://li.quest/v1/quote"
    amount_in_wei = str(int(importo_bnb * 10**18))

    params = {
        "fromChain": 56,          
        "toChain": 56,            
        "fromToken": WBNB,        
        "toToken": TOKEN_NENO,    
        "fromAmount": amount_in_wei, 
        "fromAddress": wallet_address 
    }

    try:
        response = requests.get(url, params=params, verify=False)

        if response.status_code == 200:
            dati = response.json()
            estimate = dati.get('estimate', {})
            to_amount = estimate.get('toAmount', '0')
            price_impact = estimate.get('priceImpact', '0')

            print(f"🔥 [ROUTE OK] Wallet {wallet_address[:6]}... pronto!")
            print(f"   Invia: {importo_bnb} BNB -> Riceve: {float(to_amount)/10**18:.2f} NENO")
            print(f"   Price Impact: {float(price_impact)*100:.2f}%")
        else:
            print(f"❌ Errore Server (Status {response.status_code}): {response.text[:200]}")

    except Exception as e:
        print(f"🛑 Errore di rete: {e}")

# --- ESECUZIONE CICLO AUTOMATIZZATO ---
print("🚀 Avvio strategia Self-Volume (6 Fasi Frazionate)...")

for i in range(6):
    wallet_scelto = random.choice(WALLETS)
    importo_casuale = round(random.uniform(0.002, 0.004), 4)

    print(f"\n[Fase {i+1}/6] Tocca al wallet: {wallet_scelto}")
    esegui_acquisto_diretto(wallet_scelto, importo_casuale)
    
    # Pausa casuale tra 2 e 4 minuti per simulare attività umana sul grafico
    attesa = random.randint(120, 240)
    if i < 5:
        print(f"😴 Attesa casuale di {attesa} secondi...")
        time.sleep(attesa)

print("\n✅ Strategia di volume completata.")

