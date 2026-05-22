import time
import requests
import urllib3
import random
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAZIONE ---
TOKEN_NENO = "0x7c5e8af2c7705517c6af7d3637983449034c4368"
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# Usiamo un indirizzo generico visto che non spendiamo gas, non servono variabili d'ambiente
WALLET_SIMULATO = "0xEB11aeBA04902b6b53E329B81eeF02abd5BA9F45"

def simula_traffico_api(importo_bnb):
    url = "https://li.quest"
    amount_in_wei = str(int(importo_bnb * 10**18))

    params = {
        "fromChain": 56,          
        "toChain": 56,            
        "fromToken": WBNB,        
        "toToken": TOKEN_NENO,    
        "fromAmount": amount_in_wei, 
        "fromAddress": WALLET_SIMULATO 
    }

    try:
        # Interroga il motore di LI.FI ad alta velocità
        response = requests.get(url, params=params, verify=False, timeout=3)

        if response.status_code == 200:
            dati = response.json()
            estimate = dati.get('estimate', {})
            to_amount = estimate.get('toAmount', '0')
            print(f"📡 [PING API OK] Simulazione query: {importo_bnb} BNB -> Calcolati: {float(to_amount)/10**18:.0f} NENO sui nodi BSC")
        else:
            print(f"❌ Server occupato (Status {response.status_code})")

    except Exception as e:
        pass # Ignora gli errori di rete per mantenere la raffica continua

# --- LOOP CONTINUO A COSTO ZERO ---
print("⚙️ MACCHINA DEL VOLUME VIRTUALE ATTIVATA (Frequenza 5s - 0 gas) ⚙️")
print("Lascia correre questo script per mantenere il contratto attivo sui radar.")
print("-" * 65)

contatore = 1
while True:
    # Genera richieste con importi casuali per simulare trader diversi che calcolano lo swap
    importo_casuale = round(random.uniform(0.005, 0.05), 4)

    print(f"[{contatore}] Pinging router...", end=" ")
    simula_traffico_api(importo_casuale)
    
    contatore += 1
    # Spariamo ogni 5 secondi (massima velocità gratuita)
    time.sleep(5)
