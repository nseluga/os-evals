"""Tests for the judge join in score.py and the quarantined appendix in stats.py.

Covers: sidecar joined into rec["judge"]; *.judge.jsonl never scored as a run; judge_mean/judge_n on
majority records (and no new keys without judge data); the appendix renders without a deck, with a
stubbed deck, and when the deck raises; the appendix is the LAST section; headline output unchanged.

Run: python3 harness/test_score_judge.py
"""
import json
import stat
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # rewritten fake decks share size+mtime; a stale .pyc would mask them
sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402
import stats  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _make_run(tmp, with_sidecar=True):
    task_dir = tmp / "tasks" / "demo"
    task_dir.mkdir(parents=True)
    sh = task_dir / "check.sh"
    sh.write_text("#!/bin/sh\nexit 0\n")
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR)
    run = tmp / "runs" / "20260101T000000Z_demo_bare_m.json"
    run.parent.mkdir()
    run.write_text(json.dumps({"result": "done", "_meta": {
        "task": "demo", "rung": "bare", "model": "m", "workspace_dir": str(tmp)}}))
    if with_sidecar:
        run.with_name(run.stem + ".judge.jsonl").write_text(
            json.dumps({"score": 2, "rationale": "old", "rubric_sha": "a"}) + "\n"
            + "garbage\n"
            + json.dumps({"score": 4, "rationale": "new", "leak": ["dev-team"], "rubric_sha": "b"}) + "\n")
    return run, tmp / "tasks"


def test_sidecar_joined_latest_wins():
    with tempfile.TemporaryDirectory() as d:
        run, tasks = _make_run(Path(d))
        rec = score.score_run(run, tasks)
        check("judge joined", rec["judge"], {"score": 4, "rationale": "new", "leak": ["dev-team"], "rubric_sha": "b"})
        check("pass/fail untouched by judge", rec["passed"], True)


def test_no_sidecar_no_judge_key():
    with tempfile.TemporaryDirectory() as d:
        run, tasks = _make_run(Path(d), with_sidecar=False)
        check("no judge key without sidecar", "judge" in score.score_run(run, tasks), False)
        check("load_judge none", score.load_judge(run), None)


def test_judge_jsonl_never_scored():
    with tempfile.TemporaryDirectory() as d:
        run, _ = _make_run(Path(d))
        runs = run.parent
        (runs / "20260101T000000Z_demo_bare_m.judge.json").write_text("{}")
        (runs / "20260101T000000Z_demo_bare_m.trace.jsonl").write_text("{}")
        check("only the transcript is a run", [f.name for f in score.list_run_files(runs)], [run.name])
        # the sidecar must also be invisible to a plain *.json glob, the way main() once collected runs
        check("sidecar not matched by *.json", any(f.name.endswith(".judge.jsonl") for f in runs.glob("*.json")), False)


def _rec(i, passed, judge=None):
    r = {"file": f"20260101T000000Z_demo_bare_m_r{i}.json", "task": "demo", "rung": "bare", "model": "m",
         "passed": passed, "infra_error": False, "infra_reason": None, "check_rc": 0 if passed else 1,
         "is_repeat_individual": True, "repeat_index": i, "repeat_total": 3, "cost_usd": 0.1, "total_tokens": 10}
    if judge is not None:
        r["judge"] = {"score": judge}
    return r


def test_majority_judge_mean():
    (m,) = score.compute_majority_records([_rec(1, True, 4), _rec(2, True, 2), _rec(3, False)])
    check("judge_mean over judged members", m["judge_mean"], 3.0)
    check("judge_n", m["judge_n"], 2)
    check("no per-run judge on majority", "judge" in m, False)
    (m,) = score.compute_majority_records([_rec(i, True) for i in (1, 2, 3)])
    check("no judge data -> no judge keys", ("judge_mean" in m, "judge_n" in m), (False, False))


def _scored(task, rung, judge, passed=True, maj=False):
    r = {"task": task, "rung": rung, "model": "m", "passed": passed, "infra_error": False,
         "curated_skill": "sk", "total_tokens": 1, "cost_usd": 0.0, "file": f"x_{task}_{rung}.json"}
    if judge is not None:
        r.update({"judge_mean": judge} if maj else {"judge": {"score": judge, "leak": []}})
        if maj:
            r["repeat_majority"] = True
    return r


def _data(judged=True):
    rows = []
    for t, lo, hi in (("A", 1, 4), ("B", 2, 2), ("C", 1, 3)):
        rows.append(_scored(t, "bare", lo if judged else None))
        rows.append(_scored(t, "full", hi if judged else None))
    return {"os_sha": "abc", "scores": rows, "layer_order": ["bare", "full"]}


def test_appendix_without_deck():
    with tempfile.TemporaryDirectory() as d:
        out = "\n".join(stats.judge_appendix(_data(), root=d))
        check("header", "## Appendix: LLM judge (quarantined)" in out, True)
        check("promotion rule", "Promotion rule" in out, True)
        check("no-deck kappa line", "judge-vs-Nate: κ=n/a UNCALIBRATED (no deck)" in out, True)
        check("rung means rendered", "| Mean judge score |" in out.replace("Mean judge score", "| Mean judge score") or "Mean judge score" in out, True)
        check("sign test line", "judge sign-test" in out, True)
        check("separated ties counted (A, C at |gap|>=1)", "check.sh ties the judge separates (|gap| >= 1.0): 2" in out, True)
        check("leak count line", "judge leak count" in out and ": 0" in out, True)


def test_appendix_no_judged_runs():
    with tempfile.TemporaryDirectory() as d:
        out = "\n".join(stats.judge_appendix(_data(judged=False), root=d))
        check("empty note", "no judged runs" in out, True)
        check("kappa line still present", "judge-vs-Nate: κ=n/a UNCALIBRATED (no deck)" in out, True)


def _fake_deck(root, body):
    (Path(root) / "harness").mkdir(parents=True, exist_ok=True)
    (Path(root) / "harness" / "deck.py").write_text(body)


def test_appendix_with_fake_deck():
    with tempfile.TemporaryDirectory() as d:
        _fake_deck(d, "def kappa(picks, judge):\n    return {'kappa': 0.71, 'n': 52}\n")
        out = "\n".join(stats.judge_appendix(_data(), root=d))
        check("calibrated", "judge-vs-Nate: κ=0.71 CALIBRATED" in out, True)
        _fake_deck(d, "def kappa(picks, judge):\n    return {'kappa': 0.71, 'n': 12}\n")
        check("too few pairs -> uncalibrated", "κ=0.71 UNCALIBRATED" in "\n".join(stats.judge_appendix(_data(), root=d)), True)
        _fake_deck(d, "def kappa(picks, judge):\n    return 0.3\n")
        check("bare number, low -> uncalibrated", "κ=0.30 UNCALIBRATED" in "\n".join(stats.judge_appendix(_data(), root=d)), True)
        _fake_deck(d, "def kappa(picks, judge):\n    return None\n")
        check("None -> n/a", "κ=n/a UNCALIBRATED (no rated pairs)" in "\n".join(stats.judge_appendix(_data(), root=d)), True)
        # the deck receives the judge scores keyed by transcript stem
        _fake_deck(d, "def kappa(picks, judge):\n    return {'kappa': float(len(judge)), 'n': 99}\n")
        check("deck receives judge map", "κ=6.00 CALIBRATED" in "\n".join(stats.judge_appendix(_data(), root=d)), True)


def test_appendix_deck_failure_still_renders():
    with tempfile.TemporaryDirectory() as d:
        _fake_deck(d, "def kappa(picks, judge):\n    raise RuntimeError('boom')\n")
        out = "\n".join(stats.judge_appendix(_data(), root=d))
        check("deck error fallback", "κ=n/a UNCALIBRATED (deck error: boom)" in out, True)
        _fake_deck(d, "this is not python (\n")
        out = "\n".join(stats.judge_appendix(_data(), root=d))
        check("deck import error fallback", "(deck error:" in out, True)
        check("rest of appendix intact", "judge sign-test" in out, True)


def test_appendix_is_last_and_leaves_headline_alone():
    data = _data()
    st = stats.compute_stats(data["scores"])
    md = stats.render_markdown(data, st, stats.token_summary(data["scores"]))
    idx = md.index("## Appendix: LLM judge (quarantined)")
    check("appendix has no later section", "\n## " in md[idx + 5:], False)
    stripped = [dict(s) for s in data["scores"]]
    for s in stripped:
        s.pop("judge", None)
    base = {**data, "scores": stripped}
    md0 = stats.render_markdown(base, stats.compute_stats(stripped), stats.token_summary(stripped))
    check("everything before the appendix identical with/without judge data",
          md[:idx].rstrip() == md0[:md0.index("## Appendix: LLM judge (quarantined)")].rstrip(), True)


def test_majority_cells_use_judge_mean():
    rows = [_scored("A", "bare", 1.5, maj=True), _scored("A", "full", 3.5, maj=True)]
    cells = stats._judge_cells(rows)
    check("majority cell uses judge_mean", sorted(v for v, _ in cells.values()), [1.5, 3.5])


if __name__ == "__main__":
    test_sidecar_joined_latest_wins()
    test_no_sidecar_no_judge_key()
    test_judge_jsonl_never_scored()
    test_majority_judge_mean()
    test_appendix_without_deck()
    test_appendix_no_judged_runs()
    test_appendix_with_fake_deck()
    test_appendix_deck_failure_still_renders()
    test_appendix_is_last_and_leaves_headline_alone()
    test_majority_cells_use_judge_mean()
    print("ALL PASS")
