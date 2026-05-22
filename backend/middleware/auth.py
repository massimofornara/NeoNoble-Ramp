from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import logging

from utils.jwt_utils import decode_access_token
from utils.hmac_utils import verify_hmac_signature, validate_timestamp
from services.api_key_service import PlatformApiKeyService

logger = logging.getLogger(__name__)

# HTTP Bearer token security
security = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get the current authenticated user from JWT."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role")
    }


async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to optionally get the current user (no error if not authenticated)."""
    if not credentials:
        return None
    
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role")
    }


class HMACAuthMiddleware:
    """
    HMAC authentication middleware for Platform API endpoints.
    
    Required headers:
    - X-API-KEY: The public API key
    - X-TIMESTAMP: Unix timestamp in seconds
    - X-SIGNATURE: HMAC-SHA256(timestamp + bodyJson, apiSecret)
    """
    
    def __init__(self, api_key_service: PlatformApiKeyService):
        self.api_key_service = api_key_service
    
    async def authenticate(self, request: Request) -> dict:
        """Authenticate a request using HMAC.
        
        Returns:
            Dict with api_key_id and user_id on success
        
        Raises:
            HTTPException on authentication failure
        """
        # Get required headers
        api_key = request.headers.get("X-API-KEY")
        timestamp = request.headers.get("X-TIMESTAMP")
        signature = request.headers.get("X-SIGNATURE")
        
        if not api_key:
            logger.warning("HMAC auth failed: Missing X-API-KEY header")
            raise HTTPException(status_code=401, detail="Missing X-API-KEY header")
        
        if not timestamp:
            logger.warning("HMAC auth failed: Missing X-TIMESTAMP header")
            raise HTTPException(status_code=401, detail="Missing X-TIMESTAMP header")
        
        if not signature:
            logger.warning("HMAC auth failed: Missing X-SIGNATURE header")
            raise HTTPException(status_code=401, detail="Missing X-SIGNATURE header")
        
        # Validate timestamp (replay protection)
        is_valid_ts, ts_error = validate_timestamp(timestamp)
        if not is_valid_ts:
            logger.warning(f"HMAC auth failed: {ts_error}")
            raise HTTPException(status_code=401, detail=ts_error)
        
        # Validate API key
        platform_key, key_error = await self.api_key_service.validate_key(api_key)
        if not platform_key:
            logger.warning(f"HMAC auth failed: {key_error}")
            raise HTTPException(status_code=401, detail=key_error)
        
        # Get request body
        body = await request.body()
        body_json = body.decode('utf-8') if body else ""
        
        # Decrypt the API secret
        try:
            api_secret = self.api_key_service.decrypt_key_secret(platform_key)
        except Exception as e:
            logger.error(f"Failed to decrypt API secret: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
        
        # Verify HMAC signature
        if not verify_hmac_signature(signature, timestamp, body_json, api_secret):
            logger.warning(f"HMAC auth failed: Invalid signature for key {api_key[:20]}...")
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Increment usage
        await self.api_key_service.increment_usage(api_key)
        
        logger.info(f"HMAC auth successful for key {api_key[:20]}...")
        
        return {
            "api_key_id": platform_key.id,
            "user_id": platform_key.user_id,
            "api_key": api_key
        }


async def require_developer_role(current_user: dict = Depends(get_current_user)):
    """Dependency to require DEVELOPER or ADMIN role."""
    if current_user["role"] not in ["DEVELOPER", "ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Developer or Admin role required"
        )
    return current_user
