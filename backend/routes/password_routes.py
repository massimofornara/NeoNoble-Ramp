"""
Password Reset Routes - Email-based password recovery.

Provides endpoints for:
- Request password reset (sends email with token)
- Verify reset token
- Reset password with token
- Change password (authenticated)
"""

import os
import secrets
import hashlib
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from services.email_service import get_email_service, EmailService
from utils.password import hash_password, verify_password

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/password", tags=["Password"])

# Token expiry (1 hour)
RESET_TOKEN_EXPIRY_HOURS = 1


# Request/Response Models

class PasswordResetRequest(BaseModel):
    """Request to initiate password reset."""
    email: EmailStr


class PasswordResetVerify(BaseModel):
    """Verify reset token."""
    token: str


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with new password."""
    token: str
    new_password: str = Field(..., min_length=8)


class PasswordChangeRequest(BaseModel):
    """Change password (authenticated)."""
    current_password: str
    new_password: str = Field(..., min_length=8)


class PasswordResetResponse(BaseModel):
    """Response for password reset request."""
    status: str
    message: str


# Database dependency - will be set by server.py
_db: Optional[AsyncIOMotorDatabase] = None


def set_password_reset_db(db: AsyncIOMotorDatabase):
    global _db
    _db = db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db


def get_service() -> EmailService:
    service = get_email_service()
    if not service:
        raise HTTPException(status_code=503, detail="Email service not available")
    return service


def generate_reset_token() -> str:
    """Generate a secure reset token."""
    return secrets.token_urlsafe(32)


# Routes

@router.post("/forgot", response_model=PasswordResetResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    email_service: EmailService = Depends(get_service)
):
    """
    Request password reset.
    
    Sends an email with a reset link if the email exists.
    Always returns success to prevent email enumeration.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Find user by email
    user = await db.users.find_one({"email": request.email.lower()})
    
    if user:
        # Generate reset token
        reset_token = generate_reset_token()
        expiry = now + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)
        
        # Store reset token
        await db.password_resets.delete_many({"email": request.email.lower()})  # Remove old tokens
        await db.password_resets.insert_one({
            "email": request.email.lower(),
            "token": reset_token,
            "token_hash": hashlib.sha256(reset_token.encode()).hexdigest(),
            "created_at": now.isoformat(),
            "expires_at": expiry.isoformat(),
            "used": False
        })
        
        # Send reset email
        user_name = user.get("name") or user.get("email", "").split("@")[0]
        await email_service.send_password_reset_email(
            to_email=request.email,
            reset_token=reset_token,
            user_name=user_name
        )
        
        logger.info(f"[PASSWORD] Reset requested for: {request.email}")
    else:
        # Don't reveal if email exists
        logger.info(f"[PASSWORD] Reset requested for non-existent email: {request.email}")
    
    # Always return success to prevent enumeration
    return PasswordResetResponse(
        status="success",
        message="Se l'email è registrata, riceverai un link per reimpostare la password."
    )


@router.post("/verify-token")
async def verify_reset_token(request: PasswordResetVerify):
    """
    Verify if a reset token is valid.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Find token
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    reset_record = await db.password_resets.find_one({
        "token_hash": token_hash,
        "used": False
    })
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")
    
    # Check expiry
    expiry = datetime.fromisoformat(reset_record["expires_at"].replace("Z", "+00:00"))
    if now > expiry:
        raise HTTPException(status_code=400, detail="Token scaduto. Richiedi un nuovo reset.")
    
    return {
        "status": "valid",
        "email": reset_record["email"],
        "expires_in_minutes": int((expiry - now).total_seconds() / 60)
    }


@router.post("/reset", response_model=PasswordResetResponse)
async def reset_password(
    request: PasswordResetConfirm,
    email_service: EmailService = Depends(get_service)
):
    """
    Reset password using token.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Find and validate token
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    reset_record = await db.password_resets.find_one({
        "token_hash": token_hash,
        "used": False
    })
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Token non valido o già utilizzato")
    
    # Check expiry
    expiry = datetime.fromisoformat(reset_record["expires_at"].replace("Z", "+00:00"))
    if now > expiry:
        raise HTTPException(status_code=400, detail="Token scaduto. Richiedi un nuovo reset.")
    
    email = reset_record["email"]
    
    # Update user password
    new_password_hash = hash_password(request.new_password)
    
    result = await db.users.update_one(
        {"email": email},
        {
            "$set": {
                "password_hash": new_password_hash,
                "password_updated_at": now.isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    # Mark token as used
    await db.password_resets.update_one(
        {"token_hash": token_hash},
        {"$set": {"used": True, "used_at": now.isoformat()}}
    )
    
    # Get user name for email
    user = await db.users.find_one({"email": email})
    user_name = user.get("name") if user else None
    
    # Send confirmation email
    await email_service.send_password_changed_email(
        to_email=email,
        user_name=user_name
    )
    
    logger.info(f"[PASSWORD] Reset completed for: {email}")
    
    return PasswordResetResponse(
        status="success",
        message="Password reimpostata con successo. Puoi ora accedere con la nuova password."
    )


@router.post("/change", response_model=PasswordResetResponse)
async def change_password(
    request: PasswordChangeRequest,
    email_service: EmailService = Depends(get_service)
):
    """
    Change password (requires current password).
    
    Note: This endpoint should be protected with authentication middleware.
    For now, it requires the current password as verification.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # This would normally use the authenticated user's ID
    # For now, we require the current password to identify the user
    user = await db.users.find_one({"email": {"$exists": True}})
    
    # Find all users and check password
    users_cursor = db.users.find({})
    user = None
    async for user_doc in users_cursor:
        if verify_password(request.current_password, user_doc.get('password_hash', '')):
            user = user_doc
            break
    
    if not user:
        raise HTTPException(status_code=401, detail="Password attuale non corretta")
    
    # Update password
    new_password_hash = hash_password(request.new_password)
    
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "password_hash": new_password_hash,
                "password_updated_at": now.isoformat()
            }
        }
    )
    
    # Send confirmation email
    await email_service.send_password_changed_email(
        to_email=user["email"],
        user_name=user.get("name")
    )
    
    logger.info(f"[PASSWORD] Changed for user: {user['email']}")
    
    return PasswordResetResponse(
        status="success",
        message="Password modificata con successo."
    )


@router.get("/status")
async def get_password_service_status(
    email_service: EmailService = Depends(get_service)
):
    """Get password reset service status."""
    return {
        "email_configured": email_service.is_configured(),
        "token_expiry_hours": RESET_TOKEN_EXPIRY_HOURS
    }
