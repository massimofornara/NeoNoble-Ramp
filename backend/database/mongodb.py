"""
MongoDB Database Helper.

Provides access to MongoDB database instance for route handlers.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
import os

_db_instance = None


def set_database(db: AsyncIOMotorDatabase):
    """Set the database instance (called from server.py)."""
    global _db_instance
    _db_instance = db


def get_database() -> AsyncIOMotorDatabase:
    """Get the MongoDB database instance."""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call set_database() first.")
    return _db_instance
