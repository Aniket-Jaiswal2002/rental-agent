from evals.checks import CHECKS
from evals.report import render

A, B = "a" * 40, "b" * 40


def run(case, status, commit=A, dirty=False, **kw):
    checks = {name: [] for name in CHECKS}
    if status == "FAIL":
        checks["b_final_profile"] = ["budget_max: expected 30000, got 20000"]
    base = {"case": case, "model": "test-model", "commit": commit, "dirty": dirty, "status": status, "note": "",
            "checks": checks if status in ("PASS", "FAIL") else {}, "tokens": 3000, "prompt_tokens": 2400,
            "completion_tokens": 600, "llm_calls": 2, "seconds": 5,
            "turn_timings": [{"total_ms": 1000, "llm_ms": 900, "llm_calls": 2}]}
    return base | kw


def raw(results, name="evals/raw/full.json"):
    return {"generated": "20261103-000000", "results": results, "source": name}


def test_headline_table_and_run_average_wording():
    md = render([raw([run("c1", "PASS"), run("c2", "FAIL"), run("c3", "RATE_LIMITED", note="429")])], ["c1", "c2", "c3"])
    assert "| c1 | 1/1 | 0 | — |" in md and "| c2 | 0/1 | 0 | b_final_profile ×1 |" in md and "| c3 | n/a | 1 | — |" in md
    assert "**Headline: 1/2 runs passed (50%); 1 rate-limited run(s) excluded.**" in md
    assert "model `test-model` · commit `aaaaaaa`" in md
    assert "Run average per call: 1,500 total (1,200 prompt + 300 completion)" in md
    assert "| Fresh (first message, empty profile) | 2,053 | 1,452 |" in md
    assert "1,369" not in md


def test_follow_up_after_fix_is_listed_beside_first_result_and_headline_unchanged(monkeypatch):
    import evals.report as rep
    monkeypatch.setattr(rep, "commit_subject", lambda sha: "Ask about conflicting budget")
    md = render([raw([run("c1", "FAIL"), run("c2", "PASS")]), raw([run("c1", "PASS", commit=B)], "evals/raw/rerun.json")])
    assert "**Headline: 1/2 runs passed (50%)" in md  # the fix does not change the headline
    assert "| c1 | 0/1 | 0 | b_final_profile ×1 |" in md
    assert ("| c1 | FAIL (b_final_profile) (aaaaaaa) | PASS (bbbbbbb) | after fix | Ask about conflicting budget |") in md


def test_rerun_on_same_commit_is_an_extra_run_not_a_fix():
    md = render([raw([run("c1", "FAIL")]), raw([run("c1", "PASS")], "evals/raw/again.json")])
    assert "| c1 | FAIL (b_final_profile) (aaaaaaa) | PASS (aaaaaaa) | extra run, same commit | — |" in md


def test_missing_metadata_and_cases_are_flagged_not_inferred():
    legacy = run("c1", "PASS")
    del legacy["model"], legacy["commit"], legacy["dirty"]
    md = render([raw([legacy])], ["c1", "c2"])
    assert "model `not recorded`" in md and "headline pass is missing cases: c2" in md
