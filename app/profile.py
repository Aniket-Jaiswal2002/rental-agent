"""Renter profile (the agent's memory) and the confirmation state machine.

The profile is a Pydantic model updated by the `update_profile` tool, separate from
the raw chat history. `SessionState` wraps it with the flags that gate searching.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import today
from .dates import resolve_date

REQUIRED_FIELDS = ["budget_max", "areas", "bhk", "move_in_date", "commute_destination"]
OPTIONAL_FIELDS = ["furnishing", "pets", "tenant_type", "parking"]
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS


class RenterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_max: Optional[int] = Field(None, gt=0, description="Max monthly rent, INR")
    areas: list[str] = Field(default_factory=list, description="Preferred sectors/localities")
    bhk: list[int] = Field(default_factory=list, description="Acceptable BHK counts")
    move_in_date: Optional[date] = None
    commute_destination: Optional[str] = None
    furnishing: Optional[Literal["unfurnished", "semi-furnished", "fully-furnished"]] = None
    pets: Optional[bool] = None
    tenant_type: Optional[Literal["family", "bachelor"]] = None
    parking: Optional[bool] = None

    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if _is_empty(getattr(self, f))]


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == ""


class ProfileError(ValueError):
    pass


# The whole city is not a usable "area": searching it would match everything.
CITY_LEVEL = {"gurgaon", "gurugram", "ggn", "gurgaon city", "gurugram city", "delhi ncr", "ncr", "anywhere in gurgaon"}


def _drop_city_level(areas: list) -> list:
    kept = [a for a in areas if " ".join(str(a).lower().split()) not in CITY_LEVEL]
    if not kept:
        raise ProfileError(f"{areas} is the whole city, not an area: leave areas empty and ask which sectors or "
                           f"localities they prefer (asking_for: areas)")
    return kept


def apply_update(profile: RenterProfile, changes: dict[str, Any]) -> tuple[RenterProfile, list[dict]]:
    """Return (new_profile, changelog). `changes` maps field -> new value (None clears it).

    Raises ProfileError for unknown fields or invalid values; the old profile is untouched.
    """
    unknown = [k for k in changes if k not in ALL_FIELDS]
    if unknown:
        raise ProfileError(f"unknown profile field(s): {unknown}; valid fields: {ALL_FIELDS}")
    merged = profile.model_dump()
    for key, value in changes.items():
        if key in ("areas", "bhk") and value is None:
            value = []
        if key == "areas" and value:
            value = _drop_city_level(value)
        if key == "move_in_date" and isinstance(value, str) and value.strip():
            resolved = resolve_date(value, today())
            if resolved is None:
                raise ProfileError(f"could not understand move-in date {value!r}; ask the renter for a date")
            value = resolved
        merged[key] = value
    try:
        new = RenterProfile.model_validate(merged)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise ProfileError(f"invalid value: {problems}") from None

    log = []
    for field in changes:
        old_v, new_v = getattr(profile, field), getattr(new, field)
        if old_v != new_v:
            log.append({"field": field, "old": _plain(old_v), "new": _plain(new_v)})
    return new, log


def _plain(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v


CHANGE_KINDS = ("new", "correction", "conflict")


class UpdatePlan:
    """What update_profile will do, decided from the model-declared change_kind of each field."""

    def __init__(self) -> None:
        self.apply: dict[str, Any] = {}  # field -> value to write
        self.kinds: dict[str, str] = {}  # field -> "new" | "correction" for applied fields
        self.conflicts: list[str] = []  # fields NOT applied; the renter must be asked
        self.notes: list[str] = []
        self.errors: list[str] = []


def plan_update(profile: RenterProfile, changes: dict[str, Any], kinds: dict[str, str]) -> UpdatePlan:
    """Enforce the change_kind contract:

    new        -> the field is empty (or the value only widens a list). Applied.
    correction -> the renter replaces a stored value. Applied; the reply must say old -> new.
    conflict   -> incompatible values or unclear which is meant. NOT applied; the agent must ask.
    """
    plan = UpdatePlan()
    for field, value in changes.items():
        kind = kinds.get(field)
        if field not in ALL_FIELDS:
            plan.errors.append(f"unknown profile field {field!r}")
        elif kind not in CHANGE_KINDS:
            plan.errors.append(f"{field}: change_kind must be one of {list(CHANGE_KINDS)}")
        elif kind == "conflict":
            plan.conflicts.append(field)
        elif field == "areas" and value and all(" ".join(str(a).lower().split()) in CITY_LEVEL for a in value):
            plan.conflicts.append(field)  # not applied; the agent must ask, exactly as for a conflict
            plan.notes.append(f"{value} is the whole city, not an area: ask which sectors or localities they prefer")
        else:
            old = getattr(profile, field)
            try:
                _, log = apply_update(profile, {field: value})
            except ProfileError as e:
                plan.errors.append(f"{field}: {e}")
                continue
            if not log:
                continue  # same value restated: nothing to do
            widens = isinstance(old, list) and {str(x).lower() for x in old} <= {str(x).lower() for x in (value or [])}
            if kind == "new" and not _is_empty(old) and not widens:
                plan.errors.append(f"{field} already holds {_plain(old)!r}; if the renter is replacing it use "
                                   f"change_kind 'correction', if it contradicts or is unclear use 'conflict'")
            elif kind == "correction" and _is_empty(old):
                plan.errors.append(f"{field} has no stored value to correct; use change_kind 'new'")
            else:
                plan.apply[field], plan.kinds[field] = value, kind
    unknown_kinds = [f for f in kinds if f not in changes]
    if unknown_kinds:
        plan.errors.append(f"change_kinds names fields not in changes: {unknown_kinds}")
    return plan

class SessionState:
    """Profile + confirmation flags + the bookkeeping that makes the gate structural.

    Flow: read_back_profile() -> awaiting_confirmation. On the NEXT renter turn,
    confirm_profile() -> confirmed. Any real profile change clears both flags and the
    stale search results.
    """

    def __init__(self) -> None:
        self.profile = RenterProfile()
        self.changelog: list[dict] = []  # every change ever applied, with the turn number
        self.awaiting_confirmation = False
        self.confirmed = False
        self.turn = 0  # renter turns so far (1-based while a turn is in flight)
        self.read_back_turn: Optional[int] = None  # assistant turn in which read-back happened
        self.last_search: Optional[dict] = None  # latest search_listings result

    # -- profile updates -------------------------------------------------
    def update_profile(self, changes: dict[str, Any], kinds: Optional[dict[str, str]] = None) -> list[dict]:
        new, log = apply_update(self.profile, changes)
        self.profile = new
        if log:
            for entry in log:
                self.changelog.append({**entry, "kind": (kinds or {}).get(entry["field"], "new"), "turn": self.turn})
            self.awaiting_confirmation = False
            self.confirmed = False
            self.read_back_turn = None
            self.last_search = None  # results were for the old profile
        return log

    # -- confirmation gate -----------------------------------------------
    def read_back(self) -> None:
        missing = self.profile.missing_required()
        if missing:
            raise ProfileError(f"cannot read back yet, still missing required fields: {missing}")
        self.awaiting_confirmation = True
        self.confirmed = False
        self.read_back_turn = self.turn

    def confirm(self, renter_quote: str, last_user_message: str) -> None:
        if not self.awaiting_confirmation or self.read_back_turn is None:
            raise ProfileError("no read-back is pending; call read_back_profile first and wait for the renter's reply")
        if self.read_back_turn != self.turn - 1:
            raise ProfileError("the read-back must have happened on your immediately preceding turn; read it back again")
        if not _contains(last_user_message, renter_quote):
            raise ProfileError("renter_quote must be copied verbatim from the renter's latest message")
        self.awaiting_confirmation = False
        self.confirmed = True

    def search_gate(self) -> Optional[str]:
        """None if searching is allowed, else the reason it isn't."""
        missing = self.profile.missing_required()
        if missing:
            return f"cannot search: required fields still missing: {missing}"
        if not self.confirmed:
            return "cannot search: the renter has not confirmed the current profile (read it back and wait for a yes)"
        return None

    def snapshot(self) -> dict:
        p = self.profile.model_dump(mode="json")
        return {
            "profile": p,
            "missing_required": self.profile.missing_required(),
            "awaiting_confirmation": self.awaiting_confirmation,
            "confirmed": self.confirmed,
            "changelog": list(self.changelog),
        }


def _contains(haystack: str, needle: str) -> bool:
    norm = lambda s: " ".join(s.lower().split())
    return bool(norm(needle)) and norm(needle) in norm(haystack)
