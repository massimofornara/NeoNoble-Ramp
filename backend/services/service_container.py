"""
Service Registry — NeoNoble Ramp.

Centralized service initialization and wiring.
Extracted from server.py to reduce monolith bloat.
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Holds all initialized service instances."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._initialized = False

        # Core services
        self.auth_service = None
        self.api_key_service = None
        self.ramp_service = None
        self.wallet_service = None
        self.blockchain_listener = None
        self.payout_service = None
        self.por_engine = None
        self.settlement_service = None
        self.audit_logger = None
        self.webhook_service = None
        self.real_payout_service = None

        # Liquidity services
        self.treasury_service = None
        self.exposure_service = None
        self.routing_service = None
        self.hedging_service = None
        self.reconciliation_service = None

        # DEX services
        self.dex_service = None
        self.batch_executor = None

        # Exchange connectors
        self.connector_manager = None

        # Other services
        self.transak_service = None
        self.email_service = None
        self.audit_service = None

    def create_all(self):
        """Instantiate all services."""
        from services.auth_service import AuthService
        from services.api_key_service import PlatformApiKeyService
        from services.ramp_service import RampService
        from services.wallet_service import WalletService
        from services.blockchain_listener import BlockchainListener
        from services.stripe_payout_service import StripePayoutService
        from services.por_engine import InternalPoRProvider
        from services.settlement_service import SettlementService
        from services.audit_logger import AuditLogger, set_audit_logger
        from services.webhook_service import WebhookService, set_webhook_service
        from services.real_payout_service import RealPayoutService, set_real_payout_service
        from services.liquidity import (
            TreasuryService, set_treasury_service,
            ExposureService, set_exposure_service,
            MarketRoutingService, set_routing_service,
            HedgingService, set_hedging_service,
            ReconciliationService, set_reconciliation_service,
        )
        from services.dex import DEXService, BatchExecutor, set_dex_service
        from services.exchanges import ConnectorManager, set_connector_manager
        from services.transak_service import TransakService, set_transak_service
        from services.email_service import EmailService, set_email_service
        from services.audit_service import TransactionAuditService, set_audit_service

        db = self.db

        self.auth_service = AuthService(db)
        self.api_key_service = PlatformApiKeyService(db)
        self.ramp_service = RampService(db)
        self.wallet_service = WalletService(db)
        self.blockchain_listener = BlockchainListener(db)
        self.payout_service = StripePayoutService(db)
        self.por_engine = InternalPoRProvider(db)
        self.settlement_service = SettlementService(db)
        self.audit_logger = AuditLogger(db)
        self.webhook_service = WebhookService(db)
        self.real_payout_service = RealPayoutService(db)

        # Liquidity
        self.treasury_service = TreasuryService(db)
        self.exposure_service = ExposureService(db)
        self.routing_service = MarketRoutingService(db)
        self.hedging_service = HedgingService(db)
        self.reconciliation_service = ReconciliationService(db)

        # DEX
        self.dex_service = DEXService(db)
        self.batch_executor = BatchExecutor(db, self.dex_service)

        # Exchange
        self.connector_manager = ConnectorManager(db)

        # Other
        self.transak_service = TransakService(db)
        self.email_service = EmailService()
        self.audit_service = TransactionAuditService(db)

        # Set global singletons
        set_audit_logger(self.audit_logger)
        set_webhook_service(self.webhook_service)
        set_real_payout_service(self.real_payout_service)
        set_treasury_service(self.treasury_service)
        set_exposure_service(self.exposure_service)
        set_routing_service(self.routing_service)
        set_hedging_service(self.hedging_service)
        set_reconciliation_service(self.reconciliation_service)

        # Wire up service dependencies
        self.ramp_service.set_wallet_service(self.wallet_service)
        self.ramp_service.set_blockchain_listener(self.blockchain_listener)
        self.ramp_service.set_payout_service(self.payout_service)
        self.por_engine.set_wallet_service(self.wallet_service)
        self.por_engine.set_audit_logger(self.audit_logger)
        self.por_engine.set_webhook_service(self.webhook_service)
        self.por_engine.set_real_payout_service(self.real_payout_service)

        logger.info("All services created and wired")

    def wire_routes(self):
        """Wire services to route modules."""
        from routes.auth import set_auth_service
        from routes.dev_portal import set_api_key_service
        from routes.ramp_api import set_services as set_ramp_api_services
        from routes.user_ramp import set_ramp_service
        from routes.webhooks import set_payout_service
        from routes.por_api import set_por_engine
        from routes.webhook_routes import set_hmac_middleware as set_webhook_hmac
        from routes.monitoring import set_monitoring_services
        from routes.stripe_payout_routes import (
            set_payout_service as set_stripe_payout_service,
            set_por_engine as set_stripe_por_engine,
        )
        from routes.password_routes import set_password_reset_db
        from routes.user_ramp import set_por_engine as set_user_por_engine
        from routes.ramp_api import set_por_engine as set_api_por_engine
        from services.dex import set_dex_service
        from services.exchanges import set_connector_manager
        from services.transak_service import set_transak_service
        from services.email_service import set_email_service
        from services.audit_service import set_audit_service
        from middleware.auth import HMACAuthMiddleware

        set_auth_service(self.auth_service)
        set_api_key_service(self.api_key_service)
        set_ramp_api_services(self.ramp_service, self.api_key_service)
        set_ramp_service(self.ramp_service)
        set_payout_service(self.payout_service)
        set_por_engine(self.por_engine)
        set_stripe_payout_service(self.real_payout_service)
        set_stripe_por_engine(self.por_engine)
        set_user_por_engine(self.por_engine)
        set_api_por_engine(self.por_engine)

        set_monitoring_services(self.audit_logger, self.por_engine, self.settlement_service)

        hmac_middleware = HMACAuthMiddleware(self.api_key_service)
        set_webhook_hmac(hmac_middleware)

        logger.info("All routes wired to services")

    async def initialize_all(self):
        """Initialize all async services at startup."""
        inits = [
            ("Wallet", self.wallet_service),
            ("Payout", self.payout_service),
            ("RealPayout", self.real_payout_service),
            ("PoR", self.por_engine),
            ("Settlement", self.settlement_service),
            ("AuditLogger", self.audit_logger),
            ("Webhook", self.webhook_service),
            ("Treasury", self.treasury_service),
            ("Exposure", self.exposure_service),
            ("Routing", self.routing_service),
            ("Hedging", self.hedging_service),
            ("Reconciliation", self.reconciliation_service),
        ]
        for name, svc in inits:
            try:
                await svc.initialize()
                logger.info(f"{name} service initialized")
            except Exception as e:
                logger.warning(f"{name} service initialization failed: {e}")

        # Wire liquidity to PoR
        self.por_engine.set_liquidity_services(
            treasury_service=self.treasury_service,
            exposure_service=self.exposure_service,
            routing_service=self.routing_service,
            hedging_service=self.hedging_service,
            reconciliation_service=self.reconciliation_service,
        )

        # DEX
        try:
            await self.dex_service.initialize()
            from services.dex import set_dex_service
            set_dex_service(self.dex_service)
            logger.info("DEX Service initialized")
        except Exception as e:
            logger.warning(f"DEX Service initialization failed: {e}")

        try:
            await self.batch_executor.initialize()
            logger.info("Batch Executor initialized")
        except Exception as e:
            logger.warning(f"Batch Executor initialization failed: {e}")

        # Exchange connectors
        try:
            await self.connector_manager.initialize()
            from services.exchanges import set_connector_manager
            set_connector_manager(self.connector_manager)
            logger.info("Connector Manager initialized")
        except Exception as e:
            logger.warning(f"Connector Manager initialization failed: {e}")

        # Transak
        try:
            await self.transak_service.initialize()
            from services.transak_service import set_transak_service
            set_transak_service(self.transak_service)
            logger.info("Transak Service initialized")
        except Exception as e:
            logger.warning(f"Transak Service initialization failed: {e}")

        # Email
        try:
            await self.email_service.initialize()
            from services.email_service import set_email_service
            set_email_service(self.email_service)
            from routes.password_routes import set_password_reset_db
            set_password_reset_db(self.db)
            logger.info("Email Service initialized")
        except Exception as e:
            logger.warning(f"Email Service initialization failed: {e}")

        # Audit
        try:
            await self.audit_service.initialize()
            from services.audit_service import set_audit_service
            set_audit_service(self.audit_service)
            logger.info("Audit Service initialized")
        except Exception as e:
            logger.warning(f"Audit Service initialization failed: {e}")

        # PostgreSQL Dual Manager
        try:
            from database.config import init_pg_engine
            from database.dual_manager import get_dual_db_manager
            pg_engine, pg_session_factory = await init_pg_engine()
            dual_manager = get_dual_db_manager()
            await dual_manager.initialize(mongo_db=self.db, pg_session_factory=pg_session_factory)
            logger.info(f"Dual Database Manager initialized (mode: {dual_manager.state.mode.value})")
        except Exception as e:
            logger.warning(f"PostgreSQL/Dual Manager initialization failed: {e}")

        self._initialized = True
        logger.info("All services initialized")

    async def shutdown(self):
        """Clean shutdown of all services."""
        try:
            from services.background_scheduler import stop_scheduler
            await stop_scheduler()
        except Exception:
            pass

        if self.webhook_service:
            await self.webhook_service.stop_worker()
