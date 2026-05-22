#!/usr/bin/env python3
"""
Script to create Platform API Keys from the command line.

Usage:
    python scripts/create_platform_key.py --name="My Key" --description="For testing" --rate-limit=1000

This requires a developer account to be created first, then you can assign keys to that account.
For testing without a user account, you can create a "system" key with a placeholder user_id.
"""

import argparse
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / 'backend' / '.env')

from backend.services.api_key_service import PlatformApiKeyService
from backend.models.api_key import PlatformApiKeyCreate


async def create_key(name: str, description: str, rate_limit: int, user_id: str):
    """Create a new platform API key."""
    
    # Validate encryption key is set
    if not os.environ.get('API_SECRET_ENCRYPTION_KEY'):
        print("ERROR: API_SECRET_ENCRYPTION_KEY environment variable is not set.")
        print("Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
        sys.exit(1)
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'neonoble_ramp')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Initialize service
    service = PlatformApiKeyService(db)
    
    # Create the key
    key_data = PlatformApiKeyCreate(
        name=name,
        description=description,
        rate_limit=rate_limit
    )
    
    result, error = await service.create_key(user_id=user_id, key_data=key_data)
    
    if error:
        print(f"ERROR: {error}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("PLATFORM API KEY CREATED SUCCESSFULLY")
    print("=" * 60)
    print(f"\nName: {result.name}")
    print(f"Description: {result.description}")
    print(f"Rate Limit: {result.rate_limit} requests/hour")
    print(f"\n*** IMPORTANT: Save these credentials securely! ***")
    print(f"*** The secret will NOT be shown again! ***\n")
    print(f"API Key:    {result.api_key}")
    print(f"API Secret: {result.api_secret}")
    print("\n" + "=" * 60)
    print("\nTo use this key with HMAC authentication:")
    print("1. Set headers: X-API-KEY, X-TIMESTAMP, X-SIGNATURE")
    print("2. Signature = HMAC-SHA256(timestamp + requestBody, apiSecret)")
    print("3. Timestamp must be within ±5 minutes of current time")
    print("=" * 60 + "\n")
    
    client.close()


def main():
    parser = argparse.ArgumentParser(description='Create a Platform API Key')
    parser.add_argument('--name', required=True, help='Name for the API key')
    parser.add_argument('--description', default='', help='Description for the API key')
    parser.add_argument('--rate-limit', type=int, default=1000, help='Rate limit (requests per hour)')
    parser.add_argument('--user-id', default='system', help='User ID to associate the key with')
    
    args = parser.parse_args()
    
    asyncio.run(create_key(
        name=args.name,
        description=args.description,
        rate_limit=args.rate_limit,
        user_id=args.user_id
    ))


if __name__ == '__main__':
    main()
