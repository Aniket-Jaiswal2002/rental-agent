"""Latency benchmark: 3 typed turns against the live model (about 3-10 LLM calls).

    python -m scripts.bench_turns [label]

Reports LLM calls per turn and model time (HTTP round trips only) separately from client-side
pacing/backoff waits, so throttling never masquerades as model latency.
"""
import json
import os
import statistics
import sys

os.environ.setdefault("TODAY_OVERRIDE", "2026-11-02")

from app.agent import Agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import GroqClient  # noqa: E402

TURNS = [
    "I need a 2 BHK in Sector 56, budget 30000, moving 1st December, office at Cyber City.",
    "Yes, that's right.",
    "Actually make the budget 35000.",
]


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    agent = Agent(GroqClient())
    rows = []
    for text in TURNS:
        r = agent.turn(text)
        t = r.timings
        rows.append({"turn": text, "calls": t.llm_calls, "model_ms": round(t.llm_ms), "wait_ms": round(t.wait_ms),
                     "total_ms": round(t.total_ms), "tokens": t.llm_tokens, "reply": r.display_text[:160]})
        print(f"{t.llm_calls} calls  model {t.llm_ms:7.0f} ms  wait {t.wait_ms:7.0f} ms  total {t.total_ms:7.0f} ms  | {r.reply[:90]}")
    summary = {"label": label, "model": settings.groq_model, "reasoning_effort": settings.reasoning_effort,
               "calls_per_turn": [r["calls"] for r in rows],
               "median_model_ms": statistics.median(r["model_ms"] for r in rows),
               "median_total_minus_wait_ms": statistics.median(r["total_ms"] - r["wait_ms"] for r in rows), "turns": rows}
    print(json.dumps({k: v for k, v in summary.items() if k != "turns"}))


if __name__ == "__main__":
    main()
