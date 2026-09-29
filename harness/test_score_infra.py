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


if __name__ == "__main__":
    test_majority_ignores_infra()
    test_all_infra_group_is_infra()
    test_no_infra_plain_majority()
    test_workspace_missing_skips_check()
    test_workspace_present_runs_check()
    print("ALL PASS")
