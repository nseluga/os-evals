"""Tests for knockout variants: parse_layer and build_run_config(template, cfg, mod).

Run: python3 harness/test_variants.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import build_run_config, parse_layer  # noqa: E402

SETTINGS = {"autoMemoryEnabled": True, "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]}}


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _template(d, skills=True, name="tpl"):
    d = Path(d)
    t = d / name
    t.mkdir()
    (t / "CLAUDE.md").write_text("c")
    (t / "settings.json").write_text(json.dumps(SETTINGS))
    if skills:
        src = d / "src" / "skills"
        for name in ("alpha", "quote", "zeta"):
            (src / name).mkdir(parents=True)
        os.symlink(src, t / "skills")
        agents = d / "src" / "agents"
        agents.mkdir(parents=True)
        for name in ("helper.md", "quote.md"):
            (agents / name).write_text("a")
        os.symlink(agents, t / "agents")
    return t


def test_parse_layer():
    check("plain", parse_layer("memory"), ("memory", ""))
    check("nohook", parse_layer("memory~nohook"), ("memory", "nohook"))
    check("ko", parse_layer("full~ko.quote"), ("full", "ko.quote"))


def test_nohook_strips_hooks_only():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        cfg = Path(d) / "cfg"
        build_run_config(t, cfg, "nohook")
        check("hooks gone, rest kept", json.loads((cfg / "settings.json").read_text()), {"autoMemoryEnabled": True})
        check("skills still the template symlink", os.readlink(cfg / "skills"), str(Path(d) / "src" / "skills"))
        check("template settings untouched", json.loads((t / "settings.json").read_text()), SETTINGS)
        build_run_config(t, cfg)
        check("no mod keeps hooks", "hooks" in json.loads((cfg / "settings.json").read_text()), True)


def test_ko_skill_dir():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        cfg = Path(d) / "cfg"
        build_run_config(t, cfg, "ko.quote")
        check("skills is a real dir", ((cfg / "skills").is_dir(), (cfg / "skills").is_symlink()), (True, False))
        check("knocked-out skill missing, others kept", sorted(os.listdir(cfg / "skills")), ["alpha", "zeta"])
        check("entries symlink to the snapshot", os.readlink(cfg / "skills" / "alpha"), str(Path(d) / "src" / "skills" / "alpha"))
        check("hooks untouched", "hooks" in json.loads((cfg / "settings.json").read_text()), True)
        check("same-named agent dropped, others kept", sorted(os.listdir(cfg / "agents")), ["helper.md"])
        check("agents is a real dir", ((cfg / "agents").is_dir(), (cfg / "agents").is_symlink()), (True, False))
        build_run_config(t, cfg, "ko.alpha")
        check("no same-named agent: all agents kept", sorted(os.listdir(cfg / "agents")), ["helper.md", "quote.md"])
        build_run_config(t, cfg, "nohook")
        check("nohook leaves agents a symlink", (cfg / "agents").is_symlink(), True)
        build_run_config(t, cfg, "ko.quote")  # rebuild (retry path) is idempotent
        check("rebuild same", sorted(os.listdir(cfg / "skills")), ["alpha", "zeta"])
        build_run_config(t, cfg)
        check("no mod: plain symlink again", (cfg / "skills").is_symlink(), True)


def test_bad_mods_raise():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        for template, mod in ((t, "bogus"), (_template(Path(tempfile.mkdtemp(dir=d)), skills=False), "ko.quote")):
            try:
                build_run_config(template, Path(d) / "cfg", mod)
            except ValueError as e:
                print(f"  ok  {mod!r} raises: {e}")
            else:
                raise AssertionError(f"{mod!r} did not raise")


def test_retry_rebuilds_variant_cfg():
    """A timeout retry rebuilds cfg/; dropping `mod` there would run the unmodified base under a variant label."""
    import types
    import subprocess as sp
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    leak = ('{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read",'
            '"input":{"file_path":"/h/os/skills/quote/SKILL.md"}}]}}\n')
    for spec, want, ko_leak in (
        ("skills~nohook", (False, True, ["alpha", "quote", "zeta"], True), None),
        ("skills~ko.quote", (True, False, ["alpha", "zeta"], False), True),
    ):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "tasks" / "t").mkdir(parents=True)
            (d / "tasks" / "t" / "prompt.md").write_text("hi")
            (d / "configs").mkdir()
            _template(d / "configs", name="skills")
            seen = []

            def fake(cmd, **kw):
                cfg = Path(kw["env"]["CLAUDE_CONFIG_DIR"])
                seen.append(("hooks" in json.loads((cfg / "settings.json").read_text()), (cfg / "skills").is_symlink(),
                             sorted(os.listdir(cfg / "skills")), (cfg / "agents").is_symlink()))
                if len(seen) == 1:
                    raise sp.TimeoutExpired(cmd, 1, output="")
                return types.SimpleNamespace(stdout=leak + res, stderr="", returncode=0)

            orig = sp.run
            sp.run = fake
            try:
                out = run_matrix.run_one("t", spec, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
            finally:
                sp.run = orig
            check(f"{spec}: ran twice (one retry)", len(seen), 2)
            check(f"{spec}: first cfg", seen[0], want)
            check(f"{spec}: rebuilt cfg keeps the variant", seen[1], want)
            check(f"{spec}: _meta.ko_leak", json.loads(out.read_text())["_meta"].get("ko_leak"), ko_leak)


def test_ko_leaked():
    def ev(**inp):
        return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": inp}]}}
    check("read of the skill file", run_matrix.ko_leaked([ev(file_path="/h/os/skills/quote/SKILL.md")], "quote"), True)
    check("shell cat via ~/os", run_matrix.ko_leaked([ev(command="cat ~/os/skills/quote/SKILL.md")], "quote"), True)
    check("same-named agent file", run_matrix.ko_leaked([ev(command="cat agents/quote.md")], "quote"), True)
    check("other skill", run_matrix.ko_leaked([ev(command="cat skills/alpha/SKILL.md")], "quote"), False)
    check("INDEX.md alone is not a leak", run_matrix.ko_leaked([ev(command="cat skills/INDEX.md")], "quote"), False)
    check("text mention is not a tool input", run_matrix.ko_leaked([{"type": "assistant", "message": {"content": [
        {"type": "text", "text": "see skills/quote/SKILL.md"}]}}], "quote"), False)
    check("no events", run_matrix.ko_leaked([], "quote"), False)


def test_arm_mods_pass_through():
    check("parse_layer", [parse_layer("skills~trigger"), parse_layer("full~forced.dev-team")],
          [("skills", "trigger"), ("full", "forced.dev-team")])
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        for mod in ("trigger", "forced", "forced.quote"):
            cfg = Path(d) / f"cfg-{mod}"
            build_run_config(t, cfg, mod)
            check(f"{mod}: config identical to plain (hooks kept, skills symlink whole)",
                  (json.loads((cfg / "settings.json").read_text()), os.readlink(cfg / "skills")),
                  (SETTINGS, str(Path(d) / "src" / "skills")))
    try:
        build_run_config(Path("/nonexistent"), Path("/tmp/never"), "forced-ish")
    except ValueError:
        print("  ok  malformed arm mod still raises")
    else:
        raise AssertionError("malformed arm mod did not raise")


if __name__ == "__main__":
    test_arm_mods_pass_through()
    test_parse_layer()
    test_nohook_strips_hooks_only()
    test_ko_skill_dir()
    test_bad_mods_raise()
    test_retry_rebuilds_variant_cfg()
    test_ko_leaked()
    print("ALL PASS")
