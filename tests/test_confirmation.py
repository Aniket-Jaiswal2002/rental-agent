"""The structural confirmation gate: read-back -> (next renter turn) confirm -> search."""
import pytest

from app.profile import ProfileError, SessionState

FULL = {"budget_max": 30000, "areas": ["Sector 56"], "bhk": [2], "move_in_date": "2026-12-01",
        "commute_destination": "Cyber City"}


def filled_state() -> SessionState:
    s = SessionState()
    s.turn = 1
    s.update_profile(FULL)
    return s


def test_read_back_refused_while_fields_missing():
    s = SessionState()
    s.turn = 1
    s.update_profile({"budget_max": 30000})
    with pytest.raises(ProfileError):
        s.read_back()
    assert not s.awaiting_confirmation


def test_confirm_without_read_back_is_rejected():
    s = filled_state()
    s.turn = 2
    with pytest.raises(ProfileError):
        s.confirm("yes", "yes")
    assert not s.confirmed


def test_confirm_in_same_turn_as_read_back_is_rejected():
    s = filled_state()
    s.read_back()  # read back on turn 1 ...
    with pytest.raises(ProfileError):
        s.confirm("yes", "yes")  # ... cannot be confirmed within turn 1
    assert not s.confirmed


def test_confirm_must_be_on_the_immediately_following_turn():
    s = filled_state()
    s.read_back()
    s.turn = 3  # a turn went by without confirming
    with pytest.raises(ProfileError):
        s.confirm("yes", "yes")


def test_confirm_quote_must_come_from_renter_message():
    s = filled_state()
    s.read_back()
    s.turn = 2
    with pytest.raises(ProfileError):
        s.confirm("yes, that is right", "hmm, let me think")
    assert not s.confirmed
    s.confirm("Yes  that's RIGHT", "ok. yes that's right!")  # case/whitespace-insensitive
    assert s.confirmed and not s.awaiting_confirmation


def test_search_gate_requires_confirmation():
    s = filled_state()
    assert "not confirmed" in s.search_gate()
    s.read_back()
    assert s.search_gate() is not None  # read back but not yet confirmed
    s.turn = 2
    s.confirm("yes", "yes")
    assert s.search_gate() is None


def test_any_profile_change_clears_both_flags_and_stale_search():
    s = filled_state()
    s.read_back()
    s.update_profile({"budget_max": 35000})  # change while awaiting confirmation
    assert not s.awaiting_confirmation and not s.confirmed

    s.read_back()
    s.turn = 2
    s.confirm("yes", "yes")
    s.last_search = {"results": []}
    s.turn = 3
    s.update_profile({"budget_max": 40000})  # change after confirming
    assert not s.confirmed and not s.awaiting_confirmation
    assert s.last_search is None
    assert s.search_gate() is not None


def test_noop_update_does_not_reset_confirmation():
    s = filled_state()
    s.read_back()
    s.turn = 2
    s.confirm("yes", "yes")
    s.update_profile({"budget_max": 30000})  # same value
    assert s.confirmed
