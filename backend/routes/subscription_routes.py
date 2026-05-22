"""
Subscription Infrastructure API Routes.

Provides endpoints for:
- Subscription plans management
- User subscriptions
- Billing and invoices
- Feature gating

Enterprise-grade implementation for NeoNoble Ramp fintech infrastructure.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/subscriptions", tags=["Subscription Infrastructure"])


# ========================
# Enums
# ========================

class PlanType(str, Enum):
    USER = "user"
    DEVELOPER = "developer"
    ENTERPRISE = "enterprise"


class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAUSED = "paused"


# ========================
# Request/Response Models
# ========================

class PlanCreateRequest(BaseModel):
    """Request model for creating a subscription plan."""
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    plan_type: PlanType
    price_monthly: float = Field(0.0, ge=0)
    price_yearly: float = Field(0.0, ge=0)
    currency: str = "EUR"
    features: dict = Field(default_factory=dict)
    max_api_keys: int = 1
    max_tokens_created: int = 0
    max_listings: int = 0
    trading_fee_discount: float = 0.0


class PlanResponse(BaseModel):
    """Response model for subscription plan."""
    id: str
    name: str
    code: str
    description: Optional[str]
    plan_type: str
    price_monthly: float
    price_yearly: float
    currency: str
    features: dict
    max_api_keys: int
    max_tokens_created: int
    max_listings: int
    trading_fee_discount: float
    is_active: bool
    is_visible: bool
    created_at: str


class SubscribeRequest(BaseModel):
    """Request model for subscribing to a plan."""
    plan_id: str
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    payment_method: Optional[str] = "stripe"


class SubscriptionResponse(BaseModel):
    """Response model for user subscription."""
    id: str
    user_id: str
    plan_id: str
    plan_name: str
    plan_code: str
    status: str
    billing_cycle: str
    amount_paid: float
    currency: str
    started_at: str
    current_period_start: str
    current_period_end: Optional[str]
    auto_renew: bool
    api_calls_used: int
    tokens_created: int
    listings_used: int


# ========================
# Helper Functions
# ========================

def generate_id():
    from uuid import uuid4
    return str(uuid4())


def utc_now():
    return datetime.now(timezone.utc)


def generate_invoice_number():
    import random
    return f"INV-{datetime.now().strftime('%Y%m%d')}-{random.randint(10000, 99999)}"


# ========================
# Default Plans (Seed Data)
# ========================

DEFAULT_PLANS = [
    {
        "name": "Free",
        "code": "free",
        "description": "Basic access to NeoNoble Ramp platform",
        "plan_type": "user",
        "price_monthly": 0.0,
        "price_yearly": 0.0,
        "features": {
            "trading_enabled": True,
            "max_trades_per_day": 10,
            "advanced_charts": False,
            "priority_support": False
        },
        "max_api_keys": 0,
        "max_tokens_created": 0,
        "max_listings": 0,
        "trading_fee_discount": 0.0
    },
    {
        "name": "Pro Trader",
        "code": "pro_trader",
        "description": "Advanced trading features with reduced fees",
        "plan_type": "user",
        "price_monthly": 29.99,
        "price_yearly": 299.99,
        "features": {
            "trading_enabled": True,
            "max_trades_per_day": -1,  # Unlimited
            "advanced_charts": True,
            "priority_support": True,
            "trading_signals": True,
            "portfolio_analytics": True
        },
        "max_api_keys": 1,
        "max_tokens_created": 0,
        "max_listings": 0,
        "trading_fee_discount": 0.25  # 25% discount
    },
    {
        "name": "Premium",
        "code": "premium",
        "description": "Full access with token creation capabilities",
        "plan_type": "user",
        "price_monthly": 99.99,
        "price_yearly": 999.99,
        "features": {
            "trading_enabled": True,
            "max_trades_per_day": -1,
            "advanced_charts": True,
            "priority_support": True,
            "trading_signals": True,
            "portfolio_analytics": True,
            "token_creation": True,
            "listing_priority": True
        },
        "max_api_keys": 3,
        "max_tokens_created": 5,
        "max_listings": 3,
        "trading_fee_discount": 0.50  # 50% discount
    },
    {
        "name": "Developer Basic",
        "code": "developer_basic",
        "description": "API access for developers and integrators",
        "plan_type": "developer",
        "price_monthly": 49.99,
        "price_yearly": 499.99,
        "features": {
            "api_access": True,
            "api_calls_per_month": 10000,
            "webhook_support": True,
            "sandbox_environment": True,
            "basic_support": True
        },
        "max_api_keys": 3,
        "max_tokens_created": 1,
        "max_listings": 1,
        "trading_fee_discount": 0.10
    },
    {
        "name": "Developer Pro",
        "code": "developer_pro",
        "description": "Professional API access with advanced features",
        "plan_type": "developer",
        "price_monthly": 199.99,
        "price_yearly": 1999.99,
        "features": {
            "api_access": True,
            "api_calls_per_month": 100000,
            "webhook_support": True,
            "sandbox_environment": True,
            "priority_support": True,
            "custom_integrations": True,
            "dedicated_support": True
        },
        "max_api_keys": 10,
        "max_tokens_created": 10,
        "max_listings": 10,
        "trading_fee_discount": 0.30
    },
    {
        "name": "Enterprise",
        "code": "enterprise",
        "description": "Custom enterprise solution with full platform access",
        "plan_type": "enterprise",
        "price_monthly": 999.99,
        "price_yearly": 9999.99,
        "features": {
            "api_access": True,
            "api_calls_per_month": -1,  # Unlimited
            "webhook_support": True,
            "sandbox_environment": True,
            "dedicated_support": True,
            "custom_integrations": True,
            "white_label": True,
            "sla_guarantee": True,
            "dedicated_account_manager": True
        },
        "max_api_keys": -1,  # Unlimited
        "max_tokens_created": -1,
        "max_listings": -1,
        "trading_fee_discount": 0.50
    }
]


# ========================
# Plan CRUD Endpoints
# ========================

@router.post("/plans/seed")
async def seed_default_plans(current_user: dict = Depends(get_current_user)):
    """
    Seed default subscription plans.
    Admin only.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    now = utc_now()
    
    created_count = 0
    for plan_data in DEFAULT_PLANS:
        # Check if plan already exists
        existing = await db.subscription_plans.find_one({"code": plan_data["code"]})
        if not existing:
            plan_id = generate_id()
            plan = {
                "_id": plan_id,
                "id": plan_id,
                **plan_data,
                "currency": "EUR",
                "is_active": True,
                "is_visible": True,
                "created_at": now,
                "updated_at": now
            }
            await db.subscription_plans.insert_one(plan)
            created_count += 1
    
    return {
        "success": True,
        "message": f"Created {created_count} subscription plans",
        "total_plans": len(DEFAULT_PLANS)
    }


@router.post("/plans/create", response_model=PlanResponse)
async def create_plan(request: PlanCreateRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a new subscription plan.
    Admin only.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    
    # Check if code already exists
    existing = await db.subscription_plans.find_one({"code": request.code})
    if existing:
        raise HTTPException(status_code=400, detail=f"Plan code '{request.code}' already exists")
    
    plan_id = generate_id()
    now = utc_now()
    
    plan = {
        "_id": plan_id,
        "id": plan_id,
        "name": request.name,
        "code": request.code,
        "description": request.description,
        "plan_type": request.plan_type.value,
        "price_monthly": request.price_monthly,
        "price_yearly": request.price_yearly,
        "currency": request.currency,
        "features": request.features,
        "max_api_keys": request.max_api_keys,
        "max_tokens_created": request.max_tokens_created,
        "max_listings": request.max_listings,
        "trading_fee_discount": request.trading_fee_discount,
        "is_active": True,
        "is_visible": True,
        "created_at": now,
        "updated_at": now
    }
    
    await db.subscription_plans.insert_one(plan)
    
    plan.pop("_id", None)
    plan["created_at"] = plan["created_at"].isoformat()
    
    return PlanResponse(**plan)


@router.get("/plans/list")
async def list_plans(
    plan_type: Optional[str] = None,
    is_visible: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """List available subscription plans."""
    db = get_database()
    
    filter_query = {"is_active": True}
    if plan_type:
        filter_query["plan_type"] = plan_type
    if is_visible:
        filter_query["is_visible"] = True
    
    cursor = db.subscription_plans.find(filter_query).sort("price_monthly", 1)
    
    plans = []
    async for plan in cursor:
        plan.pop("_id", None)
        plan["created_at"] = plan["created_at"].isoformat() if isinstance(plan.get("created_at"), datetime) else str(plan.get("created_at", ""))
        plans.append(plan)
    
    return {"plans": plans}


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str, current_user: dict = Depends(get_current_user)):
    """Get plan details by ID."""
    db = get_database()
    
    plan = await db.subscription_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan.pop("_id", None)
    plan["created_at"] = plan["created_at"].isoformat() if isinstance(plan.get("created_at"), datetime) else str(plan.get("created_at", ""))
    
    return PlanResponse(**plan)


# ========================
# Subscription Endpoints
# ========================

@router.post("/subscribe", response_model=SubscriptionResponse)
async def subscribe_to_plan(request: SubscribeRequest, current_user: dict = Depends(get_current_user)):
    """
    Subscribe to a plan.
    
    - Creates subscription record
    - Handles billing cycle
    - Sets up payment reference
    """
    db = get_database()
    
    # Get plan
    plan = await db.subscription_plans.find_one({"id": request.plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if not plan.get("is_active"):
        raise HTTPException(status_code=400, detail="Plan is not available")
    
    # Check for existing active subscription
    existing = await db.subscriptions.find_one({
        "user_id": current_user["user_id"],
        "status": SubscriptionStatus.ACTIVE.value
    })
    if existing:
        raise HTTPException(status_code=400, detail="You already have an active subscription. Please cancel it first.")
    
    # Calculate amount
    amount = plan["price_monthly"] if request.billing_cycle == BillingCycle.MONTHLY else plan["price_yearly"]
    
    # Calculate period end
    now = utc_now()
    if request.billing_cycle == BillingCycle.MONTHLY:
        period_end = now + timedelta(days=30)
    else:
        period_end = now + timedelta(days=365)
    
    subscription_id = generate_id()
    
    subscription = {
        "_id": subscription_id,
        "id": subscription_id,
        "user_id": current_user["user_id"],
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "plan_code": plan["code"],
        "status": SubscriptionStatus.ACTIVE.value,
        "billing_cycle": request.billing_cycle.value,
        "amount_paid": amount,
        "currency": plan["currency"],
        "payment_method": request.payment_method,
        "payment_reference": None,
        "stripe_subscription_id": None,
        "started_at": now,
        "current_period_start": now,
        "current_period_end": period_end,
        "cancelled_at": None,
        "auto_renew": True,
        "api_calls_used": 0,
        "tokens_created": 0,
        "listings_used": 0,
        "created_at": now,
        "updated_at": now
    }
    
    await db.subscriptions.insert_one(subscription)
    
    # Create invoice
    invoice = {
        "_id": generate_id(),
        "id": generate_id(),
        "subscription_id": subscription_id,
        "user_id": current_user["user_id"],
        "invoice_number": generate_invoice_number(),
        "amount": amount,
        "currency": plan["currency"],
        "status": "paid" if amount == 0 else "pending",
        "paid_at": now if amount == 0 else None,
        "payment_method": request.payment_method,
        "period_start": now,
        "period_end": period_end,
        "created_at": now
    }
    await db.subscription_invoices.insert_one(invoice)
    
    # Update user role if developer plan
    if plan["plan_type"] == "developer":
        await db.users.update_one(
            {"id": current_user["user_id"]},
            {"$set": {"role": "developer"}}
        )
    
    subscription.pop("_id", None)
    subscription["started_at"] = subscription["started_at"].isoformat()
    subscription["current_period_start"] = subscription["current_period_start"].isoformat()
    subscription["current_period_end"] = subscription["current_period_end"].isoformat() if subscription["current_period_end"] else None
    
    return SubscriptionResponse(**subscription)


@router.get("/my-subscription", response_model=Optional[SubscriptionResponse])
async def get_my_subscription(current_user: dict = Depends(get_current_user)):
    """Get current user's active subscription."""
    db = get_database()
    
    subscription = await db.subscriptions.find_one({
        "user_id": current_user["user_id"],
        "status": SubscriptionStatus.ACTIVE.value
    })
    
    if not subscription:
        return None
    
    subscription.pop("_id", None)
    subscription["started_at"] = subscription["started_at"].isoformat() if isinstance(subscription.get("started_at"), datetime) else str(subscription.get("started_at", ""))
    subscription["current_period_start"] = subscription["current_period_start"].isoformat() if isinstance(subscription.get("current_period_start"), datetime) else str(subscription.get("current_period_start", ""))
    subscription["current_period_end"] = subscription["current_period_end"].isoformat() if isinstance(subscription.get("current_period_end"), datetime) else None
    
    return SubscriptionResponse(**subscription)


@router.post("/cancel")
async def cancel_subscription(current_user: dict = Depends(get_current_user)):
    """Cancel current user's subscription."""
    db = get_database()
    
    subscription = await db.subscriptions.find_one({
        "user_id": current_user["user_id"],
        "status": SubscriptionStatus.ACTIVE.value
    })
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    now = utc_now()
    
    await db.subscriptions.update_one(
        {"id": subscription["id"]},
        {
            "$set": {
                "status": SubscriptionStatus.CANCELLED.value,
                "cancelled_at": now,
                "auto_renew": False,
                "updated_at": now
            }
        }
    )
    
    return {
        "success": True,
        "message": "Subscription cancelled. You will retain access until the end of your current billing period.",
        "access_until": subscription.get("current_period_end")
    }


# ========================
# Usage Tracking
# ========================

@router.post("/track-usage")
async def track_usage(
    usage_type: str,  # api_call, token_created, listing_used
    current_user: dict = Depends(get_current_user)
):
    """Track subscription usage."""
    db = get_database()
    
    subscription = await db.subscriptions.find_one({
        "user_id": current_user["user_id"],
        "status": SubscriptionStatus.ACTIVE.value
    })
    
    if not subscription:
        return {"tracked": False, "reason": "No active subscription"}
    
    field_map = {
        "api_call": "api_calls_used",
        "token_created": "tokens_created",
        "listing_used": "listings_used"
    }
    
    field = field_map.get(usage_type)
    if not field:
        raise HTTPException(status_code=400, detail="Invalid usage type")
    
    await db.subscriptions.update_one(
        {"id": subscription["id"]},
        {"$inc": {field: 1}, "$set": {"updated_at": utc_now()}}
    )
    
    return {"tracked": True, "usage_type": usage_type}


@router.get("/check-limit")
async def check_subscription_limit(
    feature: str,  # api_calls, tokens, listings
    current_user: dict = Depends(get_current_user)
):
    """Check if user is within subscription limits."""
    db = get_database()
    
    subscription = await db.subscriptions.find_one({
        "user_id": current_user["user_id"],
        "status": SubscriptionStatus.ACTIVE.value
    })
    
    if not subscription:
        return {
            "has_subscription": False,
            "within_limit": False,
            "message": "No active subscription"
        }
    
    plan = await db.subscription_plans.find_one({"id": subscription["plan_id"]})
    if not plan:
        return {"has_subscription": True, "within_limit": True}
    
    limit_map = {
        "api_calls": ("api_calls_used", plan.get("features", {}).get("api_calls_per_month", 0)),
        "tokens": ("tokens_created", plan.get("max_tokens_created", 0)),
        "listings": ("listings_used", plan.get("max_listings", 0))
    }
    
    usage_field, limit = limit_map.get(feature, (None, 0))
    if not usage_field:
        raise HTTPException(status_code=400, detail="Invalid feature")
    
    current_usage = subscription.get(usage_field, 0)
    
    # -1 means unlimited
    within_limit = limit == -1 or current_usage < limit
    
    return {
        "has_subscription": True,
        "within_limit": within_limit,
        "current_usage": current_usage,
        "limit": limit,
        "feature": feature
    }


# ========================
# Admin Endpoints
# ========================

@router.get("/admin/list")
async def admin_list_subscriptions(
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List all subscriptions. Admin only."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    
    filter_query = {}
    if status:
        filter_query["status"] = status
    
    total = await db.subscriptions.count_documents(filter_query)
    
    skip = (page - 1) * page_size
    cursor = db.subscriptions.find(filter_query).sort("created_at", -1).skip(skip).limit(page_size)
    
    subscriptions = []
    async for sub in cursor:
        sub.pop("_id", None)
        sub["started_at"] = sub["started_at"].isoformat() if isinstance(sub.get("started_at"), datetime) else str(sub.get("started_at", ""))
        sub["current_period_start"] = sub["current_period_start"].isoformat() if isinstance(sub.get("current_period_start"), datetime) else str(sub.get("current_period_start", ""))
        sub["current_period_end"] = sub["current_period_end"].isoformat() if sub.get("current_period_end") else None
        subscriptions.append(sub)
    
    return {
        "subscriptions": subscriptions,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/admin/stats")
async def admin_subscription_stats(current_user: dict = Depends(get_current_user)):
    """Get subscription statistics. Admin only."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = get_database()
    
    # Count by status
    total = await db.subscriptions.count_documents({})
    active = await db.subscriptions.count_documents({"status": "active"})
    cancelled = await db.subscriptions.count_documents({"status": "cancelled"})
    expired = await db.subscriptions.count_documents({"status": "expired"})
    
    # Revenue (sum of amount_paid for active subs)
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": None, "total_mrr": {"$sum": "$amount_paid"}}}
    ]
    revenue_result = await db.subscriptions.aggregate(pipeline).to_list(1)
    mrr = revenue_result[0]["total_mrr"] if revenue_result else 0
    
    return {
        "total_subscriptions": total,
        "by_status": {
            "active": active,
            "cancelled": cancelled,
            "expired": expired
        },
        "monthly_recurring_revenue": mrr,
        "currency": "EUR"
    }
