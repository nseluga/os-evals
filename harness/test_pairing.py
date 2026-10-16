"""Tests for stats.py pairing, scorecard banners/reason lines, and run.sh guards.

Run: python3 harness/test_pairing.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402

RUN_SH = Path(__file__).resolve().parent.parent / "run.sh"
STATS_PY = Path(stats.__file__)


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_pairs_follow_user_order():
    allr = {"bare", "claude-md", "memory", "skills", "full"}
    check("bare,skills", stats.select_pairs(allr, ["bare", "skills"]), [("bare", "skills")])
    check("bare,memory,full", stats.select_pairs(allr, ["bare", "memory", "full"]),
          [("bare", "memory"), ("memory", "full")])
    check("bare,full", stats.select_pairs(allr, ["bare", "full"]), [("bare", "full")])
    check("reversed order kept", stats.select_pairs(allr, ["full", "bare"]), [("full", "bare")])
    check("only present layers", stats.select_pairs({"bare", "skills"}, ["bare", "skills"]),
          [("bare", "skills")])
    check("single layer -> none", stats.select_pairs({"bare"}, ["bare"]), [])


def test_ab_pairing_with_sentinel_bare():
    r = {"full@A", "full@B", "bare"}
    check("A/B + bare", stats.select_pairs(r, ["full@A", "full@B"]), [("full@A", "full@B")])
    check("A/B no bare", stats.select_pairs({"full@A", "full@B"}, ["full@A", "full@B"]),
          [("full@A", "full@B")])


def test_legacy_int_pairs():
    check("legacy", stats.select_pairs({1, 2, 3, 4}), [(1, 2), (2, 3), (3, 4), (1, 4)])


def _row(task, rung, passed, **kw):
    r = {"task": task, "rung": rung, "model": "m", "passed": passed, "infra_error": False,
         "total_tokens": 10, "cost_usd": 0.1, "curated_skill": ""}
    r.update(kw)
    return r


def test_non_adjacent_layers_compare_and_empty_message():
    rows = [_row("t1", "bare", False), _row("t1", "skills", True),
            _row("t2", "bare", True), _row("t2", "skills", True)]
    data = {"os_sha": "x", "scores": rows, "layer_order": ["bare", "skills"]}
    st = stats.compute_stats(rows, ["bare", "skills"])
    check("pair key", list(st["rung_pairs"]["m"]), ["bare_vs_skills"])
    md = stats.render_markdown(data, st, stats.token_summary(rows))
    check("no empty-pairs text when paired", "No rung pairs to compare" in md, False)

    one = [_row("t1", "bare", True), _row("t2", "bare", True)]
    data = {"os_sha": "x", "scores": one, "layer_order": ["bare"]}
    md = stats.render_markdown(data, stats.compute_stats(one, ["bare"]), stats.token_summary(one))
    check("empty pairs stated", "No rung pairs to compare" in md, True)
    check("no discriminating verdict when empty", "NO DISCRIMINATING SIGNAL" in md, False)


def test_banner():
    rows = [_row("t1", "bare", True)]
    data = {"os_sha": "x", "scores": rows, "scored_run_ids": ["20260101T000000Z_a.json"]}
    st = stats.compute_stats(rows)
    ts = stats.token_summary(rows)
    md = stats.render_markdown(data, st, ts, matrix_exit=3, planned=10)
    top = md.split("\n\n")[1]
    assert "INCOMPLETE MATRIX" in top and "code 3" in top and "1 runs present of 10 planned" in top, top
    print("  ok  banner names exit code and present/planned")
    check("no banner when clean", "INCOMPLETE MATRIX" in stats.render_markdown(data, st, ts, 0, 1), False)
    check("banner when short w/o exit", "INCOMPLETE MATRIX" in stats.render_markdown(data, st, ts, 0, 5), True)
    p = subprocess.run([sys.executable, str(STATS_PY), "--matrix-exit", "7", "--planned-runs", "4"],
                       input=json.dumps(data), capture_output=True, text=True)
    check("CLI banner", "code 7" in p.stdout, True)


def test_reason_lines_and_single_repeat():
    reasons = ["no_result", "api_error", "check_unrunnable", "check_timeout", "score_exception",
               "no_majority", "rate_limited", "contaminated"]
    rows = [_row("keep", "bare", True), _row("keep", "full", True)]
    for i, rsn in enumerate(reasons):
        rows.append(_row(f"task{i}", "bare", False, infra_error=True, infra_reason=rsn))
    rows.append(_row("task0", "full", False, infra_error=True, infra_reason="no_result"))
    rows.append(_row("solo", "bare", True, repeat_majority=True, valid_repeats=1, repeat_total=3))
    data = {"os_sha": "x", "scores": rows}
    md = stats.render_markdown(data, stats.compute_stats(rows), stats.token_summary(rows))
    lines = md.splitlines()
    for i, rsn in enumerate(reasons):
        hit = [l for l in lines if f"[{rsn}]" in l or (rsn == "contaminated" and l.startswith("⚠️ contaminated"))]
        check(f"line for {rsn}", len(hit), 1)
        assert f"task{i} (" in hit[0], hit[0]
    contam = [l for l in lines if l.startswith("⚠️ contaminated")]
    check("contaminated own line", "task7" in contam[0] and "task0" not in contam[0], True)
    nr = [l for l in lines if "[no_result]" in l][0]
    assert "task0 (2)" in nr, nr
    print("  ok  no_result groups both task0 runs on one line")
    single = [l for l in lines if "single valid repeat" in l]
    check("single-valid line", len(single) == 1 and "solo @ bare" in single[0], True)


def test_run_sh_rejects_same_sha_twice():
    with tempfile.TemporaryDirectory() as d:
        git = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "a"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "b"], check=True)
        sha = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        env = {**os.environ, "OS_DIR": d}
        for a, b in ((sha[:7], sha[:7]), ("HEAD", sha), ("HEAD", "HEAD")):
            p = subprocess.run(["bash", str(RUN_SH), "--os-sha", a, "--os-sha", b, "--dry-run", "--no-build"],
                               capture_output=True, text=True, env=env)
            check(f"same sha {a[:4]}/{b[:4]} exit", p.returncode, 1)
            assert "same commit" in p.stderr, p.stderr
        p = subprocess.run(["bash", str(RUN_SH), "--os-sha", "HEAD~1", "--os-sha", "HEAD", "--dry-run",
                            "--no-build"], capture_output=True, text=True, env=env)
        check("different shas not rejected as duplicate", "same commit" in p.stderr, False)


def _run_sh_copy(d, wrapper):
    """Throwaway run.sh tree: run.sh + harness/, one task, a snapshot whose memory-hook settings.json
    uses `wrapper`, a sentinel runs/x.json, a fake ~/os repo, and stubs so nothing can reach a real
    keychain or claude. Returns (cmd, env, runs_dir)."""
    import shutil
    d = Path(d)
    shutil.copy2(RUN_SH, d / "run.sh")
    shutil.copytree(RUN_SH.parent / "harness", d / "harness", ignore=shutil.ignore_patterns("__pycache__"))
    (d / "tasks" / "ok").mkdir(parents=True)
    (d / "tasks" / "ok" / "prompt.md").write_text("hi")
    (d / "runs").mkdir()
    (d / "runs" / "x.json").write_text("{}")
    osd = d / "os"
    osd.mkdir()
    git = ["git", "-C", str(osd), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "a"], check=True)
    sha = subprocess.run(git + ["rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    layer = d / "configs" / sha / "memory"
    layer.mkdir(parents=True)
    (layer / "settings.json").write_text('{"hooks": {"command": "%s /x/scripts/memory-relevance-hook.py"}}' % wrapper)
    (layer / "rung.env").write_text("HOME=/nonexistent\n")
    (layer / "rung.flags").write_text("--setting-sources user\n")
    stubs = d / "stubs"
    stubs.mkdir()
    for name in ("security", "claude"):  # security: no keychain item; claude: never spend
        (stubs / name).write_text("#!/bin/sh\nexit 1\n")
        (stubs / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
    env.update(OS_DIR=str(osd), PATH=f"{stubs}:{env['PATH']}")
    cmd = ["bash", str(d / "run.sh"), "--no-build", "--os-sha", sha, "--tasks", "ok", "--layers", "memory",
           "--models", "haiku", "--ws-root", str(d / "ws")]
    return cmd, env, d / "runs"


def test_run_sh_refuses_before_archive():
    """Real-run guards (missing token; pre-1.8 snapshot) exit 2 before runs/ is archived; dry run only warns."""
    old, new = 'bash -c \'set -a; . "$CLAUDE_CONFIG_DIR/rung.env"; set +a; exec', "bash -c 'security find-generic-password -s os-evals-claude-token; exec"
    with tempfile.TemporaryDirectory() as d:
        cmd, env, runs = _run_sh_copy(d, new)
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        check("no token: exit", p.returncode, 2)
        assert "no auth token" in p.stderr, p.stderr
        check("no token: sentinel untouched, nothing archived", [(runs / "x.json").exists(), (runs / "archive").exists()], [True, False])
    with tempfile.TemporaryDirectory() as d:
        cmd, env, runs = _run_sh_copy(d, old)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = "dummy-not-a-token"
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        check("pre-1.8 snapshot: exit", p.returncode, 2)
        assert "pre-1.8 snapshot" in p.stderr and "without --no-build" in p.stderr, p.stderr
        check("pre-1.8: sentinel untouched, nothing archived", [(runs / "x.json").exists(), (runs / "archive").exists()], [True, False])
        p = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True, env=env)
        check("pre-1.8 dry run not blocked", p.returncode, 0)
        assert "WARNING pre-1.8 snapshot" in p.stdout, p.stdout
    with tempfile.TemporaryDirectory() as d:
        cmd, env, runs = _run_sh_copy(d, new)
        p = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True, env=env)
        check("current-wrapper dry run: exit, no warning", [p.returncode, "pre-1.8" in p.stdout], [0, False])


if __name__ == "__main__":
    test_pairs_follow_user_order()
    test_ab_pairing_with_sentinel_bare()
    test_legacy_int_pairs()
    test_non_adjacent_layers_compare_and_empty_message()
    test_banner()
    test_reason_lines_and_single_repeat()
    test_run_sh_rejects_same_sha_twice()
    test_run_sh_refuses_before_archive()
    print("ALL PASS")
