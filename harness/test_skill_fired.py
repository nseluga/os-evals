"""Tests for detect_skill_fired and the forced-arm override (item 4.1).

Run: python3 harness/test_skill_fired.py
"""
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402
from score import score_run  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def tool(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def test_none_and_empty_needles():
    ev = [tool("Skill", {"skill": "none"}), tool("Bash", {})]
    check("empty needle -> None", rm.detect_skill_fired(ev, ""), None)
    check("'none' needle -> None", rm.detect_skill_fired(ev, "none"), None)
    check("'None' (any case) -> None", rm.detect_skill_fired(ev, "None"), None)
    check("real needle absent -> False", rm.detect_skill_fired(ev, "humanizer"), False)


def test_skill_tool_and_agent_task_alike():
    check("Skill tool_use names it", rm.detect_skill_fired([tool("Skill", {"skill": "humanizer"})], "humanizer"), True)
    for name in ("Agent", "Task"):
        ev = [tool(name, {"subagent_type": "dt-qa", "description": "run qa"})]
        check(f"{name} spawn counts the same", rm.detect_skill_fired(ev, "dt-qa"), True)
        check(f"{name} spawn, other skill", rm.detect_skill_fired(ev, "ponytail"), False)


def _run(layer, events, meta_yaml):
    out = "".join(json.dumps(e) + "\n" for e in events) + '{"type":"result","is_error":false,"result":"ok"}\n'
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("BODY")
        (d / "tasks" / "t" / "meta.yaml").write_text(meta_yaml)
        (d / "configs" / "skills").mkdir(parents=True)
        import subprocess as sp
        orig = sp.run
        sp.run = lambda cmd, **kw: types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        try:
            f = rm.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
        finally:
            sp.run = orig
        rec = score_run(f, d / "tasks")
        return json.loads(f.read_text())["_meta"], rec


def test_forced_true_by_construction_and_trigger_detected():
    meta, rec = _run("skills~forced", [], "curated_skill: humanizer\n")
    check("forced arm, no trace marker -> skill_fired True", meta["skill_fired"], True)
    check("score record honors the forced override", rec["skill_fired"], True)
    meta, rec = _run("skills~trigger", [], 'curated_skill: humanizer\ntrigger: "x:"\n')
    check("trigger arm, skill never called -> False (routing miss)", (meta["skill_fired"], rec["skill_fired"]), (False, False))
    meta, rec = _run("skills~trigger", [tool("Skill", {"skill": "humanizer"})], 'curated_skill: humanizer\ntrigger: "x:"\n')
    check("trigger arm, Skill tool_use -> True", (meta["skill_fired"], rec["skill_fired"]), (True, True))
    meta, rec = _run("skills", [], "curated_skill: none (no skill)\n")
    check("curated_skill none on a plain layer -> None", (meta["skill_fired"], rec["skill_fired"]), (None, None))
    meta, _ = _run("skills", [], "curated_skill: humanizer\n")
    check("plain layer: arm empty", (meta["arm"], meta["forced_skill"]), ("", ""))


if __name__ == "__main__":
    test_none_and_empty_needles()
    test_skill_tool_and_agent_task_alike()
    test_forced_true_by_construction_and_trigger_detected()
    print("ALL PASS")
