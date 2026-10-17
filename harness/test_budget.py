"""Tests for item 1.2: cost estimator + fallbacks, ordering, fit block, stop event, stub scoring, resume.

Run: python3 harness/test_budget.py
"""
import contextlib
import io
import json
import os
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
        (d / f"{ts}u_full_claude_x_high.json").write_text(json.dumps({"_meta": {"auth_error": True}}))     # auth failure: re-run
        (d / f"{ts}v_bare_m_high.json").write_text("{not json")                                             # corrupt: skipped by the scan
        (d / f"{ts}t_bare_m_high_r1.trace.jsonl").write_text('{"type":"result"}')                            # not a transcript
        valid, stale = rm.scan_runs(d)
        check("valid stems", valid, {"t_bare_m_high_r1"})
        check("stale (stub, rate_limited, auth_error) stems", sorted(stale),
              ["t_bare_m_high_r2", "t_bare_m_high_r3", "u_full_claude_x_high"])
        check("stub path", stale["t_bare_m_high_r3"], [stub])
        check("todo after resume", [rm.item_stem(x) for x in its if rm.item_stem(x) not in valid],
              ["t_bare_m_high_r2", "t_bare_m_high_r3", "u_full_claude_x_high"])
    check("missing runs dir", rm.scan_runs(Path("/nonexistent-runs-dir")), (set(), {}))


def test_rounds_by_repeat_index():
    """jobs>1: a round's multi-turn cells run before the next round's one-shot cells, and stop spans rounds."""
    def it(task, i, multi):
        x = item(task, "bare", "m", i=i, repeat=2)
        x["multi_turn"] = multi
        return x
    items = [it("a", 1, False), it("b", 1, False), it("mt", 1, True), it("c", 2, False), it("d", 2, False), it("mt", 2, True)]
    launched, lock = [], threading.Lock()

    def runner(x):
        with lock:
            launched.append(x["label_id"])

    rm.execute_items(items, runner, 2)
    ids = [x["label_id"] for x in items]
    check("r1 one-shots (any order), then r1 multi_turn, then r2 one-shots, then r2 multi_turn",
          (sorted(launched[:2]), launched[2], sorted(launched[3:5]), launched[5]),
          (sorted(ids[:2]), ids[2], sorted(ids[3:5]), ids[5]))
    # the stop trips on the r1 multi_turn run: r2 cells (both kinds) are skipped, not launched
    b, launched, skipped = rm.MatrixBudget(stop_after=1), [], []

    def runner2(x):
        with lock:
            launched.append(x["label_id"])
        if x["multi_turn"]:
            b.record(0, True)

    rm.execute_items(items, runner2, 2, stop=b.stop, on_skip=lambda x: skipped.append(x["label_id"]))
    check("stop spans rounds: launched", (len(launched), launched[2]), (3, ids[2]))
    check("stop spans rounds: skipped", sorted(skipped), sorted(ids[3:]))


def test_model_family_keys():
    check("family of full id and alias", [rm._model_family(m) for m in ("claude-sonnet-4-6", "opus", "claude-haiku-4-5", "m")],
          ["sonnet", "opus", "haiku", "m"])
    hist = [rec("a", "bare", "claude-sonnet-4-6", 2.0, passed=False), rec("a", "full", "claude-opus-4-8", 7.0),
            rec("a", "bare", "claude-sonnet-4-6", 1.0, passed=False), rec("a", "full", "claude-sonnet-4-6", 1.0)]
    est = rm.estimate_items(hist, [item("a", "bare", "sonnet"), item("a", "full", "opus")])
    check("alias items hit full-id history", [(e["est"], e["source"]) for e in est], [(1.5, "measured"), (7.0, "measured")])
    est = rm.estimate_items(hist + [rec("d", "bare", "claude-sonnet-4-6", 2.0)], [item("d", "bare", "opus")])
    check("sonnet-ratio works on full ids", (est[0]["est"], est[0]["source"]), (2.0 * 7.0, "sonnet-ratio"))  # ratio = opus/sonnet on a/full = 7.0 / 1.0
    disc = rm.discriminating_set(hist)
    check("discriminating set keyed by family", disc, {("a", "sonnet")})
    order = rm.order_items([item("a", "x", "opus"), item("a", "bare", "claude-sonnet-4-6")],
                           [{"est": 1.0, "source": "measured"}, {"est": 9.0, "source": "measured"}], disc)
    check("a full-id item matches the family-keyed disc entry (disc first despite higher cost)",
          [it["model"] for it, _ in order], ["claude-sonnet-4-6", "opus"])


def _write_scores(d, name, recs):
    Path(d, name).write_text(json.dumps({"scores": recs}))


def test_stamped_scorecards():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # mtime order is the reverse of the stamp order, and the aggregates are newest by mtime
        for i, name in enumerate(["20261003T000000Z-ccc.rescored.scores.json", "MERGED-aaa.scores.json",
                                  "20261001T000000Z-aaa.scores.json", "20261002T000000Z-bbb.scores.json",
                                  "20261002T000000Z-bbb.rescored.scores.json", "20261001T000000Z-aaa.md"][::-1]):
            (d / name).write_text("{}")
            os.utime(d / name, (1000 + i, 1000 + i))
        check("newest stamp first; original before its rescored copy; MERGED and non-scores files skipped",
              [f.name for f in rm.stamped_scorecards(d)],
              ["20261003T000000Z-ccc.rescored.scores.json", "20261002T000000Z-bbb.scores.json",
               "20261002T000000Z-bbb.rescored.scores.json", "20261001T000000Z-aaa.scores.json"])
    check("no scorecards dir", rm.stamped_scorecards(Path("/nonexistent-scorecards")), [])


def test_history_discriminating():
    """overnight.sh writes one scores file per stage: canary, verdict-opus, verdict-sonnet (newest). A single
    newest file would hold only sonnet keys; the set must come from all stages, first (newest) hit per key."""
    def pair(task, model, bare, full, **kw):
        return [rec(task, "bare", model, 1, passed=bare, **kw), rec(task, "full", model, 1, passed=full, **kw)]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _write_scores(d, "20261002T100003Z-aaa.scores.json",  # canary stage: both models, canary tasks
                      pair("canary/x", "opus", False, True) + pair("canary/x", "sonnet", False, True))
        _write_scores(d, "20261002T100500Z-aaa.scores.json",  # verdict-opus
                      pair("g/t1", "claude-opus-4-8", False, True) + pair("g/t2", "claude-opus-4-8", True, True))
        _write_scores(d, "20261002T110000Z-aaa.scores.json",  # verdict-sonnet (newest): sonnet keys only
                      pair("g/t3", "claude-sonnet-4-6", False, True) + [rec("g/t1", "bare", "claude-sonnet-4-6", 1, passed=True)])
        want = {("canary/x", "opus"), ("canary/x", "sonnet"), ("g/t1", "opus"), ("g/t3", "sonnet")}
        check("all three stages feed the set (a single newest file would give only g/t3)", rm.history_discriminating(d), want)

        # older night: says g/t2 opus and g/t1 sonnet differ; newer night already decided g/t2 opus (flat), and g/t1 sonnet
        # has only ONE layer in the newer file, so the older one is its first >=2-layer file.
        _write_scores(d, "20261001T000000Z-old.scores.json",
                      pair("g/t2", "opus", False, True) + pair("g/t1", "sonnet", False, True))
        check("first (newest) file with >= 2 layers decides; a 1-layer file does not shadow",
              rm.history_discriminating(d), want | {("g/t1", "sonnet")})

        # MERGED aggregate and unparseable files are ignored; a rescored copy is the only copy of an old run
        _write_scores(d, "MERGED-zzz.scores.json", pair("m/x", "opus", False, True))
        (d / "20261004T000000Z-bad.scores.json").write_text("{not json")
        _write_scores(d, "20260901T000000Z-316c160.rescored.scores.json", pair("r/only", "opus", False, True))
        # same stamp: the original (flat) beats its rescored copy (differs)
        _write_scores(d, "20260902T000000Z-abc.scores.json", pair("r/tie", "opus", True, True))
        _write_scores(d, "20260902T000000Z-abc.rescored.scores.json", pair("r/tie", "opus", False, True))
        got = rm.history_discriminating(d)
        check("rescored-only run counted", ("r/only", "opus") in got, True)
        check("original wins a same-stamp tie against its rescored copy", ("r/tie", "opus") in got, False)
        check("MERGED aggregate ignored", ("m/x", "opus") in got, False)
        check("infra rows do not count as a layer", rm.discriminating_set(
            [rec("i", "bare", "opus", 1, passed=False, infra=True), rec("i", "full", "opus", 1)]), set())


def test_family_ratios_one_figure():
    """claude-opus-4-8 sorts before the alias `opus`: the old re-key kept its 0.9x for every opus item."""
    hist = [rec("a", "bare", "sonnet", 1.0), rec("a", "bare", "claude-opus-4-8", 0.9),
            rec("b", "bare", "sonnet", 1.0), rec("b", "bare", "opus", 2.4),
            rec("d", "bare", "sonnet", 2.0)]
    r = rm.family_ratios(hist)
    check("one pooled median per family (0.9x and 2.4x -> 1.65x)", (sorted(r), round(r["opus"], 4)), (["opus"], 1.65))
    est = rm.estimate_items(hist, [item("d", "bare", "opus"), item("d", "bare", "claude-opus-4-8")])
    check("estimator uses that same ratio (sonnet 2.0 x 1.65)",
          [(round(e["est"], 4), e["source"]) for e in est], [(3.3, "sonnet-ratio"), (3.3, "sonnet-ratio")])
    # the dry-run prints the same figure
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "d").mkdir(parents=True)
        (d / "tasks" / "d" / "meta.yaml").write_text("")
        (d / "configs" / "bare").mkdir(parents=True)
        (d / "sc").mkdir()
        _write_scores(d / "sc", "20261001T000000Z-aaa.scores.json", hist)
        out = io.StringIO()
        orig = sys.argv
        sys.argv = ["run_matrix.py", "--dry-run", "--tasks", "d", "--layers", "bare", "--models", "opus,claude-opus-4-8,sonnet",
                    "--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"), "--runs-dir", str(d / "runs"),
                    "--scorecards-dir", str(d / "sc")]
        try:
            with contextlib.redirect_stdout(out):
                rc = rm.main()
        finally:
            sys.argv = orig
        lines = out.getvalue().splitlines()
        check("dry-run rc", rc, 0)
        check("dry-run prints the estimator's ratio for the alias and for the full id",
              [l for l in lines if l.startswith("measured cost ratio")],
              ["measured cost ratio opus vs sonnet: 1.65x (median, matched cells)",
               "measured cost ratio claude-opus-4-8 vs sonnet: 1.65x (median, matched cells)"])


def test_knockout_variant_is_its_own_layer():
    # discriminating: a knockout that flips the verdict is a layer of its own, not pooled with its base
    flip = [rec("t", "skills", "opus", 1, passed=True), rec("t", "skills~ko.x", "opus", 1, passed=False),
            rec("t", "bare", "opus", 1, passed=True)]
    check("variant vs base pass/fail differ -> discriminating", rm.discriminating_set(flip), {("t", "opus")})
    same = [rec("t", "skills", "opus", 1), rec("t", "skills~ko.x@abc", "opus", 1), rec("t", "skills@abc", "opus", 1)]
    check("@sha is stripped: same verdicts -> not discriminating", rm.discriminating_set(same), set())
    # estimator: a variant that never ran is NOT 'measured'
    hist = [rec("t", "skills", "opus", 4.0), rec("u", "bare", "opus", 8.0)]
    est = rm.estimate_items(hist, [item("t", "skills~ko.x", "opus"), item("t", "skills", "opus"),
                                   item("t", "skills~ko.x", "opus", "low"), item("t", "full~nohook", "opus"),
                                   item("v", "skills~ko.x", "opus")])
    got = [(e["est"], e["source"]) for e in est]
    check("unrun variant -> its base layer's cost, labelled base-layer", got[0], (4.0, "base-layer"))
    check("the base layer itself stays measured", got[1], (4.0, "measured"))
    check("base-layer fallback at another effort uses the base's no-effort mean", got[2], (4.0, "base-layer"))
    check("variant whose base never ran: median fallback, not measured", got[3][1], "global-median")
    check("no data for that task: median of the base layer's opus cells", got[4], (4.0, "layer-model-median"))
    check("base-layer counts as UNMEASURED", "base-layer" in rm.UNMEASURED_SOURCES, True)
    fits = rm.fit_block([(it, e) for it, e in zip([item("t", "skills~ko.x", "opus")], est[:1])], 100.0)
    check("fit block counts it", any(l.startswith("UNMEASURED cells: 1") for l in fits), True)
    # once the variant has run, it is measured under its own layer spec (A/B @sha stripped)
    hist2 = hist + [rec("t", "skills~ko.x@abc", "opus", 6.0)]
    est = rm.estimate_items(hist2, [item("t", "skills~ko.x", "opus"), item("t", "skills", "opus")])
    check("run variant measured on its own cost; base unaffected", [(e["est"], e["source"]) for e in est],
          [(6.0, "measured"), (4.0, "measured")])


def test_supersede_runs_paths():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        old = ["20261015T010000Z_t_opus[1m]_high", "20261015T020000Z_t_bare_m_high_r1", "20261015T030000Z_t_bare_m_high_r1"]
        keep = ["20261015T020000Z_t_bare_m_high_r10", "20261015T020000Z_t_bare_m_high_r1x", "20261015T020000Z_t_opus1m_high"]
        for stem in old + keep:
            (d / f"{stem}.json").write_text("{}")
            (d / f"{stem}.trace.jsonl").write_text("{}")
        paths = [d / f"{s}.json" for s in old]
        rm.supersede_runs(d, paths)
        check("a '[' in the stem still moves its transcript and sidecar; every stale path per stem moves",
              sorted(p.name for p in (d / "superseded").iterdir()),
              sorted(f"{s}{x}" for s in old for x in (".json", ".trace.jsonl")))
        check("_r1 does not take _r10 / _r1x / a '[1m]'-lookalike with it",
              sorted(p.name for p in d.iterdir() if p.is_file()),
              sorted(f"{s}{x}" for s in keep for x in (".json", ".trace.jsonl")))


def _run_sh_block(start, end):
    text = (Path(__file__).resolve().parent.parent / "run.sh").read_text()
    a = text.index(start)
    return text[a:text.index(end, a)]


def test_run_sh_archives_and_cleans_superseded():
    """run.sh's archive block moves runs/superseded/ with the night; its --clean-ws step reads superseded/*.json."""
    archive = _run_sh_block("shopt -s nullglob\nprior=", "\n# --- 2. Run the matrix")
    clean = _run_sh_block("import json, re, shutil, sys", "\nPY\n")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        runs = d / "runs"
        (runs / "archive" / "OLD").mkdir(parents=True)
        (runs / "archive" / "OLD" / "keep.json").write_text("{}")
        (runs / "superseded").mkdir()
        (runs / "superseded" / "a.json").write_text("{}")
        (runs / "b.json").write_text("{}")
        subprocess.run(["bash", "-c", f'set -euo pipefail\nRUNS_DIR={runs}\nRESUME=0\nTS=NEW\n{archive}'],
                       check=True, capture_output=True)
        check("superseded/ archived with the night", sorted(p.relative_to(runs / "archive" / "NEW").as_posix()
                                                            for p in (runs / "archive" / "NEW").rglob("*.json")),
              ["b.json", "superseded/a.json"])
        check("runs/ is empty of superseded afterwards; archive/OLD untouched",
              (sorted(p.name for p in runs.iterdir()), (runs / "archive" / "OLD" / "keep.json").exists()), (["archive"], True))
        # --resume keeps it in place
        (runs / "superseded").mkdir()
        (runs / "superseded" / "c.json").write_text("{}")
        subprocess.run(["bash", "-c", f'set -euo pipefail\nRUNS_DIR={runs}\nRESUME=1\nTS=N2\n{archive}'], check=True, capture_output=True)
        check("--resume leaves superseded/ in place", (runs / "superseded" / "c.json").exists(), True)
        # clean-ws: the workspace of a superseded run is removed, archive/ is not read
        ws_root = d / "ws"
        for name in ("w-0123456789", "w-abcdef0123", "w-9999999999"):
            (ws_root / name / "w").mkdir(parents=True)
        for f, name in ((runs / "superseded" / "c.json", "w-0123456789"), (runs / "d.json", "w-abcdef0123"),
                        (runs / "archive" / "OLD" / "keep.json", "w-9999999999")):
            f.write_text(json.dumps({"_meta": {"workspace_dir": str(ws_root / name / "w")}}))
        subprocess.run([sys.executable, "-c", clean, str(runs)], check=True, capture_output=True)
        check("clean-ws removes superseded and current workspaces, never archive/'s",
              sorted(p.name for p in ws_root.iterdir()), ["w-9999999999"])


def test_main_stop_returns_1_and_resume_supersedes():
    """main() with a fake run_one: a stopped matrix exits 1 and writes stubs; --resume re-runs the
    stubs and exhausted transcripts, moves the old ones (and sidecars) aside, never touches runs/archive."""
    outcomes = iter(["ok", "limited", "limited"])
    ts = "20261015T030000Z_"

    def fake_run_one(task, layer, model, tasks_dir, configs_dir, runs_dir, **kw):
        stem = rm.item_stem({"task": task, "label": kw["rung"], "model": model, "effort": kw["effort"],
                             "i": kw["repeat_index"], "repeat": kw["repeat_total"]})
        out = next(outcomes, "ok")
        meta = {"rate_limited": out == "limited"}
        kw["budget"].record(0, out == "limited")
        f = Path(runs_dir) / f"{ts}{stem}.json"
        Path(runs_dir).mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"_meta": meta}))
        f.with_suffix(".trace.jsonl").write_text("{}")
        return f

    orig = (rm.run_one, rm.oauth_token, sys.argv)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "meta.yaml").write_text("")
        (d / "configs" / "bare").mkdir(parents=True)
        (d / "runs" / "archive").mkdir(parents=True)
        (d / "runs" / "archive" / f"{ts}t_bare_m_high_r2.json").write_text(json.dumps({"_meta": {"rate_limited": True}}))
        argv = ["run_matrix.py", "--tasks", "t", "--layers", "bare", "--models", "m", "--effort", "high", "--repeat", "4",
                "--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"), "--runs-dir", str(d / "runs"),
                "--ws-root", str(d / "ws"), "--scorecards-dir", str(d / "sc")]
        rm.run_one, rm.oauth_token = fake_run_one, lambda: "tok"
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = rm.main()
            check("stopped matrix returns 1", rc, 1)
            runs = d / "runs"
            valid, stale = rm.scan_runs(runs)
            check("r1 valid; r2, r3 exhausted, r4 stub", (sorted(valid), sorted(stale)),
                  (["t_bare_m_high_r1"], ["t_bare_m_high_r2", "t_bare_m_high_r3", "t_bare_m_high_r4"]))
            outcomes = iter([])  # every re-run succeeds
            sys.argv = argv + ["--resume"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = rm.main()
            check("resumed matrix returns 0", rc, 0)
            valid, stale = rm.scan_runs(runs)
            check("all four cells valid, nothing stale left in runs/", (len(valid), stale), (4, {}))
            check("each stem scored once", sorted(p.name.split("_", 1)[1] for p in runs.glob("*.json")),
                  [f"t_bare_m_high_r{i}.json" for i in (1, 2, 3, 4)])
            check("old r2/r3/r4 moved aside with the r2 sidecar",
                  sorted(p.name.split("_", 1)[1] for p in (runs / "superseded").iterdir()),
                  ["t_bare_m_high_r2.json", "t_bare_m_high_r2.trace.jsonl", "t_bare_m_high_r3.json",
                   "t_bare_m_high_r3.trace.jsonl", "t_bare_m_high_r4.json"])
            check("archive untouched", [p.name for p in (runs / "archive").iterdir()], [f"{ts}t_bare_m_high_r2.json"])
        finally:
            rm.run_one, rm.oauth_token, sys.argv = orig


def test_model_family_fable():
    check("fable family", [rm._model_family(m) for m in ("claude-fable-5-1", "fable", "claude-opus-4-8")], ["fable", "fable", "opus"])
    ests = rm.estimate_items([rec("a", "bare", "claude-fable-5-1", 4.0)], [item("a", "bare", "claude-fable-5-1")])
    check("fable history is keyed by family", (ests[0]["est"], ests[0]["source"]), (4.0, "measured"))


def _wrec(task, model, secs, **kw):
    return {"task": task, "rung": "bare", "base_model": model, "model": f"{model}:high", "wall_clock_sec": secs, "infra_error": False, **kw}


def test_wall_estimate_and_line():
    check("stall factor pinned to the round-3 measurement (24036 / (6014.4 / 4))", rm.STALL_FACTOR, 16.0)
    check("derivation", round(24036 / (6014.4 / 4)), 16)
    hist = [_wrec("a", "claude-sonnet-4-6", 100), _wrec("a", "claude-sonnet-4-6", 200),       # a/sonnet mean 150
            _wrec("b", "claude-sonnet-4-6", 50),                                              # b/sonnet 50 -> sonnet family mean of records 350/3
            _wrec("a", "claude-sonnet-4-6", 9999, infra_error=True), _wrec("a", "claude-sonnet-4-6", 9999, repeat_majority=True),
            _wrec("a", "claude-sonnet-4-6", 0)]                                               # infra, majority, zero: ignored
    one = lambda t, m="sonnet": {**item(t, "bare", m), "multi_turn": False}  # noqa: E731
    multi = lambda t, m="sonnet": {**item(t, "bare", m), "multi_turn": True}  # noqa: E731
    secs, lacking = rm.wall_estimate(hist, [one("a"), one("b")], jobs=2, factor=1.0)
    check("one-shot cells summed over jobs", (secs, lacking), ((150 + 50) / 2, 0))
    secs, lacking = rm.wall_estimate(hist, [one("a"), multi("b")], jobs=4, factor=2.0)
    check("multi_turn added serially, factor multiplies", (secs, lacking), ((150 / 4 + 50) * 2.0, 0))
    secs, lacking = rm.wall_estimate(hist, [one("zzz")], jobs=1, factor=1.0)
    check("no cell history -> family mean of all its records, counted", (secs, lacking), (350 / 3, 1))
    secs, lacking = rm.wall_estimate(hist, [one("a", "fable")], jobs=1, factor=1.0)
    check("family with no history -> mean of every record", (secs, lacking), (350 / 3, 1))
    check("empty history: 0 and every cell lacking", rm.wall_estimate([], [one("a"), one("b")], 2), (0.0, 2))
    check("line format", rm.wall_line(2 * 3600 + 14 * 60, 16.0, 3), "est wall: 2h 14m (factor 16, 3 cells lack history)")


def test_dry_run_prints_wall_line_after_verdict():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "a").mkdir(parents=True)
        (d / "tasks" / "a" / "prompt.md").write_text("hi")
        (d / "configs" / "bare").mkdir(parents=True)
        (d / "sc").mkdir()
        _write_scores(d / "sc", "20260101T000000Z-x.scores.json", [_wrec("a", "claude-sonnet-4-6", 300)])
        base = [sys.executable, str(Path(rm.__file__)), "--dry-run", "--tasks", "a", "--layers", "bare", "--models", "sonnet",
                "--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"), "--runs-dir", str(d / "runs"),
                "--scorecards-dir", str(d / "sc")]
        out = subprocess.run(base, capture_output=True, text=True).stdout.splitlines()
        i = next(k for k, ln in enumerate(out) if ln.startswith("verdict: "))
        check("wall line directly after the verdict (300 s x 16)", out[i + 1], "est wall: 1h 20m (factor 16, 0 cells lack history)")
        out = subprocess.run(base + ["--stall-factor", "1"], capture_output=True, text=True).stdout.splitlines()
        check("--stall-factor overrides", out[i + 1], "est wall: 0h 5m (factor 1, 0 cells lack history)")
        out = subprocess.run(base[:-2] + ["--scorecards-dir", str(d / "none")], capture_output=True, text=True).stdout.splitlines()
        i = next(k for k, ln in enumerate(out) if ln.startswith("verdict: "))
        check("no history: every cell lacks it", out[i + 1], "est wall: 0h 0m (factor 16, 1 cells lack history)")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print("ALL PASS")
