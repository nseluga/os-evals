"""Tests for the item 4.1 round-1 fixes (arm skip rule, wall estimate, routing, Skill lift, prompt_head, arm pairs).

Run: python3 harness/test_arm_fixes.py
"""
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402
import stats  # noqa: E402

RM = Path(rm.__file__)


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _task(root, name, meta):
    (root / "tasks" / name).mkdir(parents=True)
    (root / "tasks" / name / "prompt.md").write_text("hi")
    (root / "tasks" / name / "meta.yaml").write_text(meta)


def _cli(root, tasks, layers, *extra):
    return subprocess.run(
        [sys.executable, str(RM), "--dry-run", "--tasks", tasks, "--layers", layers, "--tasks-dir", str(root / "tasks"),
         "--config-dir", str(root / "configs"), "--runs-dir", str(root / "runs"), "--ws-root", str(root / "ws"),
         "--scorecards-dir", str(root / "sc"), *extra], capture_output=True, text=True)


def _root(d):
    root = Path(d)
    for layer in ("skills", "full"):
        (root / "configs" / layer).mkdir(parents=True)
    (root / "configs" / "src" / "skills" / "quote").mkdir(parents=True)  # the snapshot holds `quote` only
    _task(root, "has", 'curated_skill: quote\ntrigger: "quote this:"\n')
    _task(root, "gone", 'curated_skill: baseball-research-advisor\ntrigger: "advise:"\n')
    _task(root, "plain", "curated_skill: none (no skill here)\n")
    return root


# --- 1. skip, never abort ---

def test_missing_skill_skips_both_plain_arms():
    with tempfile.TemporaryDirectory() as d:
        sk = Path(d) / "skills"
        (sk / "quote").mkdir(parents=True)
        va = rm.variant_applies
        check("skill dir present: trigger + forced run", (va("skills~trigger", "quote", "x", sk), va("skills~forced", "quote", "x", sk)), (True, True))
        check("skill dir missing: both plain arms skip", (va("skills~trigger", "baseball-research-advisor", "x", sk),
                                                          va("skills~forced", "baseball-research-advisor", "x", sk)), (False, False))
        check("full~forced skips the same way", va("full~forced", "dt-fix", "", sk), False)
        check("explicit forced.<skill> is vetted by variant_error, not per task", va("skills~forced.dt-fix", "none", "", sk), True)
        check("another sha's snapshot lacking the skill: only that cell skips", (va("skills~forced", "quote", "", sk), va("skills~forced", "quote", "", Path(d) / "other")), (True, False))
        check("notice phrases", (rm.arm_skip_need("skills~forced", "dt-fix", "", sk), rm.arm_skip_need("skills~forced", "none (x)", "", sk),
                                 rm.arm_skip_need("skills~trigger", "quote", "", sk)),
              (f"skill 'dt-fix' in {sk}", "a curated_skill", "a `trigger` in meta.yaml and a curated_skill"))


def test_cli_skip_not_abort():
    with tempfile.TemporaryDirectory() as d:
        root = _root(d)
        r = _cli(root, "gone", "skills,skills~trigger,skills~forced")
        check("missing skill dir: rc 0", r.returncode, 0)
        assert "skills~trigger: gone — skipped (needs skill 'baseball-research-advisor' in" in r.stdout, r.stdout
        assert "skills~forced: gone — skipped (needs skill 'baseball-research-advisor' in" in r.stdout, r.stdout
        assert "gone: 1 cells" in r.stdout, r.stdout
        r = _cli(root, "plain", "skills,skills~forced")
        check("all-skipped plain forced run: rc 0 with 0 cells for that layer", (r.returncode, "plain: 1 cells" in r.stdout, "total runs: 1" in r.stdout), (0, True, True))
        assert "skills~forced: plain — skipped (needs a curated_skill)" in r.stdout, r.stdout
        r = _cli(root, "plain,gone", "skills,skills~trigger,skills~forced")
        check("curated none and missing skill together: still rc 0, base cells only", (r.returncode, "total runs: 2" in r.stdout), (0, True))
        r = _cli(root, "has,gone,plain", "skills,skills~forced")
        check("mixed set: only the task whose skill exists keeps the forced cell", ("has: 2 cells" in r.stdout, "gone: 1 cells" in r.stdout, "plain: 1 cells" in r.stdout), (True, True, True))
        r = _cli(root, "has", "skills,skills~forced.nosuchskill")
        check("explicit forced.nosuchskill: rc 2", r.returncode, 2)
        assert "no skill 'nosuchskill'" in r.stderr, r.stderr
        r = _cli(root, "gone", "skills,skills~forced.quote")
        check("explicit forced.<present skill> applies to a task whose own skill is absent", (r.returncode, "gone: 2 cells" in r.stdout), (0, True))


# --- 2. wall estimate ---

def _w(task, secs, **kw):
    return {"task": task, "rung": "bare", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": secs, **kw}


def test_multi_turn_gets_per_run_ratio():
    check("measured jobs literal", rm.STALL_MEASURED_JOBS, 4)
    check("factor literal", rm.STALL_FACTOR, 16.0)
    hist = [_w("orch", 1800)]
    cell = {"task": "orch", "layer": "skills", "model": "sonnet", "effort": "high", "multi_turn": True}
    secs, lacking = rm.wall_estimate(hist, [cell], jobs=4)
    check("one 1800 s multi_turn cell = 2 h, not 8 h", (secs, lacking, rm.wall_line(secs, 16.0, lacking)), (7200.0, 0, "est wall: 2h 0m (factor 16, 0 cells lack history)"))
    secs, _ = rm.wall_estimate(hist, [cell], jobs=1)
    check("multi_turn ignores --jobs (serial)", secs, 7200.0)
    secs, _ = rm.wall_estimate(hist, [cell], jobs=4, factor=8.0)
    check("--stall-factor scales multi_turn too", secs, 3600.0)
    one = {**cell, "task": "q", "multi_turn": False}
    secs, _ = rm.wall_estimate([_w("q", 100)], [one], jobs=4)
    check("one-shot keeps (sum / jobs) x factor", secs, 100 / 4 * 16.0)
    secs, _ = rm.wall_estimate(hist + [_w("q", 100)], [cell, one], jobs=4, factor=2.0)
    check("mixed: (one / jobs + multi / 4) x factor", secs, (100 / 4 + 1800 / 4) * 2.0)


# --- 5. history hygiene ---

def test_history_dedupe_and_rejected_runs():
    dup = [_w("t", 100, file="A.json"), _w("t", 100, file="A.json"), _w("t", 300, file="B.json")]  # MERGED-* / -rescored copy of A
    it = {"task": "t", "layer": "bare", "model": "sonnet", "effort": "high", "multi_turn": False}
    secs, _ = rm.wall_estimate(dup, [it], jobs=1, factor=1.0)
    check("a record repeated under the same `file` counts once", secs, 200.0)
    secs, _ = rm.wall_estimate([_w("t", 100), _w("t", 100), _w("t", 300)], [it], jobs=1, factor=1.0)
    check("records without a `file` are never merged", secs, (100 + 100 + 300) / 3)
    # the July 429s: is_error, cost 0, 0.7-5 s, scored infra_error False (before rate_limited existed)
    rej = {"is_error": True, "cost_usd": 0, "infra_error": False}
    hist = [_w("t", 0.9, file="r1.json", **rej), _w("t", 0.8, file="r2.json", **rej), _w("t", 172.8, file="r3.json", **rej), _w("t", 120, file="ok.json", is_error=False, cost_usd=0.2)]
    secs, lacking = rm.wall_estimate(hist, [it], jobs=1, factor=1.0)
    check("is_error + zero cost (API refused the request) is excluded", (secs, lacking), (120.0, 0))
    hist = [_w("t", 90, file="b.json", is_error=True, cost_usd=0.11, subtype="error_max_budget_usd"), _w("t", 110, file="c.json")]
    secs, _ = rm.wall_estimate(hist, [it], jobs=1, factor=1.0)
    check("a budget stop (is_error but it cost money) keeps its real wall", secs, 100.0)
    only_rej = [_w("t", 0.85, file="x.json", **rej)]
    check("a cell whose only history is rejected runs reads as lacking", rm.wall_estimate(only_rej, [it], jobs=1, factor=1.0), (0.0, 1))


def test_real_july_records_are_the_rejected_ones():
    sc = Path(__file__).resolve().parent.parent / "scorecards" / "20260715T151129Z-483c1d0.scores.json"
    if not sc.exists():  # untracked history: present on Nate's machine, absent in a fresh clone
        print("  skip real-record check (scorecard absent)")
        return
    recs = [r for r in json.loads(sc.read_text())["scores"] if r["task"] == "coding/pathguard-resolver" and "opus" in r["model"] and not r.get("repeat_majority")]
    sub = [r for r in recs if r["wall_clock_sec"] < 5]
    check("pathguard opus sub-second records are is_error + zero cost + not flagged infra",
          [(r["is_error"], r["cost_usd"], r["infra_error"]) for r in sub], [(True, 0, False)] * len(sub))
    it = {"task": "coding/pathguard-resolver", "layer": "1", "model": "opus", "effort": "high", "multi_turn": True}
    secs, lacking = rm.wall_estimate(recs, [it], jobs=1, factor=1.0)
    check("none of them reaches the estimate", (lacking, secs < 5), (1, True))


# --- 6. lacking counts cells ---

def test_lacking_counts_distinct_cells():
    cell = lambda t, layer="skills", eff="high", i=1: {"task": t, "layer": layer, "model": "sonnet", "effort": eff, "multi_turn": False, "i": i}  # noqa: E731
    repeats = [cell("z", i=i) for i in (1, 2, 3)]
    check("one repeat-3 cell with no history is 1 lacking, not 3", rm.wall_estimate([], repeats, 1)[1], 1)
    check("different layer / effort / task are distinct cells", rm.wall_estimate([], repeats + [cell("z", "full"), cell("z", eff="low"), cell("y")], 1)[1], 4)


# --- 3. routing ---

def _tu(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def test_routing_matches_the_skill_name_exactly():
    fired = rm.detect_skill_fired
    check("dev-team-auto is not dev-team", fired([_tu("Skill", {"skill": "dev-team-auto"})], "dev-team"), False)
    check("dev-team is not dev-team-auto", fired([_tu("Skill", {"skill": "dev-team"})], "dev-team-auto"), False)
    check("exact name", fired([_tu("Skill", {"skill": "dev-team"})], "dev-team"), True)
    check("case-insensitive exact name", fired([_tu("Skill", {"skill": "Dev-Team"})], "dev-team"), True)
    check("<plugin>: prefix allowed", fired([_tu("Skill", {"skill": "ponytail:ponytail"})], "ponytail"), True)
    check("prefix allowed on a hyphenated skill", fired([_tu("Skill", {"skill": "myplug:dev-team"})], "dev-team"), True)
    check("a prefix is not a substring match", fired([_tu("Skill", {"skill": "myplug:dev-team-auto"})], "dev-team"), False)
    check("the plugin segment alone never matches", fired([_tu("Skill", {"skill": "dev-team:other"})], "dev-team"), False)
    check("input.command is read the same way, leading slash tolerated", fired([_tu("Skill", {"command": "/humanizer"})], "humanizer"), True)
    check("later exact call still fires after an inexact one", fired([_tu("Skill", {"skill": "dev-team-auto"}), _tu("Skill", {"skill": "dev-team"})], "dev-team"), True)
    for name in ("Agent", "Task"):  # spawn detection is unchanged: the description still names the skill
        check(f"{name} spawn semantics untouched", fired([_tu(name, {"subagent_type": "dt-engineer", "description": "dev-team build"})], "dev-team"), True)


# --- 4. Skill lift keeps @sha ---

def _lift(task, rung, passed, cost, **kw):
    return {"task": task, "rung": rung, "passed": passed, "model": "sonnet:high", "cost_usd": cost, "curated_skill": "humanizer",
            "multi_turn": False, "skill_fired": None, "infra_error": False, **kw}


def _rows(lines):
    return {(c[0], c[1]): c[2:] for c in ([x.strip() for x in ln.split("|")[1:-1]] for ln in lines if ln.startswith("| ") and "---" not in ln and not ln.startswith("| Skill |"))}


def test_skill_lift_ab_shas_do_not_cross_pair():
    scores = [_lift("a", "skills@A", False, 0.10), _lift("a", "skills~forced@A", True, 0.30),
              _lift("a", "skills@B", True, 0.50), _lift("a", "skills~forced@B", True, 0.50)]
    rows = _rows(stats.skill_lift_section(scores))
    check("one row per sha, each paired with its own base",
          rows, {("humanizer@A", "sonnet:high"): ["1", "+100pp", "n/a", "$+0.2000", "n/a"],
                 ("humanizer@B", "sonnet:high"): ["1", "+0pp", "n/a", "$+0.0000", "n/a"]})
    lone = [_lift("a", "skills@A", False, 0.10), _lift("a", "skills~forced@B", True, 0.30)]
    check("forced@B with only skills@A: no cross-sha pair", _rows(stats.skill_lift_section(lone)), {})
    plain = [_lift("a", "skills", False, 0.10), _lift("a", "skills~forced", True, 0.30)]
    check("single-sha rung labels stay unsuffixed", list(_rows(stats.skill_lift_section(plain))), [("humanizer", "sonnet:high")])


# --- 7. prompt_head ---

def _run(layer, prompt, meta_yaml):
    out = '{"type":"result","is_error":false,"result":"ok"}\n'
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text(prompt)
        (d / "tasks" / "t" / "meta.yaml").write_text(meta_yaml)
        (d / "configs" / "skills").mkdir(parents=True)
        seen = {}
        orig = subprocess.run

        def fake(cmd, **kw):
            seen["input"] = kw.get("input")
            return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        subprocess.run = fake
        try:
            f = rm.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
        finally:
            subprocess.run = orig
        return json.loads(f.read_text())["_meta"], seen["input"]


def test_prompt_head_records_the_real_stdin():
    meta, sent = _run("skills~forced", "BODY", "curated_skill: humanizer\n")
    check("forced run: head shows the /skill prefix", meta["prompt_head"], "/humanizer BODY")
    meta, sent = _run("skills~forced.dev-team", "BODY", "curated_skill: humanizer\nforced_note: \"NOTE\"\n")
    check("explicit forced skill + note: head is the stdin", (meta["prompt_head"], meta["prompt_head"] == sent), ("/dev-team BODY\n\nNOTE", True))
    meta, _ = _run("skills~trigger", "BODY", 'curated_skill: humanizer\ntrigger: "do it:"\n')
    check("trigger run: head starts with the trigger", meta["prompt_head"], "do it:\n\nBODY")
    meta, _ = _run("skills", "BODY", "curated_skill: humanizer\n")
    check("plain layer: every run records it", meta["prompt_head"], "BODY")
    long = "x" * 300
    meta, sent = _run("skills~forced", long, "curated_skill: humanizer\n")
    check("first 120 chars of the stdin", (len(meta["prompt_head"]), meta["prompt_head"] == sent[:120], meta["prompt_head"].startswith("/humanizer x")), (120, True, True))


# --- 8. arms are not knockout pairs ---

def test_arm_rungs_are_not_knockout_pairs():
    check("ko variant still pairs with its base", stats.select_pairs({"skills", "skills~ko.quote"}), [("skills~ko.quote", "skills")])
    check("arms drop out, ladder pair stays", stats.select_pairs({"bare", "skills", "skills~forced", "skills~trigger", "skills~forced.dt-qa"},
                                                                 ["bare", "skills", "skills~forced", "skills~trigger"]), [("bare", "skills")])
    check("only arms and their base: no pair at all", stats.select_pairs({"skills", "skills~forced"}), [])
    check("A/B shas with arms: the sha pair only", stats.select_pairs({"skills@A", "skills@B", "skills~forced@A"}, None), [("skills@A", "skills@B")])
    scores = [_lift("a", "bare", False, 0.1), _lift("a", "skills", False, 0.1), _lift("a", "skills~forced", True, 0.3)]
    res = stats.compute_stats(scores, ["bare", "skills", "skills~forced"])
    check("no pair reads the forced win as the base losing", sorted(res["rung_pairs"]["sonnet:high"]), ["bare_vs_skills"])
    md = stats.render_markdown({"scores": scores, "os_sha": "x"}, res, stats.token_summary(scores))
    check("an arm flip does not suppress NO DISCRIMINATING SIGNAL", "NO DISCRIMINATING SIGNAL" in md, True)
    check("...and Skill lift still reports it", "## Skill lift" in md, True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print("ALL PASS")
