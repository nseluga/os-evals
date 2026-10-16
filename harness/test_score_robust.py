"""Tests for score.py robustness: infra classification, null-safe scoring, check.sh launch
failures, main never dropping a run, and majority ties.

Run: python3 harness/test_score_robust.py
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

SCORE_PY = Path(score.__file__)


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _env(tmp: Path, check_body="#!/bin/sh\ngrep -q PASS-MARK && exit 0\nexit 1\n", mode=0o755):
    """tasks/demo/check.sh: exits 0 only if the transcript contains PASS-MARK."""
    d = tmp / "tasks" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    sh = d / "check.sh"
    sh.write_text(check_body)
    sh.chmod(mode)
    return tmp / "tasks"


def _run(tmp: Path, transcript, name="20260101T000000Z_demo_rung1_m.json", raw=None) -> Path:
    f = tmp / name
    f.write_text(raw if raw is not None else json.dumps(transcript))
    return f


def _t(**kw):
    t = {"result": "ok", "is_error": False, "subtype": "success",
         "usage": {"input_tokens": 5, "output_tokens": 5}, "num_turns": 1, "total_cost_usd": 0.01,
         "_meta": {"task": "demo", "rung": 1, "model": "m"}}
    t.update(kw)
    return t


def test_api_error_is_infra():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        r = score.score_run(_run(tmp, _t(result="API Error: 503 overloaded", is_error=True,
                                         subtype="error_during_execution")), tasks)
        check("503 is_error infra_error", r["infra_error"], True)
        check("503 is_error reason", r["infra_reason"], "api_error")
        check("503 is_error not passed", r["passed"], False)
        r = score.score_run(_run(tmp, _t(result="Connection reset by peer", is_error=True)), tasks)
        check("conn reset reason", r["infra_reason"], "api_error")


def test_answer_mentioning_503_is_scored():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        r = score.score_run(_run(tmp, _t(result="PASS-MARK: a 503 overloaded error means retry",
                                         is_error=False)), tasks)
        check("503 mention infra_error", r["infra_error"], False)
        check("503 mention scored by check.sh", r["passed"], True)
        check("503 mention rc", r["check_rc"], 0)
        r = score.score_run(_run(tmp, _t(result="a 503 overloaded error means retry")), tasks)
        check("503 mention fail is a model fail", (r["passed"], r["infra_error"]), (False, False))


def test_no_result_is_infra():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        t = _t(result="PASS-MARK")
        t["_meta"]["no_result"] = True
        r = score.score_run(_run(tmp, t), tasks)
        check("no_result infra", (r["infra_error"], r["infra_reason"], r["passed"]),
              (True, "no_result", False))
        check("classify_infra pure", score.classify_infra(t), "no_result")
        check("classify_infra clean", score.classify_infra(_t()), None)


def test_budget_stop_scored_normally():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        t = _t(result="Reached maximum budget ($1.50)", is_error=True, subtype="error_max_budget_usd")
        r = score.score_run(_run(tmp, t), tasks)
        check("budget not infra", r["infra_error"], False)
        check("budget flagged", r["budget_exceeded"], True)
        check("budget scored by check.sh (fail)", r["check_rc"], 1)
        # even when the stop text also looks like an API error, the budget guard wins
        t = _t(result="Error: reached maximum budget ($1.50); last call 503 overloaded",
               is_error=True, subtype="error_max_budget_usd")
        r = score.score_run(_run(tmp, t), tasks)
        check("budget text with api-ish words not infra", (r["infra_error"], r["budget_exceeded"]), (False, True))
        check("normal run not budget", score.score_run(_run(tmp, _t()), tasks)["budget_exceeded"], False)


def test_null_fields_do_not_raise():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        r = score.score_run(_run(tmp, _t(usage=None, num_turns=None, total_cost_usd=None,
                                         result=None, stop_reason=None)), tasks)
        check("usage null total_tokens", r["total_tokens"], 0)
        check("usage null cost", r["cost_usd"], 0)
        r = score.score_run(_run(tmp, {"result": "x", "_meta": None, "usage": {"output_tokens": None}},
                                 name="20260101T000000Z_demo_rung1_m.json"), tasks)
        check("meta null handled", (r["task"], r["total_tokens"]), ("demo", 0))


def test_check_unrunnable_and_exit1():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp, mode=0o644)  # not executable -> PermissionError on launch
        r = score.score_run(_run(tmp, _t(result="PASS-MARK")), tasks)
        check("non-exec check.sh", (r["infra_error"], r["infra_reason"], r["passed"]),
              (True, "check_unrunnable", False))
        tasks = _env(tmp, check_body="#!/nonexistent/interp\nexit 0\n")
        r = score.score_run(_run(tmp, _t()), tasks)
        check("missing interpreter", r["infra_reason"], "check_unrunnable")
        tasks = _env(tmp, check_body="#!/bin/sh\nexit 127\n")
        r = score.score_run(_run(tmp, _t()), tasks)
        check("exit 127", r["infra_reason"], "check_unrunnable")
        tasks = _env(tmp, check_body="#!/bin/sh\nexit 1\n")
        r = score.score_run(_run(tmp, _t()), tasks)
        check("exit 1 stays model fail", (r["infra_error"], r["passed"], r["check_rc"]), (False, False, 1))
        tasks = _env(tmp, check_body="#!/bin/sh\nexit 2\n")
        r = score.score_run(_run(tmp, _t()), tasks)
        check("exit 2 stays check_exit_2", r["infra_reason"], "check_exit_2")


def test_check_timeout():
    real = score.run_check

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("check.sh", 300)
    score.run_check = boom
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            tasks = _env(tmp)
            r = score.score_run(_run(tmp, _t()), tasks)
            check("check timeout", (r["infra_error"], r["infra_reason"]), (True, "check_timeout"))
    finally:
        score.run_check = real


def test_main_never_drops_a_run():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tasks = _env(tmp)
        runs = tmp / "runs"
        runs.mkdir()
        _run(runs, _t(result="PASS-MARK"), name="20260101T000000Z_demo_rung1_m.json")
        _run(runs, None, name="20260101T000001Z_demo_rung2_claude_sonnet_4_6_r2.json", raw="{not json")
        p = subprocess.run([sys.executable, str(SCORE_PY), "--runs-dir", str(runs),
                            "--tasks-dir", str(tasks)], capture_output=True, text=True)
        out = json.loads(p.stdout)  # full scores written to stdout even on failure
        check("main exits non-zero", p.returncode != 0, True)
        check("both runs present", len([x for x in out["scores"] if not x.get("repeat_majority")]), 2)
        bad = [s for s in out["scores"] if s["infra_reason"] == "score_exception" and not s.get("repeat_majority")]
        check("one score_exception", len(bad), 1)
        b = bad[0]
        check("exception record identity", (b["task"], b["rung"], b["model"], b["repeat_index"]),
              ("demo", 2, "claude_sonnet_4_6:default", 2))
        check("exception text kept", "JSONDecodeError" in b["check_output"], True)
        check("exception excluded", (b["infra_error"], b["passed"]), (True, False))
        # usage: null run alone scores cleanly with exit 0
        (runs / "20260101T000001Z_demo_rung2_claude_sonnet_4_6_r2.json").unlink()
        _run(runs, _t(usage=None), name="20260101T000002Z_demo_rung3_m.json")
        p = subprocess.run([sys.executable, str(SCORE_PY), "--runs-dir", str(runs),
                            "--tasks-dir", str(tasks)], capture_output=True, text=True)
        check("usage null exit 0", p.returncode, 0)
        check("usage null kept", len(json.loads(p.stdout)["scores"]), 2)


def _rec(i, passed, infra):
    return {"file": f"20260101T000000Z_demo_rung1_m_r{i}.json", "task": "demo", "rung": 1,
            "model": "m", "passed": passed, "infra_error": infra,
            "infra_reason": "rate_limited" if infra else None, "check_rc": 2 if infra else int(not passed),
            "is_repeat_individual": True, "repeat_index": i, "repeat_total": 4,
            "cost_usd": 0.1, "total_tokens": 10}


def test_majority_tie_is_no_majority():
    (m,) = score.compute_majority_records(
        [_rec(1, True, False), _rec(2, False, False), _rec(3, False, True), _rec(4, False, True)])
    check("tie infra_error", m["infra_error"], True)
    check("tie reason", m["infra_reason"], "no_majority")
    check("tie not passed", m["passed"], False)
    check("tie valid_repeats", m["valid_repeats"], 2)


def test_single_valid_repeat_accepted():
    (m,) = score.compute_majority_records(
        [_rec(1, True, False), _rec(2, False, True), _rec(3, False, True), _rec(4, False, True)])
    check("single valid verdict", (m["passed"], m["infra_error"], m["valid_repeats"]), (True, False, 1))


if __name__ == "__main__":
    test_api_error_is_infra()
    test_answer_mentioning_503_is_scored()
    test_no_result_is_infra()
    test_budget_stop_scored_normally()
    test_null_fields_do_not_raise()
    test_check_unrunnable_and_exit1()
    test_check_timeout()
    test_main_never_drops_a_run()
    test_majority_tie_is_no_majority()
    test_single_valid_repeat_accepted()
    print("ALL PASS")
