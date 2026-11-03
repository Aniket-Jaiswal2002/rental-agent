"""Offline smoke test of the eval harness: a scripted 'perfect' agent must pass every check,
and a deliberately sloppy one must fail the right ones."""
import json
from pathlib import Path

from evals.checks import run_checks
from evals.run import play
from test_grounding import FakeLLM, respond

CASES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (Path(__file__).parent.parent / "evals" / "cases").glob("*.json")}
FULL = {"budget_max": 30000, "areas": ["Sector 56"], "bhk": [2], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"}


def test_twelve_cases_with_unique_ids():
    assert len(CASES) == 12 and len({c["id"] for c in CASES.values()}) == 12


def test_perfect_agent_passes_case_12_city_area_5bhk_relative_date():
    upd = lambda changes, kinds: ("update_profile", {"changes": changes, "change_kinds": kinds})
    llm = FakeLLM([
        [upd({"areas": ["Gurgaon"], "bhk": [5], "move_in_date": "within a week"}, {"areas": "new", "bhk": "new", "move_in_date": "new"}),
         respond("Which sectors, and what budget?", asking_for=["areas", "budget_max"])],
        [upd({"budget_max": 60000}, {"budget_max": "new"}), respond("Which sectors, and where do you work?", asking_for=["areas", "commute_destination"])],
        [upd({"areas": ["Sector 54", "Sector 56"], "commute_destination": "Cyber City"}, {"areas": "new", "commute_destination": "new"})],
        [("confirm_profile", {"renter_quote": "Yes, that's right."})],
        [respond("No 5 BHK flats match in those sectors; could 4 BHK work?", no_match=True)],
    ])
    case = CASES["12_city_level_area_5bhk_relative_date"]
    turns = play(case, llm)
    results = run_checks(case, turns)
    assert not any(results.values()), results
    assert turns[0].result.state["profile"]["areas"] == [] and turns[-1].result.state["profile"]["move_in_date"] == "2026-11-09"


def test_perfect_agent_passes_case_07():
    llm = FakeLLM([
        [("update_profile", {"changes": FULL, "change_kinds": dict.fromkeys(FULL, "new")})],  # code reads back
        [("confirm_profile", {"renter_quote": "Yes, that's right."})],  # code searches
        [respond("Here is the best match.", shortlist=[{"listing_id": "L021", "tradeoff": "Fits your budget."}])],
    ])
    case = CASES["07_everything_in_one_sentence"]
    results = run_checks(case, play(case, llm))
    assert not any(results.values()), results


def test_no_match_case_passes_only_when_agent_says_so():
    case = CASES["05_no_match"]
    changes = {"budget_max": 20000, "areas": ["Sector 54"], "bhk": [4], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"}
    llm = FakeLLM([
        [("update_profile", {"changes": changes, "change_kinds": dict.fromkeys(changes, "new")})],
        [("confirm_profile", {"renter_quote": "Yes, that's right."})],
        [respond("Nothing matches that, sorry.", no_match=True)],
    ])
    assert not any(run_checks(case, play(case, llm)).values())


def test_sloppy_agent_is_caught():
    """Agent that never asks about the missing fields and just chats."""
    case = CASES["01_vague_renter"]
    llm = FakeLLM([[respond("Tell me more!")]] * 20)
    results = run_checks(case, play(case, llm))
    assert results["a_asked_before_search"] and results["b_final_profile"] and results["e_case_specific"]
