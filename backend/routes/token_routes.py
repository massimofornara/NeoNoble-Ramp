"""
Token Infrastructure API Routes.

Provides endpoints for:
- Token creation and management
- Token listing marketplace
- Trading pair management
- Admin approval workflows

Enterprise-grade implementation for NeoNoble Ramp fintech infrastructure.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/tokens", tags=["Token Infrastructure"])


# ========================
# Enums
# ========================

class ChainType(str, Enum):
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    BASE = "base"


class TokenStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    LIVE = "live"
    PAUSED = "paused"


class ListingStatus(str, Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    LIVE = "live"
    SUSPENDED = "suspended"


class ListingType(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    FEATURED = "featured"


# ========================
# Request/Response Models
# ========================

class TokenCreateRequest(BaseModel):
    """Request model for creating a new token."""
    name: str = Field(..., min_length=2, max_length=100, description="Token name")
    symbol: str = Field(..., min_length=2, max_length=10, description="Token symbol (uppercase)")
    description: Optional[str] = Field(None, max_length=2000)
    total_supply: float = Field(..., gt=0, description="Total token supply")
    initial_price: float = Field(..., gt=0, description="Initial price in EUR")
    chain: ChainType = Field(..., description="Blockchain network")
    decimals: int = Field(18, ge=0, le=18)
    
    # Optional metadata
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    whitepaper_url: Optional[str] = None
    social_links: Optional[dict] = None


class TokenResponse(BaseModel):
    """Response model for token data."""
    id: str
    name: str
    symbol: str
    description: Optional[str]
    total_supply: float
    circulating_supply: float
    initial_price: float
    current_price: float
    chain: str
    contract_address: Optional[str]
    decimals: int
    token_type: str
    status: str
    creator_id: str
    creation_fee: float
    creation_fee_paid: bool
    logo_url: Optional[str]
    website_url: Optional[str]
    approved_at: Optional[str]
    created_at: str
    trading_pairs_count: int = 0


class TokenListResponse(BaseModel):
    """Response model for token list."""
    tokens: List[TokenResponse]
    total: int
    page: int
    page_size: int


class ListingCreateRequest(BaseModel):
    """Request model for creating a token listing."""
    token_id: str
    listing_type: ListingType = ListingType.STANDARD
    requested_pairs: List[str] = Field(default=["EUR", "USD", "USDT"])


class ListingResponse(BaseModel):
    """Response model for listing data."""
    id: str
    token_id: str
    token_symbol: str
    listing_type: str
    listing_fee: float
    listing_fee_paid: bool
    status: str
    requested_pairs: List[str]
    approved_pairs: List[str]
    reviewed_at: Optional[str]
    created_at: str


class TradingPairCreateRequest(BaseModel):
    """Request model for creating a trading pair."""
    token_id: str
    quote_currency: str = Field(..., description="Quote currency (EUR, USD, USDT, BTC, etc.)")


class TradingPairResponse(BaseModel):
    """Response model for trading pair data."""
    id: str
    base_token_id: str
    base_token_symbol: str
    quote_currency: str
    pair_symbol: str
    status: str
    min_order_size: float
    max_order_size: float
    maker_fee: float
    taker_fee: float
    volume_24h: float
    created_at: str


class AdminTokenActionRequest(BaseModel):
    """Request model for admin actions on tokens."""
    action: str = Field(..., description="approve, reject, pause, unpause")
    reason: Optional[str] = None


# ========================
# Pricing Configuration
# ========================

LISTING_FEES = {
    "standard": 500.0,    # €500 for standard listing
    "premium": 2000.0,    # €2000 for premium listing
    "featured": 5000.0,   # €5000 for featured listing
}

TOKEN_CREATION_FEE = 100.0  # €100 to create a token

TRADING_PAIR_FEE = 50.0  # €50 per trading pair


# ========================
# Helper Functions
# ========================

def generate_id():
    from uuid import uuid4
    return str(uuid4())


def utc_now():
    return datetime.now(timezone.utc)


# ========================
# Token CRUD Endpoints
# ========================

@router.post("/create", response_model=TokenResponse)
async def create_token(request: TokenCreateRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a new token.
    
    - Validates token data
    - Calculates creation fee
    - Sets status to pending for admin approval
    """
    db = get_database()
    
    # Check if symbol already exists
    existing = await db.tokens.find_one({"symbol": request.symbol.upper()})
    if existing:
        raise HTTPException(status_code=400, detail=f"Token symbol '{request.symbol}' already exists")
    
    # Create token document
    token_id = generate_id()
    now = utc_now()
    
    token = {
        "_id": token_id,
        "id": token_id,
        "name": request.name,
        "symbol": request.symbol.upper(),
        "description": request.description,
        "total_supply": request.total_supply,
        "circulating_supply": 0.0,
        "initial_price": request.initial_price,
        "current_price": request.initial_price,
        "chain": request.chain.value,
        "contract_address": None,
        "decimals": request.decimals,
        "token_type": "custom",
        "status": TokenStatus.PENDING.value,
        "creator_id": current_user["user_id"],
        "owner_id": current_user["user_id"],
        "creation_fee": TOKEN_CREATION_FEE,
        "creation_fee_paid": False,
        "logo_url": request.logo_url,
        "website_url": request.website_url,
        "whitepaper_url": request.whitepaper_url,
        "social_links": request.social_links or {},
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        "created_at": now,
        "updated_at": now,
        "listed_at": None,
        "extra_data": {},
        "trading_pairs_count": 0
    }
    
    await db.tokens.insert_one(token)
    
    # Remove MongoDB _id for response
    token.pop("_id", None)
    token["created_at"] = token["created_at"].isoformat()
    token["approved_at"] = None
    
    return TokenResponse(**token)


@router.get("/list", response_model=TokenListResponse)
async def list_tokens(
    status: Optional[str] = None,
    chain: Optional[str] = None,
    creator_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    List tokens with filters.
    
    - Filter by status, chain, creator
    - Paginated response
    """
    db = get_database()
    
    # Build filter
    filter_query = {}
    if status:
        filter_query["status"] = status
    if chain:
        filter_query["chain"] = chain
    if creator_id:
        filter_query["creator_id"] = creator_id
    
    # Get total count
    total = await db.tokens.count_documents(filter_query)
    
    # Get paginated results
    skip = (page - 1) * page_size
    cursor = db.tokens.find(filter_query).sort("created_at", -1).skip(skip).limit(page_size)
    
    tokens = []
    async for token in cursor:
        token.pop("_id", None)
        token["created_at"] = token["created_at"].isoformat() if isinstance(token.get("created_at"), datetime) else str(token.get("created_at", ""))
        token["approved_at"] = token["approved_at"].isoformat() if token.get("approved_at") else None
        tokens.append(TokenResponse(**token))
    
    return TokenListResponse(
        tokens=tokens,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(token_id: str, current_user: dict = Depends(get_current_user)):
    """Get token details by ID."""
    db = get_database()
    
    token = await db.tokens.find_one({"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    token.pop("_id", None)
    token["created_at"] = token["created_at"].isoformat() if isinstance(token.get("created_at"), datetime) else str(token.get("created_at", ""))
    token["approved_at"] = token["approved_at"].isoformat() if token.get("approved_at") else None
    
    return TokenResponse(**token)


@router.get("/symbol/{symbol}", response_model=TokenResponse)
async def get_token_by_symbol(symbol: str, current_user: dict = Depends(get_current_user)):
    """Get token details by symbol."""
    db = get_database()
    
    token = await db.tokens.find_one({"symbol": symbol.upper()})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    token.pop("_id", None)
    token["created_at"] = token["created_at"].isoformat() if isinstance(token.get("created_at"), datetime) else str(token.get("created_at", ""))
    token["approved_at"] = token["approved_at"].isoformat() if token.get("approved_at") else None
    
    return TokenResponse(**token)


@router.put("/{token_id}", response_model=TokenResponse)
async def update_token(token_id: str, request: TokenCreateRequest, current_user: dict = Depends(get_current_user)):
    """
    Update token details.
    
    - Only creator or admin can update
    - Cannot change symbol after creation
    """
    db = get_database()
    
    token = await db.tokens.find_one({"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Check permissions
    if token["creator_id"] != current_user["user_id"] and current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Not authorized to update this token")
    
    # Update fields (symbol cannot be changed)
    update_data = {
        "name": request.name,
        "description": request.description,
        "total_supply": request.total_supply,
        "initial_price": request.initial_price,
        "chain": request.chain.value,
        "decimals": request.decimals,
        "logo_url": request.logo_url,
        "website_url": request.website_url,
        "whitepaper_url": request.whitepaper_url,
        "social_links": request.social_links or {},
        "updated_at": utc_now()
    }
    
    await db.tokens.update_one({"id": token_id}, {"$set": update_data})
    
    # Return updated token
    token = await db.tokens.find_one({"id": token_id})
    token.pop("_id", None)
    token["created_at"] = token["created_at"].isoformat() if isinstance(token.get("created_at"), datetime) else str(token.get("created_at", ""))
    token["approved_at"] = token["approved_at"].isoformat() if token.get("approved_at") else None
    
    return TokenResponse(**token)


# ========================
# Admin Token Management
# ========================

@router.post("/{token_id}/admin-action")
async def admin_token_action(
    token_id: str, 
    request: AdminTokenActionRequest, 
    current_user: dict = Depends(get_current_user)
):
    """
    Admin actions on tokens: approve, reject, pause, unpause.
    
    - Only admins can perform these actions
    - Updates token status accordingly
    """
    # Check admin role
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    
    token = await db.tokens.find_one({"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    now = utc_now()
    update_data = {"updated_at": now}
    
    if request.action == "approve":
        update_data["status"] = TokenStatus.APPROVED.value
        update_data["approved_by"] = current_user["user_id"]
        update_data["approved_at"] = now
        update_data["rejection_reason"] = None
    elif request.action == "reject":
        update_data["status"] = TokenStatus.REJECTED.value
        update_data["rejection_reason"] = request.reason
    elif request.action == "pause":
        update_data["status"] = TokenStatus.PAUSED.value
    elif request.action == "unpause":
        update_data["status"] = TokenStatus.APPROVED.value
    elif request.action == "go_live":
        update_data["status"] = TokenStatus.LIVE.value
        update_data["listed_at"] = now
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    await db.tokens.update_one({"id": token_id}, {"$set": update_data})
    
    return {
        "success": True,
        "message": f"Token {request.action}d successfully",
        "token_id": token_id,
        "new_status": update_data.get("status", token["status"])
    }


# ========================
# Token Listing Marketplace
# ========================

@router.post("/listings/create", response_model=ListingResponse)
async def create_listing(request: ListingCreateRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a token listing request.
    
    - Calculates listing fee based on type
    - Creates pending listing for admin review
    """
    db = get_database()
    
    # Verify token exists
    token = await db.tokens.find_one({"id": request.token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Check if user owns the token or is admin
    if token["creator_id"] != current_user["user_id"] and current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Only token creator can request listing")
    
    # Check for existing pending listing
    existing = await db.token_listings.find_one({
        "token_id": request.token_id,
        "status": {"$in": ["pending", "under_review"]}
    })
    if existing:
        raise HTTPException(status_code=400, detail="A pending listing request already exists for this token")
    
    # Calculate listing fee
    listing_fee = LISTING_FEES.get(request.listing_type.value, LISTING_FEES["standard"])
    
    listing_id = generate_id()
    now = utc_now()
    
    listing = {
        "_id": listing_id,
        "id": listing_id,
        "token_id": request.token_id,
        "token_symbol": token["symbol"],
        "requested_by": current_user["user_id"],
        "listing_type": request.listing_type.value,
        "listing_fee": listing_fee,
        "listing_fee_paid": False,
        "payment_reference": None,
        "status": ListingStatus.PENDING.value,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": None,
        "rejection_reason": None,
        "requested_pairs": request.requested_pairs,
        "approved_pairs": [],
        "listing_duration_days": 365,
        "listing_expires_at": None,
        "created_at": now,
        "updated_at": now
    }
    
    await db.token_listings.insert_one(listing)
    
    listing.pop("_id", None)
    listing["created_at"] = listing["created_at"].isoformat()
    listing["reviewed_at"] = None
    
    return ListingResponse(**listing)


@router.get("/listings/list")
async def list_listings(
    status: Optional[str] = None,
    token_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List token listings with filters."""
    db = get_database()
    
    filter_query = {}
    if status:
        filter_query["status"] = status
    if token_id:
        filter_query["token_id"] = token_id
    
    total = await db.token_listings.count_documents(filter_query)
    
    skip = (page - 1) * page_size
    cursor = db.token_listings.find(filter_query).sort("created_at", -1).skip(skip).limit(page_size)
    
    listings = []
    async for listing in cursor:
        listing.pop("_id", None)
        listing["created_at"] = listing["created_at"].isoformat() if isinstance(listing.get("created_at"), datetime) else str(listing.get("created_at", ""))
        listing["reviewed_at"] = listing["reviewed_at"].isoformat() if listing.get("reviewed_at") else None
        listings.append(listing)
    
    return {
        "listings": listings,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/listings/{listing_id}/admin-action")
async def admin_listing_action(
    listing_id: str,
    action: str,
    approved_pairs: Optional[List[str]] = None,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Admin actions on listings: approve, reject, suspend.
    
    - Only admins can perform these actions
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    
    listing = await db.token_listings.find_one({"id": listing_id})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    now = utc_now()
    update_data = {
        "updated_at": now,
        "reviewed_by": current_user["user_id"],
        "reviewed_at": now
    }
    
    if action == "approve":
        update_data["status"] = ListingStatus.APPROVED.value
        update_data["approved_pairs"] = approved_pairs or listing["requested_pairs"]
        update_data["listing_expires_at"] = now + timedelta(days=listing.get("listing_duration_days", 365))
        
        # Also update token status
        await db.tokens.update_one(
            {"id": listing["token_id"]},
            {"$set": {"status": TokenStatus.LIVE.value, "listed_at": now}}
        )
    elif action == "reject":
        update_data["status"] = ListingStatus.REJECTED.value
        update_data["rejection_reason"] = reason
    elif action == "suspend":
        update_data["status"] = ListingStatus.SUSPENDED.value
        update_data["review_notes"] = reason
    elif action == "go_live":
        update_data["status"] = ListingStatus.LIVE.value
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    
    await db.token_listings.update_one({"id": listing_id}, {"$set": update_data})
    
    return {
        "success": True,
        "message": f"Listing {action}d successfully",
        "listing_id": listing_id
    }


# ========================
# Trading Pairs Management
# ========================

@router.post("/pairs/create", response_model=TradingPairResponse)
async def create_trading_pair(request: TradingPairCreateRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a new trading pair for a token.
    
    - Requires token to be approved/live
    - Calculates pair creation fee
    """
    db = get_database()
    
    # Verify token exists and is approved
    token = await db.tokens.find_one({"id": request.token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token["status"] not in [TokenStatus.APPROVED.value, TokenStatus.LIVE.value]:
        raise HTTPException(status_code=400, detail="Token must be approved before creating trading pairs")
    
    # Check if pair already exists
    pair_symbol = f"{token['symbol']}/{request.quote_currency.upper()}"
    existing = await db.trading_pairs.find_one({"pair_symbol": pair_symbol})
    if existing:
        raise HTTPException(status_code=400, detail=f"Trading pair {pair_symbol} already exists")
    
    pair_id = generate_id()
    now = utc_now()
    
    pair = {
        "_id": pair_id,
        "id": pair_id,
        "base_token_id": request.token_id,
        "base_token_symbol": token["symbol"],
        "quote_currency": request.quote_currency.upper(),
        "pair_symbol": pair_symbol,
        "status": "pending",
        "min_order_size": 0.001,
        "max_order_size": 1000000.0,
        "price_precision": 8,
        "quantity_precision": 8,
        "maker_fee": 0.001,
        "taker_fee": 0.002,
        "creation_fee": TRADING_PAIR_FEE,
        "creation_fee_paid": False,
        "volume_24h": 0.0,
        "volume_total": 0.0,
        "created_at": now,
        "updated_at": now
    }
    
    await db.trading_pairs.insert_one(pair)
    
    # Update token's trading pairs count
    await db.tokens.update_one(
        {"id": request.token_id},
        {"$inc": {"trading_pairs_count": 1}}
    )
    
    pair.pop("_id", None)
    pair["created_at"] = pair["created_at"].isoformat()
    
    return TradingPairResponse(**pair)


@router.get("/pairs/list")
async def list_trading_pairs(
    token_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List trading pairs with filters."""
    db = get_database()
    
    filter_query = {}
    if token_id:
        filter_query["base_token_id"] = token_id
    if status:
        filter_query["status"] = status
    
    total = await db.trading_pairs.count_documents(filter_query)
    
    skip = (page - 1) * page_size
    cursor = db.trading_pairs.find(filter_query).sort("created_at", -1).skip(skip).limit(page_size)
    
    pairs = []
    async for pair in cursor:
        pair.pop("_id", None)
        pair["created_at"] = pair["created_at"].isoformat() if isinstance(pair.get("created_at"), datetime) else str(pair.get("created_at", ""))
        pairs.append(pair)
    
    return {
        "pairs": pairs,
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ========================
# Statistics Endpoints
# ========================

@router.get("/stats/overview")
async def get_token_stats(current_user: dict = Depends(get_current_user)):
    """Get token infrastructure statistics for admin dashboard."""
    db = get_database()
    
    # Token counts by status
    total_tokens = await db.tokens.count_documents({})
    pending_tokens = await db.tokens.count_documents({"status": "pending"})
    approved_tokens = await db.tokens.count_documents({"status": "approved"})
    live_tokens = await db.tokens.count_documents({"status": "live"})
    
    # Listing counts
    total_listings = await db.token_listings.count_documents({})
    pending_listings = await db.token_listings.count_documents({"status": "pending"})
    
    # Trading pairs count
    total_pairs = await db.trading_pairs.count_documents({})
    active_pairs = await db.trading_pairs.count_documents({"status": "active"})
    
    return {
        "tokens": {
            "total": total_tokens,
            "pending": pending_tokens,
            "approved": approved_tokens,
            "live": live_tokens
        },
        "listings": {
            "total": total_listings,
            "pending": pending_listings
        },
        "trading_pairs": {
            "total": total_pairs,
            "active": active_pairs
        },
        "fees": {
            "token_creation": TOKEN_CREATION_FEE,
            "listing_standard": LISTING_FEES["standard"],
            "listing_premium": LISTING_FEES["premium"],
            "listing_featured": LISTING_FEES["featured"],
            "trading_pair": TRADING_PAIR_FEE
        }
    }
