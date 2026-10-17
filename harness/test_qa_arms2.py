"""QA round 2 adversarial tests for item 4.1 (post fix round 1): per-sha skip, all-skipped full~ arms, CLI-level wall line
hand-computed from fabricated history, _meta arm/skill_fired through run_one, A/B Skill lift edges.

Run: python3 harness/test_qa_arms2.py
"""
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402
import stats  # noqa: E402

RM = Path(rm.__file__)


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _task(root, name, meta):
    (root / "tasks" / name).mkdir(parents=True)
    (root / "tasks" / name / "prompt.md").write_text("hi")
    (root / "tasks" / name / "meta.yaml").write_text(meta)


def _cli(root, tasks, layers, *extra):
    return subprocess.run(
        [sys.executable, str(RM), "--dry-run", "--tasks", tasks, "--layers", layers, "--tasks-dir", str(root / "tasks"),
         "--config-dir", str(root / "configs"), "--runs-dir", str(root / "runs"), "--ws-root", str(root / "ws"),
         "--scorecards-dir", str(root / "sc"), *extra], capture_output=True, text=True)


def _snap(root, sha, skills):
    """configs/<sha>/{skills,full} plus src/skills/<each skill> (the snapshot's skill dirs)."""
    for layer in ("skills", "full"):
        (root / "configs" / sha / layer).mkdir(parents=True)
    (root / "configs" / sha / "src" / "skills").mkdir(parents=True)
    for s in skills:
        (root / "configs" / sha / "src" / "skills" / s).mkdir()


# --- A/B shas: the skill snapshot is checked per cell ---

def test_ab_shas_skip_per_sha_cell():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _snap(root, "AAA", ["quote"])
        _snap(root, "BBB", [])  # the older snapshot lacks `quote`
        _task(root, "has", 'curated_skill: quote\ntrigger: "quote this:"\n')
        r = _cli(root, "has", "skills,skills~forced,skills~trigger", "--os-sha", "AAA", "--os-sha", "BBB")
        check("plain arms with the skill in one sha only: rc 0", r.returncode, 0)
        out = r.stdout
        assert "skills~forced@BBB: has — skipped (needs skill 'quote' in" in out, out
        assert "skills~trigger@BBB: has — skipped (needs skill 'quote' in" in out, out
        assert "skills~forced@AAA: has — skipped" not in out, out
        planned = [ln for ln in out.splitlines() if ln.startswith("  has: ")][0]
        check("only sha AAA keeps its arm cells (2 base + 2 AAA arm = 4 runs)",
              ("total runs: 4" in out, "skills~forced@AAA" in planned, "skills~forced@BBB" in planned, "skills@BBB" in planned),
              (True, True, False, True))
        r = _cli(root, "has", "skills,skills~forced.quote", "--os-sha", "AAA", "--os-sha", "BBB")
        check("explicit forced.<skill> missing from ANY sha: rc 2", r.returncode, 2)
        assert "no skill 'quote'" in r.stderr and "BBB" in r.stderr, r.stderr


# --- all-skipped `full~` arms are rc 0 too ---

def test_full_arms_all_skipped_rc0():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _snap(root, "AAA", [])
        for layer in ("skills", "full"):
            (root / "configs" / layer).mkdir(parents=True, exist_ok=True)
        _task(root, "plain", "curated_skill: none (no skill)\n")
        r = _cli(root, "plain", "full,full~forced,full~trigger", "--os-sha", "AAA")
        check("full~forced + full~trigger over a curated-none set: rc 0", r.returncode, 0)
        check("both skipped with a notice, only the base cell is planned",
              ("full~forced: plain — skipped (needs a curated_skill)" in r.stdout, "full~trigger: plain — skipped" in r.stdout, "total runs: 1" in r.stdout),
              (True, True, True))
        r = _cli(root, "plain", "full~forced", "--os-sha", "AAA")
        check("an arm whose base layer is absent is still the layer-spec error (rc 2), not a skip", r.returncode, 2)


# --- wall line from fabricated history, hand computed, through the CLI ---

def _rec(task, wall, file, model="claude-sonnet-4-6", **kw):
    return {"task": task, "rung": "skills", "model": model, "wall_clock_sec": wall, "file": file, "passed": True, "cost_usd": 0.2,
            "is_error": False, "infra_error": False, "multi_turn": False, "turns": 1, "total_tokens": 10, "curated_skill": "none", "skill_fired": None, **kw}


def test_cli_wall_line_hand_computed():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _snap(root, "AAA", [])
        for layer in ("skills", "full", "bare"):
            (root / "configs" / "AAA" / layer).mkdir(parents=True, exist_ok=True)
        _task(root, "q", "curated_skill: none (x)\n")
        _task(root, "m", "curated_skill: none (x)\nmulti_turn: true\n")
        (root / "sc").mkdir()
        q = [_rec("q", 100, "q1.json"), _rec("q", 140, "q2.json"),
             _rec("q", 0.9, "q3.json", is_error=True, cost_usd=0),                  # refused request: excluded
             _rec("q", 120, "q4.json", is_error=True, cost_usd=0, timed_out=True),  # timeout keeps its wall
             _rec("q", 9999, "q5.json", infra_error=True)]                          # infra: excluded
        m = [_rec("m", 400, "m1.json", multi_turn=True)]
        (root / "sc" / "20260101T000000Z-AAA.scores.json").write_text(json.dumps({"scores": q + m}))
        (root / "sc" / "20260102T000000Z-AAA-rescored.scores.json").write_text(json.dumps({"scores": [q[0]]}))  # a repeat of q1 under the same `file`: without dedupe the mean is 115, not 120
        # q mean (100+140+120)/3 = 120 ; m = 400.  jobs 2, factor 16: (120/2 + 400/4) * 16 = 2560 s = 42.67 min
        r = _cli(root, "q,m", "skills", "--models", "sonnet", "--jobs", "2", "--os-sha", "AAA")
        check("CLI exit 0", r.returncode, 0)
        wall = [ln for ln in r.stdout.splitlines() if ln.startswith("est wall:")]
        check("est wall = (120/2 + 400/4) x 16 s, nothing lacking", wall, ["est wall: 0h 43m (factor 16, 0 cells lack history)"])
        idx = r.stdout.splitlines().index(wall[0])
        check("the wall line follows the verdict line directly", r.stdout.splitlines()[idx - 1].startswith("verdict: "), True)
        r = _cli(root, "q,m", "skills", "--models", "sonnet", "--jobs", "2", "--os-sha", "AAA", "--stall-factor", "2")
        check("--stall-factor 2 scales both parts: 320 s", [ln for ln in r.stdout.splitlines() if ln.startswith("est wall:")],
              ["est wall: 0h 5m (factor 2, 0 cells lack history)"])
        r = _cli(root, "q,m", "skills", "--models", "opus", "--jobs", "2", "--os-sha", "AAA")
        check("opus has no history: both cells lack, family pool falls back to every record",
              [ln.split("(")[1] for ln in r.stdout.splitlines() if ln.startswith("est wall:")], ["factor 16, 2 cells lack history)"])
        r = _cli(root, "q", "skills", "--models", "sonnet", "--repeat", "3", "--jobs", "1", "--os-sha", "AAA")
        check("--repeat 3 triples the one-shot wall (3 x 120 x 16 = 5760 s)", [ln for ln in r.stdout.splitlines() if ln.startswith("est wall:")],
              ["est wall: 1h 36m (factor 16, 0 cells lack history)"])


# --- _meta through run_one ---

def _meta(layer, meta_yaml, events_out):
    out = "".join(json.dumps(e) + "\n" for e in events_out)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("BODY")
        (d / "tasks" / "t" / "meta.yaml").write_text(meta_yaml)
        (d / "configs" / "skills").mkdir(parents=True)
        orig = subprocess.run
        subprocess.run = lambda cmd, **kw: types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        try:
            f = rm.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
        finally:
            subprocess.run = orig
        return json.loads(f.read_text())["_meta"]


def test_meta_arm_fields_and_skill_fired():
    res = {"type": "result", "is_error": False, "result": "ok"}
    skill_call = lambda name: {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}  # noqa: E731
    m = _meta("skills~forced", "curated_skill: humanizer\n", [res])
    check("forced with zero tool_use: arm, forced_skill, skill_fired True by construction", (m["arm"], m["forced_skill"], m["skill_fired"]), ("forced", "humanizer", True))
    m = _meta("skills~forced.dev-team", "curated_skill: humanizer\n", [res])
    check("forced.<other>: forced_skill is the explicit one, intended_skill stays curated", (m["forced_skill"], m["intended_skill"], m["skill_fired"]), ("dev-team", "humanizer", True))
    m = _meta("skills~trigger", 'curated_skill: humanizer\ntrigger: "go:"\n', [res])
    check("trigger without a Skill call: skill_fired False (a measured miss)", (m["arm"], m["skill_fired"]), ("trigger", False))
    m = _meta("skills~trigger", 'curated_skill: humanizer\ntrigger: "go:"\n', [skill_call("humanizer"), res])
    check("trigger with the exact Skill call: True", m["skill_fired"], True)
    m = _meta("skills~trigger", 'curated_skill: dev-team\ntrigger: "go:"\n', [skill_call("dev-team-auto"), res])
    check("trigger on dev-team where only dev-team-auto fired: False", m["skill_fired"], False)
    m = _meta("skills", "curated_skill: none (x)\n", [res])
    check("plain layer, curated none: no arm, skill_fired None", (not m["arm"], m["skill_fired"]), (True, None))


# --- stats: A/B arms ---

def _lift(task, rung, passed, cost=0.1, **kw):
    return {"task": task, "rung": rung, "passed": passed, "model": "sonnet:high", "cost_usd": cost, "curated_skill": "humanizer",
            "multi_turn": False, "skill_fired": None, "infra_error": False, **kw}


def test_ab_arm_stats_edges():
    check("A/B shas with arm rungs: the sha pair only",
          stats.select_pairs({"skills@A", "skills@B", "skills~forced@A", "skills~forced@B", "skills~trigger@A"}, None), [("skills@A", "skills@B")])
    scores = [_lift("orch", "skills@A", False, 0.5, multi_turn=True), _lift("orch", "skills~forced@A", True, 0.9, multi_turn=True),
              _lift("orch", "skills@B", True, 0.5, multi_turn=True), _lift("orch", "skills~forced@B", False, 0.5, multi_turn=True),
              _lift("t", "skills~trigger@A", True, skill_fired=True), _lift("t", "skills~trigger@B", True, skill_fired=False)]
    text = "\n".join(stats.skill_lift_section(scores))
    for row in ("| humanizer (orch)@A | sonnet:high | 1 | +100pp | n/a | $+0.4000 | n/a |",
                "| humanizer (orch)@B | sonnet:high | 1 | -100pp | n/a | $+0.0000 | n/a |",
                "| humanizer@A | sonnet:high | 0 | n/a | n/a | n/a | 1/1 |",
                "| humanizer@B | sonnet:high | 0 | n/a | n/a | n/a | 0/1 |"):
        assert row in text, f"missing row {row!r} in\n{text}"
    print("  ok  multi_turn rows and trigger routing are per sha, never pooled")
    check("no arm runs: section omitted", stats.skill_lift_section([_lift("a", "skills", True), _lift("a", "bare", False)]), [])
    infra = [_lift("a", "skills", True), _lift("a", "skills~forced", True, infra_error=True)]
    check("an infra forced run makes no pair", "| humanizer |" in "\n".join(stats.skill_lift_section(infra)), False)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print("ALL PASS")
