"""Tests for contamination detection, opaque workspace names, env scrub, and scoring.

Run: python3 harness/test_contamination.py
"""
import json
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402
from contamination import (contamination_rules, find_contamination, scrub_env,  # noqa: E402
                           workspace_name)

REPO = Path("/r/os-evals")
HOME = Path("/h/user")
WS = "/ws/w-abc"
CFG = REPO / "configs"


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def tool(name, **inp):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": name, "input": inp}]}}


def run_home(layer):
    """HOME build_configs.sh gives an isolated run of this layer."""
    return str(CFG / "abc123" / ("home-bare" if layer == "bare" else "home"))


def hits(events, layer, isolated=True, task_dir=Path("/nonexistent")):
    f, a, t = contamination_rules(REPO, HOME, CFG, task_dir, layer, "abc123", WS, isolated,
                                  run_home=run_home(layer) if isolated else None)
    return find_contamination(events, f, a, t)


def test_paths():
    for layer in ("bare", "full"):
        check(f"tasks check.sh hit {layer}", len(hits([tool("Read", file_path=f"{REPO}/tasks/x/check.sh")], layer)), 1)
        check(f"real ~/os abs hit {layer}", len(hits([tool("Read", file_path=f"{HOME}/os/CLAUDE.md")], layer)), 1)
    check("own workspace ok", hits([tool("Read", file_path=f"{WS}/a.py"), tool("Bash", command=f"ls {WS}")], "bare"), [])
    check("snapshot ok for full", hits([tool("Read", file_path=f"{CFG}/abc123/src/CLAUDE.md")], "full"), [])
    check("snapshot hit for bare", len(hits([tool("Read", file_path=f"{CFG}/abc123/src/CLAUDE.md")], "bare")), 1)
    check("os-evals-notes not os root", hits([tool("Read", file_path=f"{HOME}/os-evals-notes.txt")], "bare"), [])
    check("relative climb hit", len(hits([tool("Bash", command=f"cat ../..{HOME}/os/CLAUDE.md")], "bare")), 1)
    check("path-in-glob hit", len(hits([tool("Grep", pattern="x", path=f"{REPO}/harness")], "full")), 1)


def test_tilde():
    ev = [tool("Bash", command="cat ~/os/CLAUDE.md")]
    check("~/os bare isolated ok (home-bare has no os/)", hits(ev, "bare"), [])
    check("~/os bare not isolated hit", len(hits(ev, "bare", isolated=False)), 1)
    check("~/os full isolated ok", hits(ev, "full", isolated=True), [])
    check("~/os full not isolated hit", len(hits(ev, "full", isolated=False)), 1)
    check("$HOME/os full not isolated hit",
          len(hits([tool("Bash", command="cat $HOME/os/x")], "full", isolated=False)), 1)
    check("~/os-evals not os", hits([tool("Bash", command="ls ~/os-evals-x")], "bare", isolated=False), [])
    f, a, t = contamination_rules(REPO, HOME, CFG, Path("/nonexistent"), "full", "abc123", WS, True)
    check("isolated but run_home unknown: ~ is the real home", len(find_contamination(ev, f, a, t)), 1)


def test_run_dir_layout():
    """09-30 run: per-run dir (w/ + cfg/) under the shared ws_root; HOME-isolated bare."""
    sha = CFG / "abc123"
    run = "/Users/Shared/evalws/w-0123456789"

    def h(cmd, layer, isolated=True):
        f, a, t = contamination_rules(REPO, HOME, CFG, Path("/nonexistent"), layer, "abc123", run,
                                      isolated, ws_root="/Users/Shared/evalws",
                                      run_home=run_home(layer) if isolated else None)
        return find_contamination([tool("Bash", command=cmd)], f, a, t)

    check("bare isolated grep ~/.claude ok", h('grep -rniIl "dt-qa" ~/.claude', "bare"), [])
    check("bare reading ws_root is a hit",
          len(h('grep -rniIl "dt-qa" ~/.claude /Users/Shared/evalws', "bare")), 1)
    check("bare reading another layer's state is a hit", len(h(f"ls {sha}/bare/projects", "bare")), 1)
    check("bare reading src/ is a hit", len(h(f"cat {sha}/src/CLAUDE.md", "bare")), 1)
    check("bare own w/ and cfg/ ok", h(f"ls {run}/w {run}/cfg", "bare"), [])
    check("non-bare reading another layer template ok", h(f"cat {sha}/full/CLAUDE.md", "skills"), [])
    check("non-bare grep -r configs/<sha> ok", h(f"cd {sha} && grep -r x .", "full"), [])
    check("non-bare ~/os/x isolated ok", h("cat ~/os/x", "full"), [])
    check("non-isolated ~/os hit", len(h("cat ~/os/x", "full", isolated=False)), 1)
    check("non-bare reading configs/ root is a hit", len(h(f"ls {CFG}", "full")), 1)
    f, a, t = contamination_rules(REPO, HOME, CFG, Path("/nonexistent"), "full", "abc123", WS, True,
                                  run_home=run_home("full"), shared_cfg=True)
    for cmd, want in ((f"cd {sha} && grep -r x .", 1), (f"cat {sha}/bare/projects/s.jsonl", 1),
                      (f"cat {sha}/full/CLAUDE.md {sha}/src/x", 0), ("cat ~/os/x", 0)):
        check(f"shared_cfg (pre-cfg/ run): {cmd[-30:]}", len(find_contamination([tool("Bash", command=cmd)], f, a, t)), want)
    check("non-bare reading a sibling run is a hit",
          len(h("cat /Users/Shared/evalws/w-9999999999/cfg/projects/x.jsonl", "full")), 1)


def test_origin_and_text():
    with tempfile.TemporaryDirectory() as d:
        td = Path(d)
        (td / "workspace.ref").write_text("origin: /h/user/project-dashboard\nsha: abc\n")
        check("origin hit", len(hits([tool("Bash", command="git -C /h/user/project-dashboard log")], "full", task_dir=td)), 1)
    answer = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": f"I did not read {REPO}/tasks/x/check.sh"}]}}
    check("answer text not a hit", hits([answer], "bare"), [])
    check("hits distinct and cut to 160",
          len(hits([tool("Bash", command=f"cat {REPO}/tasks/" + "a" * 300)] * 2, "bare")[0]), 160)


def test_sibling_workspace():
    f, a, t = contamination_rules(REPO, HOME, CFG, Path("/nonexistent"), "bare", "abc123", WS, True,
                                  ws_root="/ws")
    sib = [tool("Read", file_path="/ws/w-other/solution.py")]
    check("sibling workspace read is a hit", len(find_contamination(sib, f, a, t)), 1)
    own = [tool("Read", file_path=f"{WS}/solution.py")]
    check("own workspace is not a hit", find_contamination(own, f, a, t), [])
    check("prefix-sibling w-abcd is a hit",
          len(find_contamination([tool("Read", file_path="/ws/w-abcd/x")], f, a, t)), 1)
    check("default root = parent of ws_dir",
          len(hits([tool("Read", file_path="/ws/w-other/solution.py")], "bare")), 1)


def test_scrub_more():
    env = {"SSH_AUTH_SOCK": "s", "DATABASE_URL": "d", "POSTGRES_DATABASE_URL": "d", "SENTRY_DSN": "x",
           "PROXY_AUTH": "a", "NPM_AUTH_FOO": "a", "AUTHOR": "me", "PATH": "/bin", "DSN_NOTE": "n"}
    out = scrub_env(env, set())
    check("more names scrubbed", sorted(out), ["AUTHOR", "DSN_NOTE", "PATH"])
    out = scrub_env(env, {"SSH_AUTH_SOCK", "DATABASE_URL"})
    check("keep survives", sorted(out), ["AUTHOR", "DATABASE_URL", "DSN_NOTE", "PATH", "SSH_AUTH_SOCK"])


def test_workspace_name():
    check("stable", workspace_name("run1"), workspace_name("run1"))
    check("differs", workspace_name("run1") != workspace_name("run2"), True)
    n = workspace_name("run1")
    check("shape", n.startswith("w-") and len(n) == 12, True)


def test_scrub_env():
    env = {"GITHUB_TOKEN": "x", "FOO_API_KEY": "y", "PATH": "/bin", "HOME": "/h", "LANG": "C",
           "ANTHROPIC_AUTH_TOKEN": "z", "AWS_REGION": "r", "my_secret": "s"}
    snap = dict(env)
    out = scrub_env(env, {"ANTHROPIC_AUTH_TOKEN"})
    check("scrubbed", sorted(out), ["ANTHROPIC_AUTH_TOKEN", "HOME", "LANG", "PATH"])
    check("input unmutated", env, snap)


def test_score_contaminated():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        marker = tmp / "marker.txt"
        td = tmp / "tasks" / "demo"
        td.mkdir(parents=True)
        sh = td / "check.sh"
        sh.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 0\n')
        sh.chmod(sh.stat().st_mode | stat.S_IXUSR)
        recs = []
        for i, contaminated in ((1, True), (2, False), (3, False)):
            f = tmp / f"20260101T00000{i}Z_demo_rung1_m_r{i}.json"
            f.write_text(json.dumps({"result": "ok", "_meta": {
                "task": "demo", "rung": 1, "model": "m", "workspace_dir": str(tmp), "repeat_index": i,
                "repeat_total": 3, "contaminated": contaminated, "contamination_hits": ["/x/tasks/y"]}}))
            if i == 1:
                recs.append(score.score_run(f, tmp / "tasks"))
                check("check.sh not run", marker.exists(), False)
            else:
                recs.append(score.score_run(f, tmp / "tasks"))
        check("infra_reason", recs[0]["infra_reason"], "contaminated")
        check("infra_error", recs[0]["infra_error"], True)
        (m,) = score.compute_majority_records(recs)
        check("majority valid_repeats excludes it", (m["valid_repeats"], m["infra_repeats"]), (2, 1))


if __name__ == "__main__":
    test_paths()
    test_tilde()
    test_run_dir_layout()
    test_origin_and_text()
    test_sibling_workspace()
    test_workspace_name()
    test_scrub_env()
    test_scrub_more()
    test_score_contaminated()
    print("ALL PASS")
