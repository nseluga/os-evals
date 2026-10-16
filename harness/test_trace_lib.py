"""Tests: trace_lib on a fixture stream-json trace.

Run: python3 harness/test_trace_lib.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_lib as tl  # noqa: E402


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def asst(mid, block, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"id": mid, "content": [block]}}


def tu(name, **inp):
    return {"type": "tool_use", "id": "t", "name": name, "input": inp}


TRACE = [
    {"type": "system", "subtype": "init"},
    asst("m1", {"type": "text", "text": "plan"}),
    asst("m1", tu("Agent", subagent_type="Explore", model="haiku", description="Find files", prompt="look")),
    asst("m1", tu("Task", subagent_type="dt-engineer", description="Item 1", prompt="build")),  # parallel: same message.id
    asst("m2", tu("Skill", skill="dev-team", args="run it")),
    asst("m2", tu("Bash", command="git worktree add x")),
    asst("m2", tu("Agent", subagent_type="dt-qa", description="Later turn", prompt="verify")),  # second message
    asst("s1", tu("Bash", command="npm test"), parent="toolu_parent"),  # subagent-side event
    # a tool_result echoing an Agent dict must never be counted
    {"type": "user", "message": {"content": [{"type": "tool_result", "content": [tu("Agent", description="echo")]}]}},
    # a top-level user event with a raw tool_use-shaped block: only assistant events count
    {"type": "user", "message": {"id": "u1", "content": [tu("Agent", subagent_type="dt-fake", description="user-side")]}},
    {"type": "result", "result": "done"},
]


def test_trace_lib():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in TRACE) + "\nnot json\n[1]\n")
        ev = tl.events(p)
        check("events skips junk lines and non-dicts", len(ev), len(TRACE))
        sp = tl.spawns(ev)
        check("Agent and Task both counted, echoes and user-side blocks ignored", [x[0] for x in sp], ["Explore", "dt-engineer", "dt-qa"])
        check("Agent spawn: type, model, desc, prompt", sp[0][:4], ("Explore", "haiku", "Find files", "look"))
        check("parallel spawns share msg_id and index", (sp[0][4:], sp[1][4:]), ((("m1", 0)), ("m1", 0)))
        check("Task spawn has empty model", sp[1][1], "")
        check("skill_calls", tl.skill_calls(ev), [("dev-team", "run it")])
        check("bash_cmds includes subagent side", tl.bash_cmds(ev), ["git worktree add x", "npm test"])
        tu_ = tl.tool_uses(ev)
        check("parent_tool_use_id on subagent event", [t[2] for t in tu_ if t[0] == "Bash"], [None, "toolu_parent"])
        check("msg_index follows message.id order", [s[5] for s in tl.spawns(ev)], [0, 0, 1])


if __name__ == "__main__":
    test_trace_lib()
    print("test_trace_lib: PASS")
