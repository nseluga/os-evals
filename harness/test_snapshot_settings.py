"""Tests for snapshot_settings (pure settings strip/rewrite) and layer env/pairing wiring.

Run: python3 harness/test_snapshot_settings.py
"""
import os
import pwd
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
import stats  # noqa: E402
from snapshot_settings import layer_settings, strip_settings  # noqa: E402

SNAP = "/x/configs/abc1234/src"
LIVE = {
    "model": "opus",
    "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"},
    "outputStyle": "Concise",
    "autoMemoryEnabled": True,
    "autoMemoryDirectory": "~/os/knowledge/memory",
    "enabledPlugins": {"ponytail@ponytail": True},
    "extraKnownMarketplaces": {"ponytail": {}},
    "statusLine": {"type": "command", "command": "bash ~/.claude/statusline.sh"},
    "agentPushNotifEnabled": True,
    "hooks": {
        "PermissionRequest": [{"hooks": [{"type": "command", "command": "afplay x.aiff"}]}],
        "Stop": [{"hooks": [
            {"type": "command", "command": "python3 ~/.claude/save-chat-history.py"},
            {"type": "command", "command": "bash ~/os/scripts/maintenance.sh"}]}],
        "UserPromptSubmit": [{"hooks": [
            {"type": "command", "command": "python3 ~/.claude/memory-relevance-hook.py", "timeout": 15}]}],
        "SessionStart": [{"matcher": "startup", "hooks": [
            {"type": "command", "command": "zsh $HOME/os/scripts/digest-hook.sh"}]}],
        "PostToolUse": [{"matcher": "Write|Edit", "hooks": [
            {"type": "command", "command": "python3 /Users/someone/os/scripts/link-check-hook.py"}]}],
    },
}


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_strip():
    out = strip_settings(LIVE, SNAP)
    check("hook events", list(out["hooks"].keys()), ["UserPromptSubmit"])
    check("hook count", sum(len(g["hooks"]) for g in out["hooks"]["UserPromptSubmit"]), 1)
    cmd = out["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    check("hook path rewritten + env-wrapped", cmd,
          "bash -c 'set -a; . \"$CLAUDE_CONFIG_DIR/rung.env\"; set +a; "
          "t=$(security find-generic-password -s os-evals-claude-token -w "
          f"\"{pwd.getpwuid(os.getuid()).pw_dir}/Library/Keychains/login.keychain-db\" 2>/dev/null); "
          "[ -n \"$t\" ] && export CLAUDE_CODE_OAUTH_TOKEN=\"$t\"; "
          f"exec python3 {SNAP}/scripts/memory-relevance-hook.py'")
    check("timeout kept", out["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"], 15)
    check("memory dir rewritten", out["autoMemoryDirectory"], f"{SNAP}/knowledge/memory")
    for k in ("enabledPlugins", "extraKnownMarketplaces", "statusLine", "agentPushNotifEnabled"):
        check(f"{k} dropped", k in out, False)
    check("model kept", out["model"], "opus")
    check("env kept", out["env"], LIVE["env"])
    check("outputStyle kept", out["outputStyle"], "Concise")
    check("input not mutated", "enabledPlugins" in LIVE and len(LIVE["hooks"]) == 5, True)
    check("no live os path left", "/os/" in str(out).replace(SNAP, ""), False)


def test_layers():
    check("claude-md", layer_settings("claude-md", LIVE, SNAP), {"autoMemoryEnabled": False})
    for layer in ("memory", "skills"):
        out = layer_settings(layer, LIVE, SNAP)
        check(f"{layer} keys", sorted(out), ["autoMemoryDirectory", "autoMemoryEnabled", "hooks"])
        check(f"{layer} one hook event", list(out["hooks"]), ["UserPromptSubmit"])
        cmd = out["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        check(f"{layer} wrapped exactly once", cmd.count("rung.env"), 1)
    full_cmd = layer_settings("full", LIVE, SNAP)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    check("full wrapped exactly once", full_cmd.count("rung.env"), 1)
    check("full == strip", layer_settings("full", LIVE, SNAP), strip_settings(LIVE, SNAP))


def test_pairs():
    check("default bare/full", stats.select_pairs({"bare", "full"}), [("bare", "full")])
    order = ["bare", "claude-md", "memory", "skills", "full"]
    check("ladder adjacent", stats.select_pairs(set(order), order),
          [("bare", "claude-md"), ("claude-md", "memory"), ("memory", "skills"), ("skills", "full")])
    check("ladder order as given", stats.select_pairs({"bare", "memory", "full"}, ["bare", "memory", "full"]),
          [("bare", "memory"), ("memory", "full")])
    check("A/B", stats.select_pairs({"full@aaa", "full@bbb"}, ["full@aaa", "full@bbb"]),
          [("full@aaa", "full@bbb")])
    check("A/B order given", stats.select_pairs({"full@aaa", "full@bbb"}, ["full@bbb", "full@aaa"]),
          [("full@bbb", "full@aaa")])
    check("legacy ints", stats.select_pairs({1, 2, 3, 4}), stats.RUNG_PAIRS)
    st = stats.compute_stats([
        {"task": "t", "rung": "bare", "model": "opus", "passed": False},
        {"task": "t", "rung": "full", "model": "opus", "passed": True}])
    check("compute_stats key", list(st["rung_pairs"]["opus"]), ["bare_vs_full"])
    check("compute_stats verdict", st["rung_pairs"]["opus"]["bare_vs_full"]["task_verdicts"],
          [{"task": "t", "verdict": "full wins"}])


def test_cells():
    check("single sha label", run_matrix.plan_cells(["bare", "full"], ["s1"]),
          [("bare", "s1", "bare"), ("full", "s1", "full")])
    check("A/B label", run_matrix.plan_cells(["full"], ["a", "b"]),
          [("full", "a", "full@a"), ("full", "b", "full@b")])
    check("redact", run_matrix.redact_env({"HOME": "/h", "CLAUDE_CODE_OAUTH_TOKEN": "sekret"}),
          {"HOME": "/h", "CLAUDE_CODE_OAUTH_TOKEN": "***"})


def test_layer_env():
    """Run build_configs.sh against a throwaway os repo; HOME isolation on vs off."""
    import os
    harness = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        osd = d / "os"
        (osd / "scripts").mkdir(parents=True)
        (osd / "CLAUDE.md").write_text("hi")
        (osd / "scripts" / "memory-relevance-hook.py").write_text("")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=osd, check=True)
        subprocess.run([*git, "add", "-A"], cwd=osd, check=True)
        subprocess.run([*git, "commit", "-qm", "x"], cwd=osd, check=True)
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=osd, capture_output=True,
                             text=True, check=True).stdout.strip()
        claude = d / "claude"
        claude.mkdir()
        import json
        (claude / "settings.json").write_text(json.dumps(LIVE))
        # fake `security` so the test never touches the real keychain
        bin_ = d / "bin"
        bin_.mkdir()
        (bin_ / "security").write_text("#!/bin/sh\necho fake-token\n")
        (bin_ / "security").chmod(0o755)
        for extra, want_home in (([], True), (["--no-home-isolation"], False)):
            cfg = d / f"cfg{len(extra)}"
            sc = harness / "build_configs.sh"
            env = {**os.environ, "CONFIGS_DIR": str(cfg), "OS_DIR": str(osd), "CLAUDE_DIR": str(claude),
                   "PERSONAL_DIR": str(d / "none"), "PATH": f"{bin_}:{os.environ['PATH']}"}
            r = subprocess.run(["bash", str(sc), "--os-sha", sha, *extra], env=env, capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            base = cfg / sha
            for layer in ("bare", "claude-md", "memory", "skills", "full"):
                envtxt = (base / layer / "rung.env").read_text()
                home = [l for l in envtxt.splitlines() if l.startswith("HOME=")]
                check(f"HOME present={want_home} [{layer}]", bool(home), want_home)
                if want_home:
                    want = base / ("home-bare" if layer == "bare" else "home")
                    check(f"HOME value [{layer}]", home[0], f"HOME={want}")
                check(f"no token on disk [{layer}]", ("TOKEN" in envtxt, "fake-token" in envtxt), (False, False))
                oct_ = oct((base / layer / "rung.env").stat().st_mode & 0o777)
                check(f"rung.env mode [{layer}]", oct_, "0o600")
            check("bare flags", (base / "bare" / "rung.flags").read_text().strip(), "--bare")
            check("full flags", (base / "full" / "rung.flags").read_text().strip(), "--setting-sources user")
            if want_home:
                check("bare home empty", list((base / "home-bare").iterdir()), [])
                check("home/os -> src", (base / "home" / "os").resolve(), (base / "src").resolve())
            check("sentinel", (base / "src" / ".evals-snapshot-id").read_text().strip(), sha)
            check("full CLAUDE.md", (base / "full" / "CLAUDE.md").read_text(), "hi")
        r = subprocess.run(["bash", str(sc), "--os-sha", "deadbeefdead"], env=env, capture_output=True, text=True)
        check("bad sha exit", r.returncode, 2)


if __name__ == "__main__":
    test_strip()
    test_layers()
    test_pairs()
    test_cells()
    test_layer_env()
    print("ALL PASS")
