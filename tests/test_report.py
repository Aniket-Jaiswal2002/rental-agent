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

def test_effort_from_run_command_note_is_footnoted_and_never_overrides_recorded(tmp_path, monkeypatch):
    import json
    import evals.report as rep
    monkeypatch.setattr(rep, "EFFORT_NOTES", {"note": "from run commands; not recorded in these raw files",
                                              "files": {"old.json": "medium", "new.json": "medium"}})
    legacy = run("c1", "FAIL")
    del legacy["reasoning_effort"]  # a pass from before the field existed
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"results": [legacy]}))
    new = tmp_path / "new.json"
    new.write_text(json.dumps({"reasoning_effort": "low", "results": [run("c1", "PASS", commit=B, effort="low")]}))
    monkeypatch.setattr(rep, "commits_between", lambda base, head: ["bbbbbbb fix"])
    md = render([rep.load_raw(old), rep.load_raw(new)])
    assert "reasoning_effort `medium†`" in md
    assert "(aaaaaaa, effort medium†) | PASS (bbbbbbb, effort low) | after fix |" in md  # recorded value wins
    assert "† reasoning_effort from run commands; not recorded in these raw files" in md


def test_effort_notes_file_matches_the_committed_raw_files():
    import evals.report as rep
    from pathlib import Path
    raw_dir = Path(rep.HERE) / "raw"
    for name in rep.EFFORT_NOTES["files"]:
        assert (raw_dir / name).exists() and "reasoning_effort" not in json_load(raw_dir / name)


def json_load(p):
    import json
    return json.loads(p.read_text(encoding="utf-8"))


def test_fill_readme_lead_sentence_then_table_hashes_only_in_headers():
    from scripts.fill_readme import fill, section
    head = raw([run("01_a", "PASS"), run("03_b", "FAIL"), run("06_c", "FAIL")])
    follow = [raw([run("03_b", "FAIL", commit=B), run("06_c", "PASS", commit=B)]), raw([run("03_b", "FAIL", commit=B, effort="medium")])]
    sec = section(head, follow, final_pending="ccccccc")
    assert sec.startswith("On the first full pass, 1 of the 3 scripted conversations passed (1 run per case).")
    assert "A newer full pass is running" in sec
    assert "| Case | Headline `aaaaaaa` | After fix `bbbbbbb` | Full pass `ccccccc` |" in sec
    assert "| 03_b | FAIL | FAIL (effort low), FAIL (effort medium) | running |" in sec
    assert "[evals/results.md](evals/results.md)" in sec

    final = raw([run("01_a", "FAIL", commit="c" * 40), run("03_b", "FAIL", commit="c" * 40), run("06_c", "PASS", commit="c" * 40)])
    later = [raw([run("01_a", "PASS", commit="d" * 40)])]
    done = section(head, follow, final=final, later=later, limitations=["03"])
    lead = done.split("\n\n")[0]
    assert ("The latest full pass scored 1/3: 06 now passes; 01 newly failed (it passed again on a re-run after fixes); "
            "case 03, which is a documented limitation, still fails.") in lead
    assert "`" not in lead  # commit ids live only in the table headers
    assert "| 01_a | PASS | — | FAIL | PASS |" in done and done.startswith("On the first full pass, 1 of the 3")

    readme = "intro\n<!-- EVAL-RESULTS:START old note -->\n> PLACEHOLDER\n<!-- EVAL-RESULTS:END -->\noutro\n"
    out = fill(readme, sec)
    assert "PLACEHOLDER" not in out and out.startswith("intro\n") and out.endswith("<!-- EVAL-RESULTS:END -->\noutro\n")
    assert fill(out, done).count("On the first full pass") == 1  # refilling replaces


def test_fill_readme_summary_sentence_from_raw_data():
    from scripts.fill_readme import summary_sentence
    head = raw([run("01_a", "PASS"), run("03_b", "FAIL"), run("06_c", "FAIL")])
    final = raw([run("01_a", "PASS", commit=B), run("03_b", "FAIL", commit=B), run("06_c", "FAIL", commit=B)])
    assert summary_sentence(head, final, ["03"]) == (
        "On the first full eval pass, 1 of the 3 scripted conversations passed; the latest full pass also scored 1/3, "
        "and cases 03 and 06 failed in both.")  # 06 is not a documented limitation, so no such claim
    final["results"][2]["status"] = "PASS"
    assert summary_sentence(head, final, ["03"]).endswith(
        "the latest full pass scored 2/3, and case 03, which is a documented limitation, failed in both.")
    assert summary_sentence(head, None, []) == ("On the first full eval pass, 1 of the 3 scripted conversations passed; "
                                                "the failures were cases 03 and 06.")


def test_fill_readme_latency_block_from_turn_timings(monkeypatch):
    import scripts.fill_readme as fr
    timings = [{"total_ms": 30000, "llm_ms": ms, "llm_calls": 2, "wait_ms": 20000} for ms in (1000, 2000, 3000)]
    final = raw([run("01_a", "PASS", commit="c" * 40, turn_timings=timings)])
    monkeypatch.setattr(fr, "_code_commits_since", lambda sha: 0)
    text = fr.latency(final)
    assert "on `ccccccc` (text mode, 3 turns, 6 LLM calls, `reasoning_effort` low)" in text
    assert "| Per turn (all of the turn's LLM calls) | 2.0 s | 3.0 s |" in text
    assert "2.0 LLM calls per turn on average, about 1.0 s of model time per call" in text
    assert "a median of about 20 s per turn" in text and "not the latest commit" not in text
    monkeypatch.setattr(fr, "_code_commits_since", lambda sha: 4)
    assert "so these numbers describe `ccccccc`, not the latest commit." in fr.latency(final)


def test_fill_readme_later_reruns_get_their_own_column_after_the_full_pass():
    from scripts.fill_readme import section
    head = raw([run("01_a", "PASS"), run("03_b", "FAIL")])
    final = raw([run("01_a", "FAIL", commit="c" * 40), run("03_b", "FAIL", commit="c" * 40)])
    later = [raw([run("01_a", "PASS", commit="d" * 40)])]
    sec = section(head, [], final=final, later=later)
    assert "| Case | Headline `aaaaaaa` | Full pass `ccccccc` | Re-run `ddddddd` |" in sec
    assert "| 01_a | PASS | FAIL | PASS |" in sec and "| 03_b | FAIL | FAIL | — |" in sec