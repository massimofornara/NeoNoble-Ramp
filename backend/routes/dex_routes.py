"""
DEX Routes - C-SAFE Real Market Conversion API.

Provides endpoints for:
- Real on-chain DEX swap execution
- Progressive batch conversion
- Conversion job management
- Admin controls
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from services.dex import get_dex_service, BatchConfig, BatchExecutor
from services.dex.dex_service import (
    DEXService,
    NENO_ADDRESS,
    WBNB_ADDRESS,
    USDT_ADDRESS,
    USDC_ADDRESS,
    TOKEN_DECIMALS
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dex", tags=["DEX"])


# Request/Response Models

class SwapQuoteRequest(BaseModel):
    """Request for DEX swap quote."""
    source_token: str = Field(..., description="Source token address or symbol")
    destination_token: str = Field(..., description="Destination token address or symbol")
    amount: float = Field(..., description="Amount in token decimals")


class SwapExecuteRequest(BaseModel):
    """Request to execute DEX swap."""
    quote_id: str = Field(..., description="Quote ID to execute")
    max_slippage_pct: float = Field(2.0, description="Maximum slippage percentage")


class ConversionJobRequest(BaseModel):
    """Request to create conversion job."""
    quote_id: str = Field(..., description="Associated quote ID")
    source_token: str = Field(..., description="Source token address")
    destination_token: str = Field(..., description="Destination token address")
    source_amount: float = Field(..., description="Total source amount")
    estimated_destination_amount: float = Field(..., description="Estimated output")
    max_batch_size_eur: float = Field(500.0, description="Max EUR per batch")
    max_slippage_pct: float = Field(2.0, description="Max slippage %")


class AdminEnableRequest(BaseModel):
    """Request to enable/disable DEX service."""
    enabled: bool
    user_id: Optional[str] = None
    reason: Optional[str] = None


class WhitelistRequest(BaseModel):
    """Request to manage whitelist."""
    user_id: str
    action: str = Field(..., description="add or remove")


# Token mapping helper
TOKEN_MAP = {
    "NENO": NENO_ADDRESS,
    "WBNB": WBNB_ADDRESS,
    "BNB": WBNB_ADDRESS,
    "USDT": USDT_ADDRESS,
    "USDC": USDC_ADDRESS,
}


def resolve_token(token: str) -> str:
    """Resolve token symbol to address."""
    if token.startswith("0x"):
        return token
    return TOKEN_MAP.get(token.upper(), token)


# Dependency

def get_service() -> DEXService:
    service = get_dex_service()
    if not service:
        raise HTTPException(status_code=503, detail="DEX service not available")
    return service


# Routes

@router.get("/status")
async def get_dex_status(service: DEXService = Depends(get_service)):
    """Get DEX service status."""
    return await service.get_service_status()


@router.post("/quote")
async def get_swap_quote(
    request: SwapQuoteRequest,
    service: DEXService = Depends(get_service)
):
    """Get swap quote from DEX aggregators."""
    try:
        source_token = resolve_token(request.source_token)
        dest_token = resolve_token(request.destination_token)
        
        # Convert amount to wei
        decimals = TOKEN_DECIMALS.get(source_token.lower(), 18)
        amount_wei = int(request.amount * (10 ** decimals))
        
        quote = await service.get_best_quote(
            source_token=source_token,
            destination_token=dest_token,
            amount_wei=amount_wei
        )
        
        if not quote:
            raise HTTPException(status_code=404, detail="No quote available")
        
        return {
            "quote_id": quote.quote_id,
            "router": quote.router,
            "source_token": source_token,
            "destination_token": dest_token,
            "source_amount": quote.source_amount_decimal,
            "destination_amount": quote.destination_amount_decimal,
            "exchange_rate": quote.exchange_rate,
            "price_impact_pct": quote.price_impact_pct,
            "gas_estimate": {
                "gas": quote.gas_estimate,
                "gas_price_gwei": quote.gas_price_gwei,
                "cost_bnb": quote.estimated_gas_cost_bnb,
                "cost_eur": quote.estimated_gas_cost_eur
            },
            "route_path": quote.route_path,
            "valid_until": quote.valid_until
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quote error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_swap(
    request: SwapExecuteRequest,
    service: DEXService = Depends(get_service)
):
    """Execute a swap (requires live mode enabled)."""
    if not service.is_enabled():
        raise HTTPException(
            status_code=403,
            detail="DEX live mode not enabled. Contact admin."
        )
    
    # TODO: Implement direct swap execution
    raise HTTPException(
        status_code=501,
        detail="Direct swap execution not implemented. Use batch conversion."
    )


@router.get("/conversions")
async def get_conversions(
    status: Optional[str] = None,
    limit: int = Query(20, le=100),
    skip: int = 0,
    service: DEXService = Depends(get_service)
):
    """Get conversion history."""
    query = {}
    if status:
        query["status"] = status
    
    cursor = service.swaps_collection.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    swaps = await cursor.to_list(limit)
    
    return {
        "swaps": swaps,
        "count": len(swaps)
    }


@router.get("/conversion/{swap_id}")
async def get_conversion(
    swap_id: str,
    service: DEXService = Depends(get_service)
):
    """Get specific conversion details."""
    swap = await service.swaps_collection.find_one({"swap_id": swap_id}, {"_id": 0})
    
    if not swap:
        raise HTTPException(status_code=404, detail="Swap not found")
    
    return swap


# Admin Routes

@router.post("/admin/enable")
async def admin_enable_dex(
    request: AdminEnableRequest,
    service: DEXService = Depends(get_service)
):
    """Enable or disable DEX live mode (admin only)."""
    if request.enabled:
        await service.enable_live_mode(request.user_id)
        return {"status": "enabled", "message": "DEX live mode enabled"}
    else:
        await service.disable_live_mode(request.reason)
        return {"status": "disabled", "message": "DEX live mode disabled"}


@router.post("/admin/whitelist")
async def admin_manage_whitelist(
    request: WhitelistRequest,
    service: DEXService = Depends(get_service)
):
    """Manage DEX whitelist (admin only)."""
    if request.action == "add":
        await service.add_to_whitelist(request.user_id)
        return {"status": "added", "user_id": request.user_id}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.get("/admin/config")
async def get_dex_config(service: DEXService = Depends(get_service)):
    """Get DEX configuration (admin only)."""
    config = await service.config_collection.find_one({"config_type": "dex"}, {"_id": 0})
    return config or {}
