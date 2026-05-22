"""
NeoNoble Ramp — Service Registry & Domain Architecture.

Maps the monolith's logical microservice domains to their routes and services.
This registry enables future extraction into independent services.

Domains:
  1. EXCHANGE    — NENO Exchange, Trading Engine, Order Book
  2. WALLET      — Multi-chain Wallet, Balances, Deposits
  3. BANKING     — IBAN/SEPA, Card Issuing (NIUM), Off-Ramp
  4. COMPLIANCE  — KYC/AML, PEP Screening, Audit, Export
  5. ANALYTICS   — Portfolio, Monte Carlo VaR, Market Data
  6. GATEWAY     — Auth, Public API, Dev Portal, Webhooks
  7. NOTIFICATION — Email, SMS, Push, SSE
  8. SCHEDULER   — Background jobs, DCA bot, Price alerts
"""

DOMAIN_REGISTRY = {
    "exchange": {
        "description": "NENO Exchange, Trading Engine, Order Book, DCA Bot",
        "routes": [
            "neno_exchange_routes",
            "exchange_routes",
            "trading_engine_routes",
            "advanced_orders_routes",
            "dca_routes",
            "dex_routes",
        ],
        "services": [
            "neno_price_history",
            "dex/dex_service",
            "dex/batch_executor",
            "exchanges/connector_manager",
            "exchanges/binance_connector",
            "exchanges/kraken_connector",
            "exchanges/coinbase_connector",
        ],
        "db_collections": [
            "neno_transactions", "trades", "orders", "order_book",
            "custom_tokens", "dca_plans", "dca_executions",
        ],
    },
    "wallet": {
        "description": "Multi-chain Wallet, Balances, Token Discovery",
        "routes": ["wallet_routes", "multichain_routes", "token_routes"],
        "services": ["multichain_service", "blockchain_listener"],
        "db_collections": ["wallets", "wallet_transactions", "tokens"],
    },
    "banking": {
        "description": "IBAN/SEPA Banking, Card Issuing, NIUM Integration",
        "routes": [
            "banking_routes", "card_routes",
            "nium_onboarding_routes", "stripe_payout_routes",
            "ramp_api", "user_ramp", "transak_routes",
        ],
        "services": ["nium_service", "nium_banking_service"],
        "db_collections": [
            "banking_transactions", "cards", "ibans",
            "nium_customers", "stripe_payouts",
        ],
    },
    "compliance": {
        "description": "KYC/AML Tiers, PEP Screening, Sanctions, Audit, Export",
        "routes": [
            "kyc_routes", "pep_routes", "audit_routes",
            "admin_audit_routes", "export_routes",
        ],
        "services": [
            "kyc_verification_service", "pep_screening_service",
            "audit_service", "audit_logger",
        ],
        "db_collections": [
            "kyc_submissions", "kyc_tiers", "pep_screening_log",
            "pep_watchlist", "audit_events", "compliance_reports",
        ],
    },
    "analytics": {
        "description": "Portfolio Analytics, Monte Carlo VaR, Market Data, Price History",
        "routes": [
            "analytics_routes", "advanced_analytics_routes",
            "montecarlo_routes", "market_data_routes",
            "price_history_routes",
        ],
        "services": ["neno_price_history"],
        "db_collections": ["price_history", "portfolio_snapshots"],
    },
    "gateway": {
        "description": "Auth, Public API, Dev Portal, Webhooks, API Keys",
        "routes": [
            "auth", "password_routes", "totp_routes",
            "dev_portal", "public_api_routes",
            "webhook_routes", "webhooks",
        ],
        "services": ["auth_service", "api_key_service"],
        "db_collections": ["users", "api_keys", "webhook_subscriptions", "webhook_events"],
    },
    "notification": {
        "description": "Email, SMS, Push, SSE Notifications",
        "routes": ["notification_routes", "alert_routes"],
        "services": ["notification_service", "notification_dispatch", "email_service"],
        "db_collections": ["notifications", "price_alerts"],
    },
    "scheduler": {
        "description": "Background Jobs, DCA Execution, Price Monitoring",
        "routes": [],
        "services": ["background_scheduler"],
        "db_collections": [],
    },
    "infrastructure": {
        "description": "PoR, Liquidity, Monitoring, Migration, Subscriptions, Referrals",
        "routes": [
            "por_api", "liquidity_routes", "monitoring",
            "migration_control", "subscription_routes",
            "referral_routes", "websocket_routes",
        ],
        "services": ["por_engine", "liquidity/*"],
        "db_collections": [
            "referral_codes", "referral_links", "referral_bonus_log",
            "subscriptions",
        ],
    },
}


def get_domain_for_route(route_name: str) -> str:
    """Find which domain a route belongs to."""
    for domain, config in DOMAIN_REGISTRY.items():
        if route_name in config["routes"]:
            return domain
    return "unknown"


def get_all_collections() -> list:
    """Get all MongoDB collections across all domains."""
    collections = set()
    for config in DOMAIN_REGISTRY.values():
        collections.update(config["db_collections"])
    return sorted(collections)
