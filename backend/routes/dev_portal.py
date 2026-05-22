from fastapi import APIRouter, HTTPException, Depends
from typing import List
import logging

from models.api_key import PlatformApiKeyCreate, PlatformApiKeyResponse, PlatformApiKeyWithSecret
from services.api_key_service import PlatformApiKeyService
from middleware.auth import get_current_user, require_developer_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["Developer Portal"])

# Service will be set by main app
api_key_service: PlatformApiKeyService = None


def set_api_key_service(service: PlatformApiKeyService):
    global api_key_service
    api_key_service = service


@router.post("/api-keys", response_model=PlatformApiKeyWithSecret)
async def create_api_key(
    request: PlatformApiKeyCreate,
    current_user: dict = Depends(require_developer_role)
):
    """
    Create a new Platform API key.
    
    **Important**: The API secret is only returned once at creation time.
    Store it securely - it cannot be retrieved later.
    """
    key, error = await api_key_service.create_key(
        user_id=current_user["user_id"],
        key_data=request
    )
    
    if error:
        logger.error(f"Failed to create API key: {error}")
        raise HTTPException(status_code=400, detail=error)
    
    logger.info(f"Created API key '{request.name}' for user {current_user['user_id']}")
    return key


@router.get("/api-keys", response_model=List[PlatformApiKeyResponse])
async def list_api_keys(current_user: dict = Depends(require_developer_role)):
    """List all API keys for the current user."""
    keys = await api_key_service.get_keys_by_user(current_user["user_id"])
    return keys


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(require_developer_role)
):
    """Revoke an API key."""
    success, error = await api_key_service.revoke_key(key_id, current_user["user_id"])
    
    if not success:
        raise HTTPException(status_code=404, detail=error)
    
    return {"success": True, "message": "API key revoked"}


@router.get("/dashboard")
async def get_dashboard_stats(current_user: dict = Depends(require_developer_role)):
    """Get developer dashboard statistics."""
    keys = await api_key_service.get_keys_by_user(current_user["user_id"])
    
    total_usage = sum(key.usage_count for key in keys)
    active_keys = len([k for k in keys if k.status.value == "ACTIVE"])
    
    return {
        "total_keys": len(keys),
        "active_keys": active_keys,
        "total_api_calls": total_usage,
        "keys": keys
    }
