import requests


class MetaSwapClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def health(self):
        return self.get("/health")

    def plans(self):
        return self.get("/developer/plans")

    def revenue_scale_plan(self):
        return self.get("/revenue/scale-plan")

    def rpc(self, chain: str, method: str, params=None):
        return self.post("/rpc/proxy", {"chain": chain, "method": method, "params": params or []})

    def acceleration_quote(self, chain: str, urgency: str = "standard", estimated_gas: int = 21000):
        return self.post("/tx/acceleration/quote", {"chain": chain, "urgency": urgency, "estimatedGas": estimated_gas})

    def relay_transaction(self, chain: str, raw_transaction: str, urgency: str = "standard"):
        return self.post("/tx/relay", {"chain": chain, "rawTransaction": raw_transaction, "urgency": urgency, "userConsent": True})

    def subscribe_webhook(self, url: str, events: list[str]):
        return self.post("/webhooks", {"url": url, "events": events})

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict):
        return self.request("POST", path, body)

    def request(self, method: str, path: str, body: dict | None = None):
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        response = requests.request(method, f"{self.base_url}{path}", json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
