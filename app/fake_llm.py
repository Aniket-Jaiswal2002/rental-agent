"""FAKE_LLM=1: a canned, rule-based stand-in for the model, for building and screenshotting the UI at zero
token cost. It speaks the same tool-calling protocol as the real model, so every turn still runs through the
real agent loop, profile memory, confirmation gate, search and rendering. Only the "language understanding"
is fake: simple regexes over the renter's words. Not used by evals or by default.
"""
from __future__ import annotations

import itertools
import json
import re
import time

from .llm import LLMResponse, ToolCall

_ids = itertools.count(1)
_YES = re.compile(r"\b(yes|yeah|yep|correct|right|haan|ha|sahi|go ahead|confirm(ed)?)\b", re.I)
_CORRECTION = re.compile(r"\b(actually|make it|change|sorry|instead|nahi|kar do)\b", re.I)
_QUESTIONS = {
    "budget_max": "What's your monthly budget?",
    "areas": "Which sectors or areas do you prefer?",
    "bhk": "How many bedrooms do you need?",
    "move_in_date": "When do you want to move in?",
    "commute_destination": "Where will you be commuting to?",
}


def _parse(text: str) -> dict:
    t = text.lower()
    out: dict = {}
    if m := re.search(r"(\d{2,3})\s*k\b|(\d{2,3}),?(\d{3})\b|(\d{2,3})\s*(hazaar|thousand)", t):
        out["budget_max"] = int(m.group(1) or m.group(4) or "0") * 1000 if (m.group(1) or m.group(4)) \
            else int(m.group(2) + m.group(3))
    if m := re.search(r"(\d)\s*bhk", t):
        out["bhk"] = [int(m.group(1))]
    sectors = re.findall(r"sector\s*(\d{1,3})", t)
    named = [n for n in ("DLF Phase 2", "DLF Phase 3", "DLF Phase 4", "Golf Course Road", "Sushant Lok 1") if n.lower() in t]
    if sectors or named:
        out["areas"] = [f"Sector {s}" for s in sectors] + named
    for dest in ("Cyber City", "Golf Course Road", "Udyog Vihar"):
        if dest.lower() in t and ("office" in t or "commut" in t or "work" in t):
            out["commute_destination"] = dest
    if m := re.search(r"(\d{1,2}(st|nd|rd|th)?\s+(of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|dec|jan|nov))"
                      r"|(within a week|next week|next month|immediately|in \d+ days)", t):
        out["move_in_date"] = m.group(0)
    if re.search(r"\b(dog|cat|pet)\b", t):
        out["pets"] = True
    if "bachelor" in t:
        out["tenant_type"] = "bachelor"
    elif "family" in t:
        out["tenant_type"] = "family"
    return out


def _state(messages: list[dict]) -> dict:
    system = messages[0]["content"]
    return json.loads(system.split("STATE (live memory):\n", 1)[1])


def _call(name: str, args: dict) -> ToolCall:
    return ToolCall(id=f"fake_{next(_ids)}", name=name, arguments=args)


def _tradeoff(r: dict) -> str:
    bits = []
    if r["over_budget_by"]:
        bits.append(f"{r['over_budget_by']:,} rupees over budget")
    else:
        bits.append("within budget")
    if r["commute_km"] is not None:
        bits.append(f"{r['commute_km']} km from your office")
    if r["available_days_after_move_in"]:
        bits.append(f"frees up {r['available_days_after_move_in']} days after your move-in")
    if r["furnishing_mismatch"]:
        bits.append(f"{r['furnishing']} rather than what you asked for")
    return "; ".join(bits).capitalize() + "."


class FakeLLM:
    model = "fake-llm (canned replies, no API calls)"

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        time.sleep(0.15)  # a little latency so the UI's states are visible
        state = _state(messages)
        last = messages[-1]
        if last["role"] == "tool" and last.get("tool_call_id") == "auto_search":
            calls = [self._shortlist(json.loads(last["content"]))]
        elif last["role"] == "tool":  # we already updated the profile this turn: now just reply
            calls = [self._ask(_state(messages), last)]
        else:
            text = last["content"]
            calls = []
            if state["awaiting_confirmation"] and _YES.search(text) and not _parse(text):
                calls = [_call("confirm_profile", {"renter_quote": _YES.search(text).group(0)})]
            else:
                changes = _parse(text)
                if changes:
                    profile = state["profile"]
                    kinds = {f: ("correction" if profile.get(f) not in (None, []) and _CORRECTION.search(text) else "new")
                             for f in changes}
                    changes = {f: v for f, v in changes.items() if kinds[f] == "correction" or profile.get(f) in (None, [])}
                    kinds = {f: kinds[f] for f in changes}
                    if changes:
                        calls.append(_call("update_profile", {"changes": changes, "change_kinds": kinds}))
                if not calls:
                    calls = [self._ask(state, None)]
        raw = {"role": "assistant", "content": "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}} for c in calls]}
        return LLMResponse(content="", tool_calls=calls, raw_message=raw, elapsed_ms=150.0, total_tokens=0)

    @staticmethod
    def _ask(state: dict, tool_msg: dict | None) -> ToolCall:
        missing = state["missing_required"]
        if tool_msg:
            result = json.loads(tool_msg["content"])
            missing = result.get("missing_required", missing)
            if result.get("not_applied_conflicts"):
                f = result["not_applied_conflicts"][0]
                return _call("respond", {"reply": "Just to check, which sectors do you mean?" if f == "areas"
                                         else f"You mentioned two different values for {f.replace('_', ' ')}. Which one is right?",
                                         "asking_for": [f], "shortlist": []})
        if not missing:
            return _call("respond", {"reply": "Anything else I can help with?", "asking_for": [], "shortlist": []})
        ask = missing[:2]
        reply = " ".join(_QUESTIONS[f] for f in ask)
        return _call("respond", {"reply": ("Got it. " if tool_msg else "") + reply, "asking_for": ask, "shortlist": []})

    @staticmethod
    def _shortlist(result: dict) -> ToolCall:
        if not result.get("results"):
            return _call("respond", {"reply": "Nothing in the listings matches all of that. Would you like to widen the budget or the areas?",
                                     "asking_for": [], "shortlist": [], "no_match_notice": True})
        picks = result["results"][:3]
        return _call("respond", {"reply": f"I found {result['total_matches']} matches. Here are the best {len(picks)}.",
                                 "asking_for": [],
                                 "shortlist": [{"listing_id": r["id"], "tradeoff": _tradeoff(r)} for r in picks]})
