from datetime import date

import pytest

from app.profile import ProfileError, RenterProfile, SessionState, apply_update


def test_apply_update_returns_changelog_and_new_profile():
    p, log = apply_update(RenterProfile(), {"budget_max": 30000, "bhk": [2]})
    assert p.budget_max == 30000 and p.bhk == [2]
    assert log == [{"field": "budget_max", "old": None, "new": 30000}, {"field": "bhk", "old": [], "new": [2]}]


def test_budget_change_is_logged_with_old_and_new():
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000})
    p2, log = apply_update(p, {"budget_max": 35000})
    assert p2.budget_max == 35000
    assert log == [{"field": "budget_max", "old": 30000, "new": 35000}]


def test_noop_update_has_empty_changelog():
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000})
    _, log = apply_update(p, {"budget_max": 30000})
    assert log == []


def test_string_numbers_are_coerced_and_dates_parsed():
    p, _ = apply_update(RenterProfile(), {"budget_max": "25000", "move_in_date": "2026-12-01"})
    assert p.budget_max == 25000 and p.move_in_date == date(2026, 12, 1)


def test_invalid_value_rejected_and_profile_untouched():
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000})
    with pytest.raises(ProfileError):
        apply_update(p, {"budget_max": "25k", "bhk": [2]})
    assert p.budget_max == 30000 and p.bhk == []


def test_unknown_field_rejected():
    with pytest.raises(ProfileError):
        apply_update(RenterProfile(), {"favourite_colour": "blue"})


def test_none_clears_a_field_and_lists():
    p, _ = apply_update(RenterProfile(), {"pets": True, "areas": ["Sector 56"]})
    p2, log = apply_update(p, {"pets": None, "areas": None})
    assert p2.pets is None and p2.areas == []
    assert {e["field"] for e in log} == {"pets", "areas"}


def test_split_conflicts_flags_silent_overwrites_only():
    from app.profile import has_correction_cue, split_conflicts
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000, "areas": ["Sector 56"]})
    ok, bad = split_conflicts(p, {"budget_max": 20000, "areas": ["Sector 56", "Sector 57"], "bhk": [2], "pets": True})
    assert bad == {"budget_max": 20000}  # different value for a filled field
    assert set(ok) == {"areas", "bhk", "pets"}  # widening a list and filling empty fields are fine
    assert split_conflicts(p, {"budget_max": 30000})[1] == {}  # re-stating is fine
    assert has_correction_cue("Sorry, I meant Sector 56") and not has_correction_cue("My budget is 20000")


def test_missing_required():
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000, "areas": ["Sector 56"]})
    assert p.missing_required() == ["bhk", "move_in_date", "commute_destination"]
    p, _ = apply_update(p, {"bhk": [2], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"})
    assert p.missing_required() == []
    # optional fields never count as missing
    assert "pets" not in p.missing_required()
