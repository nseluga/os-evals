"""Tests for infra exclusion in stats.py.

Fixture: tasks A, B, X, one model, rungs 1-4. X is infra at rung 2 and passes elsewhere;
A fails r1 then passes r2+ (a real flip); B passes everywhere.

Verifies X: never a flip / prune / regressed, excluded from the 1->2 and 2->3 sign-test
denominators, excluded from pass-table denominators, and named on the top infra line.

Run: python3 harness/test_stats_infra.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _s(task, rung, passed, infra=False, skill="sk"):
    return {"task": task, "rung": rung, "model": "m", "passed": passed and not infra,
            "infra_error": infra, "curated_skill": skill, "total_tokens": 1, "cost_usd": 0.0}


def _fixture():
    rows = []
    for r in (1, 2, 3, 4):
        rows.append(_s("B", r, True))
        rows.append(_s("A", r, r >= 2))
        rows.append(_s("X", r, True, infra=(r == 2)))
    return {"os_sha": "abc", "scores": rows,
            "scored_run_ids": ["20260101T000000Z_a.json", "20260103T000000Z_b.json"]}


def _md():
    data = _fixture()
    st = stats.compute_stats(data["scores"])
    return data, st, stats.render_markdown(data, st, stats.token_summary(data["scores"]))


def test_sign_test_excludes_x():
    _, st, _ = _md()
    pairs = st["rung_pairs"]["m"]
    for name in ("rung1_vs_rung2", "rung2_vs_rung3"):
        v = {t["task"]: t["verdict"] for t in pairs[name]["task_verdicts"]}
        check(f"{name} X excluded", v["X"], "infra (excluded)")
        n = pairs[name]["higher_wins"] + pairs[name]["lower_wins"] + pairs[name]["ties"]
        check(f"{name} denominator", n, 2)
    v34 = {t["task"]: t["verdict"] for t in pairs["rung3_vs_rung4"]["task_verdicts"]}
    check("rung3_vs_rung4 X counted", v34["X"], "tie")


def test_no_flip_prune_regressed_for_x():
    _, _, md = _md()
    flips = [l for l in md.splitlines() if "fail→pass flips" not in l and l.startswith("- **") and "net" in l]
    check("X not in any flip line", any("X" in l.split("=")[-1] for l in flips), False)
    check("X not a prune candidate", "Prune candidates" in md and "(X)" in md.split("Prune candidates")[-1].split("\n")[0], False)
    check("no regressed row for X", any(l.startswith("| X |") and "regressed" in l for l in md.splitlines()), False)


def test_denominators_and_infra_count():
    _, _, md = _md()
    assert "- rung2: 2/2 passed, 1 infra" in md, md
    assert "- rung1: 2/3 passed" in md and "- rung1: 2/3 passed, " not in md, md
    assert "| rung2 | 2 | 0 | 1 |" in md, md
    print("  ok  pass-table denominators exclude infra, infra count shown")


def test_infra_warning_and_header():
    _, _, md = _md()
    warn = [l for l in md.splitlines() if l.startswith("⚠️ infra runs")]
    check("one infra warning line", len(warn), 1)
    assert "X (1)" in warn[0], warn[0]
    assert "scored run ids: 2 (20260101T000000Z to 20260103T000000Z)" in md
    print("  ok  infra line names X; header lists scored run ids + date range")


def test_cross_model_excludes_infra():
    rows = [
        {"task": "T", "rung": 1, "model": "claude-sonnet", "passed": False, "infra_error": True},
        {"task": "T", "rung": 1, "model": "claude-opus", "passed": True, "infra_error": False},
        {"task": "U", "rung": 1, "model": "claude-sonnet", "passed": True, "infra_error": False},
        {"task": "U", "rung": 1, "model": "claude-opus", "passed": True, "infra_error": False},
    ]
    for r in rows:
        r["rung"] = 1
    md = "\n".join(stats.cross_model_section(rows))
    check("infra task absent from cross-model table", "| T |" in md, False)
    check("valid task present", "| U |" in md, True)


def test_token_summary_excludes_infra():
    rows = [
        {"task": "a", "rung": "bare", "model": "m", "passed": False, "infra_error": True,
         "infra_reason": "api_error", "total_tokens": 0, "cost_usd": 0.0},
        {"task": "b", "rung": "bare", "model": "m", "passed": True, "infra_error": False,
         "total_tokens": 1000, "cost_usd": 0.5},
    ]
    ts = stats.token_summary(rows)["bare"]
    check("token avg excludes infra", ts["avg_tokens"], 1000)
    check("token n excludes infra", ts["n"], 1)
    check("avg cost excludes infra", ts["avg_cost"], 0.5)


def _flag(hi_wins, lo_wins):
    """action_flag for rung 1 vs 2 with hi_wins tasks only rung 2 passes, lo_wins only rung 1 passes."""
    rows = []
    for i in range(hi_wins):
        rows += [_s(f"h{i}", 1, False), _s(f"h{i}", 2, True)]
    for i in range(lo_wins):
        rows += [_s(f"l{i}", 1, True), _s(f"l{i}", 2, False)]
    (pr,) = stats.compute_stats(rows)["rung_pairs"]["m"].values()
    return pr["action_flag"]


def test_action_flag_needs_no_majority_for_higher_rung():
    check("3 hi wins / 0 lo -> no flag", _flag(3, 0), False)
    check("2 hi wins / 1 lo -> no flag", _flag(2, 1), False)
    check("1 hi win / 2 lo -> flag", _flag(1, 2), True)
    check("0 hi / 3 lo -> flag", _flag(0, 3), True)
    check("1 hi / 1 lo (<3 decisive) -> no flag", _flag(1, 1), False)


def test_layer_neutral_excluded_from_verdicts_kept_in_costs():
    rows = []
    for t in ("a", "b", "c"):  # three decisive tasks where the higher rung wins
        rows += [_s(t, 1, False), _s(t, 2, True)]
    ln = [{**_s("puz", r, True), "layer_neutral": True, "cost_usd": 1.0} for r in (1, 2)]
    check("sign test ignores layer_neutral rows",
          stats.compute_stats(rows + ln)["rung_pairs"], stats.compute_stats(rows)["rung_pairs"])
    verdict = "\n".join(stats.verdict_section({}, rows + ln))
    check("verdict has no layer_neutral task", "puz" in verdict, False)
    check("token/cost table keeps layer_neutral", stats.token_summary(rows + ln)["rung1"]["total_cost"], 1.0)
    check("frontier keeps layer_neutral", sum(c["n"] for c in stats.frontier_cells(rows + ln).values()), 8)


def test_layer_neutral_excluded_from_per_rung_pass_counts():
    data = _fixture()
    base_md = stats.render_markdown(data, stats.compute_stats(data["scores"]), stats.token_summary(data["scores"]))
    base_hist = stats.history_line(data)["rungs"]
    data["scores"].append({**_s("LN", 1, True), "layer_neutral": True, "cost_usd": 1.0})  # bare-only row
    md = stats.render_markdown(data, stats.compute_stats(data["scores"]), stats.token_summary(data["scores"]))
    check("Pass/Fail by Rung table unchanged by a layer_neutral row", md.split("## Pass/Fail by Rung")[1].split("##")[0],
          base_md.split("## Pass/Fail by Rung")[1].split("##")[0])
    check("history rung counts unchanged", stats.history_line(data)["rungs"], base_hist)
    check("per-run results still list it", "| LN | rung1 |" in md, True)


if __name__ == "__main__":
    test_layer_neutral_excluded_from_per_rung_pass_counts()
    test_layer_neutral_excluded_from_verdicts_kept_in_costs()
    test_token_summary_excludes_infra()
    test_sign_test_excludes_x()
    test_no_flip_prune_regressed_for_x()
    test_denominators_and_infra_count()
    test_infra_warning_and_header()
    test_cross_model_excludes_infra()
    test_action_flag_needs_no_majority_for_higher_rung()
    print("ALL PASS")
