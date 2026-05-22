"""
Two-Factor Authentication (TOTP) Routes.

Provides:
- TOTP setup (generate secret, QR code)
- TOTP verification (enable 2FA)
- TOTP validation (on login)
- 2FA disable (with verification)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
import pyotp
import qrcode
import base64
import io

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/auth/2fa", tags=["Two-Factor Authentication"])


class TOTPSetupResponse(BaseModel):
    secret: str
    qr_code_base64: str
    uri: str


class TOTPVerifyRequest(BaseModel):
    code: str


class TOTPDisableRequest(BaseModel):
    code: str
    password: str


@router.post("/setup")
async def setup_2fa(current_user: dict = Depends(get_current_user)):
    """Generate TOTP secret and QR code for 2FA setup."""
    db = get_database()
    user_id = current_user["user_id"]

    existing = await db.totp_secrets.find_one({"user_id": user_id, "enabled": True})
    if existing:
        raise HTTPException(status_code=400, detail="2FA gia' abilitata")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=current_user.get("email", user_id),
        issuer_name="NeoNoble Ramp",
    )

    # Generate QR code
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    # Store pending secret
    await db.totp_secrets.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "secret": secret,
            "enabled": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    return {
        "secret": secret,
        "qr_code_base64": f"data:image/png;base64,{qr_b64}",
        "uri": uri,
        "message": "Scansiona il QR code con la tua app authenticator, poi verifica con un codice",
    }


@router.post("/verify")
async def verify_and_enable_2fa(req: TOTPVerifyRequest, current_user: dict = Depends(get_current_user)):
    """Verify TOTP code to enable 2FA."""
    db = get_database()
    user_id = current_user["user_id"]

    record = await db.totp_secrets.find_one({"user_id": user_id})
    if not record:
        raise HTTPException(status_code=400, detail="Configura prima il 2FA con /setup")

    totp = pyotp.TOTP(record["secret"])
    if not totp.verify(req.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codice TOTP non valido")

    # Generate backup codes
    import secrets
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]

    await db.totp_secrets.update_one(
        {"user_id": user_id},
        {"$set": {
            "enabled": True,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "backup_codes": backup_codes,
        }},
    )
    await db.users.update_one({"id": user_id}, {"$set": {"totp_enabled": True}})

    return {
        "message": "2FA abilitata con successo",
        "backup_codes": backup_codes,
        "warning": "Salva i codici di backup in un posto sicuro. Non potranno essere recuperati.",
    }


@router.post("/validate")
async def validate_totp(req: TOTPVerifyRequest, current_user: dict = Depends(get_current_user)):
    """Validate a TOTP code (used during login or sensitive operations)."""
    db = get_database()
    user_id = current_user["user_id"]

    record = await db.totp_secrets.find_one({"user_id": user_id, "enabled": True})
    if not record:
        return {"valid": True, "message": "2FA non abilitata"}

    totp = pyotp.TOTP(record["secret"])
    if totp.verify(req.code, valid_window=1):
        return {"valid": True, "message": "Codice valido"}

    # Check backup codes
    if req.code.upper() in (record.get("backup_codes") or []):
        codes = record["backup_codes"]
        codes.remove(req.code.upper())
        await db.totp_secrets.update_one({"user_id": user_id}, {"$set": {"backup_codes": codes}})
        return {"valid": True, "message": "Codice backup utilizzato", "remaining_backup_codes": len(codes)}

    raise HTTPException(status_code=401, detail="Codice TOTP non valido")


@router.post("/disable")
async def disable_2fa(req: TOTPDisableRequest, current_user: dict = Depends(get_current_user)):
    """Disable 2FA (requires valid TOTP code)."""
    db = get_database()
    user_id = current_user["user_id"]

    record = await db.totp_secrets.find_one({"user_id": user_id, "enabled": True})
    if not record:
        raise HTTPException(status_code=400, detail="2FA non abilitata")

    totp = pyotp.TOTP(record["secret"])
    if not totp.verify(req.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codice TOTP non valido")

    await db.totp_secrets.update_one({"user_id": user_id}, {"$set": {"enabled": False}})
    await db.users.update_one({"id": user_id}, {"$set": {"totp_enabled": False}})

    return {"message": "2FA disabilitata"}


@router.get("/status")
async def get_2fa_status(current_user: dict = Depends(get_current_user)):
    """Get 2FA status for current user."""
    db = get_database()
    record = await db.totp_secrets.find_one({"user_id": current_user["user_id"]}, {"_id": 0, "secret": 0})
    return {
        "enabled": record.get("enabled", False) if record else False,
        "verified_at": record.get("verified_at") if record else None,
        "backup_codes_remaining": len(record.get("backup_codes", [])) if record else 0,
    }
