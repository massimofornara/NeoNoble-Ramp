from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid


class ApiKeyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PlatformApiKey(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    api_key: str  # Public key (visible)
    encrypted_secret: str  # AES-256-GCM encrypted secret
    iv: str  # Initialization vector for AES
    auth_tag: str  # Authentication tag for GCM
    status: ApiKeyStatus = ApiKeyStatus.ACTIVE
    rate_limit: int = 1000  # requests per hour
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class PlatformApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    rate_limit: int = Field(default=1000, ge=1, le=100000)


class PlatformApiKeyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    api_key: str
    status: ApiKeyStatus
    rate_limit: int
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]


class PlatformApiKeyWithSecret(PlatformApiKeyResponse):
    """Only returned once when creating a new key"""
    api_secret: str
