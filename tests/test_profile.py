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


def test_plan_update_new_correction_conflict_contract():
    from app.profile import plan_update
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000, "areas": ["Sector 56"]})

    # new: fills an empty field, or widens a list
    plan = plan_update(p, {"bhk": [2], "areas": ["Sector 56", "Sector 57"]}, {"bhk": "new", "areas": "new"})
    assert not plan.errors and set(plan.apply) == {"bhk", "areas"}

    # correction: replaces a stored value
    plan = plan_update(p, {"budget_max": 35000}, {"budget_max": "correction"})
    assert not plan.errors and plan.apply == {"budget_max": 35000} and plan.kinds == {"budget_max": "correction"}

    # conflict: never applied, reported for a clarifying question
    plan = plan_update(p, {"budget_max": 20000}, {"budget_max": "conflict"})
    assert plan.conflicts == ["budget_max"] and plan.apply == {} and not plan.errors


def test_plan_update_rejects_mislabelled_changes():
    from app.profile import plan_update
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000})
    assert plan_update(p, {"budget_max": 20000}, {"budget_max": "new"}).errors  # silent overwrite labelled 'new'
    assert plan_update(p, {"bhk": [2]}, {"bhk": "correction"}).errors  # nothing stored to correct
    assert plan_update(p, {"bhk": [2]}, {}).errors  # missing change_kind
    assert plan_update(p, {"bhk": [2]}, {"bhk": "maybe"}).errors  # invalid change_kind
    assert not plan_update(p, {"budget_max": 30000}, {"budget_max": "new"}).errors  # restating is fine


def test_missing_required():
    p, _ = apply_update(RenterProfile(), {"budget_max": 30000, "areas": ["Sector 56"]})
    assert p.missing_required() == ["bhk", "move_in_date", "commute_destination"]
    p, _ = apply_update(p, {"bhk": [2], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"})
    assert p.missing_required() == []
    # optional fields never count as missing
    assert "pets" not in p.missing_required()
