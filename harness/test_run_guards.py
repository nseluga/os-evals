"""Tests: parser robustness, no_result meta, trace without _meta, layer/draft guards, load_rung.

Run: python3 harness/test_run_guards.py
"""
import json
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


def _run_one(stdout, timed_out=False):
    import subprocess as sp
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("hi")
        (d / "configs" / "bare").mkdir(parents=True)

        def fake(cmd, **kw):
            if timed_out:
                raise sp.TimeoutExpired(cmd, 1, output=stdout)
            return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

        orig = sp.run
        sp.run = fake
        try:
            out = run_matrix.run_one("t", "bare", "m", d / "tasks", d / "configs", d / "runs",
                                     ws_root=d / "ws")
        finally:
            sp.run = orig
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


if __name__ == "__main__":
    test_parser_survives_junk()
    test_guards()
    test_load_rung_missing()
    test_meta_no_result_and_trace()
    test_token_keychain()
    test_token_injected()
    print("ALL PASS")
