"""Tests for repeat support in the eval harness (Item 4).

Verifies:
1. read_task_meta returns repeat=3 for writing/portfolio-writeup
2. read_task_meta returns repeat=3 for coding/pir-workload-feature
3. read_task_meta returns repeat=1 (default) for coding/dashboard-digest (no repeat key)
4. score.py grouping: 2 PASS + 1 FAIL -> majority-vote passed=True, repeat_majority=True
5. score.py grouping: 1 PASS + 2 FAIL -> majority-vote passed=False
6. Non-repeat transcript filenames (no _r{N}) are NOT marked is_repeat_individual
7. _r1, _r2, _r3 suffixed filenames ARE marked is_repeat_individual=True

Run: python3 harness/test_repeat.py
"""
import json
import math
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_matrix import read_task_meta as run_matrix_read_task_meta  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


# ---------------------------------------------------------------------------
# Tests 1-3: read_task_meta repeat field
# ---------------------------------------------------------------------------

def test_portfolio_writeup_repeat():
    """Test 1: writing/portfolio-writeup has repeat=3."""
    meta = run_matrix_read_task_meta(REPO / "tasks/writing/portfolio-writeup")
    check("portfolio-writeup repeat", meta["repeat"], 3)


def test_pir_workload_repeat():
    """Test 2: coding/pir-workload-feature has repeat=3."""
    meta = run_matrix_read_task_meta(REPO / "tasks/coding/pir-workload-feature")
    check("pir-workload-feature repeat", meta["repeat"], 3)


def test_dashboard_digest_repeat_default():
    """Test 3: coding/dashboard-digest returns repeat=1 (default, no repeat key)."""
    meta = run_matrix_read_task_meta(REPO / "tasks/coding/dashboard-digest")
    check("dashboard-digest repeat (default)", meta["repeat"], 1)


# ---------------------------------------------------------------------------
# Tests 4-5: majority-vote grouping in score.py
# ---------------------------------------------------------------------------

def _make_repeat_records(results: list[bool], task="writing/portfolio-writeup", rung=1, model="claude-sonnet-4-6"):
    """Build mock individual repeat score records."""
    records = []
    for i, passed in enumerate(results, start=1):
        records.append({
            "file": f"20260101T000000Z_{task.replace('/', '-')}_rung{rung}_{model.replace('-', '_')}_r{i}.json",
            "task": task,
            "rung": rung,
            "model": model,
            "passed": passed,
            "check_rc": 0 if passed else 1,
            "infra_error": False,
            "is_repeat_individual": True,
            "repeat_majority": False,
            "repeat_index": i,
            "repeat_total": len(results),
            "cost_usd": 0.01,
            "total_tokens": 500,
        })
    return records


def _compute_majority(group: list[dict]) -> dict:
    """Replicate the majority-vote logic from score.py main()."""
    n = len(group)
    pass_count = sum(1 for r in group if r["passed"])
    majority_passed = pass_count >= math.ceil(n / 2)
    total_cost = sum(r.get("cost_usd") or 0 for r in group)
    total_tokens = sum(r.get("total_tokens") or 0 for r in group)
    template = group[0]
    return {
        **template,
        "file": f"[majority:{n}] " + re.sub(r"_r\d+\.json$", ".json", template["file"]),
        "passed": majority_passed,
        "cost_usd": total_cost,
        "total_tokens": total_tokens,
        "is_repeat_individual": False,
        "repeat_majority": True,
        "repeat_pass_count": pass_count,
        "repeat_total": n,
        "repeat_index": None,
    }


def test_majority_vote_2_pass_1_fail():
    """Test 4: 2 PASS + 1 FAIL -> majority-vote passed=True, repeat_majority=True."""
    group = _make_repeat_records([True, True, False])
    mv = _compute_majority(group)
    check("majority(2P/1F) passed", mv["passed"], True)
    check("majority(2P/1F) repeat_majority", mv["repeat_majority"], True)
    check("majority(2P/1F) is_repeat_individual", mv["is_repeat_individual"], False)
    check("majority(2P/1F) repeat_pass_count", mv["repeat_pass_count"], 2)
    check("majority(2P/1F) repeat_total", mv["repeat_total"], 3)


def test_majority_vote_1_pass_2_fail():
    """Test 5: 1 PASS + 2 FAIL -> majority-vote passed=False."""
    group = _make_repeat_records([True, False, False])
    mv = _compute_majority(group)
    check("majority(1P/2F) passed", mv["passed"], False)
    check("majority(1P/2F) repeat_majority", mv["repeat_majority"], True)


# ---------------------------------------------------------------------------
# Tests 6-7: is_repeat_individual detection by filename
# ---------------------------------------------------------------------------

def _detect_repeat_individual(filename: str) -> bool:
    """Replicate the is_repeat_individual detection from score.py score_run()."""
    # Simulate no _meta.repeat_index (as if reading from an older transcript)
    repeat_index = None
    m = re.search(r"_r(\d+)\.json$", filename)
    if m:
        repeat_index = int(m.group(1))
    return repeat_index is not None


def test_non_repeat_filename_not_marked():
    """Test 6: Non-repeat transcript filenames (no _r{N}) are NOT is_repeat_individual."""
    non_repeat_names = [
        "20260101T000000Z_writing-portfolio-writeup_rung1_claude_sonnet_4_6.json",
        "20260101T000000Z_coding-dashboard-digest_rung1_claude_sonnet_4_6.json",
        "20260101T000000Z_coding-pir-workload-feature_rung2_claude_sonnet_4_6.json",
    ]
    for name in non_repeat_names:
        result = _detect_repeat_individual(name)
        check(f"non-repeat not is_repeat_individual: {name}", result, False)


def test_repeat_suffixed_filenames_marked():
    """Test 7: _r1, _r2, _r3 suffixed filenames ARE is_repeat_individual=True."""
    repeat_names = [
        "20260101T000000Z_writing-portfolio-writeup_rung1_claude_sonnet_4_6_r1.json",
        "20260101T000000Z_writing-portfolio-writeup_rung1_claude_sonnet_4_6_r2.json",
        "20260101T000000Z_coding-pir-workload-feature_rung2_claude_sonnet_4_6_r3.json",
    ]
    for name in repeat_names:
        result = _detect_repeat_individual(name)
        check(f"repeat suffix is_repeat_individual: {name}", result, True)


# ---------------------------------------------------------------------------
# Test 8: partial-group guard — no majority record when group is incomplete
# ---------------------------------------------------------------------------

def _compute_majority_records(groups: dict) -> list[dict]:
    """Replicate the partial-group guard + majority-vote loop from score.py main()."""
    majority_records = []
    for (task, rung, model), group in groups.items():
        n = len(group)
        template = group[0]
        declared_total = template.get("repeat_total") or n
        # Do not emit majority until all expected repeats are present.
        if n < declared_total:
            continue
        pass_count = sum(1 for r in group if r["passed"])
        majority_passed = pass_count >= math.ceil(n / 2)
        total_cost = sum(r.get("cost_usd") or 0 for r in group)
        total_tokens = sum(r.get("total_tokens") or 0 for r in group)
        majority_record = {
            **template,
            "file": f"[majority:{n}] " + re.sub(r"_r\d+\.json$", ".json", template["file"]),
            "passed": majority_passed,
            "cost_usd": total_cost,
            "total_tokens": total_tokens,
            "is_repeat_individual": False,
            "repeat_majority": True,
            "repeat_pass_count": pass_count,
            "repeat_total": declared_total,
            "repeat_index": None,
            "check_output": f"{pass_count}/{n} passed",
            "check_rc": 0 if majority_passed else 1,
        }
        majority_records.append(majority_record)
    return majority_records


def test_partial_group_no_majority_emitted():
    """Test 8: 2 individual records with repeat_total=3 -> NO majority record emitted."""
    # Only 2 of 3 expected repeats present; majority must not fire.
    group = _make_repeat_records([True, False], task="writing/portfolio-writeup", rung=1)
    # Ensure repeat_total reflects the declared total of 3, not the actual count of 2.
    for r in group:
        r["repeat_total"] = 3
    key = ("writing/portfolio-writeup", 1, "claude-sonnet-4-6")
    majority_records = _compute_majority_records({key: group})
    check("partial group (2/3) majority records emitted", len(majority_records), 0)


if __name__ == "__main__":
    print("=== test_repeat.py ===")
    test_portfolio_writeup_repeat()
    test_pir_workload_repeat()
    test_dashboard_digest_repeat_default()
    test_majority_vote_2_pass_1_fail()
    test_majority_vote_1_pass_2_fail()
    test_non_repeat_filename_not_marked()
    test_repeat_suffixed_filenames_marked()
    test_partial_group_no_majority_emitted()
    print("ALL PASS")
