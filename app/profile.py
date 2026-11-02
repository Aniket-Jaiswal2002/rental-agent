"""Renter profile (the agent's memory) and the confirmation state machine.

The profile is a Pydantic model updated by the `update_profile` tool, separate from
the raw chat history. `SessionState` wraps it with the flags that gate searching.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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


CORRECTION_CUES = ("actually", "sorry", "meant", "instead", "make it", "change", "wrong", "correction",
                   "rather", "update", "no wait", "nahi", "galat", "badal")


def split_conflicts(profile: RenterProfile, changes: dict[str, Any]) -> tuple[dict, dict]:
    """Separate changes that silently overwrite a different earlier value (conflicts) from the rest.

    Filling an empty field, re-stating the same value, or widening a list (areas/bhk gaining entries)
    is not a conflict.
    """
    ok, conflicts = {}, {}
    for field, new in changes.items():
        old = getattr(profile, field, None)
        if field not in ALL_FIELDS or _is_empty(old) or new is None or new == old:
            ok[field] = new
        elif isinstance(old, list) and isinstance(new, list) and {str(x).lower() for x in old} <= {str(x).lower() for x in new}:
            ok[field] = new
        else:
            conflicts[field] = new
    return ok, conflicts


def has_correction_cue(message: str) -> bool:
    return any(cue in message.lower() for cue in CORRECTION_CUES)


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
        self.ever_read_back = False  # once the renter has seen the profile, any change they make is a correction
        self.last_search: Optional[dict] = None  # latest search_listings result

    # -- profile updates -------------------------------------------------
    def update_profile(self, changes: dict[str, Any]) -> list[dict]:
        new, log = apply_update(self.profile, changes)
        self.profile = new
        if log:
            for entry in log:
                self.changelog.append({**entry, "turn": self.turn})
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
        self.ever_read_back = True

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
