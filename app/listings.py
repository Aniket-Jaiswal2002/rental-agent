"""The listings dataset and the deterministic search tool.

Hard filters decide what can be shown at all; soft criteria only rank and annotate.
Every number the renter hears about a listing is rendered from this data (see render()).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

from .config import LISTINGS_PATH
from .profile import RenterProfile

BUDGET_TOLERANCE = 0.10  # listings up to 10% over budget are shown, flagged as over_budget_by
MOVE_IN_SLACK_DAYS = 15  # listings that free up up to 15 days late are shown, flagged
SEARCH_LIMIT = 5


@lru_cache(maxsize=1)
def load_listings() -> dict[str, dict]:
    data = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))
    assert data.get("SYNTHETIC") is True, "listings.json must be labelled SYNTHETIC"
    return {l["id"]: l for l in data["listings"]}


def get_listing(listing_id: str) -> Optional[dict]:
    return load_listings().get(str(listing_id).strip().upper())


def known_localities() -> list[str]:
    """Canonical sector and locality names, so the agent can normalise what the renter says."""
    names = {l["sector"] for l in load_listings().values()} | {l["area"] for l in load_listings().values()}
    return sorted(names)


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\bsec\.?\s*(\d)", r"sector \1", s)
    s = re.sub(r"\bext\.?\b", "extension", s)
    return " ".join(s.split())


def _commute_key(destination: Optional[str]) -> Optional[str]:
    d = _norm(destination or "")
    if "cyber" in d:
        return "distance_cyber_city_km"
    if "golf course road" in d or d in ("gcr", "golf course rd"):
        return "distance_golf_course_road_km"
    return None


@dataclass
class SearchFilters:
    budget_max: Optional[int] = None
    areas: list[str] = field(default_factory=list)
    bhk: list[int] = field(default_factory=list)
    move_in_date: Optional[date] = None
    commute_destination: Optional[str] = None
    furnishing: Optional[str] = None
    pets: Optional[bool] = None
    tenant_type: Optional[str] = None
    parking: Optional[bool] = None

    @classmethod
    def from_profile(cls, p: RenterProfile) -> "SearchFilters":
        return cls(**p.model_dump())


def _hard_checks(l: dict, f: SearchFilters) -> dict[str, bool]:
    wanted_areas = {_norm(a) for a in f.areas}
    return {
        "bhk": not f.bhk or l["bhk"] in f.bhk,
        "budget": f.budget_max is None or l["rent"] <= f.budget_max * (1 + BUDGET_TOLERANCE),
        "area": not wanted_areas or _norm(l["sector"]) in wanted_areas or _norm(l["area"]) in wanted_areas,
        "move_in": f.move_in_date is None
        or date.fromisoformat(l["available_from"]) <= f.move_in_date + timedelta(days=MOVE_IN_SLACK_DAYS),
        "pets": not f.pets or l["pets_allowed"],
        "tenant_type": f.tenant_type is None or l["tenant_preference"] in ("any", f.tenant_type),
        "parking": not f.parking or l["parking"],
    }


def search_listings(f: SearchFilters, limit: int = SEARCH_LIMIT) -> dict:
    """Return up to `limit` ranked matches, plus diagnostics when nothing matches."""
    listings = list(load_listings().values())
    commute_field = _commute_key(f.commute_destination)
    checks = {l["id"]: _hard_checks(l, f) for l in listings}
    matches = [l for l in listings if all(checks[l["id"]].values())]

    def annotate(l: dict) -> dict:
        out = {k: l[k] for k in ("id", "sector", "area", "bhk", "rent", "deposit", "furnishing",
                                 "available_from", "pets_allowed", "tenant_preference", "parking")}
        out["distance_cyber_city_km"] = l["distance_cyber_city_km"]
        out["distance_golf_course_road_km"] = l["distance_golf_course_road_km"]
        out["broker_description"] = l["description"]
        out["over_budget_by"] = max(0, l["rent"] - f.budget_max) if f.budget_max else 0
        late = (date.fromisoformat(l["available_from"]) - f.move_in_date).days if f.move_in_date else 0
        out["available_days_after_move_in"] = max(0, late)
        out["furnishing_mismatch"] = bool(f.furnishing and l["furnishing"] != f.furnishing)
        out["commute_km"] = l[commute_field] if commute_field else None
        return out

    ranked = sorted(
        (annotate(l) for l in matches),
        key=lambda a: (a["over_budget_by"] > 0, a["available_days_after_move_in"] > 0,
                       a["furnishing_mismatch"], a["commute_km"] if a["commute_km"] is not None else 0, a["rent"]),
    )
    result: dict = {
        "total_matches": len(ranked),
        "results": ranked[:limit],
        "commute_distance_available": commute_field is not None,
    }
    if not ranked:
        result["no_matches"] = True
        # How many listings satisfy each constraint on its own: tells the renter what to loosen.
        result["passing_each_constraint_alone"] = {
            name: sum(c[name] for c in checks.values()) for name in next(iter(checks.values()))
        }
    return result


def render(listing_id: str, tradeoff: str = "") -> dict:
    """The only way listing facts reach the renter: copied from the dataset, never from the model."""
    l = load_listings()[listing_id]
    return {
        "id": l["id"],
        "title": f"{l['bhk']} BHK, {l['sector']} ({l['area']})",
        "rent": l["rent"],
        "deposit": l["deposit"],
        "furnishing": l["furnishing"],
        "available_from": l["available_from"],
        "pets_allowed": l["pets_allowed"],
        "tenant_preference": l["tenant_preference"],
        "parking": l["parking"],
        "distance_cyber_city_km": l["distance_cyber_city_km"],
        "distance_golf_course_road_km": l["distance_golf_course_road_km"],
        "tradeoff": tradeoff,
    }


def format_card(r: dict) -> str:
    return (f"{r['id']} · {r['title']} · ₹{r['rent']:,}/mo (deposit ₹{r['deposit']:,}) · {r['furnishing']} · "
            f"from {r['available_from']} — {r['tradeoff']}")
