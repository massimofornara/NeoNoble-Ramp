"""
Database Configuration and Connection Management.

Supports both PostgreSQL (primary) and MongoDB (legacy) databases.
"""

import os
import logging
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

# PostgreSQL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# MongoDB (legacy support)
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# SQLAlchemy Base for models
Base = declarative_base()

# Database type configuration
DATABASE_TYPE = os.environ.get("DATABASE_TYPE", "postgresql").lower()


class DatabaseConfig:
    """Database configuration and connection management."""
    
    def __init__(self):
        self.database_type = DATABASE_TYPE
        
        # PostgreSQL configuration
        self._pg_engine = None
        self._pg_session_factory = None
        
        # MongoDB configuration (legacy)
        self._mongo_client = None
        self._mongo_db = None
    
    @property
    def is_postgresql(self) -> bool:
        return self.database_type == "postgresql"
    
    @property
    def is_mongodb(self) -> bool:
        return self.database_type == "mongodb"
    
    def get_postgresql_url(self) -> str:
        """Build PostgreSQL connection URL from environment variables."""
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "neonoble")
        password = os.environ.get("POSTGRES_PASSWORD", "neonoble_secret")
        database = os.environ.get("POSTGRES_DB", "neonoble_ramp")
        
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    
    def get_mongodb_url(self) -> str:
        """Get MongoDB connection URL from environment."""
        return os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    
    async def initialize_postgresql(self):
        """Initialize PostgreSQL connection."""
        if self._pg_engine is not None:
            return
        
        url = self.get_postgresql_url()
        
        self._pg_engine = create_async_engine(
            url,
            echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={
                "timeout": 10,
                "command_timeout": 10,
            },
            pool_timeout=10,
        )
        
        self._pg_session_factory = async_sessionmaker(
            self._pg_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create tables
        async with self._pg_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info(f"PostgreSQL initialized: {url.split('@')[1] if '@' in url else url}")
    
    async def initialize_mongodb(self):
        """Initialize MongoDB connection (legacy support)."""
        if self._mongo_client is not None:
            return
        
        url = self.get_mongodb_url()
        db_name = os.environ.get("DB_NAME", "neonoble_ramp")
        
        self._mongo_client = AsyncIOMotorClient(url)
        self._mongo_db = self._mongo_client[db_name]
        
        logger.info(f"MongoDB initialized: {db_name}")
    
    async def initialize(self):
        """Initialize the configured database."""
        if self.is_postgresql:
            await self.initialize_postgresql()
        else:
            await self.initialize_mongodb()
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get PostgreSQL session."""
        if self._pg_session_factory is None:
            raise RuntimeError("PostgreSQL not initialized")
        
        async with self._pg_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    def get_mongodb(self) -> AsyncIOMotorDatabase:
        """Get MongoDB database instance (legacy)."""
        if self._mongo_db is None:
            raise RuntimeError("MongoDB not initialized")
        return self._mongo_db
    
    async def close(self):
        """Close database connections."""
        if self._pg_engine:
            await self._pg_engine.dispose()
            self._pg_engine = None
            self._pg_session_factory = None
        
        if self._mongo_client:
            self._mongo_client.close()
            self._mongo_client = None
            self._mongo_db = None


# Global database config instance
db_config = DatabaseConfig()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with db_config.get_session() as session:
        yield session


def get_mongodb() -> AsyncIOMotorDatabase:
    """Get MongoDB database (legacy)."""
    return db_config.get_mongodb()


async def init_pg_engine():
    """Initialize PostgreSQL engine and return session factory."""
    await db_config.initialize_postgresql()
    return db_config._pg_engine, db_config._pg_session_factory


def get_pg_session_factory():
    """Get PostgreSQL session factory (must be initialized first)."""
    return db_config._pg_session_factory
