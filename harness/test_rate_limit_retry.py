"""Tests: looks_like_rate_limit false positives, and retry workspace reset.

Run: python3 harness/test_rate_limit_retry.py
"""
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import looks_like_rate_limit  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


SUCCESS = {
    "type": "result", "subtype": "success", "is_error": False,
    "result": "done", "num_turns": 5, "total_cost_usd": 1.2,
    "uuid": "03e34429-1111-2222-3333-444455556666",
    "usage": {"input_tokens": 5, "output_tokens": 2039, "estimated_tokens": 1429},
}
ERR_429 = {
    "type": "result", "subtype": "success", "is_error": True, "num_turns": 1,
    "usage": {"input_tokens": 0, "output_tokens": 0},
    "result": 'API Error: 429 {"type":"error","error":{"type":"rate_limit_error",'
              '"message":"This request would exceed your account\'s rate limit"}}',
}


def test_uuid_and_token_counts():
    t = {**SUCCESS, "_meta": {"returncode": 0}}
    stdout = json.dumps({**SUCCESS, "estimated_tokens": 1429})
    check("uuid/1429 transcript", looks_like_rate_limit("", "", t), False)
    check("uuid/1429 with json stdout", looks_like_rate_limit(stdout, "", t), False)


def test_real_false_positives():
    for name in (
        "20260717T191026Z_coding-rangestats-engine_rung4_claude_sonnet_4_6.json",
        "20260718T013500Z_coding-pir-workload-feature_rung2_claude_sonnet_4_6_r3.json",
    ):
        p = REPO / "runs" / name
        if not p.exists():
            print(f"  skip {name} (not on disk)")
            continue
        check(name[:40], looks_like_rate_limit("", "", json.loads(p.read_text())), False)


def test_true_positives():
    check("429 error transcript", looks_like_rate_limit("", "", ERR_429), True)
    t = {"type": "result", "is_error": True, "result": "no terminal result event"}
    check("429 in stderr", looks_like_rate_limit(
        "", "API Error: 429 Too Many Requests", t), True)


def test_answer_text_not_an_infra_error():
    from run_matrix import looks_like_auth_error
    ans401 = {"result": "The API returns 401 Unauthorized when the token is missing", "is_error": False}
    ans429 = {"result": "Return HTTP 429 Too Many Requests when rate limit exceeded", "is_error": False}
    check("auth: answer mentions 401 -> False", looks_like_auth_error("", "", ans401), False)
    check("rate: answer mentions 429 -> False", looks_like_rate_limit("", "", ans429), False)
    check("auth: is_error + 401 -> True",
          looks_like_auth_error("", "", {"result": "API Error: 401 Unauthorized", "is_error": True}), True)
    check("rate: is_error + 429 -> True",
          looks_like_rate_limit("", "", {"result": "API Error: 429 Too Many Requests", "is_error": True}), True)
    check("auth: stderr always inspected", looks_like_auth_error("", "HTTP 401", ans401), True)
    check("auth: plain stdout inspected", looks_like_auth_error("Invalid API key", "", {}), True)
    check("auth: json stdout not inspected",
          looks_like_auth_error('{"type":"result","result":"401"}', "", ans401), False)


def test_retry_resets_workspace():
    calls = []

    def fake_run(cmd, **kw):
        cwd = Path(kw["cwd"])
        calls.append({"marker": (cwd / "marker.txt").exists(),
                      "seed": (cwd / "seed.txt").exists()})
        if len(calls) == 1:
            (cwd / "marker.txt").write_text("edited")
            out, rc = json.dumps(ERR_429), 1
        else:
            out, rc = json.dumps(SUCCESS), 0
        return types.SimpleNamespace(stdout=out, stderr="", returncode=rc)

    orig = (subprocess.run, run_matrix.time.sleep, run_matrix.rate_limit_backoff_seconds)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        task = d / "tasks" / "t1"
        (task / "seed").mkdir(parents=True)
        (task / "seed" / "seed.txt").write_text("x")
        (task / "prompt.md").write_text("hi")
        (task / "meta.yaml").write_text("timeout_sec: 60\n")
        (d / "configs" / "1").mkdir(parents=True)  # load_rung raises on a missing layer dir
        subprocess.run = fake_run
        run_matrix.time.sleep = lambda s: None
        run_matrix.rate_limit_backoff_seconds = lambda a: 0
        try:
            run_matrix.run_one("t1", 1, "m", d / "tasks", d / "configs", d / "runs")
        finally:
            subprocess.run, run_matrix.time.sleep, run_matrix.rate_limit_backoff_seconds = orig
    check("call count", len(calls), 2)
    check("call 1 had seed", calls[0]["seed"], True)
    check("call 2 no marker", calls[1]["marker"], False)
    check("call 2 has seed", calls[1]["seed"], True)


def _run_with_outcomes(outcomes):
    """run_one with subprocess.run scripted: each outcome is 'timeout' or a stdout string.
    Returns (calls, saved transcript)."""
    calls = []

    def fake_run(cmd, **kw):
        out = outcomes[len(calls)]
        calls.append(kw["cwd"])
        if out == "timeout":
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], output=b"", stderr=b"")
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    orig = (subprocess.run, run_matrix.time.sleep)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        task = d / "tasks" / "t1"
        task.mkdir(parents=True)
        (task / "prompt.md").write_text("hi")
        (task / "meta.yaml").write_text("timeout_sec: 60\n")
        (d / "configs" / "1").mkdir(parents=True)
        subprocess.run = fake_run
        run_matrix.time.sleep = lambda s: None
        try:
            out = run_matrix.run_one("t1", 1, "m", d / "tasks", d / "configs", d / "runs")
        finally:
            subprocess.run, run_matrix.time.sleep = orig
        return calls, json.loads(out.read_text())


def test_timeout_retries_once():
    calls, t = _run_with_outcomes(["timeout", json.dumps(SUCCESS)])
    check("timeout then success: calls", len(calls), 2)
    check("timeout then success: result", t["result"], "done")
    check("timeout then success: timed_out", t["_meta"]["timed_out"], False)
    check("timeout then success: timeout_retries", t["_meta"]["timeout_retries"], 1)

    calls, t = _run_with_outcomes(["timeout", "timeout", json.dumps(SUCCESS)])
    check("two timeouts: stops after 2 calls", len(calls), 2)
    check("two timeouts: timed_out", t["_meta"]["timed_out"], True)
    check("two timeouts: timeout_retries", t["_meta"]["timeout_retries"], 1)

    calls, t = _run_with_outcomes([json.dumps(SUCCESS)])
    check("no timeout: 1 call", len(calls), 1)
    check("no timeout: timeout_retries", t["_meta"]["timeout_retries"], 0)


if __name__ == "__main__":
    test_uuid_and_token_counts()
    test_real_false_positives()
    test_true_positives()
    test_answer_text_not_an_infra_error()
    test_retry_resets_workspace()
    test_timeout_retries_once()
    print("ALL PASS")
