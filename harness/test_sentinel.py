"""Tests for dashboard-digest sentinel implementation.

Verifies:
1. read_task_meta returns sentinel=True for dashboard-digest
2. read_task_meta returns sentinel=False (default) for non-sentinel task
3. run_matrix.py rung-filtering: sentinel tasks only run rung 1
4. stats.py: sentinel records excluded from sign-test and pass/fail table

Run: python3 harness/test_sentinel.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_matrix import read_task_meta  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


# --- Test 1: dashboard-digest has sentinel=True ---
def test_dashboard_digest_sentinel():
    meta = read_task_meta(REPO / "tasks/coding/dashboard-digest")
    check("dashboard-digest sentinel", meta["sentinel"], True)


# --- Test 2: pir-workload-feature has sentinel=False (default) ---
def test_non_sentinel_task():
    meta = read_task_meta(REPO / "tasks/coding/pir-workload-feature")
    check("pir-workload-feature sentinel", meta.get("sentinel", False), False)


# --- Test 3: rung-filtering logic in run_matrix.py ---
def test_rung_filtering_logic():
    """Confirm sentinel tasks only run rung 1 via the list comprehension in main()."""
    import run_matrix as rm

    import importlib, inspect
    source = inspect.getsource(rm.main)

    # Confirm the filter line exists as expected
    assert "task_rungs" in source, "FAIL: task_rungs variable not found in main()"
    assert "sentinel" in source, "FAIL: sentinel check not found in main()"
    assert 'r == 1 or not task_meta["sentinel"]' in source or "r == 1 or not task_meta['sentinel']" in source, \
        "FAIL: rung filter expression not found"
    print("  ok  run_matrix.py: rung filter `r == 1 or not task_meta[sentinel]` found in main()")

    # Simulate the filter directly
    all_rungs = [1, 2, 3, 4]
    task_meta_sentinel = {"sentinel": True}
    task_meta_normal = {"sentinel": False}
    rungs_sentinel = [r for r in all_rungs if r == 1 or not task_meta_sentinel["sentinel"]]
    rungs_normal = [r for r in all_rungs if r == 1 or not task_meta_normal["sentinel"]]

    check("sentinel task rungs", rungs_sentinel, [1])
    check("normal task rungs", rungs_normal, [1, 2, 3, 4])


# --- Test 4: stats.py excludes sentinel records from sign-test and pass/fail table ---
def test_stats_excludes_sentinels():
    import stats

    # Build mock scores: 1 sentinel at rung1, 2 non-sentinel across rungs 1-4
    sentinel_score = {
        "task": "coding/dashboard-digest",
        "rung": 1,
        "model": "claude-sonnet-4-6",
        "passed": False,
        "sentinel": True,
        "total_tokens": 500,
        "cost_usd": 0.001,
        "curated_skill": "",
        "category": "coding",
    }
    non_sentinel_a = [
        {"task": "coding/task-a", "rung": r, "model": "claude-sonnet-4-6",
         "passed": True, "sentinel": False, "total_tokens": 100, "cost_usd": 0.001,
         "curated_skill": "", "category": "coding"}
        for r in [1, 2, 3, 4]
    ]
    non_sentinel_b = [
        {"task": "coding/task-b", "rung": r, "model": "claude-sonnet-4-6",
         "passed": False, "sentinel": False, "total_tokens": 200, "cost_usd": 0.002,
         "curated_skill": "", "category": "coding"}
        for r in [1, 2, 3, 4]
    ]
    all_scores = [sentinel_score] + non_sentinel_a + non_sentinel_b

    # compute_stats should exclude sentinel
    result = stats.compute_stats(all_scores)
    assert "coding/dashboard-digest" not in result["tasks"], \
        "FAIL: sentinel task appeared in compute_stats tasks list"
    check("compute_stats excludes sentinel", "coding/dashboard-digest" not in result["tasks"], True)

    # token_summary should exclude sentinel
    tok = stats.token_summary(all_scores)
    # rung1 should have 2 runs (task-a and task-b), not 3
    rung1 = tok.get("rung1", {})
    check("token_summary rung1 N (excludes sentinel)", rung1.get("n", 0), 2)

    # _is_sentinel helper
    check("_is_sentinel sentinel record", stats._is_sentinel(sentinel_score), True)
    check("_is_sentinel non-sentinel record", stats._is_sentinel(non_sentinel_a[0]), False)


# --- Behavioral Check 2: full render_markdown with sentinel ---
def test_render_markdown_sentinel():
    import stats

    sentinel_score = {
        "task": "coding/dashboard-digest",
        "rung": 1,
        "model": "claude-sonnet-4-6",
        "passed": False,
        "sentinel": True,
        "total_tokens": 500,
        "cost_usd": 0.001,
        "curated_skill": "",
        "category": "coding",
    }
    non_sentinel_scores = [
        {"task": "coding/task-a", "rung": r, "model": "claude-sonnet-4-6",
         "passed": True, "sentinel": False, "total_tokens": 100, "cost_usd": 0.001,
         "curated_skill": "", "category": "coding"}
        for r in [1, 2, 3, 4]
    ] + [
        {"task": "coding/task-b", "rung": r, "model": "claude-sonnet-4-6",
         "passed": r <= 2, "sentinel": False, "total_tokens": 200, "cost_usd": 0.002,
         "curated_skill": "", "category": "coding"}
        for r in [1, 2, 3, 4]
    ]
    all_scores = [sentinel_score] + non_sentinel_scores
    data = {"scores": all_scores, "os_sha": "abc1234", "run_count": len(all_scores)}

    all_s = data["scores"]
    scored = [s for s in all_s if not stats._is_sentinel(s)]
    computed = stats.compute_stats(scored)
    # compute_stats operates on scored, so pass all_scores to render_markdown
    # but the function itself filters internally
    computed2 = stats.compute_stats(all_scores)
    tok = stats.token_summary(all_scores)
    md = stats.render_markdown(data, computed2, tok)

    # Difficulty Anchors section must be present
    assert "## Difficulty Anchors" in md, "FAIL: '## Difficulty Anchors' section not in output"
    print("  ok  render_markdown: '## Difficulty Anchors' section present")

    # Verdict note mentions excluded anchors count
    assert "excluded as difficulty anchors" in md, \
        "FAIL: Verdict note about excluded anchors not in output"
    print("  ok  render_markdown: Verdict note mentions excluded anchors")

    # Sentinel task NOT in Pass/Fail table
    pass_fail_idx = md.find("## Pass/Fail by Rung")
    per_run_idx = md.find("## Per-Run Results")
    assert pass_fail_idx != -1 and per_run_idx != -1, "FAIL: expected sections not found"
    # dashboard-digest should not appear in body sections before Difficulty Anchors
    anchors_idx = md.find("## Difficulty Anchors")
    md_before_anchors = md[:anchors_idx]
    assert "coding/dashboard-digest" not in md_before_anchors, \
        "FAIL: sentinel task appeared in main body before Difficulty Anchors"
    print("  ok  render_markdown: sentinel task excluded from main body (appears only in Difficulty Anchors)")

    # dashboard-digest appears IN Difficulty Anchors
    md_anchors_section = md[anchors_idx:]
    assert "coding/dashboard-digest" in md_anchors_section, \
        "FAIL: sentinel task not listed in Difficulty Anchors section"
    print("  ok  render_markdown: sentinel task listed in Difficulty Anchors section")

    # Non-sentinel pass rates: task-a passes all 4 rungs, task-b passes rungs 1 and 2
    # rung1: 2/2 pass, rung2: 2/2 pass, rung3: 1/2 pass, rung4: 1/2 pass
    assert "2/2 passed" in md or "rung1: 2/2 passed" in md or "- rung1: 2/2 passed" in md, \
        f"FAIL: expected '2/2 passed' for rung1 in verdict section. Relevant part:\n{md[md.find('## Verdict'):][:500]}"
    print("  ok  render_markdown: non-sentinel pass rates correct (2/2 at rung1)")


if __name__ == "__main__":
    print("=== test_sentinel.py ===")
    test_dashboard_digest_sentinel()
    test_non_sentinel_task()
    test_rung_filtering_logic()
    test_stats_excludes_sentinels()
    test_render_markdown_sentinel()
    print("ALL PASS")
