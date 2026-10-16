"""Tests: parser robustness, no_result meta, trace without _meta, layer/draft guards, load_rung.

Run: python3 harness/test_run_guards.py
"""
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import _iter_tool_uses, _parse_stream, load_rung  # noqa: E402

RM = Path(run_matrix.__file__)


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_parser_survives_junk():
    t, ev = _parse_stream("123\n", "")
    check("_parse_stream survives bare number", ev, [])
    t, ev = _parse_stream('[1]\n"x"\nnull\n{"type":"assistant","message":null}\n', "")
    check("_parse_stream survives list/str/null/message:null", len(ev), 1)
    check("_iter_tool_uses survives junk", list(_iter_tool_uses([123, None, {"message": None}, {"message": {"content": "x"}}])), [])


def _cli(*args):
    return subprocess.run([sys.executable, str(RM), *args], capture_output=True, text=True)


def _fixture(d):
    d = Path(d)
    for name in ("ok", "_draft/canary/claude-md"):
        (d / "tasks" / name).mkdir(parents=True)
        (d / "tasks" / name / "prompt.md").write_text("hi")
    (d / "configs" / "bare").mkdir(parents=True)
    return ["--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"),
            "--runs-dir", str(d / "runs"), "--ws-root", str(d / "ws"), "--dry-run"]


def test_guards():
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        r = _cli(*base, "--tasks", "ok", "--layers", "memroy")
        check("unknown layer exits 2", r.returncode, 2)
        assert "memroy" in r.stderr, r.stderr
        r = _cli(*base, "--tasks", "_draft/canary/claude-md", "--layers", "bare")
        check("draft entry exits 2", r.returncode, 2)
        assert "_draft/canary/claude-md" in r.stderr and "promoted out of _draft" in r.stderr, r.stderr
        r = _cli(*base, "--tasks", "ok", "--layers", "bare")
        check("valid plan exits 0", r.returncode, 0)


def test_load_rung_missing():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "sha" / "bare").mkdir(parents=True)
        check("existing layer loads", load_rung(Path(d), "bare", "sha"), ({}, []))
        for layer in ("memroy", "full"):
            try:
                load_rung(Path(d), layer, "sha")
            except FileNotFoundError:
                print(f"  ok  load_rung raises for missing layer {layer!r}")
            else:
                raise AssertionError(f"load_rung did not raise for missing layer {layer!r}")


def _run_one(stdout, timed_out=False, info=None, **kw_run):
    import subprocess as sp
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("hi")
        (d / "configs" / "bare").mkdir(parents=True)

        def fake(cmd, **kw):
            if info is not None:
                info["cmd"] = cmd
            if timed_out:
                raise sp.TimeoutExpired(cmd, 1, output=stdout)
            return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

        orig = sp.run
        sp.run = fake
        try:
            out = run_matrix.run_one("t", "bare", "m", d / "tasks", d / "configs", d / "runs",
                                     ws_root=d / "ws", **kw_run)
        finally:
            sp.run = orig
        if info is not None:
            info["name"] = out.name
        tr = out.with_name(out.name.removesuffix(".json") + ".trace.jsonl")
        return json.loads(out.read_text()), (tr.read_text() if tr.exists() else "")


def test_meta_no_result_and_trace():
    ev = '{"type":"assistant","message":{"usage":{"output_tokens":3}}}\n'
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    t, _ = _run_one(ev)
    check("no result event -> no_result True", t["_meta"]["no_result"], True)
    t, trace = _run_one(ev + res)
    check("result event -> no_result False", t["_meta"]["no_result"], False)
    check("trace has no _meta", "_meta" in trace, False)
    check("trace keeps result event", '"type": "result"' in trace, True)
    t, _ = _run_one(ev, timed_out=True)
    check("timeout -> no_result False", t["_meta"]["no_result"], False)


def _fake_security(d, code, marker):
    """A `security` on PATH that records the call and exits `code` (44 = item not found)."""
    bin_ = Path(d) / "bin"
    bin_.mkdir()
    (bin_ / "security").write_text(f"#!/bin/sh\necho called >> {marker}\n"
                                   f"{'echo fake-token' if code == 0 else ''}\nexit {code}\n")
    (bin_ / "security").chmod(0o755)
    return str(bin_)


def test_token_keychain():
    import os
    with tempfile.TemporaryDirectory() as d:
        marker = Path(d) / "calls"
        bin_ = _fake_security(d, 44, marker)
        base = _fixture(d)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
        env["PATH"] = f"{bin_}:{os.environ['PATH']}"

        def cli(*a, **extra):
            return subprocess.run([sys.executable, str(RM), *a], capture_output=True, text=True, env={**env, **extra})

        r = cli(*base, "--tasks", "ok", "--layers", "bare")
        check("dry-run needs no keychain", (r.returncode, marker.exists()), (0, False))
        live = [a for a in base if a != "--dry-run"]
        r = cli(*live, "--tasks", "ok", "--layers", "bare")
        check("missing keychain item exits 2", r.returncode, 2)
        assert "os-evals-claude-token" in r.stderr and "security add-generic-password" in r.stderr, r.stderr
        check("keychain was asked", marker.exists(), True)
        check("no run dir made before failing", (Path(d) / "ws").exists(), False)

        # env override: the keychain is never consulted
        marker.unlink()
        run_matrix._TOKEN = None
        old = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), os.environ["PATH"]
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"], os.environ["PATH"] = "from-env", env["PATH"]
        try:
            check("env override wins", run_matrix.oauth_token(), "from-env")
            check("env override skips keychain", marker.exists(), False)
            # no override + working keychain: read once, cached
            del os.environ["CLAUDE_CODE_OAUTH_TOKEN"]
            run_matrix._TOKEN = None
            (Path(bin_) / "security").write_text(f"#!/bin/sh\necho called >> {marker}\necho kc-token\n")
            check("keychain read", run_matrix.oauth_token(), "kc-token")
            run_matrix.oauth_token()
            check("keychain read once per process", marker.read_text().count("called"), 1)
        finally:
            run_matrix._TOKEN = None
            os.environ["PATH"] = old[1]
            if old[0] is not None:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = old[0]


def test_token_injected():
    import subprocess as sp
    seen = {}
    for layer in ("bare", "full"):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "tasks" / "t").mkdir(parents=True)
            (d / "tasks" / "t" / "prompt.md").write_text("hi")
            (d / "configs" / layer).mkdir(parents=True)
            (d / "configs" / layer / "rung.env").write_text("HOME=/h\n")

            def fake(cmd, **kw):
                seen[layer] = kw["env"]
                return types.SimpleNamespace(stdout="", stderr="", returncode=0)

            orig, run_matrix._TOKEN, sp.run = sp.run, "tok-123", fake
            try:
                run_matrix.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
            finally:
                sp.run, run_matrix._TOKEN = orig, None
    check("full gets OAuth name only", (seen["full"].get("CLAUDE_CODE_OAUTH_TOKEN"), "ANTHROPIC_AUTH_TOKEN" in seen["full"]),
          ("tok-123", False))
    check("bare gets both names", (seen["bare"].get("CLAUDE_CODE_OAUTH_TOKEN"), seen["bare"].get("ANTHROPIC_AUTH_TOKEN")),
          ("tok-123", "tok-123"))
    check("rung.env HOME kept", seen["full"]["HOME"], "/h")


def test_pre18_snapshot():
    old = '{"h": "bash -c \'set -a; . \\"$CLAUDE_CONFIG_DIR/rung.env\\"; set +a; exec python3 /s/scripts/memory-relevance-hook.py\'"}'
    cur = old.replace("exec", "t=$(security find-generic-password -s os-evals-claude-token -w); exec")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, text in (("old", old), ("cur", cur), ("nohook", '{"autoMemoryEnabled": false}')):
            (d / "configs" / name / "memory").mkdir(parents=True)  # configs/<sha>/<layer>
            (d / "configs" / name / "memory" / "settings.json").write_text(text)
        t = lambda n: run_matrix.is_pre18_snapshot(d / "configs" / n / "memory")  # noqa: E731
        check("old wrapper flagged", t("old"), True)
        check("current wrapper / no hook / no settings.json pass", [t("cur"), t("nohook"), t("absent")], [False] * 3)
        (d / "tasks" / "ok").mkdir(parents=True)
        (d / "tasks" / "ok" / "prompt.md").write_text("hi")
        argv = ["--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"), "--runs-dir", str(d / "runs"),
                "--ws-root", str(d / "ws"), "--tasks", "ok", "--layers", "memory", "--models", "m", "--os-sha", "old"]
        (d / "bin").mkdir()  # guard rail: if the refusal ever regresses, the "claude" that runs is this stub
        (d / "bin" / "claude").write_text("#!/bin/sh\nexit 1\n")
        (d / "bin" / "claude").chmod(0o755)
        env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "CLAUDE_CODE_OAUTH_TOKEN": "dummy"}
        r = subprocess.run([sys.executable, str(RM), *argv], capture_output=True, text=True, env=env)  # real path
        check("real run on old snapshot exits 2", r.returncode, 2)
        assert "pre-1.8 snapshot" in r.stderr, r.stderr
        r = _cli(*argv, "--dry-run")
        check("dry run on old snapshot warns, exits 0", (r.returncode, "WARNING pre-1.8" in r.stdout), (0, True))


def test_effort_in_run_id_and_meta():
    init = '{"type":"system","subtype":"init","model":"claude-haiku-9-9"}\n'
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    info = {}
    t, _ = _run_one(init + res, info=info, effort="xhigh")
    check("run file name ends _m_xhigh.json", info["name"].endswith("_bare_m_xhigh.json"), True)
    check("cmd carries --effort xhigh", info["cmd"][info["cmd"].index("--effort") + 1], "xhigh")
    check("_meta.effort", t["_meta"]["effort"], "xhigh")
    check("_meta.model_resolved from init event", t["_meta"]["model_resolved"], "claude-haiku-9-9")
    info = {}
    t, _ = _run_one(res, info=info)
    check("default effort high in name", info["name"].endswith("_bare_m_high.json"), True)
    check("no init event -> model_resolved None", t["_meta"]["model_resolved"], None)


def test_task_budget_override_and_passthrough():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d) / "t"
        t.mkdir()
        (t / "meta.yaml").write_text(
            "max_budget_usd: 6  # C1\nlayer_neutral: true\nsignals: a,b  # non-gating\n"
            'judge_files: "src/x.mjs,test/*.test.mjs"\ndescription: |\n  max_budget_usd: 99\n  layer_neutral: false\n')
        m = run_matrix.read_task_meta(t)
        check("max_budget_usd parsed, indented prose ignored", m["max_budget_usd"], 6.0)
        check("layer_neutral parsed", m["layer_neutral"], True)
        check("signals passed through, comment stripped", m["signals"], "a,b")
        check("judge_files passed through, quotes stripped", m["judge_files"], "src/x.mjs,test/*.test.mjs")
        check("defaults when absent", run_matrix.read_task_meta(Path(d) / "none")["max_budget_usd"], None)
    cmd = run_matrix.build_cmd("m", [], {"max_budget_usd": 6.0}, 1.5)
    check("meta max_budget_usd overrides CLI default", cmd[cmd.index("--max-budget-usd") + 1], "6.0")
    cmd = run_matrix.build_cmd("m", [], {"max_budget_usd": None}, 1.5)
    check("no meta value -> CLI default", cmd[cmd.index("--max-budget-usd") + 1], "1.5")
    info = {}
    _run_one('{"type":"result","is_error":false,"result":"ok"}\n', info=info)
    check("run_one with no task cap uses build_cmd default (flag absent)", "--max-budget-usd" in info["cmd"], False)


def test_skill_fired_agent_and_one_shot():
    ev = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "dt-engineer", "description": "x"}}]}}]
    check("Agent spawn naming the skill counts", run_matrix.detect_skill_fired(ev, "dt-engineer"), True)
    check("Task spawn still counts", run_matrix.detect_skill_fired(
        [{"message": {"content": [{"type": "tool_use", "name": "Task", "input": {"subagent_type": "dt-qa"}}]}}], "dt-qa"), True)
    check("no match -> False", run_matrix.detect_skill_fired(ev, "ponytail"), False)
    check("no curated skill -> None", run_matrix.detect_skill_fired(ev, ""), None)
    # one-shot (multi_turn false) run with a curated_skill still gets skill_fired computed
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("hi")
        (d / "tasks" / "t" / "meta.yaml").write_text("curated_skill: dt-engineer\nlayer_neutral: true\n")
        (d / "configs" / "bare").mkdir(parents=True)
        out = json.dumps(ev[0]) + '\n{"type":"result","is_error":false,"result":"ok"}\n'
        import subprocess as sp
        orig = sp.run
        sp.run = lambda cmd, **kw: types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        try:
            f = run_matrix.run_one("t", "bare", "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
        finally:
            sp.run = orig
        meta = json.loads(f.read_text())["_meta"]
        check("one-shot run: skill_fired computed", (meta["multi_turn"], meta["skill_fired"]), (False, True))
        check("_meta.layer_neutral", meta["layer_neutral"], True)


def test_layer_neutral_bare_only_dry_run():
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        (Path(d) / "configs" / "full").mkdir()
        for name, meta in (("ln", "layer_neutral: true\n"), ("sent", "sentinel: true\n"), ("ok", "")):
            (Path(d) / "tasks" / name).mkdir(exist_ok=True)
            (Path(d) / "tasks" / name / "prompt.md").write_text("hi")
            (Path(d) / "tasks" / name / "meta.yaml").write_text(meta)
        r = _cli(*base, "--tasks", "ln,sent,ok", "--layers", "bare,full")
        check("exit 0", r.returncode, 0)
        out = r.stdout
        check("layer_neutral listed on bare only", "layer_neutral: ln \u2014 bare layer only" in out, True)
        check("ln plans 1 cell", "  ln: 1 cells" in out, True)
        check("sentinel still bare only", "sentinel: sent \u2014 bare layer only" in out and "  sent: 1 cells" in out, True)
        check("normal task keeps both cells", "  ok: 2 cells" in out, True)


if __name__ == "__main__":
    test_task_budget_override_and_passthrough()
    test_skill_fired_agent_and_one_shot()
    test_layer_neutral_bare_only_dry_run()
    test_parser_survives_junk()
    test_guards()
    test_load_rung_missing()
    test_meta_no_result_and_trace()
    test_token_keychain()
    test_token_injected()
    test_pre18_snapshot()
    test_effort_in_run_id_and_meta()
    print("ALL PASS")
