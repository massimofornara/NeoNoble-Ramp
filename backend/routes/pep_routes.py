"""
PEP Screening & Sanctions API — NeoNoble Ramp.

Endpoints for screening individuals against PEP/Sanctions lists
and managing the internal watchlist.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from routes.auth import get_current_user
from services.pep_screening_service import screen_individual, add_to_watchlist, get_screening_history

router = APIRouter(prefix="/pep", tags=["PEP Screening & Sanctions"])


def admin_required(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Accesso admin richiesto")
    return current_user


class ScreenRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    nationality: Optional[str] = ""
    additional_info: Optional[str] = ""


class WatchlistEntry(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(description="PEP, SANCTIONS, ADVERSE_MEDIA")
    severity: str = Field(description="low, medium, high, critical")
    reason: str = Field(min_length=1, max_length=500)
    aliases: Optional[str] = ""


@router.post("/screen")
async def screen_person(req: ScreenRequest, current_user: dict = Depends(admin_required)):
    """Screen an individual against PEP and sanctions lists."""
    result = await screen_individual(
        first_name=req.first_name,
        last_name=req.last_name,
        nationality=req.nationality or "",
        additional_info=req.additional_info or "",
    )
    return result


@router.post("/watchlist")
async def add_watchlist_entry(req: WatchlistEntry, current_user: dict = Depends(admin_required)):
    """Add an individual to the internal watchlist."""
    entry = await add_to_watchlist(
        name=req.name,
        category=req.category,
        severity=req.severity,
        reason=req.reason,
        aliases=req.aliases or "",
    )
    return {"message": f"Aggiunto alla watchlist: {req.name}", "entry": entry}


@router.get("/history")
async def screening_history(current_user: dict = Depends(admin_required)):
    """Get PEP/Sanctions screening history."""
    results = await get_screening_history()
    return {"screenings": results, "total": len(results)}


@router.get("/stats")
async def screening_stats(current_user: dict = Depends(admin_required)):
    """Get aggregate screening statistics."""
    from database.mongodb import get_database
    db = get_database()

    total = await db.pep_screening_log.count_documents({})
    clear = await db.pep_screening_log.count_documents({"status": "CLEAR"})
    review = await db.pep_screening_log.count_documents({"status": "REVIEW"})
    blocked = await db.pep_screening_log.count_documents({"status": "BLOCKED"})
    watchlist_count = await db.pep_watchlist.count_documents({})

    return {
        "total_screenings": total,
        "clear": clear,
        "review": review,
        "blocked": blocked,
        "watchlist_entries": watchlist_count,
        "lists_active": ["OFAC-SDN", "UN-Sanctions", "EU-Sanctions", "Internal-Watchlist", "PEP-Database"],
    }
