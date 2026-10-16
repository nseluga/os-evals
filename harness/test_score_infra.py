"""Tests for infra handling in score.py.

Verifies:
1. Majority vote over repeats ignores infra runs (pass/infra/pass -> pass, valid_repeats 2; a pass/infra/fail tie is no_majority, see test_score_robust.py)
2. A group is infra only when every repeat is infra
3. No infra: plain majority still works (pass/fail/fail -> fail)
4. workspace_missing: check.sh is NOT executed, record is infra with check_rc 2
5. workspace present: check.sh does run (contrast case)

Run: python3 harness/test_score_infra.py
"""
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _rec(i, passed, infra):
    return {
        "file": f"20260101T000000Z_demo_rung1_m_r{i}.json",
        "task": "demo", "rung": 1, "model": "m",
        "passed": passed, "infra_error": infra,
        "infra_reason": "rate_limited" if infra else None,
        "check_rc": 2 if infra else (0 if passed else 1),
        "is_repeat_individual": True, "repeat_index": i, "repeat_total": 3,
        "cost_usd": 0.1, "total_tokens": 10,
    }


def test_majority_ignores_infra():
    (m,) = score.compute_majority_records(
        [_rec(1, True, False), _rec(2, False, True), _rec(3, True, False)])
    check("pass/infra/pass passed", m["passed"], True)
    check("pass/infra/pass valid_repeats", m["valid_repeats"], 2)
    check("pass/infra/pass infra_repeats", m["infra_repeats"], 1)
    check("pass/infra/pass infra_error", m["infra_error"], False)


def test_all_infra_group_is_infra():
    (m,) = score.compute_majority_records([_rec(i, False, True) for i in (1, 2, 3)])
    check("all-infra infra_error", m["infra_error"], True)
    check("all-infra passed", m["passed"], False)
    check("all-infra valid_repeats", m["valid_repeats"], 0)
    check("all-infra check_rc", m["check_rc"], 2)


def test_no_infra_plain_majority():
    (m,) = score.compute_majority_records(
        [_rec(1, True, False), _rec(2, False, False), _rec(3, False, False)])
    check("pass/fail/fail passed", m["passed"], False)
    check("pass/fail/fail valid_repeats", m["valid_repeats"], 3)
    check("pass/fail/fail infra_error", m["infra_error"], False)


def _make_task_and_run(tmp: Path, workspace_dir: str):
    """Task whose check.sh touches marker.txt if (and only if) it runs."""
    marker = tmp / "marker.txt"
    task_dir = tmp / "tasks" / "demo"
    task_dir.mkdir(parents=True)
    sh = task_dir / "check.sh"
    sh.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 0\n')
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR)
    run_file = tmp / "20260101T000000Z_demo_rung1_m.json"
    run_file.write_text(json.dumps({
        "result": "done",
        "_meta": {"task": "demo", "rung": 1, "model": "m", "workspace_dir": workspace_dir},
    }))
    return run_file, tmp / "tasks", marker


def test_workspace_missing_skips_check():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        run_file, tasks_dir, marker = _make_task_and_run(tmp, str(tmp / "no-such-ws"))
        rec = score.score_run(run_file, tasks_dir)
        check("workspace_missing infra_reason", rec["infra_reason"], "workspace_missing")
        check("workspace_missing infra_error", rec["infra_error"], True)
        check("workspace_missing check_rc", rec["check_rc"], 2)
        check("workspace_missing passed", rec["passed"], False)
        check("check.sh NOT executed", marker.exists(), False)


def test_workspace_present_runs_check():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        run_file, tasks_dir, marker = _make_task_and_run(tmp, str(tmp))
        rec = score.score_run(run_file, tasks_dir)
        check("workspace present infra_error", rec["infra_error"], False)
        check("workspace present passed", rec["passed"], True)
        check("check.sh executed", marker.exists(), True)


def test_timeout_is_infra():
    stub = {"type": "result", "is_error": True, "result": "no terminal result event (run truncated)",
            "usage": {"output_tokens": 3}}
    check("timed_out + stub result -> timeout",
          score.classify_infra({**stub, "_meta": {"timed_out": True, "no_result": False}}), "timeout")
    real = {"type": "result", "subtype": "success", "is_error": False, "result": "done"}
    check("timed_out + real result -> not timeout",
          score.classify_infra({**real, "_meta": {"timed_out": True}}), None)
    check("not timed_out + stub -> not timeout",
          score.classify_infra({**stub, "_meta": {"timed_out": False, "no_result": False}}), None)


def test_runaway_output_is_infra():
    # Real shape from 2026-10-01 Opus: --tools "" run wrote fake tool calls to the 128k cap.
    runaway = {"type": "result", "subtype": "error_max_budget_usd", "is_error": True, "result": None,
               "stop_reason": "max_tokens", "errors": ["Reached maximum budget ($1.5)"], "_meta": {}}
    check("max_tokens + no result -> runaway_output", score.classify_infra(runaway), "runaway_output")
    spent = {**runaway, "stop_reason": "end_turn"}
    check("budget stop without max_tokens -> real fail", score.classify_infra(spent), None)
    answered = {"type": "result", "subtype": "success", "is_error": False, "result": "done",
                "stop_reason": "max_tokens", "_meta": {}}
    check("max_tokens but answered -> not infra", score.classify_infra(answered), None)


def _task_dir(d, body, meta=""):
    t = Path(d) / "tasks" / "demo"
    t.mkdir(parents=True)
    (t / "check.sh").write_text("#!/bin/bash\n" + body)
    (t / "check.sh").chmod(0o755)
    (t / "meta.yaml").write_text(meta)
    return Path(d) / "tasks"


def test_trace_file_export():
    with tempfile.TemporaryDirectory() as d:
        tasks = _task_dir(d, 'cat >/dev/null; echo "TF=${TRACE_FILE:-unset}"; [ -z "${TRACE_FILE:-}" ] || cat "$TRACE_FILE"\n')
        tr = Path(d) / "runs" / "x.trace.jsonl"
        tr.parent.mkdir()
        tr.write_text("TRACE-BODY")
        os.environ["TRACE_FILE"] = "/stray/value"  # a caller's shell value must not leak into the check
        try:
            _, out, _ = score.run_check("demo", "{}", tasks, "")
            check("no trace_file arg -> TRACE_FILE unset", out, "TF=unset")
            _, out, _ = score.run_check("demo", "{}", tasks, "", str(tr.with_name("nope.trace.jsonl")))
            check("trace_file that does not exist -> unset", out, "TF=unset")
            _, out, _ = score.run_check("demo", "{}", tasks, "", str(tr))
            check("existing trace exported", out, f"TF={tr}\nTRACE-BODY")
        finally:
            del os.environ["TRACE_FILE"]


def test_score_run_exports_run_trace_and_layer_neutral():
    with tempfile.TemporaryDirectory() as d:
        tasks = _task_dir(d, 'cat >/dev/null; [ -f "${TRACE_FILE:-}" ] && [ "${TRACE_FILE##*.}" = jsonl ]\n',
                          "category: x\nlayer_neutral: true\n")
        run = Path(d) / "runs" / "20260101T000000Z_demo_bare_m_high.json"
        run.parent.mkdir()
        run.write_text(json.dumps({"type": "result", "result": "ok", "_meta": {"task": "demo", "rung": "bare", "model": "m"}}))
        r = score.score_run(run, tasks)
        check("no sidecar -> TRACE_FILE unset -> check fails", r["passed"], False)
        run.with_name(run.stem + ".trace.jsonl").write_text("{}")
        r = score.score_run(run, tasks)
        check("sidecar <stem>.trace.jsonl exported by score_run", r["passed"], True)
        check("layer_neutral passes through the score record", r["layer_neutral"], True)
        check("layer_neutral is not a sentinel", r["sentinel"], False)
        check("layer_neutral defaults False", score.read_task_meta(tasks, "nope")["layer_neutral"], False)


def test_validate_marker_not_inherited():
    # An operator-shell OS_EVALS_VALIDATE=1 must not reach check.sh: it would rebuild .git from the
    # model-written fixture.sh (running model code). gh-merge-live with .git removed must just fail rc 1.
    tasks = Path(__file__).resolve().parent.parent / "tasks"
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        shutil.copytree(tasks / "process/gh-merge-live/tests/good", ws)
        shutil.rmtree(ws / ".git", ignore_errors=True)
        os.environ["OS_EVALS_VALIDATE"] = "1"
        try:
            _, _, rc = score.run_check("process/gh-merge-live", "{}", tasks, str(ws))
        finally:
            del os.environ["OS_EVALS_VALIDATE"]
        check("OS_EVALS_VALIDATE in caller env -> rc 1", rc, 1)
        check("fixture.sh did not run (no .git rebuilt)", (ws / ".git").exists(), False)


if __name__ == "__main__":
    test_validate_marker_not_inherited()
    test_trace_file_export()
    test_score_run_exports_run_trace_and_layer_neutral()
    test_majority_ignores_infra()
    test_all_infra_group_is_infra()
    test_no_infra_plain_majority()
    test_workspace_missing_skips_check()
    test_workspace_present_runs_check()
    test_timeout_is_infra()
    test_runaway_output_is_infra()
    print("ALL PASS")
