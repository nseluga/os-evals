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


def test_variant_guards():
    """Knockout variants: four rc-2 preflight refusals, plus the accepted shapes."""
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        for layer in ("claude-md", "memory", "skills"):
            (Path(d) / "configs" / layer).mkdir()
        (Path(d) / "configs" / "src" / "skills" / "quote").mkdir(parents=True)
        run = lambda layers: _cli(*base, "--tasks", "ok", "--layers", layers)  # noqa: E731
        for label, layers, want in [
            ("unknown mod", "memory,memory~nope", "unknown variant 'nope'"),
            ("nohook on bare", "bare,bare~nohook", "nohook needs a base with the memory hook"),
            ("nohook on claude-md", "claude-md,claude-md~nohook", "nohook needs a base with the memory hook"),
            ("ko of a missing skill", "skills,skills~ko.ghost", "no skill 'ghost'"),
            ("ko on a base without skills", "memory,memory~ko.quote", "ko.<skill> needs a base with skills"),
            ("variant base not in --layers", "bare,memory~nohook", "needs its base 'memory'"),
        ]:
            r = run(layers)
            check(f"{label} exits 2", r.returncode, 2)
            assert want in r.stderr, (label, r.stderr)
        for label, layers in [("nohook", "memory,memory~nohook"), ("ko.quote", "skills,skills~ko.quote")]:
            r = run(layers)
            check(f"{label} plan exits 0", r.returncode, 0)
            assert f"cells=['{layers.split(',')[0]}', '{layers.split(',')[1]}']" in r.stdout, r.stdout


def test_ko_runs_only_on_curated_task():
    check("curated token matches", run_matrix.variant_applies("skills~ko.quote", "quote"), True)
    check("'none (…)' does not match", run_matrix.variant_applies("skills~ko.quote", "none (proves the skills layer loads)"), False)
    check("other skill does not match", run_matrix.variant_applies("full~ko.quote", "dt-qa"), False)
    check("nohook and plain layers always apply",
          [run_matrix.variant_applies(x, "none (x)") for x in ("memory~nohook", "full")], [True, True])


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
            out = run_matrix.run_one("t", kw_run.pop("layer", "bare"), "m", d / "tasks", d / "configs", d / "runs",
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


def test_variant_meta():
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    info = {}
    t, _ = _run_one(res, info=info, layer="bare~nohook")
    m = t["_meta"]
    check("_meta layer=base, variant, rung=full spec", (m["layer"], m["variant"], m["rung"]), ("bare", "nohook", "bare~nohook"))
    check("run id embeds the full spec", "_bare~nohook_m_high.json" in info["name"], True)
    t, _ = _run_one(res)
    check("plain layer: variant empty", (t["_meta"]["layer"], t["_meta"]["variant"], t["_meta"]["rung"]), ("bare", "", "bare"))


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


if __name__ == "__main__":
    test_parser_survives_junk()
    test_guards()
    test_variant_guards()
    test_ko_runs_only_on_curated_task()
    test_load_rung_missing()
    test_variant_meta()
    test_meta_no_result_and_trace()
    test_token_keychain()
    test_token_injected()
    test_pre18_snapshot()
    test_effort_in_run_id_and_meta()
    print("ALL PASS")
