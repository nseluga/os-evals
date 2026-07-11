"""Focused checks for read_task_meta's top-level-key parsing.

Regression guard for the bug where prose inside a task's `description:` block —
e.g. a wrapped line beginning "multi_turn: git-repo'd ..." — was read as the
real field and silently misclassified a multi-turn task as one-shot.

Run: python3 harness/test_read_task_meta.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_matrix import read_task_meta  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_real_tasks():
    rs = read_task_meta(REPO / "tasks/coding/rangestats-engine")
    check("rangestats multi_turn", rs["multi_turn"], True)
    check("rangestats timeout_sec", rs["timeout_sec"], 1800)
    check("rangestats curated_skill", rs["curated_skill"], "dev-team-auto")

    pg = read_task_meta(REPO / "tasks/coding/pathguard-resolver")
    check("pathguard multi_turn", pg["multi_turn"], True)
    check("pathguard timeout_sec", pg["timeout_sec"], 1200)
    check("pathguard curated_skill", pg["curated_skill"], "dev-team")


def test_prose_cannot_shadow_top_level_keys():
    # Synthetic meta whose description: block contains prose lines that look like
    # top-level keys. The real keys sit at column 0; the prose is indented.
    synthetic = (
        "multi_turn: true\n"
        "timeout_sec: 1800\n"
        "curated_skill: dev-team-auto\n"
        "description: |\n"
        "  multi_turn: git-repo'd workspace so the orchestrator can branch.\n"
        "  timeout_sec: 300 is far too small for this prose sentence.\n"
        "  curated_skill: none-because-this-is-just-description-text.\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "meta.yaml").write_text(synthetic)
        m = read_task_meta(Path(d))
    check("synthetic multi_turn", m["multi_turn"], True)
    check("synthetic timeout_sec", m["timeout_sec"], 1800)
    check("synthetic curated_skill", m["curated_skill"], "dev-team-auto")


if __name__ == "__main__":
    test_real_tasks()
    test_prose_cannot_shadow_top_level_keys()
    print("ALL PASS")
