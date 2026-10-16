"""Tests for item 1.2: cost estimator + fallbacks, ordering, fit block, stop event, stub scoring, resume.

Run: python3 harness/test_budget.py
"""
import json
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402
import score  # noqa: E402


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def rec(task, rung, model, cost, effort="high", passed=True, infra=False, **kw):
    return {"task": task, "rung": rung, "base_model": model, "effort": effort, "model": f"{model}:{effort}",
            "cost_usd": cost, "passed": passed, "infra_error": infra, **kw}


def item(task, layer, model, effort="high", i=1, repeat=1):
    return {"task": task, "layer": layer, "label": layer, "model": model, "effort": effort, "i": i, "repeat": repeat,
            "multi_turn": False, "sha": "", "label_id": f"{task}/{layer}/{model}/{effort}/r{i}"}


def test_estimator():
    hist = [
        rec("a", "bare", "sonnet", 1.0), rec("a", "bare", "sonnet", 3.0),              # mean 2.0
        rec("a", "bare", "sonnet", 0.0, infra=True, infra_reason="auth_error"),         # infra counts: mean 4/3
        rec("a", "bare", "sonnet", 99.0, repeat_majority=True),                          # summed row: ignored
        rec("a", "bare", "sonnet", 0.0, infra=True, infra_reason="skipped"),             # stub: ignored
        rec("a", "bare", "sonnet", 4.0, effort="low"),                                   # other effort
        rec("a", "full", "sonnet", 2.0), rec("a", "full", "opus", 5.0),                  # ratio opus/sonnet = 2.5
        rec("b", "bare", "sonnet", 10.0, effort="default"),                              # old data: no effort
        rec("c", "bare", "opus", 7.0),
    ]
    items = [item("a", "bare", "sonnet"), item("a", "bare", "sonnet", "low"), item("b", "bare", "sonnet"),
             item("b", "full", "opus"), item("c", "bare", "opus", "low"), item("z", "bare", "opus"),
             item("z", "memory", "haiku"), item("a", "full", "opus", "max")]
    est = rm.estimate_items(hist, items)
    got = [(round(e["est"], 4), e["source"]) for e in est]
    check("infra run lowers the mean (1+3+0)/3", got[0], (round(4 / 3, 4), "measured"))
    check("exact effort cell", got[1], (4.0, "measured"))
    check("drop effort (history only has 'default')", got[2], (10.0, "no-effort"))
    # b/full has no sonnet cell, so it cannot use the ratio: layer/model median of opus@full cells (5.0)
    check("no sonnet cell -> layer/model median", got[3], (5.0, "layer-model-median"))
    check("drop effort beats ratio", got[4], (7.0, "no-effort"))
    check("opus at an unseen task/layer: layer/model median", got[5][1], "layer-model-median")
    check("unseen model: global median", got[6][1], "global-median")
    check("a/full/opus at unseen effort: no-effort", got[7], (5.0, "no-effort"))
    # the sonnet x ratio rung: task d has only a sonnet cell
    est2 = rm.estimate_items(hist + [rec("d", "bare", "sonnet", 2.0)], [item("d", "bare", "opus")])
    check("sonnet x model ratio", (round(est2[0]["est"], 4), est2[0]["source"]), (5.0, "sonnet-ratio"))
    check("empty history", rm.estimate_items([], [item("a", "bare", "opus")])[0], {"est": 0.0, "source": "none"})
    check("A/B rung label maps to its base layer",
          rm.estimate_items([rec("a", "full@abc", "opus", 6.0)], [item("a", "full", "opus")])[0]["est"], 6.0)


def test_ordering():
    hist = [rec("disc", "bare", "opus", 1, passed=False), rec("disc", "full", "opus", 1, passed=True),
            rec("flat", "bare", "opus", 1, passed=True), rec("flat", "full", "opus", 1, passed=True),
            rec("junk", "bare", "opus", 1, passed=False, infra=True), rec("junk", "full", "opus", 1, passed=True)]
    disc = rm.discriminating_set(hist)
    check("discriminating set (infra rows ignored)", disc, {("disc", "opus")})
    items = [item("flat", "bare", "opus", i=1), item("disc", "bare", "opus", i=2), item("disc", "full", "opus", i=1),
             item("flat", "full", "opus", i=1), item("disc", "memory", "opus", i=1)]
    ests = [{"est": 1.0, "source": "measured"}, {"est": 0.1, "source": "measured"}, {"est": 5.0, "source": "measured"},
            {"est": 0.5, "source": "measured"}, {"est": 2.0, "source": "measured"}]
    order = [it["label_id"] for it, _ in rm.order_items(items, ests, disc)]
    check("repeat first, then discriminating, then cheapest",
          order, ["disc/memory/opus/high/r1", "disc/full/opus/high/r1", "flat/full/opus/high/r1",
                  "flat/bare/opus/high/r1", "disc/bare/opus/high/r2"])


def test_fit_block():
    its = [item("a", "bare", "sonnet"), item("a", "full", "opus"), item("a", "full", "opus", i=2)]
    ordered = [(it, {"est": e, "source": s}) for it, e, s in
               zip(its, (10.0, 30.0, 40.0), ("measured", "global-median", "sonnet-ratio"))]
    fits = rm.fit_block(ordered, 100.0)
    check("FITS verdict", fits[-1], "verdict: FITS ($80.00 <= $100.00)")
    check("all fit: cutoff = N", "cutoff index: 3 of 3 (every cell fits)" in fits, True)
    check("by model", "by model: opus:high $70.00, sonnet:high $10.00" in fits, True)
    check("unmeasured count", any(l.startswith("UNMEASURED cells: 2") for l in fits), True)
    over = rm.fit_block(ordered, 45.0)
    check("OVER verdict", over[-1], "verdict: OVER BY $35.00 ($80.00 > $45.00)")
    check("cutoff index names the first cell that busts", over[3].startswith("cutoff index: 2 of 3 (cell 2 is a/full/opus/high/r2"), True)
    check("r1 cells fit yes/no", ("all r1 cells fit: yes (r1 est $40.00)" in over, "all r1 cells fit: no (r1 est $40.00)" in rm.fit_block(ordered, 30.0)), (True, True))
    check("exactly at the window FITS", rm.fit_block(ordered, 80.0)[-1].startswith("verdict: FITS"), True)


def test_rate_limit_wording():
    for txt in ("You've hit your usage limit", "Your limit resets at 3am", "You're out of extra usage"):
        check(f"matches {txt!r}", bool(rm._RATE_LIMIT_RE.search(txt)), True)
    check("no match on a plain error", bool(rm._RATE_LIMIT_RE.search("syntax error")), False)


def test_stop_after_two_consecutive():
    b = rm.MatrixBudget()
    check("cum accumulates", (b.record(1.5, False), b.record(None, False)), (1.5, 1.5))
    b.record(0.5, True)
    check("one exhausted run does not stop", b.stop.is_set(), False)
    b.record(0.5, False)
    b.record(0.5, True)
    check("a success resets the streak", b.stop.is_set(), False)
    b.record(0.5, True)
    check("2 consecutive stop", b.stop.is_set(), True)

    # the 3rd run is never launched; its cell becomes a skipped stub
    b, launched, skipped = rm.MatrixBudget(), [], []
    items = [item("t", "bare", "m", i=i, repeat=5) for i in range(1, 6)]

    def runner(it):
        launched.append(it["i"])
        b.record(1.0, True)

    results, failures = rm.execute_items(items, runner, 1, stop=b.stop, on_skip=lambda it: skipped.append(it["i"]))
    check("launched", launched, [1, 2])
    check("skipped", skipped, [3, 4, 5])
    check("failures stay 0 (rc comes from the skipped count)", failures, 0)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p = rm.write_skipped(items[2], d / "runs", "abc", b.cum, "stopped")
        meta = json.loads(p.read_text())["_meta"]
        check("stub meta", (meta["skipped"], meta["matrix_cum_usd"], meta["repeat_index"], meta["model"]), (True, 2.0, 3, "m"))
        check("stub file name = timestamp + item stem", p.name.split("_", 1)[1], rm.item_stem(items[2]) + ".json")
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "meta.yaml").write_text("")
        s = score.score_run(p, d / "tasks")
        check("score.py: stub is infra 'skipped'", (s["infra_error"], s["infra_reason"], s["passed"]), (True, "skipped", False))

    # jobs>1: threads stop launching too
    b, n, lock = rm.MatrixBudget(), [], threading.Lock()

    def runner2(it):
        with lock:
            n.append(1)
        b.record(0, True)

    rm.execute_items([item("t", "bare", "m", i=i, repeat=30) for i in range(1, 31)], runner2, 4, stop=b.stop)
    check("pool: stop honoured (at most stop + in-flight workers)", len(n) <= 2 + 3, True)


def test_run_one_stamps_cum_and_trips_stop():
    ok = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "x", "total_cost_usd": 1.25,
                     "usage": {"output_tokens": 10}})
    limited = json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "You've hit your usage limit",
                          "total_cost_usd": 0.0, "usage": {"output_tokens": 0}})
    outs = iter([ok] + [limited] * 8)
    orig = (subprocess.run, rm.time.sleep, rm.rate_limit_backoff_seconds)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t1").mkdir(parents=True)
        (d / "tasks" / "t1" / "prompt.md").write_text("hi")
        (d / "tasks" / "t1" / "meta.yaml").write_text("timeout_sec: 60\n")
        (d / "configs" / "1").mkdir(parents=True)
        subprocess.run = lambda cmd, **kw: types.SimpleNamespace(stdout=next(outs), stderr="", returncode=0)
        rm.time.sleep = lambda s: None
        rm.rate_limit_backoff_seconds = lambda a: 0
        b, cums = rm.MatrixBudget(), []
        try:
            for _ in range(3):
                f = rm.run_one("t1", 1, "m", d / "tasks", d / "configs", d / "runs", budget=b)
                cums.append(json.loads(f.read_text())["_meta"]["matrix_cum_usd"])
        finally:
            subprocess.run, rm.time.sleep, rm.rate_limit_backoff_seconds = orig
    check("matrix_cum_usd stamped, running", cums, [1.25, 1.25, 1.25])
    check("two exhausted runs tripped stop", b.stop.is_set(), True)


def test_resume():
    its = [item("t", "bare", "m", i=i, repeat=3) for i in (1, 2, 3)] + [item("u", "full", "claude-x", repeat=1)]
    check("stem has _rN only when repeated", [rm.item_stem(x) for x in its],
          ["t_bare_m_high_r1", "t_bare_m_high_r2", "t_bare_m_high_r3", "u_full_claude_x_high"])
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ts = "20261015T030000Z_"
        (d / f"{ts}t_bare_m_high_r1.json").write_text(json.dumps({"_meta": {"task": "t"}}))                  # valid
        (d / f"{ts}t_bare_m_high_r2.json").write_text(json.dumps({"_meta": {"rate_limited": True}}))         # exhausted: re-run
        stub = rm.write_skipped(its[2], d, "", 0.0, "stopped")                                              # stub: re-run
        (d / f"{ts}u_full_claude_x_high.json").write_text("{not json")                                      # corrupt: re-run
        (d / f"{ts}t_bare_m_high_r1.trace.jsonl").write_text('{"type":"result"}')                            # not a transcript
        valid, stubs = rm.scan_runs(d)
        check("valid stems", valid, {"t_bare_m_high_r1"})
        check("stubs found", list(stubs), ["t_bare_m_high_r3"])
        check("stub path", stubs["t_bare_m_high_r3"], stub)
        check("todo after resume", [rm.item_stem(x) for x in its if rm.item_stem(x) not in valid],
              ["t_bare_m_high_r2", "t_bare_m_high_r3", "u_full_claude_x_high"])
    check("missing runs dir", rm.scan_runs(Path("/nonexistent-runs-dir")), (set(), {}))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print("ALL PASS")
