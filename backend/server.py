from services.exchanges.connector_manager import get_connector_manager
from services.liquidity.routing_service import MarketRoutingService,set_routing_service
from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from services.arbitrage.arbitrage_engine import ArbitrageEngine
from services.mev.mev_engine import MEVEngine
from services.institutional.dark_pool import DarkPool
from services.institutional.rfq_engine import RFQEngine
from services.treasury.netting_engine import NettingEngine
from services.profit.ai_pricing_engine import AIPricingEngine
from services.profit.cross_chain_arbitrage import CrossChainArbitrage
from services.clearing.clearing_engine import ClearingEngine
from services.risk.risk_engine import RiskEngine
from services.profit.advanced_sor import AdvancedSOR


arb_engine = ArbitrageEngine()
mev_engine = MEVEngine()

@app.on_event("startup")
async def start_profit_engines():
    import asyncio
    asyncio.create_task(mev_engine.run())

app = FastAPI()

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate required environment variables
def validate_env():
    required_vars = ['MONGO_URL', 'DB_NAME']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")
    
    # Warn about optional but recommended vars
    if not os.environ.get('API_SECRET_ENCRYPTION_KEY'):
        logger.warning(
            "API_SECRET_ENCRYPTION_KEY not set. Platform API keys will not work."
        )
    
    # Log blockchain integration status
    if os.environ.get('BSC_RPC_URL'):
        logger.info("BSC_RPC_URL configured - blockchain integration enabled")
    else:
        logger.warning("BSC_RPC_URL not set - blockchain monitoring disabled")
    
    if os.environ.get('NENO_WALLET_MNEMONIC'):
        logger.info("NENO_WALLET_MNEMONIC configured - HD wallet enabled")
    else:
        logger.warning("NENO_WALLET_MNEMONIC not set - deposit address generation disabled")
    
    if os.environ.get('STRIPE_SECRET_KEY'):
        logger.info("STRIPE_SECRET_KEY configured - Stripe payouts enabled")
    else:
        logger.warning("STRIPE_SECRET_KEY not set - payouts will be logged for manual processing")

validate_env()

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'neonoble_ramp')]

# Set database instance for routes
from database.mongodb import set_database
set_database(db)

# Import services
from services.auth_service import AuthService
from services.api_key_service import PlatformApiKeyService
from services.ramp_service import RampService
from services.pricing_service import pricing_service
from services.wallet_service import WalletService
from services.blockchain_listener import BlockchainListener
from services.stripe_payout_service import StripePayoutService
from services.por_engine import InternalPoRProvider
from services.settlement_service import SettlementService
from services.audit_logger import AuditLogger, set_audit_logger
from services.webhook_service import WebhookService, set_webhook_service
from services.real_payout_service import RealPayoutService, set_real_payout_service


# Import liquidity services (Hybrid PoR Liquidity Architecture)
from services.liquidity import (
    TreasuryService, set_treasury_service,
    ExposureService, set_exposure_service,
    MarketRoutingService, set_routing_service,
    HedgingService, set_hedging_service,
    ReconciliationService, set_reconciliation_service
)

# Import DEX services (C-SAFE Real Market Conversion)
from services.dex import DEXService, BatchExecutor, set_dex_service

# Import Exchange Connectors (Phase 2 - Venue Integration)
from services.exchanges import ConnectorManager, set_connector_manager

# Import Transak service (On/Off-Ramp Widget)
from services.transak_service import TransakService, set_transak_service

# Import Email service (Password Reset)
from services.email_service import EmailService, set_email_service

# Import Audit service (Transaction Timeline)
from services.audit_service import TransactionAuditService, set_audit_service

# Import database modules for PostgreSQL migration
from database.dual_manager import get_dual_db_manager
from database.config import get_pg_session_factory, init_pg_engine

# Import routes
from routes.auth import router as auth_router, set_auth_service
from routes.dev_portal import router as dev_router, set_api_key_service
from routes.ramp_api import (
    router as ramp_api_router,
    set_services as set_ramp_api_services,
    set_execution_services
)
from routes.user_ramp import router as user_ramp_router, set_ramp_service
from routes.webhooks import router as webhooks_router, set_payout_service
from routes.por_api import router as por_router, set_por_engine
from routes.webhook_routes import router as webhook_mgmt_router, set_hmac_middleware as set_webhook_hmac
from routes.monitoring import router as monitoring_router, set_monitoring_services
from routes.migration_control import router as migration_router
from routes.stripe_payout_routes import (
    router as stripe_payout_router,
    set_payout_service as set_stripe_payout_service,
    set_por_engine as set_stripe_por_engine
)
from routes.liquidity_routes import router as liquidity_router
from routes.swap_routes import router as swap_router

# Import DEX and Transak routes
from routes.dex_routes import router as dex_router
from routes.transak_routes import router as transak_router
from routes.exchange_routes import router as exchange_router

# Import Password Reset routes
from routes.password_routes import router as password_router, set_password_reset_db

# Import Audit routes
from routes.audit_routes import router as audit_router

# Import WebSocket routes
from routes.websocket_routes import router as websocket_router

# Import Price History routes
from routes.price_history_routes import router as price_history_router

# Import Notification routes
from routes.notification_routes import router as notification_router

# Import Token Infrastructure routes
from routes.token_routes import router as token_router

# Import Subscription Infrastructure routes
from routes.subscription_routes import router as subscription_router

# Import Market Data routes
from routes.market_data_routes import router as market_data_router

# Import Analytics routes
from routes.analytics_routes import router as analytics_router

# Import Card Infrastructure routes
from routes.card_routes import router as card_router

# Import Trading Engine routes
from routes.trading_engine_routes import router as trading_engine_router

# Import Public API routes
from routes.public_api_routes import router as public_api_router

# Import Wallet & Settlement routes
from routes.wallet_routes import router as wallet_router

# Import Multi-Chain Wallet routes
from routes.multichain_routes import router as multichain_router

# Import Banking Rails routes
from routes.banking_routes import router as banking_router

# Import NENO Exchange routes
from routes.neno_exchange_routes import router as neno_exchange_router

# Import KYC/AML Compliance routes
from routes.kyc_routes import router as kyc_router

# Import Advanced Orders routes
from routes.advanced_orders_routes import router as advanced_orders_router

# Import 2FA TOTP routes
from routes.totp_routes import router as totp_router

# Import Admin Audit routes
from routes.admin_audit_routes import router as admin_audit_router

# Import Export routes
from routes.export_routes import router as export_router

# Import NIUM Onboarding routes
from routes.nium_onboarding_routes import router as nium_onboarding_router

# Import Alert & Browser Push routes
from routes.alert_routes import router as alert_router

# Import DCA Bot routes
from routes.dca_routes import router as dca_router

# Import Market Maker routes
from routes.market_maker_routes import router as market_maker_router
from routes.exchange_orders_routes import router as exchange_orders_router
from routes.institutional_routes import router as institutional_router
from routes.strategic_routes import router as strategic_router

# Import Circle USDC routes
from routes.circle_routes import router as circle_router

# Import Cashout Engine routes
from routes.cashout_routes import router as cashout_router

# Import Real-Time Sync routes
from routes.sync_routes import router as sync_router

# Import Live Execution routes
from routes.live_routes import router as live_router

# Import Hybrid Liquidity routes
from routes.hybrid_routes import router as hybrid_router

# Import Referral System routes
from routes.referral_routes import router as referral_router

# Import Card Issuing Engine routes
from routes.card_issuing_routes import router as card_issuing_router

# Import Growth & Analytics routes
from routes.growth_routes import router as growth_router

# Import Pipeline & Webhook routes
from routes.pipeline_routes import router as pipeline_router

# Import Advanced Analytics routes
from routes.advanced_analytics_routes import router as advanced_analytics_router

# Import Monte Carlo VaR routes
from routes.montecarlo_routes import router as montecarlo_router

# Import PEP Screening routes
from routes.pep_routes import router as pep_router

# Initialize services
auth_service = AuthService(db)
api_key_service = PlatformApiKeyService(db)
ramp_service = RampService(db)
wallet_service = WalletService(db)
blockchain_listener = BlockchainListener(db)
payout_service = StripePayoutService(db)
por_engine = InternalPoRProvider(db)
settlement_service = SettlementService(db)
audit_logger = AuditLogger(db)
webhook_service = WebhookService(db)
real_payout_service = RealPayoutService(db)

# Initialize liquidity services (Hybrid PoR Liquidity Architecture)
treasury_service = TreasuryService(db)
exposure_service = ExposureService(db)
routing_service = MarketRoutingService(db)
hedging_service = HedgingService(db)
reconciliation_service = ReconciliationService(db)

# Initialize DEX services (C-SAFE Real Market Conversion)
dex_service = DEXService(db)
batch_executor = BatchExecutor(db, dex_service)

# Initialize Exchange Connector Manager (Phase 2 - Venue Integration)
connector_manager = ConnectorManager(db)

# Initialize Transak service (On/Off-Ramp Widget)
transak_service = TransakService(db)

# Initialize Email service (Password Reset)
email_service = EmailService()

# Initialize Audit service (Transaction Timeline)
audit_service = TransactionAuditService(db)

# Set global service instances
set_audit_logger(audit_logger)
set_webhook_service(webhook_service)
set_real_payout_service(real_payout_service)

# Set liquidity service instances
set_treasury_service(treasury_service)
set_exposure_service(exposure_service)
set_routing_service(routing_service)
set_hedging_service(hedging_service)
set_reconciliation_service(reconciliation_service)

# Wire up services
ramp_service.set_wallet_service(wallet_service)
ramp_service.set_blockchain_listener(blockchain_listener)
ramp_service.set_payout_service(payout_service)
por_engine.set_wallet_service(wallet_service)
por_engine.set_audit_logger(audit_logger)
por_engine.set_webhook_service(webhook_service)
por_engine.set_real_payout_service(real_payout_service)

# Wire up services to routes
set_auth_service(auth_service)
set_api_key_service(api_key_service)
set_ramp_api_services(ramp_service, api_key_service)
# 🔴 REAL EXECUTION SERVICES (CRITICAL)
set_execution_services(
    routing_service,
    real_payout_service,
    settlement_service
)
set_ramp_service(ramp_service)
set_payout_service(payout_service)
set_por_engine(por_engine)
set_stripe_payout_service(real_payout_service)
set_stripe_por_engine(por_engine)

# Import and wire PoR engine to user routes and ramp API routes
from routes.user_ramp import set_por_engine as set_user_por_engine
from routes.ramp_api import set_por_engine as set_api_por_engine
set_user_por_engine(por_engine)
set_api_por_engine(por_engine)

# Background task for blockchain monitoring
blockchain_poll_task = None

async def on_deposit_confirmed(result: dict):
    """Callback when a deposit is confirmed on-chain."""
    quote_id = result['quote_id']
    tx_hash = result['transfer']['transaction_hash']
    amount = result['transfer']['amount']
    
    logger.info(f"Deposit confirmed for quote {quote_id}: {amount} NENO (tx: {tx_hash})")
    
    # Check if this is a PoR quote (starts with 'por_')
    if quote_id.startswith('por_'):
        # Process via PoR engine
        quote, error = await por_engine.process_deposit(
            quote_id=quote_id,
            tx_hash=tx_hash,
            amount=amount
        )
        if quote:
            logger.info(f"PoR deposit processed for {quote_id}: state={quote.state.value}")
        else:
            logger.error(f"Failed to process PoR deposit for {quote_id}: {error}")
    else:
        # Process via legacy ramp service
        success, error = await ramp_service.process_deposit_received(
            quote_id=quote_id,
            tx_hash=tx_hash,
            amount_received=amount
        )
        
        if success:
            logger.info(f"Successfully processed deposit for quote {quote_id}")
        else:
            logger.error(f"Failed to process deposit for quote {quote_id}: {error}")

async def get_active_quotes_for_monitoring():
    """Get active quotes for blockchain monitoring (both PoR and legacy)."""
    # Get legacy quotes
    legacy_quotes = await ramp_service.get_active_offramp_quotes()
    
    # Get PoR quotes in DEPOSIT_PENDING state
    from services.provider_interface import TransactionState
    por_quotes = await por_engine.list_transactions(
        state=TransactionState.DEPOSIT_PENDING,
        limit=100
    )
    
    # Convert PoR quotes to monitoring format
    por_monitoring = []
    for q in por_quotes:
        if q.deposit_address:
            por_monitoring.append({
                'quote_id': q.quote_id,
                'deposit_address': q.deposit_address,
                'expected_amount': q.crypto_amount
            })
    
    return legacy_quotes + por_monitoring

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    global blockchain_poll_task
    
    # Startup — keep this lightweight so health checks pass quickly
    logger.info("NeoNoble Ramp API starting up...")
    
    # Launch heavy initialization in background
    init_task = asyncio.create_task(_background_init())
    
    yield
    
    # Shutdown
    init_task.cancel()
    logger.info("NeoNoble Ramp API shutting down...")
    try:
        from services.auto_operation_loop import AutoOperationLoop
        await AutoOperationLoop.get_instance().stop()
    except Exception:
        pass
    try:
        from services.cashout_engine import CashoutEngine
        await CashoutEngine.get_instance().stop()
    except Exception:
        pass
    try:
        from services.background_scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
    if blockchain_poll_task:
        blockchain_listener.stop_polling()
        blockchain_poll_task.cancel()
        try:
            await blockchain_poll_task
        except asyncio.CancelledError:
            pass
    if webhook_service:
        await webhook_service.stop_worker()
    await pricing_service.close()
    client.close()
    logger.info("NeoNoble Ramp API shutdown complete.")


async def _background_init():
    """Initialize all services in background so health checks pass immediately."""
    logger.info("🏦 HEDGE FUND MODE ACTIVE")
    global blockchain_poll_task
    
    try:
        # Small delay to let the server bind first
        await asyncio.sleep(0.5)
        
        logger.info("[INIT] Starting background service initialization...")
        
        # Create database indexes
        try:
            await db.users.create_index("email", unique=True)
            await db.users.create_index("id", unique=True)
            await db.platform_api_keys.create_index("api_key", unique=True)
            await db.platform_api_keys.create_index("id", unique=True)
            await db.platform_api_keys.create_index("user_id")
            await db.transactions.create_index("id", unique=True)
            await db.transactions.create_index("user_id")
            await db.transactions.create_index("reference", unique=True)
            await db.transactions.create_index("metadata.quote_id")
            
            # Token Infrastructure indexes
            await db.tokens.create_index("id", unique=True)
            await db.tokens.create_index("symbol", unique=True)
            await db.tokens.create_index("creator_id")
            await db.tokens.create_index([("chain", 1), ("status", 1)])
            await db.token_listings.create_index("id", unique=True)
            await db.token_listings.create_index("token_id")
            await db.token_listings.create_index("status")
            await db.trading_pairs.create_index("id", unique=True)
            await db.trading_pairs.create_index("pair_symbol", unique=True)
            await db.trading_pairs.create_index("base_token_id")
            
            # Subscription Infrastructure indexes
            await db.subscription_plans.create_index("id", unique=True)
            await db.subscription_plans.create_index("code", unique=True)
            await db.subscriptions.create_index("id", unique=True)
            await db.subscriptions.create_index([("user_id", 1), ("status", 1)])
            await db.subscription_invoices.create_index("id", unique=True)
            await db.subscription_invoices.create_index("subscription_id")
            
            logger.info("[INIT] Token and Subscription infrastructure indexes created")
        
            # Alert and push indexes
            await db.price_alerts.create_index([("user_id", 1), ("triggered", 1)])
            await db.browser_push_queue.create_index([("user_id", 1), ("delivered", 1)])
            
            # DCA Bot indexes
            await db.dca_plans.create_index([("user_id", 1), ("status", 1)])
            await db.dca_plans.create_index("id", unique=True)
            await db.dca_executions.create_index([("plan_id", 1), ("executed_at", -1)])
            await db.dca_executions.create_index("id", unique=True)
            await db.sms_log.create_index([("user_id", 1), ("sent_at", -1)])
            
            # Referral indexes
            await db.referral_codes.create_index("code", unique=True)
            await db.referral_codes.create_index("user_id", unique=True)
            await db.referral_links.create_index("referred_user_id", unique=True)
            await db.referral_links.create_index("referrer_user_id")
            await db.referral_bonus_log.create_index([("user_id", 1), ("created_at", -1)])
            
            # KYC risk score indexes
            await db.kyc_risk_scores.create_index("user_id", unique=True)
            
            # Circle USDC & Wallet Segregation indexes
            await db.circle_audit_log.create_index([("timestamp", -1)])
            await db.circle_audit_log.create_index("operation")
            await db.wallet_segregation_movements.create_index([("created_at", -1)])
            await db.wallet_segregation_movements.create_index("rule_type")
            await db.wallet_segregation_movements.create_index("from_wallet")
            await db.wallet_segregation_movements.create_index("to_wallet")
            await db.auto_op_metrics.create_index([("cycle", -1)])
            await db.auto_op_events.create_index([("timestamp", -1)])
            await db.auto_op_state.create_index("key", unique=True)
            
            # Cashout Engine indexes
            await db.cashout_log.create_index([("created_at", -1)])
            await db.cashout_log.create_index("type")
            await db.cashout_log.create_index("status")
            await db.cashout_events.create_index([("timestamp", -1)])
            await db.cashout_metrics.create_index([("cycle", -1)])
            await db.auto_conversions.create_index([("created_at", -1)])
            
            # Instant Withdraw & Event Bus indexes
            await db.instant_withdrawals.create_index([("created_at", -1)])
            await db.instant_withdrawals.create_index("status")
            await db.event_bus_log.create_index([("timestamp", -1)])
            await db.event_bus_log.create_index("event")
            
            # DEX Swap & Pipeline indexes
            await db.dex_swap_log.create_index([("timestamp", -1)])
            await db.pipeline_executions.create_index([("timestamp", -1)])
            
            # Hybrid Liquidity indexes
            await db.internal_order_book.create_index("status")
            await db.internal_order_book.create_index([("created_at", -1)])
            await db.internal_matches.create_index([("matched_at", -1)])
            
            logger.info("[INIT] Database indexes created")
        except Exception as e:
            logger.warning(f"[INIT] Index creation failed (non-fatal): {e}")
    except Exception as e:
        logger.error(f"[INIT] Critical initialization error: {e}")
    
    # Initialize wallet service
    try:
        await wallet_service.initialize()
        logger.info("Wallet service initialized")
    except Exception as e:
        logger.warning(f"Wallet service initialization failed: {e}")
    
    # Initialize payout service
    try:
        await payout_service.initialize()
        logger.info("Payout service initialized")
    except Exception as e:
        logger.warning(f"Payout service initialization failed: {e}")
    
    # Initialize real payout service (Stripe payouts for real EUR transfers)
    try:
        await real_payout_service.initialize()
        logger.info("Real Payout Service initialized - Stripe EUR payouts enabled")
    except Exception as e:
        logger.warning(f"Real Payout Service initialization failed: {e}")
    
    # Initialize PoR Engine (always available - no credentials required)
    try:
        await por_engine.initialize()
        logger.info("PoR Engine initialized - autonomous off-ramp provider ready")
    except Exception as e:
        logger.warning(f"PoR Engine initialization failed: {e}")
    
    # Initialize settlement service
    try:
        await settlement_service.initialize()
        logger.info("Settlement service initialized")
    except Exception as e:
        logger.warning(f"Settlement service initialization failed: {e}")
    
    # Initialize audit logger
    try:
        await audit_logger.initialize()
        logger.info("Audit logger initialized")
    except Exception as e:
        logger.warning(f"Audit logger initialization failed: {e}")
    
    # Initialize webhook service
    try:
        await webhook_service.initialize()
        logger.info("Webhook service initialized")
    except Exception as e:
        logger.warning(f"Webhook service initialization failed: {e}")
    
    # Initialize Liquidity Services (Hybrid PoR Liquidity Architecture - Phase 1)
    try:
        await treasury_service.initialize()
        logger.info("Treasury Service initialized - Real treasury tracking enabled")
    except Exception as e:
        logger.warning(f"Treasury Service initialization failed: {e}")
    
    try:
        await exposure_service.initialize()
        logger.info("Exposure Service initialized - Real exposure tracking enabled")
    except Exception as e:
        logger.warning(f"Exposure Service initialization failed: {e}")
    
    try:
        await routing_service.initialize()
        logger.info("Market Routing Service initialized - Shadow mode (log-only)")
    except Exception as e:
        logger.warning(f"Market Routing Service initialization failed: {e}")
    
    try:
        await hedging_service.initialize()
        logger.info("Hedging Service initialized - Shadow mode (audit-only proposals)")
    except Exception as e:
        logger.warning(f"Hedging Service initialization failed: {e}")
    
    try:
        await reconciliation_service.initialize()
        logger.info("Reconciliation Service initialized - Real audit ledger enabled")
    except Exception as e:
        logger.warning(f"Reconciliation Service initialization failed: {e}")
    
    # Wire liquidity services to PoR engine for lifecycle hooks
    por_engine.set_liquidity_services(
        treasury_service=treasury_service,
        exposure_service=exposure_service,
        routing_service=routing_service,
        hedging_service=hedging_service,
        reconciliation_service=reconciliation_service
    )
    logger.info("Liquidity services wired to PoR engine")
    
    # Initialize DEX Service (C-SAFE Real Market Conversion)
    try:
        await dex_service.initialize()
        set_dex_service(dex_service)
        logger.info("DEX Service initialized - Real on-chain swaps (1inch + PancakeSwap)")
    except Exception as e:
        logger.warning(f"DEX Service initialization failed: {e}")
    
    # Initialize Batch Executor for progressive swaps
    try:
        await batch_executor.initialize()
        logger.info("Batch Executor initialized - TWAP-like progressive execution")
    except Exception as e:
        logger.warning(f"Batch Executor initialization failed: {e}")
    
    # Initialize Exchange Connector Manager (Phase 2 - Venue Integration)
    try:
        await connector_manager.initialize()
        set_connector_manager(connector_manager)
        logger.info("Connector Manager initialized - Binance + Kraken venues")
    except Exception as e:
        logger.warning(f"Connector Manager initialization failed: {e}")
    
    # Initialize Transak Service (On/Off-Ramp Widget)
    try:
        await transak_service.initialize()
        set_transak_service(transak_service)
        logger.info("Transak Service initialized - On/Off-ramp widget enabled")
    except Exception as e:
        logger.warning(f"Transak Service initialization failed: {e}")
    
    # Initialize Email Service (Password Reset)
    try:
        await email_service.initialize()
        set_email_service(email_service)
        set_password_reset_db(db)
        logger.info("Email Service initialized - Password reset enabled")
    except Exception as e:
        logger.warning(f"Email Service initialization failed: {e}")
    
    # Initialize Audit Service (Transaction Timeline)
    try:
        await audit_service.initialize()
        set_audit_service(audit_service)
        logger.info("Audit Service initialized - Transaction timeline enabled")
    except Exception as e:
        logger.warning(f"Audit Service initialization failed: {e}")
    
    # Initialize PostgreSQL and Dual Database Manager for migration
    # ONLY if DATABASE_MODE is not mongodb_only
    database_mode = os.environ.get("DATABASE_MODE", "mongodb_only").lower()
    if database_mode != "mongodb_only":
        try:
            pg_engine, pg_session_factory = await asyncio.wait_for(
                init_pg_engine(), timeout=15
            )
            dual_manager = get_dual_db_manager()
            await dual_manager.initialize(mongo_db=db, pg_session_factory=pg_session_factory)
            logger.info(f"Dual Database Manager initialized (mode: {dual_manager.state.mode.value})")
        except asyncio.TimeoutError:
            logger.warning("PostgreSQL initialization timed out (15s) - skipping")
        except Exception as e:
            logger.warning(f"PostgreSQL/Dual Manager initialization failed: {e}")
    else:
        logger.info("DATABASE_MODE=mongodb_only - skipping PostgreSQL initialization")
    
    # Start blockchain monitoring if configured
    if os.environ.get('BSC_RPC_URL'):
        try:
            await blockchain_listener.initialize()
            # Legacy quote-based polling
            blockchain_poll_task = asyncio.create_task(
                blockchain_listener.start_polling(
                    get_active_quotes_for_monitoring,
                    on_deposit_confirmed
                )
            )
            # Hot wallet auto-deposit monitor (watches ALL incoming NENO to hot wallet)
            try:
                from eth_account import Account
                Account.enable_unaudited_hdwallet_features()
                mnemonic = os.environ.get('NENO_WALLET_MNEMONIC', '')
                if mnemonic:
                    hot_wallet_addr = Account.from_mnemonic(mnemonic).address
                    asyncio.create_task(blockchain_listener.monitor_hot_wallet(hot_wallet_addr))
                    logger.info(f"Hot wallet monitor started for {hot_wallet_addr[:12]}...")
                else:
                    logger.warning("NENO_WALLET_MNEMONIC not set - hot wallet monitoring disabled")
            except Exception as hw_err:
                logger.warning(f"Hot wallet monitor failed to start: {hw_err}")
            logger.info("Blockchain monitoring started")
        except Exception as e:
            logger.warning(f"Blockchain monitoring failed to start: {e}")
    
    logger.info("Database indexes created")
    
    # Start background scheduler (price alerts, NIUM auth, rate limiter cleanup, DCA bot)
    try:
        from services.background_scheduler import start_scheduler
        await start_scheduler()
        logger.info("Background scheduler started")
    except Exception as e:
        logger.warning(f"Background scheduler failed to start: {e}")

    # Load NIUM_TEMPLATE_ID from DB config if not in env
    try:
        template_cfg = await db.platform_config.find_one({"key": "NIUM_TEMPLATE_ID"}, {"_id": 0})
        if template_cfg and template_cfg.get("value") and not os.environ.get("NIUM_TEMPLATE_ID"):
            os.environ["NIUM_TEMPLATE_ID"] = template_cfg["value"]
            logger.info(f"Loaded NIUM_TEMPLATE_ID from DB: {template_cfg['value']}")
    except Exception as e:
        logger.warning(f"Failed to load NIUM_TEMPLATE_ID from DB: {e}")
    logger.info("[INIT] Institutional modules loaded: DarkPool, RFQ, Netting, AI Pricing, CrossChainArbitrage, Clearing, Risk, AdvancedSOR")
    
    logger.info("[INIT] Background initialization complete - all services ready")

    # Ensure admin role for designated admin user
    try:
        admin_email = "massimo.fornara.2212@gmail.com"
        admin_user = await db.users.find_one({"email": admin_email})
        if admin_user:
            if admin_user.get("role") != "ADMIN":
                await db.users.update_one({"email": admin_email}, {"$set": {"role": "ADMIN"}})
                logger.info(f"[INIT] Admin role assigned to {admin_email}")
            else:
                logger.info(f"[INIT] {admin_email} already has ADMIN role")
        else:
            logger.info(f"[INIT] Admin user {admin_email} not found — will be assigned on next login/register")
    except Exception as e:
        logger.warning(f"[INIT] Admin role assignment failed: {e}")

    # Initialize idempotency indexes
    try:
        from services.idempotency_service import IdempotencyService
        idem_svc = IdempotencyService.get_instance()
        await idem_svc.ensure_indexes()
        logger.info("[INIT] Idempotency indexes created")
    except Exception as e:
        logger.warning(f"[INIT] Idempotency index creation failed: {e}")

    # Start Autonomous Financial Pipeline
    try:
        from services.auto_financial_pipeline import AutonomousFinancialPipeline
        pipeline = AutonomousFinancialPipeline.get_instance()
        asyncio.create_task(pipeline.start_background_loop())
        logger.info("[INIT] Autonomous Financial Pipeline started")
    except Exception as e:
        logger.warning(f"[INIT] Pipeline start failed: {e}")

    # Initialize Circle USDC Wallet Service
    try:
        from services.circle_wallet_service import CircleWalletService
        circle_svc = CircleWalletService.get_instance()
        await circle_svc.initialize()
        logger.info("[INIT] Circle USDC Wallet Service initialized")
    except Exception as e:
        logger.warning(f"[INIT] Circle USDC initialization failed: {e}")

    # Start Auto-Operation Loop (autonomous monitoring)
    try:
        from services.auto_operation_loop import AutoOperationLoop
        auto_op = AutoOperationLoop.get_instance()
        await auto_op.start()
        logger.info("[INIT] Auto-Operation Loop started — autonomous mode active")
    except Exception as e:
        logger.warning(f"[INIT] Auto-Operation Loop failed to start: {e}")

    # Start Cashout Engine (autonomous profit extraction)
    try:
        from services.cashout_engine import CashoutEngine
        cashout = CashoutEngine.get_instance()
        await cashout.start()
        logger.info("[INIT] Cashout Engine started — continuous extraction active")
    except Exception as e:
        logger.warning(f"[INIT] Cashout Engine failed to start: {e}")

    # Initialize Instant Withdraw Engine + Event Bus
    try:
        from services.realtime_sync_service import EventBus
        from services.instant_withdraw_engine import InstantWithdrawEngine
        event_bus = EventBus.get_instance()
        iw_engine = InstantWithdrawEngine.get_instance()
        event_bus.on("trade_executed", iw_engine.on_trade_executed)
        event_bus.on("fee_collected", iw_engine.on_fee_collected)
        event_bus.on("settlement_confirmed", iw_engine.on_settlement_confirmed)
        logger.info("[INIT] Instant Withdraw Engine + Event Bus connected — event-driven cashout active")
    except Exception as e:
        logger.warning(f"[INIT] Instant Withdraw Engine init failed: {e}")

    # Initialize Market Maker Treasury
    try:
        from services.market_maker_service import MarketMakerService
        mm = MarketMakerService.get_instance()
        await mm.initialize_treasury()
        logger.info("[INIT] Market Maker Treasury initialized from on-chain state")
    except Exception as e:
        logger.warning(f"[INIT] Market Maker Treasury initialization failed: {e}")


# Create the main app
app = FastAPI(
    # 🔴 AGGIUNGI QUI
from services.exchanges.connector_manager import get_connector_manager

manager = get_connector_manager()

@app.on_event("startup")
async def startup():
    manager = get_connector_manager()
    
    await manager.enable_live_trading(user_id="system")

    await routing_service.initialize()
    set_routing_service(routing_service)
    
print("🚀 SYSTEM LIVE: REAL TRADING ENABLED")
    title="NeoNoble Ramp API",
    description="Crypto on/off-ramp platform with HMAC-secured API access and BSC blockchain integration",
    version="2.0.0",
    lifespan=lifespan
)

# Root-level health check for Kubernetes (without /api prefix)
@app.get("/health")
async def root_health():
    return {"status": "healthy", "service": "NeoNoble Ramp"}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Root endpoint
@api_router.get("/")
async def root():
    return {
        "message": "Welcome to NeoNoble Ramp API",
        "version": "2.0.0",
        "features": {
            "blockchain_monitoring": bool(os.environ.get('BSC_RPC_URL')),
            "hd_wallet": bool(os.environ.get('NENO_WALLET_MNEMONIC')),
            "stripe_payouts": bool(os.environ.get('STRIPE_SECRET_KEY')),
            "por_engine": True,
            "circle_usdc": bool(os.environ.get('CIRCLE_API_KEY')),
        },
        "por_engine": {
            "name": "NeoNoble Internal PoR",
            "version": "2.0.0",
            "available": True,
            "settlement_mode": "instant"
        },
        "docs": "/docs"
    }

# Health check (also available at /api/health)
@api_router.get("/health")
async def health():
    return {"status": "healthy", "service": "NeoNoble Ramp"}

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(dev_router)
api_router.include_router(ramp_api_router)
api_router.include_router(user_ramp_router)
api_router.include_router(webhooks_router)
api_router.include_router(por_router)
api_router.include_router(webhook_mgmt_router)
api_router.include_router(monitoring_router)
api_router.include_router(migration_router)
api_router.include_router(stripe_payout_router)
api_router.include_router(liquidity_router)
api_router.include_router(dex_router)
api_router.include_router(transak_router)
api_router.include_router(exchange_router)
api_router.include_router(password_router)
api_router.include_router(audit_router)
api_router.include_router(websocket_router)
api_router.include_router(price_history_router)
api_router.include_router(notification_router)
api_router.include_router(token_router)
api_router.include_router(swap_router)
api_router.include_router(subscription_router)
api_router.include_router(market_data_router)
api_router.include_router(analytics_router)
api_router.include_router(card_router)
api_router.include_router(trading_engine_router)
api_router.include_router(public_api_router)
api_router.include_router(wallet_router)
api_router.include_router(multichain_router)
api_router.include_router(banking_router)
api_router.include_router(neno_exchange_router)
api_router.include_router(kyc_router)
api_router.include_router(advanced_orders_router)
api_router.include_router(totp_router)
api_router.include_router(admin_audit_router)
api_router.include_router(export_router)
api_router.include_router(nium_onboarding_router)
api_router.include_router(alert_router)
api_router.include_router(dca_router)
api_router.include_router(referral_router)
api_router.include_router(advanced_analytics_router)
api_router.include_router(montecarlo_router)
api_router.include_router(pep_router)
api_router.include_router(market_maker_router)
api_router.include_router(exchange_orders_router)
api_router.include_router(institutional_router)
api_router.include_router(strategic_router)
api_router.include_router(circle_router)
api_router.include_router(cashout_router)
api_router.include_router(sync_router)
api_router.include_router(live_router)
api_router.include_router(hybrid_router)

# Card Issuing Engine
api_router.include_router(card_issuing_router)

# Growth & Analytics Engine
api_router.include_router(growth_router)

# Autonomous Pipeline & Stripe Webhooks
api_router.include_router(pipeline_router)

# Infrastructure API
from routes.infra_routes import router as infra_router
api_router.include_router(infra_router)

# Institutional Liquidity Router
from routes.router_routes import router as liquidity_router_api
api_router.include_router(liquidity_router_api)

# KYC/AML Provider
from routes.kyc_provider_routes import router as kyc_provider_router
api_router.include_router(kyc_provider_router)

# Set monitoring services
set_monitoring_services(audit_logger, por_engine, settlement_service)

# Set HMAC middleware for webhook routes
from middleware.auth import HMACAuthMiddleware
hmac_middleware = HMACAuthMiddleware(api_key_service)
set_webhook_hmac(hmac_middleware)

# Include the main router
app.include_router(api_router)

# Rate Limiting middleware (must be added BEFORE CORS so CORS wraps it)
from middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# CORS middleware (added LAST = executes FIRST = outermost)
# allow_credentials=False with allow_origins=["*"] per la spec CORS:
# "*" + credentials=true è vietato dai browser → blocca la lettura delle risposte
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Remaining", "X-RateLimit-Limit"],
)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
