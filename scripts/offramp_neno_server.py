#!/usr/bin/env python3
"""
Sample NENO off-ramp script for server-to-server integration.

Usage:
    # Set environment variables first
    export API_URL="https://multi-chain-wallet-14.preview.emergentagent.com"
    export API_KEY="your_api_key"
    export API_SECRET="your_api_secret"
    
    python scripts/offramp_neno_server.py
"""

import time
import hmac
import hashlib
import json
import os
import requests

# Configuration from environment
BASE_URL = os.environ.get("API_URL", "https://multi-chain-wallet-14.preview.emergentagent.com")
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")


def sign_and_post(path, payload):
    if not API_KEY or not API_SECRET:
        print("❌ API_KEY and API_SECRET environment variables are required")
        return None
    
    url = BASE_URL + path
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = str(int(time.time()))

    to_sign = (timestamp + body).encode("utf-8")
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        to_sign,
        hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": API_KEY,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature,
    }

    print(f"\n➡️ POST {url}")
    print("Payload:", body)

    resp = requests.post(url, headers=headers, data=body, timeout=30)
    print("Status:", resp.status_code)

    try:
        data = resp.json()
        print("Response JSON:")
        print(json.dumps(data, indent=2))
        return data
    except Exception:
        print("Response Text:")
        print(resp.text)
        return None


def health():
    url = BASE_URL + "/api/ramp-api-health"
    print(f"\n➡️ GET {url}")
    r = requests.get(url, timeout=10)
    print("Status:", r.status_code)
    print("Body:", r.text)


def offramp_quote_neno(crypto_amount, source_address, iban):
    payload = {
        "fiat_currency": "EUR",
        "fiat_destination_iban": iban,
        "crypto_symbol": "NENO",
        "crypto_currency": "NENO",
        "crypto_amount": crypto_amount,
        "source_address": source_address,
    }
    return sign_and_post("/api/ramp-api-offramp-quote", payload)


def offramp_execute(quote_id, reference_id="withdraw-nn-server-1"):
    payload = {
        "quote_id": quote_id,
        "payout_method": "sepa",
        "reference_id": reference_id,
    }
    return sign_and_post("/api/ramp-api-offramp", payload)


if __name__ == "__main__":
    health()

    amount = 0.01
    source = "0xC28eFdB734B8d789658421DfC10d8Cca50131721"
    iban = "IT22B0200822800000103317304"

    print("\n=== OFF-RAMP NENO → EUR (SERVER) ===")
    print("NENO:", amount)
    print("Source:", source)
    print("IBAN:", iban)

    quote = offramp_quote_neno(amount, source, iban)

    if not quote or "quote_id" not in quote:
        print("\n❌ No quote_id received, stopping.")
    else:
        qid = quote["quote_id"]
        print("\n✅ quote_id:", qid)
        tx = offramp_execute(qid)
        print("\n✅ OFF-RAMP Result:")
        print(tx)
