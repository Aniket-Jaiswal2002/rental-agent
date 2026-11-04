"""Render evals/results.md from raw eval results.

    python -m evals.report evals/raw/<first-full-pass>.json [evals/raw/<follow-up>.json ...]

The FIRST file is the headline: a full pass on one commit, and the only source of the headline pass rate.
Later files are follow-ups. They never replace anything: each follow-up run is listed next to the case's
first result, as "after fix" (different commit; the note lists every code commit between the two) or as an extra
run of the same commit. The reasoning_effort each run used is shown wherever the raw file recorded it. results.md is a pure function of the raw files; never edit it by hand.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

from .checks import CHECKS

HERE = Path(__file__).parent
ROOT = HERE.parent
UNKNOWN = "not recorded"
NOTE_MARK = "†"
_notes_path = HERE / "effort_notes.json"
EFFORT_NOTES = json.loads(_notes_path.read_text(encoding="utf-8")) if _notes_path.exists() else {}

# Prompt tokens per LLM call, measured with `python -m scripts.probe_tokens` (Groq usage numbers).
PROBE = [
    ("Fresh (first message, empty profile)", 2053, 1452),
    ("Mid-conversation (turn 10, full profile, search result, 9 earlier turns)", 2441, 1624),
]


def load_raw(path: Path) -> dict:
    """A raw pass file, or a directory of per-run files. Model/commit come only from what was recorded."""
    if path.is_dir():
        results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))]
        raw = {"generated": path.name, "results": results}
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    raw["source"] = path.as_posix().split("rental-agent/")[-1]
    for r in raw["results"]:
        r.setdefault("model", raw.get("model", UNKNOWN))
        r.setdefault("commit", raw.get("commit", UNKNOWN))
        r.setdefault("dirty", raw.get("dirty"))
        r.setdefault("reasoning_effort", raw.get("reasoning_effort", UNKNOWN))
    noted = EFFORT_NOTES.get("files", {}).get(path.name) if "reasoning_effort" not in raw else None
    if noted:  # an older pass: effort comes from its run command, footnoted, never mixed up with recorded values
        for r in raw["results"]:
            if r["reasoning_effort"] == UNKNOWN:
                r["reasoning_effort"], r["effort_from_note"] = noted, True
    return raw


def commit_label(r: dict) -> str:
    sha = r.get("commit") or UNKNOWN
    short = sha[:7] if sha != UNKNOWN else sha
    return short + (" (dirty tree)" if r.get("dirty") else "")


def commits_between(base: str, head: str) -> list[str]:
    """'<sha> <subject>' for every code commit in base..head, oldest first. Commits that touch only eval
    outputs (evals/raw, evals/results.md) are left out."""
    if not head or head == UNKNOWN:
        return ["unknown change (commit not recorded)"]
    rng = [f"{base}..{head}"] if base and base != UNKNOWN else ["-1", head]
    out = subprocess.run(["git", "log", "--reverse", "--format=%h %s", *rng, "--",
                          ".", ":(exclude)evals/raw", ":(exclude)evals/results.md"], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")  # git prints UTF-8; the Windows code page would garble it
    if out.returncode != 0:
        return [f"commit {head[:7]} (not in this repository's history)"]
    return [s for s in out.stdout.splitlines() if s.strip()] or ["no code change"]


def _run_label(r: dict) -> str:
    return f"{commit_label(r)}, effort {_effort(r)}"


def _effort(r: dict) -> str:
    return (r.get("reasoning_effort") or UNKNOWN) + (NOTE_MARK if r.get("effort_from_note") else "")


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))] if s else 0.0


def _status(r: dict) -> str:
    failing = [name for name, f in r.get("checks", {}).items() if f]
    return r["status"] + (f" ({', '.join(failing)})" if failing else "")


def render(passes: list[dict], all_case_ids: list[str] | None = None) -> str:
    head = passes[0]
    results = head["results"]
    case_ids = list(dict.fromkeys(r["case"] for r in results))
    models = sorted({r.get("model") or UNKNOWN for r in results})
    commits = sorted({commit_label(r) for r in results})
    efforts = sorted({_effort(r) for r in results})
    runs = max(sum(r["case"] == c for r in results) for c in case_ids)
    missing = [c for c in (all_case_ids or []) if c not in case_ids]

    lines = ["# Eval results", "",
             f"Headline: first full pass, `{head['source']}` · model `{', '.join(models)}` · reasoning_effort `{', '.join(efforts)}` · commit `{', '.join(commits)}` · {runs} run(s) per case.", "",
             *(["- **1 run per case; 3 planned, limited by Groq free-tier caps.**"] if runs == 1 else []),
             "- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.",
             "- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.",
             "- Rendered by `python -m evals.report` from raw results; post-fix runs are reported separately below and never change the headline.",
             *([f"- **Warning:** headline pass spans several commits ({', '.join(commits)})."] if len(commits) > 1 else []),
             *([f"- **Warning:** headline pass is missing cases: {', '.join(missing)}."] if missing else []),
             "", "| Case | Pass rate | Rate-limited | Most common failing checks |", "|---|---|---|---|"]
    tot_pass = tot_real = tot_rl = 0
    for cid in case_ids:
        rs = [r for r in results if r["case"] == cid]
        real = [r for r in rs if r["status"] != "RATE_LIMITED"]
        passed = sum(r["status"] == "PASS" for r in real)
        failing = Counter(name for r in real for name, f in r.get("checks", {}).items() if f)
        if any(r["status"] == "ERROR" for r in real):
            failing["api_error"] = sum(r["status"] == "ERROR" for r in real)
        fail_txt = ", ".join(f"{n} ×{c}" for n, c in failing.most_common(3)) or "—"
        lines.append(f"| {cid} | {f'{passed}/{len(real)}' if real else 'n/a'} | {len(rs) - len(real)} | {fail_txt} |")
        tot_pass, tot_real, tot_rl = tot_pass + passed, tot_real + len(real), tot_rl + len(rs) - len(real)
    overall = f"{tot_pass}/{tot_real} runs passed ({100 * tot_pass / tot_real:.0f}%)" if tot_real else "no completed runs"
    lines += ["", f"**Headline: {overall}; {tot_rl} rate-limited run(s) excluded.**", ""]

    done = [r for r in results if r["status"] in ("PASS", "FAIL")]
    lines += ["## Per-check pass rate (headline pass, completed runs)", "", "| Check | Passed |", "|---|---|"]
    lines += [f"| {name} | {sum(not r['checks'][name] for r in done)}/{len(done)} |" for name in CHECKS]

    timings = [t for r in done for t in r["turn_timings"]]
    if timings:
        totals, llm_ms = [t["total_ms"] for t in timings], [t["llm_ms"] for t in timings]
        lines += ["", "## Agent latency per turn (headline pass, text mode, no STT/TTS)", "", "| | p50 | p95 |", "|---|---|---|",
                  f"| LLM time | {pct(llm_ms, .5):.0f} ms | {pct(llm_ms, .95):.0f} ms |",
                  f"| Turn total | {pct(totals, .5):.0f} ms | {pct(totals, .95):.0f} ms |",
                  f"| Mean LLM calls/turn | {statistics.mean(t['llm_calls'] for t in timings):.1f} | |",
                  "", "Latency includes the client-side token pacing sleeps and 429 waits, so it overstates real model latency."]

    calls = sum(r["llm_calls"] for r in results)
    if calls:
        tot = lambda k: sum(r.get(k, 0) for r in results)
        lines += ["", f"Tokens used in the headline pass: {tot('tokens'):,} across {calls} LLM calls. Run average per call: "
                      f"{tot('tokens') / calls:,.0f} total ({tot('prompt_tokens') / calls:,.0f} prompt + "
                      f"{tot('completion_tokens') / calls:,.0f} completion)."]
    lines += ["", "## Prompt size per call (`python -m scripts.probe_tokens`)", "",
              "| Scenario | Before trim | After trim |", "|---|---|---|"]
    lines += [f"| {name} | {before:,} | {after:,} |" for name, before, after in PROBE]

    # -- follow-ups: listed beside the first result, never replacing it --------------------------
    follow = [(p, r) for p in passes[1:] for r in p["results"]]
    if follow:
        first = {}
        for r in results:
            first.setdefault(r["case"], r)
        lines += ["", "## Follow-up runs (not part of the headline)", "",
                  "| Case | First result (commit, effort) | Follow-up result (commit, effort) | Kind | What changed |",
                  "|---|---|---|---|---|"]
        for p, r in follow:
            f0 = first.get(r["case"])
            same = f0 is not None and f0.get("commit") == r.get("commit") and f0.get("dirty") == r.get("dirty") \
                and r.get("commit") != UNKNOWN and not r.get("dirty")
            same_effort = f0 is not None and f0.get("reasoning_effort") == r.get("reasoning_effort") != UNKNOWN
            kind = ("extra run, same commit" if same_effort else "same commit, other settings") if same else "after fix"
            note = "—" if same else "<br>".join(commits_between(f0.get("commit") if f0 else UNKNOWN, r.get("commit")))
            before = f"{_status(f0)} ({_run_label(f0)})" if f0 else "not in headline pass"
            lines.append(f"| {r['case']} | {before} | {_status(r)} ({_run_label(r)}) | {kind} | {note} |")
        lines += ["", "Sources: " + ", ".join(f"`{p['source']}`" for p in passes[1:]) + "."]
    if any(r.get("effort_from_note") for p in passes for r in p["results"]):
        lines += ["", f"{NOTE_MARK} reasoning_effort {EFFORT_NOTES.get('note', 'from run commands')} (`evals/effort_notes.json`)."]

    bad = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if bad:
        lines += ["", "## Headline failures", ""]
        for r in bad:
            lines.append(f"### {r['case']}" + (f" — {r['status']}: {r['note']}" if r["note"] else ""))
            lines += [f"- **{name}**: {f}" for name, fs in r["checks"].items() for f in fs]
            lines.append("")
    rl_runs = [r for r in results if r["status"] == "RATE_LIMITED"]
    if rl_runs:
        lines += ["## Rate-limited runs (headline pass)", ""] + [f"- {r['case']}: {r['note']}" for r in rl_runs]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="+", help="first: the full headline pass; then any follow-up passes, oldest first")
    ap.add_argument("--out", default=str(HERE / "results.md"))
    args = ap.parse_args()
    all_ids = [json.loads(p.read_text(encoding="utf-8"))["id"] for p in sorted((HERE / "cases").glob("*.json"))]
    Path(args.out).write_text(render([load_raw(Path(p)) for p in args.raw], all_ids), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
