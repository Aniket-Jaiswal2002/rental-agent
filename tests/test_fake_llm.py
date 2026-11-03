"""FAKE_LLM mode drives the real agent loop end to end without any API call."""
from app.agent import Agent
from app.fake_llm import FakeLLM


def test_fake_llm_full_flow_through_real_agent(monkeypatch):
    monkeypatch.setenv("TODAY_OVERRIDE", "2026-11-03")
    a = Agent(FakeLLM())
    r = a.turn("Hi, I need a flat")
    assert r.asking_for and r.timings.llm_tokens == 0

    a.turn("2 BHK in Sector 56 or Sector 57, budget 30k")
    r = a.turn("Moving 1st December, office at Cyber City")
    assert r.state["awaiting_confirmation"] and r.reply.startswith("Let me confirm")

    r = a.turn("Actually make it 35k")
    assert r.state["profile"]["budget_max"] == 35000 and r.updates and r.state["awaiting_confirmation"]

    r = a.turn("Yes, that's right")
    assert r.state["confirmed"] and 1 <= len(r.shortlist) <= 3
    assert all(c["rent"] <= 35000 * 1.1 for c in r.shortlist)
