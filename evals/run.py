"""Run the text-mode evals: python -m evals.run [--runs 3] [--cases 05,07] [--out evals/results.md]

Each case is replayed --runs times against the live model. A run is PASS (all checks pass),
FAIL (some check failed), RATE_LIMITED (Groq 429s outlasted the retries; not counted either way)
or ERROR (non-429 API failure; counted as a failure).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TODAY_OVERRIDE", "2026-11-02")  # same "today" as the dataset's as_of date

from app.agent import Agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import GroqClient, LLMError, RateLimited  # noqa: E402

from .checks import CHECKS, TurnRecord, run_checks  # noqa: E402

CASES_DIR = Path(__file__).parent / "cases"
NUDGE = "Sure, please go ahead."
MAX_NUDGES = 2


class CountingLLM:
    def __init__(self, inner) -> None:
        self.inner, self.tokens, self.calls, self.retries = inner, 0, 0, 0

    def chat(self, messages, tools):
        resp = self.inner.chat(messages, tools)
        self.tokens += resp.total_tokens
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


def run_once(case: dict, client) -> dict:
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
    return {"case": case["id"], "status": status, "note": note, "checks": checks, "tokens": llm.tokens,
            "llm_calls": llm.calls, "seconds": round(time.perf_counter() - started, 1),
            "turn_timings": [t.result.timings.to_dict() for t in turns],
            "transcript": [{"script_idx": t.script_idx, "user": t.user, "reply": t.result.display_text,
                            "asking_for": t.result.asking_for, "state": t.result.state,
                            "tools": [{"name": c["name"], "args": c["args"], "error": c["result"].get("error")} for c in t.result.tool_log]}
                           for t in turns]}


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))] if s else 0.0


def summarise(results: list[dict], cases: list[dict], runs: int, model: str) -> str:
    by_case: dict[str, list[dict]] = {c["id"]: [r for r in results if r["case"] == c["id"]] for c in cases}
    lines = [f"# Eval results", "",
             f"- Model: `{model}` · {runs} run(s) per case · generated {datetime.now():%Y-%m-%d %H:%M}",
             "- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.",
             "- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.", "",
             "| Case | Pass rate | Rate-limited | Most common failing checks |", "|---|---|---|---|"]
    tot_pass = tot_real = tot_rl = 0
    for cid, rs in by_case.items():
        real = [r for r in rs if r["status"] != "RATE_LIMITED"]
        passed = sum(r["status"] == "PASS" for r in real)
        rl = len(rs) - len(real)
        failing = Counter(name for r in real for name, f in r["checks"].items() if f)
        if any(r["status"] == "ERROR" for r in real):
            failing["api_error"] = sum(r["status"] == "ERROR" for r in real)
        fail_txt = ", ".join(f"{n} ×{c}" for n, c in failing.most_common(3)) or "—"
        rate = f"{passed}/{len(real)}" if real else "n/a"
        lines.append(f"| {cid} | {rate} | {rl} | {fail_txt} |")
        tot_pass, tot_real, tot_rl = tot_pass + passed, tot_real + len(real), tot_rl + rl
    overall = f"{tot_pass}/{tot_real} runs passed ({100 * tot_pass / tot_real:.0f}%)" if tot_real else "no completed runs"
    lines += ["", f"**Overall: {overall}; {tot_rl} rate-limited run(s) excluded.**", ""]

    lines += ["## Per-check pass rate (completed runs)", "", "| Check | Passed |", "|---|---|"]
    done = [r for r in results if r["status"] in ("PASS", "FAIL")]
    for name in CHECKS:
        lines.append(f"| {name} | {sum(not r['checks'][name] for r in done)}/{len(done)} |")

    totals = [t["total_ms"] for r in done for t in r["turn_timings"]]
    llm_ms = [t["llm_ms"] for r in done for t in r["turn_timings"]]
    if totals:
        lines += ["", "## Agent latency per turn (text mode, no STT/TTS)", "", "| | p50 | p95 |", "|---|---|---|",
                  f"| LLM time | {pct(llm_ms, .5):.0f} ms | {pct(llm_ms, .95):.0f} ms |",
                  f"| Turn total | {pct(totals, .5):.0f} ms | {pct(totals, .95):.0f} ms |",
                  f"| Mean LLM calls/turn | {statistics.mean(t['llm_calls'] for r in done for t in r['turn_timings']):.1f} | |"]
    lines += ["", f"Tokens used: {sum(r['tokens'] for r in results):,} across {sum(r['llm_calls'] for r in results)} LLM calls."]

    bad = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if bad:
        lines += ["", "## Failures (first failing run per case)", ""]
        seen = set()
        for r in bad:
            if r["case"] in seen:
                continue
            seen.add(r["case"])
            lines.append(f"### {r['case']}" + (f" — {r['status']}: {r['note']}" if r["note"] else ""))
            for name, fs in r["checks"].items():
                for f in fs:
                    lines.append(f"- **{name}**: {f}")
            lines.append("")
    rl_runs = [r for r in results if r["status"] == "RATE_LIMITED"]
    if rl_runs:
        lines += ["## Rate-limited runs", ""] + [f"- {r['case']}: {r['note']}" for r in rl_runs]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", help="comma-separated substrings of case ids")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.md"))
    args = ap.parse_args()

    cases = load_cases(args.cases)
    client = GroqClient()
    results: list[dict] = []
    run_dir = Path(__file__).parent / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(cases)} case(s) x {args.runs} run(s), model {client.model}\n")
    for case in cases:
        for n in range(1, args.runs + 1):
            r = run_once(case, client)
            results.append(r)
            (run_dir / f"{case['id']}_{n}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
            failing = [name for name, f in r["checks"].items() if f]
            print(f"  {case['id']:<32} run {n}: {r['status']:<12} {r['seconds']:>5}s {r['tokens']:>7} tok  {','.join(failing) or r['note']}")
    report = summarise(results, cases, args.runs, client.model)
    Path(args.out).write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"transcripts: {run_dir}\nwritten: {args.out}")


if __name__ == "__main__":
    main()
