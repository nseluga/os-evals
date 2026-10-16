"""Tests for the cost/quality frontier and run history in stats.py (item 1.4).

Run: python3 harness/test_frontier.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _r(task, rung, model, passed, cost, **kw):
    return {"task": task, "rung": rung, "model": model, "passed": passed, "cost_usd": cost, **kw}


# Pareto: A (cheap, 50%), B (mid, 100%), C (dear, 100%: dominated by B), D (cheap, 0%: dominated by A)
PARETO = ([_r("t1", "a", "m", True, 1.0), _r("t2", "a", "m", False, 1.0)]
          + [_r("t1", "b", "m", True, 2.0), _r("t2", "b", "m", True, 2.0)]
          + [_r("t1", "c", "m", True, 5.0), _r("t2", "c", "m", True, 5.0)]
          + [_r("t1", "d", "m", False, 1.0), _r("t2", "d", "m", False, 1.0)])

cells = stats.frontier_cells(PARETO)
check("pareto flags", {k[0]: c["pareto"] for k, c in cells.items()}, {"a": True, "b": True, "c": False, "d": False})
check("pass_rate", cells[("a", "m", "default")]["pass_rate"], 0.5)
check("pass_per_dollar", cells[("b", "m", "default")]["pass_per_dollar"], 0.5)
check("zero cost guard", stats.frontier_cells([_r("t", "z", "m", True, 0)])[("z", "m", "default")]["pass_per_dollar"], None)
check("missing cost guard", stats.frontier_cells([{"task": "t", "rung": "z", "model": "m", "passed": True}])[("z", "m", "default")]["pass_per_dollar"], None)
twin = [_r("t", "x", "m", True, 1.0), _r("u", "y", "m", True, 1.0)]
check("equal cells both pareto", [c["pareto"] for c in stats.frontier_cells(twin).values()], [True, True])

# Repeat=3: three individuals at $1 each plus a majority row carrying the summed $3 -> mean stays $1, n stays 3.
REP = ([_r("t", "bare", "m", True, 1.0, is_repeat_individual=True) for _ in range(3)]
       + [_r("t", "bare", "m", True, 3.0, repeat_majority=True, repeat_total=3)])
c = stats.frontier_cells(REP)[("bare", "m", "default")]
check("repeat n", c["n"], 3)
check("repeat mean cost not tripled", c["mean_cost_usd"], 1.0)

# Sentinel and infra rows are excluded.
check("sentinel/infra excluded", stats.frontier_cells([_r("s", "bare", "m", True, 1.0, sentinel=True),
                                                       _r("i", "bare", "m", False, 1.0, infra_error=True)]), {})

# Effort: missing -> "default"; present -> its own cell.
eff = stats.frontier_cells([_r("t", "bare", "m", True, 1.0), _r("t", "bare", "m", True, 1.0, effort="high")])
check("effort keys", sorted(k[2] for k in eff), ["default", "high"])

# History line shape.
INFRA = _r("i", "bare", "m", False, 2.0, infra_error=True)
DATA = {"os_sha": "abc1234", "scores": REP + [_r("s", "bare", "m2", True, 0.5, sentinel=True), INFRA]}
h = stats.history_line(DATA, "20260101T000000Z-abc1234")
check("history keys", sorted(h), ["cost_by_model", "n", "os_sha", "rungs", "stamp", "task_set"])
check("history rungs", h["rungs"], {"bare": {"pass": 1, "n": 1}})
# Real spend: 3 individuals ($3) + infra ($2) + sentinel ($0.5); the $3 majority row is not added again.
check("history cost (all individual rows incl. infra and sentinel)", h["cost_by_model"], {"m": 5.0, "m2": 0.5})
check("history n", h["n"], 1)
check("task_set ignores order", stats.task_set_hash([{"task": "a"}, {"task": "b"}]), stats.task_set_hash([{"task": "b"}, {"task": "a"}]))
json.dumps(h)

# Trend: filter by task_set, last line per stamp wins, last 8 only.
with tempfile.TemporaryDirectory() as td:
    hp = Path(td) / "history.jsonl"
    mine = stats.task_set_hash(PARETO)
    lines = [{"stamp": f"2026010{i}", "os_sha": f"sha{i}", "task_set": mine, "rungs": {"a": {"pass": i, "n": 9}}, "cost_by_model": {"m": 1.0}, "n": 9}
             for i in range(1, 10)]
    lines.append({"stamp": "20260105", "os_sha": "REWRITTEN", "task_set": mine, "rungs": {}, "cost_by_model": {}, "n": 0})
    lines.append({"stamp": "20260106", "os_sha": "OTHERSET", "task_set": "ffffffffffff", "rungs": {}, "cost_by_model": {}, "n": 0})
    hp.write_text("".join(json.dumps(l) + "\n" for l in lines) + "not json\n")
    out = "\n".join(stats.trend_section(PARETO, hp))
    check("trend heading", "## Trend across os commits" in out, True)
    check("trend excludes other task_set", "OTHERSET" in out, False)
    check("trend last stamp wins", "REWRITTEN" in out and "sha5" not in out, True)
    check("trend keeps last 8 (drops oldest)", "sha1" not in out and "sha2" in out, True)
    check("trend no matching lines -> no section", stats.trend_section([_r("zz", 1, "m", True, 1)], hp), [])
    check("trend missing file -> no section", stats.trend_section(PARETO, Path(td) / "nope"), [])

    # Backfill: skips bad files, one line per good scores.json.
    sc = Path(td) / "sc"
    sc.mkdir()
    (sc / "20260101T000000Z-abc.scores.json").write_text(json.dumps(DATA))
    (sc / "20260102T000000Z-bad.scores.json").write_text("{not json")
    out_h = Path(td) / "out.jsonl"
    check("backfill count", stats.backfill_history(sc, out_h), 1)
    check("backfill stamp", json.loads(out_h.read_text())["stamp"], "20260101T000000Z-abc")

    # Render includes both sections after Token & Cost, before Pass/Fail.
    md = stats.render_markdown({"os_sha": "x", "scores": PARETO}, stats.compute_stats(PARETO), stats.token_summary(PARETO), history_path=hp)
    i = [md.index(s) for s in ("## Token & Cost", "## Cost/Quality Frontier (per run)", "## Trend across os commits", "## Pass/Fail by Rung")]
    check("section order", i == sorted(i), True)

print("PASS test_frontier")
