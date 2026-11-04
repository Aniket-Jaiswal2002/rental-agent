from evals.checks import CHECKS
from evals.report import render

A, B = "a" * 40, "b" * 40


def run(case, status, commit=A, dirty=False, effort="low", **kw):
    checks = {name: [] for name in CHECKS}
    if status == "FAIL":
        checks["b_final_profile"] = ["budget_max: expected 30000, got 20000"]
    base = {"case": case, "model": "test-model", "commit": commit, "dirty": dirty, "reasoning_effort": effort, "status": status, "note": "",
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
    assert "model `test-model` · reasoning_effort `low` · commit `aaaaaaa`" in md
    assert "Run average per call: 1,500 total (1,200 prompt + 300 completion)" in md
    assert "| Fresh (first message, empty profile) | 2,053 | 1,452 |" in md
    assert "1,369" not in md


def test_follow_up_after_fix_is_listed_beside_first_result_and_headline_unchanged(monkeypatch):
    import evals.report as rep
    monkeypatch.setattr(rep, "commits_between", lambda base, head: [f"{head[:7]} Ask about conflicting budget", "ccccccc Fix read-back"])
    md = render([raw([run("c1", "FAIL"), run("c2", "PASS")]), raw([run("c1", "PASS", commit=B)], "evals/raw/rerun.json")])
    assert "**Headline: 1/2 runs passed (50%)" in md  # the fix does not change the headline
    assert "| c1 | 0/1 | 0 | b_final_profile ×1 |" in md
    assert ("| c1 | FAIL (b_final_profile) (aaaaaaa, effort low) | PASS (bbbbbbb, effort low) | after fix | "
            "bbbbbbb Ask about conflicting budget<br>ccccccc Fix read-back |") in md


def test_rerun_on_same_commit_is_an_extra_run_not_a_fix():
    md = render([raw([run("c1", "FAIL")]), raw([run("c1", "PASS")], "evals/raw/again.json")])
    assert "| c1 | FAIL (b_final_profile) (aaaaaaa, effort low) | PASS (aaaaaaa, effort low) | extra run, same commit | — |" in md


def test_missing_metadata_and_cases_are_flagged_not_inferred():
    legacy = run("c1", "PASS")
    del legacy["model"], legacy["commit"], legacy["dirty"], legacy["reasoning_effort"]
    md = render([raw([legacy])], ["c1", "c2"])
    assert "model `not recorded`" in md and "reasoning_effort `not recorded`" in md and "headline pass is missing cases: c2" in md


def test_same_commit_other_effort_and_unrecorded_effort_are_labelled(monkeypatch):
    md = render([raw([run("c1", "FAIL"), run("c2", "FAIL")]),
                 raw([run("c1", "FAIL", effort="medium"), run("c2", "PASS", effort=None)], "evals/raw/medium.json")])
    assert "| c1 | FAIL (b_final_profile) (aaaaaaa, effort low) | FAIL (b_final_profile) (aaaaaaa, effort medium) | same commit, other settings | — |" in md
    assert "PASS (aaaaaaa, effort not recorded) | same commit, other settings |" in md


def test_commits_between_lists_every_code_commit_and_skips_eval_output_commits(tmp_path, monkeypatch):
    import subprocess
    import evals.report as rep
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path,
                                    capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q")
    def commit(path, msg):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(msg)
        git("add", "-A"); git("commit", "-q", "-m", msg)
        return git("rev-parse", "HEAD")
    base = commit("app.py", "headline code")
    commit("app.py", "fix one")
    commit("evals/raw/x.json", "add raw results")
    head = commit("app2.py", "fix two")
    monkeypatch.setattr(rep, "ROOT", tmp_path)
    assert [s.split(" ", 1)[1] for s in rep.commits_between(base, head)] == ["fix one", "fix two"]
    assert rep.commits_between(base, "f" * 40)[0].endswith("(not in this repository's history)")