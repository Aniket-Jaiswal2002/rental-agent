"""Agent-loop tests with a scripted fake LLM (no network): grounding and the search gate."""
import json

from app.agent import Agent
from app.listings import load_listings
from app.llm import LLMResponse, ToolCall

FULL = {"budget_max": 30000, "areas": ["Sector 56"], "bhk": [2], "move_in_date": "2026-12-01",
        "commute_destination": "Cyber City"}


class FakeLLM:
    """Replays scripted tool calls; each script item is a list of (tool_name, args) for one LLM call."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def chat(self, messages, tools):
        self.calls.append(json.loads(json.dumps(messages, default=str)))
        batch = self.script.pop(0)
        tcs = [ToolCall(id=f"c{len(self.calls)}_{i}", name=n, arguments=a) for i, (n, a) in enumerate(batch)]
        raw = {"role": "assistant", "content": "", "tool_calls": [
            {"id": t.id, "type": "function", "function": {"name": t.name, "arguments": json.dumps(t.arguments)}} for t in tcs]}
        return LLMResponse(content="", tool_calls=tcs, raw_message=raw, elapsed_ms=1.0)


def respond(reply="ok", asking_for=(), shortlist=(), no_match=None):
    args = {"reply": reply, "asking_for": list(asking_for), "shortlist": list(shortlist)}
    if no_match is not None:
        args["no_match_notice"] = no_match
    return ("respond", args)


def awaiting_agent(script) -> Agent:
    """An agent whose profile is complete and was read back on the previous turn."""
    a = Agent(FakeLLM(script))
    a.state.turn = 1
    a.state.update_profile(FULL)
    a.state.read_back()
    return a


def tool_results(agent: Agent, call_index: int) -> list[dict]:
    return [json.loads(m["content"]) for m in agent.llm.calls[call_index] if m["role"] == "tool"]


def test_invented_listing_id_is_rejected_then_real_one_rendered_from_dataset():
    a = awaiting_agent([
        [("confirm_profile", {"renter_quote": "yes"})],
        [("search_listings", {})],
        [respond("Here you go.", shortlist=[{"listing_id": "L999", "tradeoff": "Great flat for 20000"}])],
        [respond("Here you go.", shortlist=[{"listing_id": "L021", "tradeoff": "Closest to your budget."}])],
    ])
    r = a.turn("yes")
    rejected = [m for m in tool_results(a, 3) if "error" in m]
    assert rejected and "L999" in rejected[0]["error"]
    assert [x["id"] for x in r.shortlist] == ["L021"]
    truth = load_listings()["L021"]
    assert r.shortlist[0]["rent"] == truth["rent"] and r.shortlist[0]["deposit"] == truth["deposit"]
    assert f"{truth['rent']:,}" in r.display_text  # price in the output is the dataset's, rendered by the server


def test_listing_not_in_latest_results_cannot_be_cited():
    # L001 exists in the dataset but is not in the latest search results (2 BHK, Sector 56 -> only L021)
    a = awaiting_agent([
        [("confirm_profile", {"renter_quote": "yes"})],
        [("search_listings", {})],
        [respond(shortlist=[{"listing_id": "L001", "tradeoff": "x"}])],
        [respond(shortlist=[{"listing_id": "L021", "tradeoff": "y"}])],
    ])
    r = a.turn("yes")
    assert [x["id"] for x in r.shortlist] == ["L021"]


def test_search_before_confirmation_is_refused():
    a = Agent(FakeLLM([[upd(FULL, dict.fromkeys(FULL, "new"))], [("search_listings", {})],
                       [("read_back_profile", {})], [respond("Please confirm: 2 BHK...")]]))
    r = a.turn("2 BHK Sector 56 30k 1 Dec Cyber City")
    searches = [t for t in r.tool_log if t["name"] == "search_listings"]
    assert searches and "error" in searches[0]["result"] and "not confirmed" in searches[0]["result"]["error"]
    assert r.state["awaiting_confirmation"] and not r.state["confirmed"]


def test_no_match_requires_notice_and_empty_shortlist():
    a = awaiting_agent([
        [upd({"bhk": [4], "budget_max": 20000, "areas": ["Sector 54"]}, dict.fromkeys(["bhk", "budget_max", "areas"], "correction"))],
        [("read_back_profile", {})],
        [respond("Please confirm.")],
    ])
    a.turn("make it 4 BHK, 20k, sector 54")  # 3 LLM calls (indices 0-2); renter now sees a new read-back
    a.llm.script += [
        [("confirm_profile", {"renter_quote": "yes"})],
        [("search_listings", {})],
        [respond("Found some.", shortlist=[{"listing_id": "L022", "tradeoff": "x"}])],  # forced bad match
        [respond("Nothing matches 4 BHK under 20k there.", no_match=True)],
    ]
    r = a.turn("yes")
    assert r.no_match and r.shortlist == []
    assert any("error" in m for m in tool_results(a, 6))  # the forced match was bounced back to the model


def upd(changes, kinds):
    return ("update_profile", {"changes": changes, "change_kinds": kinds})


def test_conflict_is_not_applied_and_agent_must_ask():
    a = Agent(FakeLLM([
        [upd({"budget_max": 30000, "bhk": [2]}, {"budget_max": "new", "bhk": "new"})], [respond("When?", asking_for=["move_in_date"])],
        [upd({"budget_max": 20000, "move_in_date": "2026-12-01"}, {"budget_max": "conflict", "move_in_date": "new"})],
        [respond("All set!")],  # rejected: must ask about the conflicted budget
        [respond("Is your budget 30000 or 20000?", asking_for=["budget_max"])],
    ]))
    a.turn("2 BHK, budget is 30000")
    r = a.turn("My budget is 20000, moving 1 December")
    assert r.state["profile"]["budget_max"] == 30000 and r.state["profile"]["move_in_date"] == "2026-12-01"
    assert r.tool_log[0]["result"]["not_applied_conflicts"] == ["budget_max"]
    assert any(c["name"] == "respond_rejected" for c in r.tool_log)
    assert r.asking_for == ["budget_max"] and r.updates == []


def test_conflict_blocks_read_back_in_the_same_turn():
    a = Agent(FakeLLM([
        [upd({"budget_max": 30000, "areas": ["Sector 56"], "bhk": [2], "move_in_date": "2026-12-01", "commute_destination": "Cyber City"},
             dict.fromkeys(["budget_max", "areas", "bhk", "move_in_date", "commute_destination"], "new"))],
        [respond("Which budget?", asking_for=["budget_max"])],
        [upd({"budget_max": 20000}, {"budget_max": "conflict"})], [("read_back_profile", {})],
        [respond("Which budget, 30000 or 20000?", asking_for=["budget_max"])],
    ]))
    a.turn("everything, budget 30000")
    r = a.turn("budget is 20000")
    read_back = next(c for c in r.tool_log if c["name"] == "read_back_profile")
    assert "error" in read_back["result"] and not r.state["awaiting_confirmation"]


def test_english_correction_is_applied_and_announced_old_to_new():
    a = Agent(FakeLLM([
        [upd({"budget_max": 30000}, {"budget_max": "new"})], [respond("ok", asking_for=["bhk"])],
        [upd({"budget_max": 35000}, {"budget_max": "correction"})], [respond("Got it.", asking_for=["bhk"])],
    ]))
    a.turn("budget 30000")
    r = a.turn("Actually make it 35k")
    assert r.state["profile"]["budget_max"] == 35000
    assert r.updates == ["Updated budget max: ₹30,000 -> ₹35,000."]
    assert r.display_text.startswith(r.updates[0])
    assert r.state["changelog"][-1]["kind"] == "correction"


def test_hinglish_correction_nahi_35_kar_do():
    a = Agent(FakeLLM([
        [upd({"budget_max": 30000}, {"budget_max": "new"})], [respond("ok", asking_for=["bhk"])],
        [upd({"budget_max": 35000}, {"budget_max": "correction"})], [respond("Noted.", asking_for=["bhk"])],
    ]))
    a.turn("budget tees hazaar")
    r = a.turn("nahi, 35 kar do")
    assert r.state["profile"]["budget_max"] == 35000 and r.updates == ["Updated budget max: ₹30,000 -> ₹35,000."]


def test_overwrite_mislabelled_new_is_rejected_atomically():
    a = Agent(FakeLLM([
        [upd({"budget_max": 30000}, {"budget_max": "new"})], [respond("ok", asking_for=["bhk"])],
        [upd({"budget_max": 20000, "bhk": [2]}, {"budget_max": "new", "bhk": "new"})],
        [upd({"budget_max": 20000, "bhk": [2]}, {"budget_max": "conflict", "bhk": "new"})],
        [respond("Which budget?", asking_for=["budget_max"])],
    ]))
    a.turn("budget 30000")
    r = a.turn("budget 20000, 2 bhk")
    assert "already holds" in r.tool_log[0]["result"]["error"]
    assert r.tool_log[0]["result"].get("applied") is None  # nothing applied by the bad call
    assert r.state["profile"]["budget_max"] == 30000 and r.state["profile"]["bhk"] == [2]

def test_changing_budget_after_confirmation_resets_and_requires_new_read_back():
    a = awaiting_agent([
        [("confirm_profile", {"renter_quote": "yes"})], [("search_listings", {})],
        [respond(shortlist=[{"listing_id": "L021", "tradeoff": "ok"}])],
        [upd({"budget_max": 40000}, {"budget_max": "correction"})],
        [respond("Updated to 40,000.")],  # rejected: complete + unconfirmed + not asking anything
        [("read_back_profile", {})],
        [respond("Updated budget to 40,000. Shall I go ahead with that?")],
    ])
    a.turn("yes")
    assert a.state.confirmed
    r = a.turn("actually make it 40k")
    assert r.changes[0]["field"] == "budget_max" and r.changes[0]["new"] == 40000
    assert r.state["awaiting_confirmation"] and not r.state["confirmed"]
    assert a.state.last_search is None
