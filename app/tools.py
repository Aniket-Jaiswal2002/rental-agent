"""Tool schemas shown to the model, and the code that executes them against SessionState."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import listings
from .profile import ALL_FIELDS, ProfileError, SessionState, plan_update

_NULLABLE = lambda t: {"type": [t, "null"]}

TOOLS = [
    {"type": "function", "function": {
        "name": "update_profile",
        "description": (
            "Record what the renter just told you. Pass only the fields that changed this turn, with their FULL new "
            "value (e.g. areas replaces the whole list), and a change_kind for EACH field: \"new\" (field was empty, or a list "
            "gains entries), \"correction\" (renter clearly replaces a stored value, e.g. \"actually make it 35k\", \"nahi, 35 kar do\", "
            "\"sorry I meant Sector 56\"), or \"conflict\" (renter gave two incompatible values in one turn, or a value that "
            "contradicts a stored one and it is unclear which is meant: NOT applied, you must ask). Use null to clear a field."
        ),
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "changes": {"type": "object", "additionalProperties": False, "properties": {
                "budget_max": {**_NULLABLE("integer"), "description": "Max monthly rent in INR, e.g. 35000"},
                "areas": {"type": ["array", "null"], "items": {"type": "string"},
                          "description": "Sectors/localities, canonical names, e.g. ['Sector 56', 'Golf Course Road']"},
                "bhk": {"type": ["array", "null"], "items": {"type": "integer"}},
                "move_in_date": {**_NULLABLE("string"), "description": "ISO date YYYY-MM-DD"},
                "commute_destination": {**_NULLABLE("string"), "description": "e.g. 'Cyber City'"},
                "furnishing": {"enum": ["unfurnished", "semi-furnished", "fully-furnished", None]},
                "pets": _NULLABLE("boolean"),
                "tenant_type": {"enum": ["family", "bachelor", None]},
                "parking": _NULLABLE("boolean"),
            }},
            "change_kinds": {"type": "object", "description": "field name -> \"new\" | \"correction\" | \"conflict\", one entry per field in changes",
                             "additionalProperties": {"enum": ["new", "correction", "conflict"]}},
        }, "required": ["changes", "change_kinds"]}}},
    {"type": "function", "function": {
        "name": "read_back_profile",
        "description": (
            "Call once all required fields are filled and you are about to read the profile back to the renter for "
            "confirmation. Your reply this turn must then read the profile back and ask them to confirm."
        ),
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "confirm_profile",
        "description": (
            "Call ONLY on the turn right after you read the profile back, and only if the renter's latest message "
            "explicitly confirms it (yes / correct / haan sahi hai). If they change anything, call update_profile instead."
        ),
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "renter_quote": {"type": "string", "description": "The confirming words, copied verbatim from the renter's latest message"},
        }, "required": ["renter_quote"]}}},
    {"type": "function", "function": {
        "name": "search_listings",
        "description": (
            "Search the listings dataset using the confirmed profile as filters. Only works after the renter confirmed. "
            "Returns ranked candidates with flags such as over_budget_by."
        ),
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_listing",
        "description": "Look up one listing by id (e.g. L012). Use it whenever the renter mentions a listing id.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "listing_id": {"type": "string"}}, "required": ["listing_id"]}}},
    {"type": "function", "function": {
        "name": "respond",
        "description": "Your reply to the renter. Every turn ends with exactly this call.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "reply": {"type": "string", "description": "What you say to the renter, in English, 1-3 short spoken sentences. No listing prices/addresses here."},
            "asking_for": {"type": "array", "items": {"enum": ALL_FIELDS},
                           "description": "Profile fields your question asks the renter for (empty if you ask nothing)"},
            "shortlist": {"type": "array", "maxItems": 3, "items": {
                "type": "object", "additionalProperties": False, "properties": {
                    "listing_id": {"type": "string"},
                    "tradeoff": {"type": "string", "description": "One sentence on this listing's trade-offs vs the renter's wishes"}},
                "required": ["listing_id", "tradeoff"]},
                "description": "Listings to show. IDs must come from the latest search_listings/get_listing result."},
            "no_match_notice": {"type": "boolean", "description": "true if the search found nothing and you are telling the renter so"},
        }, "required": ["reply", "asking_for", "shortlist"]}}},
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
