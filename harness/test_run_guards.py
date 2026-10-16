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


if __name__ == "__main__":
    test_parser_survives_junk()
    test_guards()
    test_load_rung_missing()
    test_meta_no_result_and_trace()
    print("ALL PASS")
