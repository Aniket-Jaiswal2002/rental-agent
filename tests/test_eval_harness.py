"""Offline smoke test of the eval harness: a scripted 'perfect' agent must pass every check,
and a deliberately sloppy one must fail the right ones."""
import json
from pathlib import Path

from evals.checks import run_checks
from evals.run import play
from test_grounding import FakeLLM, respond

CASES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (Path(__file__).parent.parent / "evals" / "cases").glob("*.json")}
FULL = {"budget_max": 30000, "areas": ["Sector 56"], "bhk": [2], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"}


def test_eleven_cases_with_unique_ids():
    assert len(CASES) == 11 and len({c["id"] for c in CASES.values()}) == 11


def test_perfect_agent_passes_case_07():
    llm = FakeLLM([
        [("update_profile", {"changes": FULL, "change_kinds": dict.fromkeys(FULL, "new")})], [("read_back_profile", {})], [respond("Confirm 2 BHK Sector 56?")],
        [("confirm_profile", {"renter_quote": "Yes, that's right."})], [("search_listings", {})],
        [respond("Here is the best match.", shortlist=[{"listing_id": "L021", "tradeoff": "Fits your budget."}])],
    ])
    case = CASES["07_everything_in_one_sentence"]
    results = run_checks(case, play(case, llm))
    assert not any(results.values()), results


def test_no_match_case_passes_only_when_agent_says_so():
    case = CASES["05_no_match"]
    changes = {"budget_max": 20000, "areas": ["Sector 54"], "bhk": [4], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"}
    llm = FakeLLM([
        [("update_profile", {"changes": changes, "change_kinds": dict.fromkeys(changes, "new")})], [("read_back_profile", {})], [respond("Confirm?")],
        [("confirm_profile", {"renter_quote": "Yes, that's right."})], [("search_listings", {})],
        [respond("Nothing matches that, sorry.", no_match=True)],
    ])
    assert not any(run_checks(case, play(case, llm)).values())


def test_sloppy_agent_is_caught():
    """Agent that never asks about the missing fields and just chats."""
    case = CASES["01_vague_renter"]
    llm = FakeLLM([[respond("Tell me more!")]] * 20)
    results = run_checks(case, play(case, llm))
    assert results["a_asked_before_search"] and results["b_final_profile"] and results["e_case_specific"]
