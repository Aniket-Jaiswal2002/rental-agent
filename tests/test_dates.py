"""Relative move-in dates resolve deterministically against a fixed 'today'."""
from datetime import date

import pytest

from app.dates import resolve_date
from app.profile import RenterProfile, apply_update, plan_update

TODAY = date(2026, 11, 3)


@pytest.mark.parametrize("phrase, expected", [
    ("2026-12-01", date(2026, 12, 1)),
    ("within a week", date(2026, 11, 10)),
    ("ready to move in within a week", date(2026, 11, 10)),
    ("ek hafte mein", date(2026, 11, 10)),
    ("next week", date(2026, 11, 10)),
    ("immediately", TODAY),
    ("asap", TODAY),
    ("tomorrow", date(2026, 11, 4)),
    ("in 10 days", date(2026, 11, 13)),
    ("within two weeks", date(2026, 11, 17)),
    ("3 mahine mein", date(2027, 2, 3)),
    ("next month", date(2026, 12, 1)),
    ("agle mahine", date(2026, 12, 1)),
    ("end of the month", date(2026, 11, 30)),
    ("1st December", date(2026, 12, 1)),
    ("December 15", date(2026, 12, 15)),
    ("1 March", date(2027, 3, 1)),  # already past this year -> next year
    ("15 jan 2027", date(2027, 1, 15)),
])
def test_resolve_date(phrase, expected):
    assert resolve_date(phrase, TODAY) == expected


@pytest.mark.parametrize("phrase", ["whenever", "soonish maybe", "31 February"])
def test_unparseable_dates_return_none(phrase):
    assert resolve_date(phrase, TODAY) is None


def test_profile_resolves_relative_phrase_using_pinned_today(monkeypatch):
    monkeypatch.setenv("TODAY_OVERRIDE", "2026-11-03")
    p, log = apply_update(RenterProfile(), {"move_in_date": "within a week"})
    assert p.move_in_date == date(2026, 11, 10) and log[0]["new"] == "2026-11-10"


def test_profile_rejects_date_it_cannot_understand(monkeypatch):
    from app.profile import ProfileError
    monkeypatch.setenv("TODAY_OVERRIDE", "2026-11-03")
    with pytest.raises(ProfileError):
        apply_update(RenterProfile(), {"move_in_date": "whenever"})


def test_city_level_area_is_not_stored_and_must_be_asked():
    plan = plan_update(RenterProfile(), {"areas": ["Gurgaon"], "bhk": [5]}, {"areas": "new", "bhk": "new"})
    assert plan.conflicts == ["areas"] and "areas" not in plan.apply and plan.apply == {"bhk": [5]}
    assert "whole city" in plan.notes[0]


def test_city_name_alongside_a_sector_is_dropped():
    p, _ = apply_update(RenterProfile(), {"areas": ["Sector 56", "Gurugram"]})
    assert p.areas == ["Sector 56"]
