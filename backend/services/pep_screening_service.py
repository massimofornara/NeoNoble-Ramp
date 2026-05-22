"""
PEP Screening & Sanctions List Service — NeoNoble Ramp.

Checks individuals against:
- Politically Exposed Persons (PEP) lists
- International sanctions lists (OFAC, EU, UN)
- Adverse media signals

Uses an internal screening database seeded with known PEP/Sanctions patterns.
Production deployment would connect to real-time providers (Dow Jones, Refinitiv, etc.)
"""

import re
from datetime import datetime, timezone
import uuid

from database.mongodb import get_database

# Sanctions/PEP patterns for demo screening
SANCTIONS_PATTERNS = [
    {"pattern": r"\b(kim jong|putin|lukashenko|maduro|assad|khamenei)\b", "list": "OFAC-SDN", "severity": "critical"},
    {"pattern": r"\b(hezbollah|hamas|al.?qaeda|isis|isil|taliban)\b", "list": "UN-Sanctions", "severity": "critical"},
    {"pattern": r"\b(north korea|dprk|syria|iran|cuba|crimea)\b", "list": "EU-Sanctions-Countries", "severity": "high"},
]

PEP_TITLES = [
    "president", "prime minister", "minister", "senator", "congressman",
    "governor", "mayor", "ambassador", "judge", "general", "admiral",
    "director of central bank", "ceo of state company",
]


async def screen_individual(first_name: str, last_name: str, nationality: str = "", additional_info: str = "") -> dict:
    """Screen an individual against PEP and sanctions lists."""
    db = get_database()
    full_name = f"{first_name} {last_name}".strip().lower()
    search_text = f"{full_name} {nationality} {additional_info}".lower()

    hits = []
    risk_score = 0

    # Sanctions check
    for s in SANCTIONS_PATTERNS:
        if re.search(s["pattern"], search_text, re.IGNORECASE):
            hits.append({
                "type": "SANCTIONS",
                "list": s["list"],
                "severity": s["severity"],
                "match": s["pattern"],
            })
            risk_score += 80 if s["severity"] == "critical" else 50

    # PEP check (title-based heuristic)
    for title in PEP_TITLES:
        if title in search_text:
            hits.append({
                "type": "PEP",
                "category": "Government Official",
                "match": title,
                "severity": "medium",
            })
            risk_score += 30
            break

    # High-risk country check
    high_risk_countries = ["iran", "north korea", "syria", "cuba", "myanmar", "afghanistan", "yemen", "libya", "somalia", "south sudan"]
    for country in high_risk_countries:
        if country in search_text:
            hits.append({
                "type": "HIGH_RISK_COUNTRY",
                "country": country,
                "severity": "high",
            })
            risk_score += 25
            break

    # Check internal watchlist from DB
    db_match = await db.pep_watchlist.find_one(
        {"$or": [
            {"name": {"$regex": re.escape(full_name), "$options": "i"}},
            {"aliases": {"$regex": re.escape(full_name), "$options": "i"}},
        ]},
        {"_id": 0},
    )
    if db_match:
        hits.append({
            "type": db_match.get("category", "WATCHLIST"),
            "list": "Internal-Watchlist",
            "severity": db_match.get("severity", "high"),
            "details": db_match.get("reason", ""),
        })
        risk_score += 60

    risk_score = min(risk_score, 100)
    status = "CLEAR" if risk_score == 0 else "REVIEW" if risk_score < 50 else "BLOCKED"

    result = {
        "id": str(uuid.uuid4()),
        "screened_name": f"{first_name} {last_name}",
        "nationality": nationality,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "risk_score": risk_score,
        "status": status,
        "hits": hits,
        "hit_count": len(hits),
        "lists_checked": ["OFAC-SDN", "UN-Sanctions", "EU-Sanctions", "Internal-Watchlist", "PEP-Database"],
    }

    # Log the screening
    await db.pep_screening_log.insert_one({
        "_id": result["id"],
        **result,
    })

    return result


async def add_to_watchlist(name: str, category: str, severity: str, reason: str, aliases: str = "") -> dict:
    """Add an individual to the internal PEP/sanctions watchlist."""
    db = get_database()
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "category": category,
        "severity": severity,
        "reason": reason,
        "aliases": aliases,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.pep_watchlist.insert_one({"_id": entry["id"], **entry})
    return entry


async def get_screening_history(user_id: str = None, limit: int = 50) -> list:
    """Get screening history, optionally filtered by user."""
    db = get_database()
    query = {"user_id": user_id} if user_id else {}
    results = await db.pep_screening_log.find(query, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return results
