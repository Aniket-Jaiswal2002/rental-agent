"""Run the text-mode evals: python -m evals.run [--runs 3] [--cases 05,07] [--out evals/results.md]

Each case is replayed --runs times against the live model. A run is PASS (all checks pass),
FAIL (some check failed), RATE_LIMITED (Groq 429s outlasted the retries; not counted either way)
or ERROR (non-429 API failure; counted as a failure).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TODAY_OVERRIDE", "2026-11-02")  # same "today" as the dataset's as_of date

from app.agent import Agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import GroqClient, LLMError, RateLimited  # noqa: E402

from .checks import TurnRecord, run_checks  # noqa: E402

CASES_DIR = Path(__file__).parent / "cases"
RAW_DIR = Path(__file__).parent / "raw"
ROOT = Path(__file__).parent.parent


def git_state() -> tuple[str, bool]:
    """(HEAD sha, dirty) for the code under test. Eval outputs (evals/raw, evals/results.md) do not count as dirty."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    sha = git("rev-parse", "HEAD") or "not recorded"
    dirty = bool(git("status", "--porcelain", "--", ".", ":(exclude)evals/raw", ":(exclude)evals/results.md"))
    return sha, dirty
NUDGE = "Sure, please go ahead."
MAX_NUDGES = 2


class CountingLLM:
    def __init__(self, inner) -> None:
        self.inner, self.tokens, self.calls, self.retries = inner, 0, 0, 0
        self.prompt_tokens = self.completion_tokens = 0

    def chat(self, messages, tools):
        resp = self.inner.chat(messages, tools)
        self.tokens += resp.total_tokens
        self.prompt_tokens += resp.prompt_tokens
        self.completion_tokens += resp.completion_tokens
        self.calls += 1
        self.retries += resp.retries
        return resp


def load_cases(selector: str | None) -> list[dict]:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]
    if selector:
        wanted = selector.split(",")
        cases = [c for c in cases if any(w in c["id"] for w in wanted)]
    return cases


def play(case: dict, llm) -> list[TurnRecord]:
    """Replay the scripted renter lines. A line marked await_read_back is held until the agent has read the
    profile back (the harness sends a neutral nudge meanwhile), so fixed scripts survive question-order differences."""
    agent, records = Agent(llm), []
    for idx, line in enumerate(case["turns"], 1):
        if line.get("await_read_back"):
            for _ in range(MAX_NUDGES):
                if agent.state.awaiting_confirmation:
                    break
                records.append(TurnRecord(None, NUDGE, agent.turn(NUDGE)))
        records.append(TurnRecord(idx, line["say"], agent.turn(line["say"])))
    return records


def run_once(case: dict, client, commit: str, dirty: bool) -> dict:
    llm = CountingLLM(client)
    started = time.perf_counter()
    turns: list[TurnRecord] = []
    try:
        turns = play(case, llm)
        checks = run_checks(case, turns)
        status = "PASS" if not any(checks.values()) else "FAIL"
        note = ""
    except RateLimited as e:
        checks, status, note = {}, "RATE_LIMITED", str(e)[:200]
    except LLMError as e:
        checks, status, note = {}, "ERROR", str(e)[:200]
    return {"case": case["id"], "model": client.model, "commit": commit, "dirty": dirty, "status": status, "note": note, "checks": checks, "tokens": llm.tokens, "prompt_tokens": llm.prompt_tokens, "completion_tokens": llm.completion_tokens,
            "llm_calls": llm.calls, "seconds": round(time.perf_counter() - started, 1),
            "turn_timings": [t.result.timings.to_dict() for t in turns],
            "transcript": [{"script_idx": t.script_idx, "user": t.user, "reply": t.result.display_text,
                            "asking_for": t.result.asking_for, "state": t.result.state,
                            "tools": [{"name": c["name"], "args": c["args"], "error": c["result"].get("error")} for c in t.result.tool_log]}
                           for t in turns]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="runs per case (3 were planned; 1 is what Groq free-tier caps allow)")
    ap.add_argument("--cases", help="comma-separated substrings of case ids")
    args = ap.parse_args()

    cases = load_cases(args.cases)
    client = GroqClient()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(__file__).parent / "runs" / stamp  # per-run files, written as each run finishes
    raw_path = RAW_DIR / f"{stamp}.json"  # one file for the whole pass: input to `python -m evals.report`
    run_dir.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(exist_ok=True)
    commit, dirty = git_state()
    results: list[dict] = []
    print(f"{len(cases)} case(s) x {args.runs} run(s), model {client.model}, commit {commit[:7]}{' (dirty tree)' if dirty else ''}\n")
    for case in cases:
        for n in range(1, args.runs + 1):
            r = run_once(case, client, commit, dirty)
            results.append(r)
            (run_dir / f"{case['id']}_{n}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
            raw_path.write_text(json.dumps({"model": client.model, "commit": commit, "dirty": dirty, "runs": args.runs,
                                            "generated": stamp, "results": results},
                                           indent=2, ensure_ascii=False), encoding="utf-8")
            failing = [name for name, f in r["checks"].items() if f]
            print(f"  {case['id']:<32} run {n}: {r['status']:<12} {r['seconds']:>5}s {r['tokens']:>7} tok  {','.join(failing) or r['note']}")
    print(f"\nraw results: {raw_path}\nrender with: python -m evals.report {raw_path.relative_to(Path.cwd()) if raw_path.is_relative_to(Path.cwd()) else raw_path}")


if __name__ == "__main__":
    main()