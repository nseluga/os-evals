"""Tests for stats.py pairing, scorecard banners/reason lines, and run.sh guards.

Run: python3 harness/test_pairing.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402

RUN_SH = Path(__file__).resolve().parent.parent / "run.sh"
STATS_PY = Path(stats.__file__)


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_pairs_follow_user_order():
    allr = {"bare", "claude-md", "memory", "skills", "full"}
    check("bare,skills", stats.select_pairs(allr, ["bare", "skills"]), [("bare", "skills")])
    check("bare,memory,full", stats.select_pairs(allr, ["bare", "memory", "full"]),
          [("bare", "memory"), ("memory", "full")])
    check("bare,full", stats.select_pairs(allr, ["bare", "full"]), [("bare", "full")])
    check("reversed order kept", stats.select_pairs(allr, ["full", "bare"]), [("full", "bare")])
    check("only present layers", stats.select_pairs({"bare", "skills"}, ["bare", "skills"]),
          [("bare", "skills")])
    check("single layer -> none", stats.select_pairs({"bare"}, ["bare"]), [])


def test_ab_pairing_with_sentinel_bare():
    r = {"full@A", "full@B", "bare"}
    check("A/B + bare", stats.select_pairs(r, ["full@A", "full@B"]), [("full@A", "full@B")])
    check("A/B no bare", stats.select_pairs({"full@A", "full@B"}, ["full@A", "full@B"]),
          [("full@A", "full@B")])


def test_legacy_int_pairs():
    check("legacy", stats.select_pairs({1, 2, 3, 4}), [(1, 2), (2, 3), (3, 4), (1, 4)])


def _row(task, rung, passed, **kw):
    r = {"task": task, "rung": rung, "model": "m", "passed": passed, "infra_error": False,
         "total_tokens": 10, "cost_usd": 0.1, "curated_skill": ""}
    r.update(kw)
    return r


def test_non_adjacent_layers_compare_and_empty_message():
    rows = [_row("t1", "bare", False), _row("t1", "skills", True),
            _row("t2", "bare", True), _row("t2", "skills", True)]
    data = {"os_sha": "x", "scores": rows, "layer_order": ["bare", "skills"]}
    st = stats.compute_stats(rows, ["bare", "skills"])
    check("pair key", list(st["rung_pairs"]["m"]), ["bare_vs_skills"])
    md = stats.render_markdown(data, st, stats.token_summary(rows))
    check("no empty-pairs text when paired", "No rung pairs to compare" in md, False)

    one = [_row("t1", "bare", True), _row("t2", "bare", True)]
    data = {"os_sha": "x", "scores": one, "layer_order": ["bare"]}
    md = stats.render_markdown(data, stats.compute_stats(one, ["bare"]), stats.token_summary(one))
    check("empty pairs stated", "No rung pairs to compare" in md, True)
    check("no discriminating verdict when empty", "NO DISCRIMINATING SIGNAL" in md, False)


def test_filename_round_trip():
    import score
    f = score._meta_from_filename
    check("effort segment", f("20261015T010203Z_canary-skill_bare_haiku_low.json"),
          {"task": "canary-skill", "rung": "bare", "model": "haiku", "effort": "low", "repeat_index": None})
    check("effort + repeat + multiword model", f("20261015T010203Z_t_full_claude_opus_4_7_xhigh_r2.json")["effort"], "xhigh")
    check("multiword model kept whole", f("20261015T010203Z_t_full_claude_opus_4_7_xhigh_r2.json")["model"], "claude_opus_4_7")
    check("repeat index", f("20261015T010203Z_t_full_claude_opus_4_7_xhigh_r2.json")["repeat_index"], 2)
    check("old filename -> default", f("20261001T010203Z_t_full_opus.json")["effort"], "default")
    check("old multiword -> default", f("20261001T010203Z_t_full_claude_sonnet_4_6_r1.json")["model"], "claude_sonnet_4_6")
    check("old legacy rung", f("20260901T010203Z_t_rung2_sonnet.json")["rung"], 2)
    check("effort-named model is not an effort", f("20261001T010203Z_t_full_max.json")["effort"], "default")


def _run_file(tmp, name, meta, extra=None):
    d = Path(tmp)
    (d / "t" / "x").mkdir(parents=True, exist_ok=True)
    (d / "t" / "x" / "prompt.md").write_text("p")
    (d / "t" / "x" / "check.sh").write_text("#!/bin/bash\nexit 0\n")
    (d / "t" / "x" / "check.sh").chmod(0o755)
    f = d / name
    f.write_text(json.dumps({"type": "result", "result": "ok", "num_turns": 1, "total_cost_usd": 0.01,
                             "usage": {"input_tokens": 1, "output_tokens": 2}, "_meta": meta, **(extra or {})}))
    return f, d / "t"


def test_score_effort_and_model_usage():
    import score
    with tempfile.TemporaryDirectory() as t:
        mu = {"claude-haiku-4-5": {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 100,
                                    "cacheCreationInputTokens": 1000, "costUSD": 0.01},
              "claude-sonnet-4-6": {"inputTokens": 1, "outputTokens": 2, "cacheReadInputTokens": 3,
                                     "cacheCreationInputTokens": 4}}
        f, tasks = _run_file(t, "20261015T010203Z_x_bare_haiku_low.json",
                             {"task": "x", "rung": "bare", "model": "haiku", "effort": "low"}, {"modelUsage": mu})
        r = score.score_run(f, tasks)
        check("model = base:effort", (r["model"], r["base_model"], r["effort"]), ("haiku:low", "haiku", "low"))
        check("total_tokens sums modelUsage across models", r["total_tokens"], 10 + 20 + 100 + 1000 + 1 + 2 + 3 + 4)
        check("old usage fields kept", (r["input_tokens"], r["output_tokens"]), (1, 2))
        f, tasks = _run_file(t, "20261015T010203Z_x_bare_haiku_low2.json",
                             {"task": "x", "rung": "bare", "model": "haiku"})
        r = score.score_run(f, tasks)
        check("no modelUsage -> usage fallback", r["total_tokens"], 3)
        check("old _meta w/o effort -> default", r["model"], "haiku:default")
        f, tasks = _run_file(t, "20261015T010203Z_x_bare_haiku_max.json", {"task": "x", "rung": "bare", "model": "haiku"})
        check("effort from filename when _meta lacks it", score.score_run(f, tasks)["model"], "haiku:max")


def _crow(task, model, cost, rung="bare", effort="high", passed=True, **kw):
    return {"task": task, "rung": rung, "model": f"{model}:{effort}", "base_model": model, "effort": effort,
            "passed": passed, "cost_usd": cost, **kw}


def test_model_ratios_and_effort_section():
    rows = [_crow("a", "sonnet", 1.0), _crow("b", "sonnet", 2.0), _crow("a", "opus", 2.0), _crow("b", "opus", 6.0),
            _crow("a", "haiku", 0.5, effort="low")]  # haiku only at a different effort -> unmatched
    r = stats.model_ratios(rows)
    check("median ratio over matched cells", r["opus"], 2.5)
    check("no matched cell -> UNMEASURED", r["haiku"], "UNMEASURED")
    check("sonnet not listed", "sonnet" in r, False)
    check("no sonnet at all -> UNMEASURED", stats.model_ratios([_crow("a", "opus", 2.0)]), {"opus": "UNMEASURED"})
    check("infra/sentinel excluded", stats.model_ratios(rows + [_crow("c", "opus", 99, infra_error=True)]), r)
    old = [{"task": "a", "rung": "bare", "model": "sonnet", "passed": True, "cost_usd": 1.0},
           {"task": "a", "rung": "bare", "model": "opus", "passed": True, "cost_usd": 3.0}]
    check("old records (no effort) match as default", stats.model_ratios(old), {"opus": 3.0})
    md = "\n".join(stats.model_ratios_section(rows))
    check("section prints UNMEASURED", "- haiku: UNMEASURED" in md and "- opus: 2.50x" in md, True)

    # effort sign-test: low fails b, high passes both; medium in the middle
    rows = [_crow("a", "sonnet", 1, effort="low"), _crow("b", "sonnet", 1, effort="low", passed=False),
            _crow("a", "sonnet", 2, effort="medium"), _crow("b", "sonnet", 2, effort="medium", passed=False),
            _crow("a", "sonnet", 3), _crow("b", "sonnet", 3)]
    lines = stats.effort_section(rows)
    body = "\n".join(lines)
    check("adjacent pairs only", ("low -> medium" in body, "medium -> high" in body, "low -> high" in body),
          (True, True, False))
    check("medium->high: high won 1/1", "medium -> high** higher effort won 1/1 (ties=1)" in body, True)
    check("low->medium: n/a-free tie", "low -> medium** higher effort won n/a (no discriminating tasks)" in body, True)
    check("single effort -> no section", stats.effort_section([_crow("a", "sonnet", 1)]), [])
    check("default-effort records ignored", stats.effort_section(
        [_crow("a", "sonnet", 1, effort="default"), _crow("a", "sonnet", 1)]), [])
    data = {"os_sha": "x", "scores": rows}
    md = stats.render_markdown(data, stats.compute_stats(rows), stats.token_summary(rows))
    check("wired into scorecard", "## Effort Sign-Test" in md, True)


def test_banner():
    rows = [_row("t1", "bare", True)]
    data = {"os_sha": "x", "scores": rows, "scored_run_ids": ["20260101T000000Z_a.json"]}
    st = stats.compute_stats(rows)
    ts = stats.token_summary(rows)
    md = stats.render_markdown(data, st, ts, matrix_exit=3, planned=10)
    top = md.split("\n\n")[1]
    assert "INCOMPLETE MATRIX" in top and "code 3" in top and "1 runs present of 10 planned" in top, top
    print("  ok  banner names exit code and present/planned")
    check("no banner when clean", "INCOMPLETE MATRIX" in stats.render_markdown(data, st, ts, 0, 1), False)
    check("banner when short w/o exit", "INCOMPLETE MATRIX" in stats.render_markdown(data, st, ts, 0, 5), True)
    p = subprocess.run([sys.executable, str(STATS_PY), "--matrix-exit", "7", "--planned-runs", "4"],
                       input=json.dumps(data), capture_output=True, text=True)
    check("CLI banner", "code 7" in p.stdout, True)


def test_reason_lines_and_single_repeat():
    reasons = ["no_result", "api_error", "check_unrunnable", "check_timeout", "score_exception",
               "no_majority", "rate_limited", "contaminated"]
    rows = [_row("keep", "bare", True), _row("keep", "full", True)]
    for i, rsn in enumerate(reasons):
        rows.append(_row(f"task{i}", "bare", False, infra_error=True, infra_reason=rsn))
    rows.append(_row("task0", "full", False, infra_error=True, infra_reason="no_result"))
    rows.append(_row("solo", "bare", True, repeat_majority=True, valid_repeats=1, repeat_total=3))
    data = {"os_sha": "x", "scores": rows}
    md = stats.render_markdown(data, stats.compute_stats(rows), stats.token_summary(rows))
    lines = md.splitlines()
    for i, rsn in enumerate(reasons):
        hit = [l for l in lines if f"[{rsn}]" in l or (rsn == "contaminated" and l.startswith("⚠️ contaminated"))]
        check(f"line for {rsn}", len(hit), 1)
        assert f"task{i} (" in hit[0], hit[0]
    contam = [l for l in lines if l.startswith("⚠️ contaminated")]
    check("contaminated own line", "task7" in contam[0] and "task0" not in contam[0], True)
    nr = [l for l in lines if "[no_result]" in l][0]
    assert "task0 (2)" in nr, nr
    print("  ok  no_result groups both task0 runs on one line")
    single = [l for l in lines if "single valid repeat" in l]
    check("single-valid line", len(single) == 1 and "solo @ bare" in single[0], True)


def test_run_sh_rejects_same_sha_twice():
    with tempfile.TemporaryDirectory() as d:
        git = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "a"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "b"], check=True)
        sha = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        env = {**os.environ, "OS_DIR": d}
        for a, b in ((sha[:7], sha[:7]), ("HEAD", sha), ("HEAD", "HEAD")):
            p = subprocess.run(["bash", str(RUN_SH), "--os-sha", a, "--os-sha", b, "--dry-run", "--no-build"],
                               capture_output=True, text=True, env=env)
            check(f"same sha {a[:4]}/{b[:4]} exit", p.returncode, 1)
            assert "same commit" in p.stderr, p.stderr
        p = subprocess.run(["bash", str(RUN_SH), "--os-sha", "HEAD~1", "--os-sha", "HEAD", "--dry-run",
                            "--no-build"], capture_output=True, text=True, env=env)
        check("different shas not rejected as duplicate", "same commit" in p.stderr, False)


if __name__ == "__main__":
    test_pairs_follow_user_order()
    test_ab_pairing_with_sentinel_bare()
    test_legacy_int_pairs()
    test_non_adjacent_layers_compare_and_empty_message()
    test_filename_round_trip()
    test_score_effort_and_model_usage()
    test_model_ratios_and_effort_section()
    test_banner()
    test_reason_lines_and_single_repeat()
    test_run_sh_rejects_same_sha_twice()
    print("ALL PASS")
