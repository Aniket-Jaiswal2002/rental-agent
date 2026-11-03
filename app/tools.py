"""Tool schemas shown to the model, and the code that executes them against SessionState."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import listings
from .profile import ALL_FIELDS, ProfileError, SessionState, plan_update

_NULLABLE = lambda t: {"type": [t, "null"]}

def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    params = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        params["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


TOOLS = [
    _fn("update_profile",
        "Record details the renter gave or changed: only changed fields, full new value (areas/bhk replace the list), null clears. "
        "change_kinds needs new|correction|conflict for each field.",
        {"changes": {"type": "object", "additionalProperties": False, "properties": {
            "budget_max": _NULLABLE("integer"),
            "areas": {"type": ["array", "null"], "items": {"type": "string"}},
            "bhk": {"type": ["array", "null"], "items": {"type": "integer"}},
            "move_in_date": {**_NULLABLE("string"), "description": "YYYY-MM-DD"},
            "commute_destination": _NULLABLE("string"),
            "furnishing": {"enum": ["unfurnished", "semi-furnished", "fully-furnished", None]},
            "pets": _NULLABLE("boolean"),
            "tenant_type": {"enum": ["family", "bachelor", None]},
            "parking": _NULLABLE("boolean")}},
         "change_kinds": {"type": "object", "additionalProperties": {"enum": ["new", "correction", "conflict"]}}},
        ["changes", "change_kinds"]),
    _fn("read_back_profile", "Call when all required fields are filled, before reading the profile back for confirmation.", {}),
    _fn("confirm_profile",
        "Only on the turn right after a read-back, and only if the renter's latest message explicitly confirms it.",
        {"renter_quote": {"type": "string", "description": "confirming words, verbatim from the renter's latest message"}},
        ["renter_quote"]),
    _fn("search_listings", "Search listings with the confirmed profile. Only works after confirmation.", {}),
    _fn("get_listing", "Look up one listing by id, e.g. L012.", {"listing_id": {"type": "string"}}, ["listing_id"]),
    _fn("respond",
        "Your reply. Every turn ends with this call. Shortlist ids must come from the latest search/lookup.",
        {"reply": {"type": "string"},
         "asking_for": {"type": "array", "items": {"enum": ALL_FIELDS}, "description": "profile fields your question asks for"},
         "shortlist": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "properties": {
             "listing_id": {"type": "string"}, "tradeoff": {"type": "string", "description": "one sentence"}},
             "required": ["listing_id", "tradeoff"]}},
         "no_match_notice": {"type": "boolean"}},
        ["reply", "asking_for", "shortlist"]),
]

@dataclass
class TurnContext:
    """Per-turn scratch space: what the renter said, which tools ran, which listing IDs are citable."""
    user_message: str
    tool_log: list[dict] = field(default_factory=list)
    searched: list[dict] = field(default_factory=list)  # search results produced this turn
    fetched_ids: set[str] = field(default_factory=set)  # get_listing hits this turn
    changes: list[dict] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)  # fields the renter contradicted this turn (not applied)

    def citable_ids(self, state: SessionState) -> set[str]:
        ids = set(self.fetched_ids)
        latest = self.searched[-1] if self.searched else state.last_search
        if latest:
            ids |= {r["id"] for r in latest["results"]}
        return ids


def run_tool(name: str, args: dict[str, Any], state: SessionState, ctx: TurnContext) -> dict:
    """Execute one non-terminal tool. Errors come back as {"error": ...} for the model to react to."""
    try:
        if "__invalid_json__" in args:
            raise ProfileError("tool arguments were not valid JSON; try again")
        if name == "update_profile":
            changes = args.get("changes")
            if not isinstance(changes, dict) or not changes:
                raise ProfileError("changes must be a non-empty object")
            kinds = args.get("change_kinds")
            if not isinstance(kinds, dict):
                raise ProfileError("change_kinds is required: one of new/correction/conflict for every field in changes")
            plan = plan_update(state.profile, changes, kinds)
            if plan.errors:
                raise ProfileError("; ".join(plan.errors))  # atomic: nothing applied
            log = state.update_profile(plan.apply, plan.kinds) if plan.apply else []
            ctx.changes += [{**e, "kind": plan.kinds.get(e["field"], "new"), "turn": state.turn} for e in log]
            ctx.conflicts += [f for f in plan.conflicts if f not in ctx.conflicts]
            out = {"applied": log, "unchanged": not log and not plan.conflicts, "missing_required": state.profile.missing_required(),
                   "note": "confirmation reset; read the profile back again before searching" if log else ""}
            if plan.conflicts:
                out["not_applied_conflicts"] = plan.conflicts
                out["instruction"] = ("Ask the renter ONE clarifying question about these fields and put them in asking_for; "
                                      "do not read the profile back until it is resolved.")
            return out
        if name == "read_back_profile":
            if ctx.conflicts:
                raise ProfileError(f"unresolved conflict on {ctx.conflicts}: ask the renter first")
            state.read_back()
            return {"profile": state.snapshot()["profile"], "next": "read this profile back to the renter and ask them to confirm"}
        if name == "confirm_profile":
            state.confirm(str(args.get("renter_quote", "")), ctx.user_message)
            return {"confirmed": True, "next": "call search_listings"}
        if name == "search_listings":
            reason = state.search_gate()
            if reason:
                raise ProfileError(reason)
            result = listings.search_listings(listings.SearchFilters.from_profile(state.profile))
            state.last_search = result
            ctx.searched.append(result)
            return result
        if name == "get_listing":
            listing = listings.get_listing(args.get("listing_id", ""))
            if listing is None:
                return {"error": "not_found", "listing_id": args.get("listing_id"),
                        "note": "no such listing exists; tell the renter plainly, do not guess"}
            ctx.fetched_ids.add(listing["id"])
            return {k: v for k, v in listing.items() if k != "description"} | {"broker_description": listing["description"]}
        return {"error": f"unknown tool {name}"}
    except (ProfileError, KeyError, TypeError) as e:
        return {"error": str(e)}
