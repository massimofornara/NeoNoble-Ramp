from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging
import uuid

from models.api_key import (
    PlatformApiKey,
    PlatformApiKeyCreate,
    PlatformApiKeyResponse,
    PlatformApiKeyWithSecret,
    ApiKeyStatus
)
from utils.encryption import (
    generate_api_key,
    generate_api_secret,
    encrypt_secret,
    decrypt_secret
)

logger = logging.getLogger(__name__)


class PlatformApiKeyService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.platform_api_keys
    
    async def create_key(
        self,
        user_id: str,
        key_data: PlatformApiKeyCreate
    ) -> tuple[Optional[PlatformApiKeyWithSecret], Optional[str]]:
        """Create a new platform API key.
        
        Returns:
            Tuple of (KeyWithSecret, None) on success, or (None, error) on failure
            The secret is only returned once at creation time.
        """
        try:
            # Generate key and secret
            api_key = generate_api_key()
            api_secret = generate_api_secret()
            
            # Encrypt the secret
            encrypted_secret, iv, auth_tag = encrypt_secret(api_secret)
            
            # Create the key object
            platform_key = PlatformApiKey(
                name=key_data.name,
                description=key_data.description,
                api_key=api_key,
                encrypted_secret=encrypted_secret,
                iv=iv,
                auth_tag=auth_tag,
                rate_limit=key_data.rate_limit,
                user_id=user_id
            )
            
            # Save to database
            key_dict = platform_key.model_dump()
            key_dict['created_at'] = key_dict['created_at'].isoformat()
            key_dict['updated_at'] = key_dict['updated_at'].isoformat()
            if key_dict.get('last_used_at'):
                key_dict['last_used_at'] = key_dict['last_used_at'].isoformat()
            if key_dict.get('expires_at'):
                key_dict['expires_at'] = key_dict['expires_at'].isoformat()
            
            await self.collection.insert_one(key_dict)
            logger.info(f"Created API key for user {user_id}: {api_key[:20]}...")
            
            # Return with the plaintext secret (only time it's visible)
            return PlatformApiKeyWithSecret(
                id=platform_key.id,
                name=platform_key.name,
                description=platform_key.description,
                api_key=api_key,
                api_secret=api_secret,  # Only returned at creation!
                status=platform_key.status,
                rate_limit=platform_key.rate_limit,
                usage_count=platform_key.usage_count,
                last_used_at=platform_key.last_used_at,
                created_at=platform_key.created_at,
                expires_at=platform_key.expires_at
            ), None
            
        except Exception as e:
            logger.error(f"Failed to create API key: {e}")
            return None, str(e)
    
    async def get_key_by_api_key(self, api_key: str) -> Optional[PlatformApiKey]:
        """Get a platform key by its public API key."""
        key_doc = await self.collection.find_one({"api_key": api_key})
        if key_doc:
            return self._doc_to_model(key_doc)
        return None
    
    async def get_keys_by_user(self, user_id: str) -> List[PlatformApiKeyResponse]:
        """Get all API keys for a user."""
        keys = []
        cursor = self.collection.find({"user_id": user_id})
        async for doc in cursor:
            key = self._doc_to_model(doc)
            keys.append(self._to_response(key))
        return keys
    
    async def revoke_key(self, key_id: str, user_id: str) -> tuple[bool, Optional[str]]:
        """Revoke an API key."""
        try:
            result = await self.collection.update_one(
                {"id": key_id, "user_id": user_id},
                {
                    "$set": {
                        "status": ApiKeyStatus.REVOKED.value,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            if result.modified_count == 0:
                return False, "Key not found or not owned by user"
            logger.info(f"Revoked API key: {key_id}")
            return True, None
        except Exception as e:
            logger.error(f"Failed to revoke key: {e}")
            return False, str(e)
    
    async def increment_usage(self, api_key: str) -> bool:
        """Increment usage count for an API key."""
        try:
            result = await self.collection.update_one(
                {"api_key": api_key},
                {
                    "$inc": {"usage_count": 1},
                    "$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to increment usage: {e}")
            return False
    
    async def validate_key(self, api_key: str) -> tuple[Optional[PlatformApiKey], Optional[str]]:
        """Validate an API key for use.
        
        Checks:
        - Key exists
        - Status is ACTIVE
        - Not expired
        
        Returns:
            Tuple of (key, None) if valid, or (None, error) if invalid
        """
        key = await self.get_key_by_api_key(api_key)
        
        if not key:
            return None, "Invalid API key"
        
        if key.status != ApiKeyStatus.ACTIVE:
            return None, f"API key is {key.status.value}"
        
        if key.expires_at and key.expires_at < datetime.now(timezone.utc):
            return None, "API key has expired"
        
        return key, None
    
    def decrypt_key_secret(self, key: PlatformApiKey) -> str:
        """Decrypt the secret for an API key."""
        return decrypt_secret(key.encrypted_secret, key.iv, key.auth_tag)
    
    def _doc_to_model(self, doc: dict) -> PlatformApiKey:
        """Convert MongoDB document to PlatformApiKey model."""
        for field in ['created_at', 'updated_at', 'last_used_at', 'expires_at']:
            if doc.get(field) and isinstance(doc[field], str):
                doc[field] = datetime.fromisoformat(doc[field])
        return PlatformApiKey(**doc)
    
    def _to_response(self, key: PlatformApiKey) -> PlatformApiKeyResponse:
        """Convert PlatformApiKey to response (without encrypted fields)."""
        return PlatformApiKeyResponse(
            id=key.id,
            name=key.name,
            description=key.description,
            api_key=key.api_key,
            status=key.status,
            rate_limit=key.rate_limit,
            usage_count=key.usage_count,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
            expires_at=key.expires_at
        )
