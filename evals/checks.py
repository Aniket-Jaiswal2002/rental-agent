"""Deterministic eval checks. Nothing here uses an LLM judge or pattern-matches model prose.

Everything is computed from structured data: the tool log, the per-turn `asking_for` field, the
profile snapshots, the shortlist (listing ids) and the dataset in data/listings.json.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.agent import TurnResult
from app.listings import load_listings, render
from app.profile import REQUIRED_FIELDS


@dataclass
class TurnRecord:
    script_idx: int | None  # 1-based index of the scripted renter line; None for harness nudges
    user: str
    result: TurnResult


CHECKS = ["a_asked_before_search", "b_final_profile", "c_grounding", "d_no_match", "e_case_specific", "f_no_fallback"]


def _ok_searches(t: TurnRecord) -> list[dict]:
    return [c for c in t.result.tool_log if c["name"] == "search_listings" and "error" not in c["result"]]


def _norm_list(v):
    return sorted(str(x).lower() for x in v) if isinstance(v, list) else v


# --- (a) asked for every missing required field before searching ---------------------------------
def check_a(case: dict, turns: list[TurnRecord]) -> list[str]:
    fails = []
    first = next((i for i, t in enumerate(turns) if _ok_searches(t)), len(turns))
    # a1: no search without a prior read-back + confirmation
    prev_confirmed, prev_awaiting = False, False
    for k, t in enumerate(turns, 1):
        if _ok_searches(t):
            confirmed_now = any(c["name"] == "confirm_profile" and "error" not in c["result"] for c in t.result.tool_log)
            if not (prev_confirmed or (prev_awaiting and confirmed_now)):
                fails.append(f"turn {k}: search ran without read-back + confirmation")
        prev_confirmed = t.result.state["confirmed"]
        prev_awaiting = t.result.state["awaiting_confirmation"]
    pre = turns[:first]
    # a2: while something required is missing, the turn's asking_for names at least one missing field
    for k, t in enumerate(pre):
        missing = set(t.result.state["missing_required"])
        asking = set(t.result.asking_for)
        if missing and not (asking & missing):
            fails.append(f"turn {k + 1}: missing {sorted(missing)} but asking_for={sorted(asking)}")
    # a3: every field missing at the end of a pre-search turn was asked about later, or the renter filled it next turn
    for k, t in enumerate(pre):
        for f in t.result.state["missing_required"]:
            asked_later = any(f in p.result.asking_for for p in pre[k:])
            filled_next = k + 1 < len(turns) and f not in turns[k + 1].result.state["missing_required"]
            if not (asked_later or filled_next):
                fails.append(f"turn {k + 1}: '{f}' was missing and never asked about")
    # a4: renter gave everything up front -> no extra questions, straight to read-back
    if case["expect"].get("zero_questions_first_turn"):
        r = turns[0].result
        if r.asking_for or not r.state["awaiting_confirmation"]:
            fails.append(f"expected immediate read-back with no questions; asking_for={r.asking_for}, "
                         f"awaiting_confirmation={r.state['awaiting_confirmation']}")
    return fails


# --- (b) final profile equals expected (fields not listed must be empty) --------------------------
def check_b(case: dict, turns: list[TurnRecord]) -> list[str]:
    actual = turns[-1].result.state["profile"]
    expected = case["expected_profile"]
    fails = []
    for field in actual:
        want, got = expected.get(field), actual[field]
        if isinstance(want, dict) and "between" in want:  # e.g. a relative move-in date: any day in the window
            lo, hi = want["between"]
            ok = bool(got) and lo <= got <= hi
        elif field == "commute_destination" and want:
            ok = bool(got) and want.lower() in got.lower()
        elif isinstance(got, list) or isinstance(want, list):
            ok = _norm_list(want or []) == _norm_list(got or [])
        else:
            ok = want == got
        if not ok:
            fails.append(f"{field}: expected {want!r}, got {got!r}")
    return fails


# --- (c) grounding: shortlist ids come from the latest tool results; rendered fields equal the JSON ----
def _violations(l: dict, p: dict) -> list[str]:
    v = []
    if p["bhk"] and l["bhk"] not in p["bhk"]:
        v.append("bhk")
    if p["budget_max"] and l["rent"] > p["budget_max"] * 1.10:
        v.append("budget")
    names = {a.lower() for a in p["areas"]}
    if names and l["sector"].lower() not in names and l["area"].lower() not in names:
        v.append("area")
    if p["move_in_date"] and date.fromisoformat(l["available_from"]) > date.fromisoformat(p["move_in_date"]) + timedelta(days=15):
        v.append("move_in")
    if p["pets"] and not l["pets_allowed"]:
        v.append("pets")
    if p["tenant_type"] and l["tenant_preference"] not in ("any", p["tenant_type"]):
        v.append("tenant_type")
    if p["parking"] and not l["parking"]:
        v.append("parking")
    return v


def check_c(case: dict, turns: list[TurnRecord]) -> list[str]:
    data = load_listings()
    fails = []
    latest: set[str] = set()
    for k, t in enumerate(turns, 1):
        searches = _ok_searches(t)
        if searches:
            latest = {r["id"] for r in searches[-1]["result"]["results"]}
        elif t.result.changes:
            latest = set()  # profile changed: old results are stale
        fetched = {c["result"]["id"] for c in t.result.tool_log if c["name"] == "get_listing" and "error" not in c["result"]}
        citable = latest | fetched
        for item in t.result.shortlist:
            lid = item["id"]
            if lid not in citable:
                fails.append(f"turn {k}: {lid} not in latest tool results")
            if lid not in data:
                fails.append(f"turn {k}: {lid} not in dataset")
                continue
            truth = render(lid)
            for key, val in truth.items():
                if key != "tradeoff" and item.get(key) != val:
                    fails.append(f"turn {k}: {lid}.{key} rendered {item.get(key)!r} != dataset {val!r}")
            if not item["tradeoff"].strip():
                fails.append(f"turn {k}: {lid} has no trade-off sentence")
            # only hard constraints that were true when this shortlist was made
            bad = _violations(data[lid], t.result.state["profile"])
            if bad:
                fails.append(f"turn {k}: {lid} violates hard constraints {bad}")
    return fails


# --- (d) no match => say so, show nothing -------------------------------------------------------
def check_d(case: dict, turns: list[TurnRecord]) -> list[str]:
    fails = []
    empty_search_turns = []
    for k, t in enumerate(turns, 1):
        s = _ok_searches(t)
        if s and s[-1]["result"]["total_matches"] == 0:
            empty_search_turns.append(k)
            if t.result.shortlist or not t.result.no_match:
                fails.append(f"turn {k}: empty search but shortlist={len(t.result.shortlist)}, no_match={t.result.no_match}")
        elif t.result.no_match:
            fails.append(f"turn {k}: claimed no match although the search did not come back empty")
    if case["expect"].get("no_match") and not empty_search_turns:
        fails.append("expected a no-match search, but every search returned results")
    if not case["expect"].get("no_match"):
        last = next((t for t in reversed(turns) if _ok_searches(t)), None)
        if last and not last.result.shortlist:
            fails.append("search had matches but nothing was shortlisted")
    return fails


# --- (e) per-case expectations ---------------------------------------------------------------------
def _match_change(entry: dict, want: dict) -> bool:
    return all(_norm_list(entry.get(k)) == _norm_list(v) for k, v in want.items())


def check_e(case: dict, turns: list[TurnRecord]) -> list[str]:
    ex, fails = case["expect"], []
    n_search = sum(len(_ok_searches(t)) for t in turns)
    if n_search < ex.get("min_searches", 1):
        fails.append(f"expected >= {ex.get('min_searches', 1)} successful searches, got {n_search}")
    for idx, fields in ex.get("asking_at_turn", {}).items():
        asked = {f for t in turns if t.script_idx == int(idx) for f in t.result.asking_for}
        if not set(fields) <= asked:
            fails.append(f"scripted turn {idx}: expected asking_for to include {fields}, got {sorted(asked)}")
    if lid := ex.get("listing_not_found"):
        looked_up = any(c["name"] == "get_listing" and c["result"].get("error") == "not_found"
                        and str(c["args"].get("listing_id", "")).upper() == lid for t in turns for c in t.result.tool_log)
        if not looked_up:
            fails.append(f"agent never looked up {lid} and got not_found")
        if any(i["id"] == lid for t in turns for i in t.result.shortlist):
            fails.append(f"{lid} appeared in a shortlist")
    for idx in ex.get("no_shortlist_at_turns", []):
        for t in turns:
            if t.script_idx == idx and t.result.shortlist:
                fails.append(f"scripted turn {idx}: shortlist must be empty, got {[i['id'] for i in t.result.shortlist]}")
    for want in ex.get("changes_contain", []):
        if not any(_match_change(c, want) for t in turns for c in t.result.changes):
            fails.append(f"no memory change matching {want}")
    for bad in ex.get("reply_must_not_contain", []):
        if any(bad.lower() in t.result.reply.lower() for t in turns):
            fails.append(f"reply leaked {bad!r}")
    # any profile change must leave the session unconfirmed
    for k, t in enumerate(turns, 1):
        if t.result.changes and t.result.state["confirmed"]:
            fails.append(f"turn {k}: profile changed but confirmed is still true")
    # a second search must follow a second read-back
    reads = sum(1 for t in turns for c in t.result.tool_log if c["name"] == "read_back_profile" and "error" not in c["result"])
    if n_search > 1 and reads < n_search:
        fails.append(f"{n_search} searches but only {reads} read-backs")
    return fails


# --- (f) the agent never fell back / errored ---------------------------------------------------------
def check_f(case: dict, turns: list[TurnRecord]) -> list[str]:
    return [f"turn {k}: fallback reply ({t.result.error or 'no valid respond'})"
            for k, t in enumerate(turns, 1) if t.result.fallback]


def run_checks(case: dict, turns: list[TurnRecord]) -> dict[str, list[str]]:
    fns = [check_a, check_b, check_c, check_d, check_e, check_f]
    return {name: fn(case, turns) for name, fn in zip(CHECKS, fns)}
