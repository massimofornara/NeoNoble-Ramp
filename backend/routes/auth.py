from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
import logging

from models.user import UserCreate, UserLogin, UserResponse, UserRole
from services.auth_service import AuthService
from middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Service will be set by the main app
auth_service: AuthService = None


def set_auth_service(service: AuthService):
    global auth_service
    auth_service = service


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "USER"  # USER or DEVELOPER


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    token: str = None
    user: UserResponse = None


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user."""
    try:
        # Validate role
        try:
            role = UserRole(request.role.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {[r.value for r in UserRole]}"
            )
        
        user_create = UserCreate(
            email=request.email,
            password=request.password,
            role=role
        )
        
        user, error = await auth_service.register(user_create)
        
        if error:
            logger.warning(f"Registration failed for {request.email}: {error}")
            raise HTTPException(status_code=400, detail=error)
        
        # Auto-login after registration
        token, _ = await auth_service.login(request.email, request.password)
        
        return AuthResponse(
            success=True,
            message="Registration successful",
            token=token,
            user=auth_service.user_to_response(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login with email and password."""
    try:
        token, error = await auth_service.login(request.email, request.password)
        
        if error:
            logger.warning(f"Login failed for {request.email}: {error}")
            raise HTTPException(status_code=401, detail=error)
        
        user = await auth_service.get_user_by_email(request.email)
        
        return AuthResponse(
            success=True,
            message="Login successful",
            token=token,
            user=auth_service.user_to_response(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info."""
    user = await auth_service.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return auth_service.user_to_response(user)


@router.post("/logout")
async def logout():
    """Logout (client should discard token)."""
    return {"success": True, "message": "Logged out successfully"}



@router.get("/admin/users")
async def admin_list_users(current_user: dict = Depends(get_current_user)):
    """List all users. Admin only."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = await auth_service.db.users.find(
        {}, {"_id": 0, "password_hash": 0}
    ).sort("created_at", -1).to_list(500)
    
    for u in users:
        if "created_at" in u and hasattr(u["created_at"], "isoformat"):
            u["created_at"] = u["created_at"].isoformat()
    
    return {"users": users, "total": len(users)}
