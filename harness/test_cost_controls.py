"""Tests: default:false, tools:none, --jobs pool, --ws-root, dry-run cost estimate, --repeat.

Run: python3 harness/test_cost_controls.py
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import build_cmd, estimate_cost, execute_items, find_tasks, read_task_meta  # noqa: E402


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def mk_task(root: Path, name: str, meta: str) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "prompt.md").write_text("hi")
    (d / "meta.yaml").write_text(meta)
    return d


def test_default_false():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        mk_task(root, "a", "timeout_sec: 10\n")
        mk_task(root, "b", "default: false  # costly\n")
        check("default meta", read_task_meta(root / "a")["default"], True)
        check("default false parsed", read_task_meta(root / "b")["default"], False)
        check("excluded without --tasks", find_tasks(root, include_non_default=False), ["a"])
        check("all tasks listed", find_tasks(root), ["a", "b"])
        # naming a task bypasses find_tasks entirely (main uses args.tasks.split(",")).


def test_tools_none():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        mk_task(root, "n", "tools: none\n")
        mk_task(root, "x", "tools: Read\n")
        mk_task(root, "y", "timeout_sec: 5\n")
        cmd = build_cmd("m", ["--bare"], read_task_meta(root / "n"), 1.5)
        i = cmd.index("--tools")
        check("--tools then empty string", cmd[i:i + 2], ["--tools", ""])
        for name in ("x", "y"):
            check(f"{name}: no --tools", "--tools" in build_cmd("m", [], read_task_meta(root / name)), False)
        check("multi-turn flags kept", build_cmd("m", [], {"multi_turn": True, "tools": ""})[2:5],
              ["--output-format", "stream-json", "--verbose"])


def test_jobs_pool():
    items = [{"task": f"t{i}", "multi_turn": i % 4 == 3, "label_id": f"t{i}"} for i in range(12)]
    lock, order, active, peak = threading.Lock(), [], [0], [0]

    def runner(it):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.02)
        with lock:
            active[0] -= 1
            order.append(it["task"])
        return it["task"]

    results, failures = execute_items(items, runner, jobs=3)
    check("all complete", len(results), len(items))
    check("no duplicates", len(set(results)), len(items))
    check("no failures", failures, 0)
    check("pool used concurrency", peak[0] > 1, True)
    multi = [i["task"] for i in items if i["multi_turn"]]
    check("multi-turn last, in order", order[-len(multi):], multi)
    check("multi-turn not in pool", order[:-len(multi)] == [t for t in order if t not in multi], True)

    order.clear()
    results, _ = execute_items(items, runner, jobs=1)
    check("jobs=1 original order", results, [i["task"] for i in items])

    def boom(it):
        if it["task"] == "t1":
            raise RuntimeError("x")
        return it["task"]
    results, failures = execute_items(items, boom, jobs=3)
    check("failure counted, others kept", (len(results), failures), (11, 1))


def test_ws_root():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        tasks, runs, ws, cfg = root / "tasks", root / "runs", root / "ws", root / "cfg"
        mk_task(tasks, "a", "timeout_sec: 5\n")
        (cfg / "bare").mkdir(parents=True)
        fake = type("R", (), {"stdout": '{"type":"result","is_error":false,"usage":{"output_tokens":5}}',
                              "stderr": "", "returncode": 0})
        seen = {}

        def fake_run(cmd, **kw):
            seen["cwd"] = kw["cwd"]
            return fake

        orig = run_matrix.subprocess.run
        run_matrix.subprocess.run = fake_run
        try:
            out = run_matrix.run_one("a", "bare", "m", tasks, cfg, runs, ws_root=ws)
        finally:
            run_matrix.subprocess.run = orig
        import json
        wd = json.loads(out.read_text())["_meta"]["workspace_dir"]
        check("transcript stays in runs", out.parent, runs)
        check("workspace is <ws-root>/w-<hex>/w", (Path(wd).parent.parent, Path(wd).name), (ws, "w"))
        check("workspace_dir absolute", Path(wd).is_absolute(), True)
        check("cwd is the workspace", seen["cwd"], wd)


def test_estimate():
    hist = [
        [{"task": "a", "cost_usd": 1.0, "wall_clock_sec": 100, "infra_error": False},
         {"task": "a", "cost_usd": 3.0, "wall_clock_sec": 200, "infra_error": False},
         {"task": "a", "cost_usd": 99.0, "wall_clock_sec": 999, "infra_error": True},
         {"task": "m", "cost_usd": 4.0, "wall_clock_sec": 600, "infra_error": False}],
        [{"task": "a", "cost_usd": 50.0, "wall_clock_sec": 5000},   # older: ignored for a
         {"task": "b", "cost_usd": 2.0, "wall_clock_sec": 50}],     # only place b appears
    ]
    est = estimate_cost(hist, {"a": 2, "b": 1, "m": 1, "new": 3}, {"m"})
    # means: a=(2.0,150) b=(2.0,50) m=(4.0,600); median cost 2.0, secs 150 for "new"
    check("cost", est["cost"], 2.0 * 2 + 2.0 + 4.0 + 2.0 * 3)
    check("one-shot secs", est["secs_one"], 150 * 2 + 50 + 150 * 3)
    check("multi secs", est["secs_multi"], 600)
    check("no history", est["no_history"], ["new"])
    check("empty history", estimate_cost([], {"a": 1}, set())["no_history"], ["a"])


def _dry_run(argv, tmp: Path):
    """main(--dry-run) on a scratch tasks/configs tree; returns (stdout, counts given to estimate)."""
    import contextlib
    import io
    tasks, cfg = tmp / "tasks", tmp / "configs"
    if not tasks.exists():
        mk_task(tasks, "once", "timeout_sec: 5\n")
        mk_task(tasks, "thrice", "repeat: 3\n")
        (cfg / "bare").mkdir(parents=True)
    seen = {}
    orig_argv, orig_est = sys.argv, run_matrix.estimate_cost

    def fake_est(history, counts, multi):
        seen.update(counts)
        return orig_est([], counts, multi)

    sys.argv = ["run_matrix.py", "--tasks", "once,thrice", "--layers", "bare", "--models", "m1,m2",
                "--config-dir", str(cfg), "--tasks-dir", str(tasks), "--runs-dir", str(tmp / "runs"),
                "--dry-run", *argv]
    run_matrix.estimate_cost = fake_est
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = run_matrix.main()
    finally:
        sys.argv, run_matrix.estimate_cost = orig_argv, orig_est
    return rc, buf.getvalue(), seen


def test_repeat_flag():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        rc, out, counts = _dry_run([], tmp)
        check("no --repeat: meta repeat used", counts, {"once": 2, "thrice": 6})
        check("no --repeat: total", "total runs: 8" in out, True)
        rc, out, counts = _dry_run(["--repeat", "4"], tmp)
        check("--repeat 4 overrides meta (estimate counts)", counts, {"once": 8, "thrice": 8})
        check("--repeat 4: total", "total runs: 16" in out, True)
        check("--repeat 4: per-task line", "thrice: 1 cells x 2 models x 4 repeat = 8" in out, True)
        check("no runs/ written", (tmp / "runs").exists(), False)
        rc, out, _ = _dry_run(["--repeat", "0"], tmp)
        check("--repeat 0 refused", (rc, "must be >= 1" in out), (2, True))


def test_effort_axis():
    check("build_cmd no effort -> no flag", "--effort" in build_cmd("m", [], {}), False)
    cmd = build_cmd("m", ["--bare"], {}, 1.5, "xhigh")
    check("build_cmd effort flag", cmd[cmd.index("--effort") + 1], "xhigh")
    check("efforts are the CLI set (literal)", run_matrix.EFFORTS, ("low", "medium", "high", "xhigh", "max"))
    import score
    check("score.EFFORTS == run_matrix.EFFORTS", score.EFFORTS, run_matrix.EFFORTS)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        rc, out, counts = _dry_run([], tmp)
        check("default effort high: total", ("total runs: 8" in out, "[effort=high]" in out), (True, True))
        rc, out, counts = _dry_run(["--effort", "low,high"], tmp)
        check("two efforts double total", "total runs: 16" in out, True)
        check("two efforts double estimate counts", counts, {"once": 4, "thrice": 12})
        check("each task line shows its effort", (out.count("[effort=low]"), out.count("[effort=high]")), (2, 2))
        for bad in ("turbo", "low,turbo", ""):
            rc, out, _ = _dry_run(["--effort", bad], tmp)
            check(f"--effort {bad!r} refused", (rc, "unknown --effort" in out), (2, True))
        rc, out, _ = _dry_run(["--effort", "max"], tmp)
        check("max accepted", rc, 0)


if __name__ == "__main__":
    test_default_false()
    test_tools_none()
    test_jobs_pool()
    test_ws_root()
    test_estimate()
    test_repeat_flag()
    test_effort_axis()
    print("ALL PASS")
