"""Tests for deck.py: strata, exclusions, determinism, side balance, blind HTML, kappa, win rates, server.

Run: python3 harness/test_deck.py
"""
import contextlib
import io
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck  # noqa: E402

RUNGS = ["bare", "claude-md", "memory", "skills", "full"]


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


class Fixture:
    """tmp repo: tasks/alpha/tNN (prompt + rubric), runs/*.json with workspaces, a scores file."""

    def __init__(self, tmp, ntasks=24, mem_passes=True):
        self.root = Path(tmp)
        self.tasks, self.runs, self.human = self.root / "tasks", self.root / "runs", self.root / "human"
        self.scores, self.stems = [], {}
        self.runs.mkdir(parents=True)
        for i in range(ntasks):
            task = f"alpha/t{i:02d}"
            d = self.tasks / task
            d.mkdir(parents=True)
            (d / "prompt.md").write_text(f"Summarize widget report {i}.")
            (d / "rubric.md").write_text("1 point per fact.")
            for rung in RUNGS:
                for k in (1, 2):
                    passed = not (rung == "bare" and i % 2) and not (rung == "memory" and not mem_passes)
                    self.add(task, rung, k, passed, f"Widget answer {i} version {rung[:1]}{k}.")

    def add(self, task, rung, k, passed, result="neutral text", ws=True, **flags):
        stem = f"20261002T112834Z_{task.replace('/', '-')}_{rung}_sonnet_r{k}"
        wsd = self.root / "evalws" / stem
        if ws:
            wsd.mkdir(parents=True)
        (self.runs / f"{stem}.json").write_text(json.dumps({
            "result": result, "_meta": {"task": task, "workspace_dir": str(wsd)}}))
        rec = {"file": stem + ".json", "task": task, "rung": rung, "model": "sonnet", "passed": passed,
               "infra_error": False, "is_error": False, "timed_out": False, "budget_exceeded": False,
               "contaminated": False, "is_repeat_individual": True, "repeat_index": k, **flags}
        self.scores.append(rec)
        self.stems[(task, rung, k)] = stem
        return stem

    def scores_file(self):
        p = self.root / "scores.json"
        p.write_text(json.dumps({"scores": self.scores}))
        return p

    def build(self, seed=1, n=20, ts="T1", human=None):
        return deck.build(self.scores_file(), seed, n, self.runs, self.tasks, human or self.human, ts)

    def pick(self, pid, pick, rnd="T1"):
        with open(self.human / "picks.jsonl", "a") as f:
            f.write(json.dumps({"round": rnd, "pair": pid, "pick": pick, "note": "", "ts": "x"}) + "\n")


def counts(key):
    out = {}
    for e in key.values():
        out[e["stratum"]] = out.get(e["stratum"], 0) + 1
    return out


def test_candidates_no_rebind():
    """3 repeats/rung: every cross-rung pair appears exactly once (a, b = b, a used to rebind the loop run)."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=1)
        for rung in RUNGS:
            fx.add("alpha/t00", rung, 3, True, f"Widget answer 0 version {rung[:1]}3.")
        strata = deck.candidates(deck.load_runs(fx.scores, fx.runs, fx.tasks))
        check("stratum sizes", [len(x) for x in strata], [9, 9, 18, 0, 15])  # 3x3, 3x3, 2 x 3x3, -, 5 x C(3,2)
        for i, lst in enumerate(strata):
            ids = [deck.pair_identity(a, b) for a, b in lst]
            check(f"stratum {i} no duplicate pairs", len(ids), len(set(ids)))
        for a, b in strata[1]:
            assert (a["rung"], b["rung"]) == ("skills", "full"), (a["stem"], b["stem"])
        check("skills-vs-full unique stems", len({s for a, b in strata[1] for s in (a["stem"], b["stem"])}), 6)


def test_quotas_literal():
    check("quota table", [q for _, q in deck.STRATA], [6, 6, 4, 2, 2])
    check("names", [n for n, _ in deck.STRATA],
          ["memory-vs-skills", "skills-vs-full", "adjacent-tie", "check-disagree", "null"])
    check("quotas(20)", deck.quotas(20), [6, 6, 4, 2, 2])
    check("quotas(10) sums", sum(deck.quotas(10)), 10)
    check("quotas(7) sums", sum(deck.quotas(7)), 7)


def test_strata_quotas():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp)
        for seed in range(6):
            _, dk, key = fx.build(seed=seed, ts=f"S{seed}")
            check(f"seed {seed} quotas", counts(key), {"memory-vs-skills": 6, "skills-vs-full": 6,
                                                       "adjacent-tie": 4, "check-disagree": 2, "null": 2})
            per_task = {}
            for e in key.values():
                per_task[e["task"]] = per_task.get(e["task"], 0) + 1
            assert max(per_task.values()) <= 2, per_task
            stems = [s for e in key.values() for s in e["stems"].values()]
            check(f"seed {seed} stems unique", len(stems), len(set(stems)))
            for e in key.values():  # strata semantics
                la, lb = sorted(e["layers"].values(), key=RUNGS.index)
                want = {"memory-vs-skills": ("memory", "skills"), "skills-vs-full": ("skills", "full")}
                if e["stratum"] in want:
                    assert (la, lb) == want[e["stratum"]], e
                if e["stratum"] == "null":
                    assert la == lb, e
                    assert e["stems"]["A"] != e["stems"]["B"], e  # repeats exist -> not flipped


def test_strata_default_unchanged():
    check("default STRATA", deck.STRATA, [("memory-vs-skills", 6), ("skills-vs-full", 6), ("adjacent-tie", 4),
                                          ("check-disagree", 2), ("null", 2)])
    check("quotas(20, None)", deck.quotas(20, None), [6, 6, 4, 2, 2])
    check("quotas(20, STRATA)", deck.quotas(20, deck.STRATA), [6, 6, 4, 2, 2])
    check("rung order known", sorted(RUNGS[::-1], key=deck._rung_key), RUNGS)
    check("variant after base", sorted(["full", "skills~forced", "skills", "memory~nohook", "memory"],
                                       key=deck._rung_key),
          ["memory", "memory~nohook", "skills", "skills~forced", "full"])


def test_strata_parse():
    check("preset", deck.parse_strata(deck.PRESETS["skill-lift"]),
          [("skills-vs-skills~forced", 10), ("skills-vs-skills~trigger", 4), ("bare-vs-skills~forced", 4), ("null", 2)])
    check("dash layer + variants", deck.parse_strata("claude-md-vs-memory=3, skills~forced.fable-orchestrate-vs-memory~nohook=2,null=1"),
          [("claude-md-vs-memory", 3), ("skills~forced.fable-orchestrate-vs-memory~nohook", 2), ("null", 1)])
    for bad in ("", "skills", "a-vs-b", "a-vs-b=x", "a-vs-b=0", "a-vs-a=2", "a-vs-b-vs-c=2", "-vs-b=1", "a-vs-b=1,b-vs-a=1", "null=1,null=2"):
        try:
            deck.parse_strata(bad)
        except ValueError:
            print(f"  ok  rejects {bad!r}")
        else:
            raise AssertionError(f"accepted {bad!r}")
    try:
        deck.main(["build", "--scores-file", "x", "--strata", "nonsense"])
    except SystemExit as e:
        check("bad --strata exits 2", e.code, 2)
    else:
        raise AssertionError("bad --strata accepted")


def test_preset_quotas():
    st = deck.parse_strata(deck.PRESETS["skill-lift"])
    check("preset quotas(20)", deck.quotas(20, st), [10, 4, 4, 2])
    for n in (20, 10, 7, 1, 33):
        check(f"preset quotas({n}) sum", sum(deck.quotas(n, st)), n)


def test_preset_mutual_exclusion():
    try:
        deck.main(["build", "--preset", "skill-lift", "--strata", "a-vs-b=1", "--scores-file", "x"])
    except SystemExit as e:
        check("preset+strata exit code", e.code, 2)
    else:
        raise AssertionError("no error")


def test_preset_build_and_report():
    layers = ["skills", "skills~forced", "skills~trigger", "bare"]
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=0)
        for i in range(12):
            task = f"alpha/t{i:02d}"
            d = fx.tasks / task
            d.mkdir(parents=True)
            (d / "prompt.md").write_text(f"Summarize widget report {i}.")
            (d / "rubric.md").write_text("1 point per fact.")
            for rung in layers:
                for k in (1, 2):
                    fx.add(task, rung, k, i % 3 != 0, f"Widget answer {i} {rung} {k}.")
        # a default-rung-only run set has no custom pairs; the preset must still pick these variant layers
        st = deck.parse_strata(deck.PRESETS["skill-lift"])
        _, dk, key = deck.build(fx.scores_file(), 1, 20, fx.runs, fx.tasks, fx.human, "P1", strata=st)
        check("n=20 filled", len(dk), 20)
        want = {"skills-vs-skills~forced": ("skills", "skills~forced"),
                "skills-vs-skills~trigger": ("skills", "skills~trigger"),
                "bare-vs-skills~forced": ("bare", "skills~forced")}
        c = counts(key)
        assert set(c) <= {n for n, _ in st}, c
        for e in key.values():
            if e["stratum"] in want:
                check("layers", tuple(sorted(e["layers"].values(), key=deck._rung_key)),
                      tuple(sorted(want[e["stratum"]], key=deck._rung_key)))
            else:
                assert e["stratum"] == "null" and e["layers"]["A"] == e["layers"]["B"], e
        assert c.get("skills-vs-skills~forced", 0) >= 10 and c.get("null", 0) >= 1, c
        for pid in key:
            fx.pick(pid, "A", "P1")
        rep = deck.report("P1", fx.human, fx.runs)
        check("report counted all", rep["n_picks"], 20)
        assert "skills>skills~forced" in rep["win_rates"] and "bare>skills~forced" in rep["win_rates"], rep["win_rates"]
        # default build on the same scores ignores variant layers entirely (default path unchanged)
        _, dk2, key2 = fx.build(n=5, ts="P2", human=fx.human / "d")
        assert all(set(e["layers"].values()) <= {"skills", "bare"} for e in key2.values()), key2
        # zero pairs: clean SystemExit naming the strata
        try:
            deck.build(fx.scores_file(), 1, 4, fx.runs, fx.tasks, fx.human / "z", "Z",
                       strata=[("memory-vs-full", 4)])
        except SystemExit as e:
            check("zero pairs msg", str(e), "no eligible pairs: nothing written (strata: memory-vs-full=4)")
        else:
            raise AssertionError("no SystemExit")


def test_preset_one_repeat():
    """--repeat 1 data (one run per layer per cell): a run anchors one pair per stratum, null falls back to flipped."""
    def fixture(tmp, layers, ntasks=10):
        fx = Fixture(tmp, ntasks=0)
        for i in range(ntasks):
            task = f"alpha/t{i:02d}"
            (fx.tasks / task).mkdir(parents=True)
            (fx.tasks / task / "prompt.md").write_text(f"Summarize widget report {i}.")
            (fx.tasks / task / "rubric.md").write_text("1 point per fact.")
            for rung in layers:
                fx.add(task, rung, 1, True, f"Widget answer {i} {rung}.")
        return fx

    st = deck.parse_strata(deck.PRESETS["skill-lift"])
    want = {"skills-vs-skills~forced": 10, "skills-vs-skills~trigger": 4, "bare-vs-skills~forced": 4, "null": 2}
    with tempfile.TemporaryDirectory() as tmp:
        fx = fixture(tmp, ["skills", "skills~forced", "skills~trigger", "bare"])
        for seed in range(5):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                _, dk, key = deck.build(fx.scores_file(), seed, 20, fx.runs, fx.tasks, fx.human, f"O{seed}", strata=st)
            check(f"seed {seed} deck size", len(dk), 20)
            check(f"seed {seed} quotas met", counts(key), want)
            check(f"seed {seed} no short-stratum warning", err.getvalue(), "")
            nulls = [e for e in key.values() if e["stratum"] == "null"]
            check(f"seed {seed} null pairs are flipped (stems A == B)",
                  [e["stems"]["A"] == e["stems"]["B"] for e in nulls], [True, True])
    # no trigger / bare arms at all: the deck tops up with nulls and the stderr warning names both short strata
    with tempfile.TemporaryDirectory() as tmp:
        fx = fixture(tmp, ["skills", "skills~forced"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _, dk, key = deck.build(fx.scores_file(), 1, 20, fx.runs, fx.tasks, fx.human, "O", strata=st)
        check("short deck still 20", len(dk), 20)
        check("short deck counts", counts(key), {"skills-vs-skills~forced": 10, "null": 10})
        check("short-stratum warnings", err.getvalue().splitlines(),
              ["warning: stratum skills-vs-skills~trigger: 0/4", "warning: stratum bare-vs-skills~forced: 0/4"])
    # default strata never warn, even when a stratum is empty
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, mem_passes=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fx.build()
        check("default path prints no warning", err.getvalue(), "")


def test_fill_forward():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, mem_passes=False)  # memory never passes: stratum 0 empty, 1 has candidates
        _, dk, key = fx.build()
        c = counts(key)
        check("total still 20", len(dk), 20)
        check("memory-vs-skills empty", c.get("memory-vs-skills", 0), 0)
        assert c["skills-vs-full"] >= 12, c  # its 6 + the 6 carried over
        # exhausted pool: tiny fixture yields fewer than n and does not crash
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=2)
        _, dk, _ = fx.build()
        assert 0 < len(dk) < 20, len(dk)
        assert len(dk) <= 4  # 2 tasks x MAX_PER_TASK
        print(f"  ok  short pool -> {len(dk)} pairs")


def test_build_zero_pairs():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=0)
        try:
            fx.build()
            raise AssertionError("empty build returned")
        except SystemExit as e:
            assert e.code, e.code
        check("no round dir written", (fx.human / "rounds").exists(), False)
        r = subprocess.run([sys.executable, str(Path(deck.__file__)), "build", "--scores-file", str(fx.scores_file()),
                            "--runs-dir", str(fx.runs), "--tasks-dir", str(fx.tasks), "--human-dir", str(fx.human)],
                           capture_output=True, text=True)
        check("CLI exits non-zero", r.returncode != 0, True)
        assert "no eligible pairs" in r.stderr, r.stderr
        check("still no human dir", fx.human.exists(), False)


def test_exclusions():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=24)
        bad = []
        # extra task whose every run is bad in some way; each must never show up
        t = "alpha/t90"
        for d in ("alpha/t90",):
            (fx.tasks / d).mkdir(parents=True)
            (fx.tasks / d / "prompt.md").write_text("p")
            (fx.tasks / d / "rubric.md").write_text("r")
        bad.append(fx.add(t, "memory", 1, True, infra_error=True))
        bad.append(fx.add(t, "skills", 1, True, contaminated=True))
        bad.append(fx.add(t, "skills", 2, True, is_error=True))
        bad.append(fx.add(t, "full", 1, True, timed_out=True))
        bad.append(fx.add(t, "full", 2, True, budget_exceeded=True))
        bad.append(fx.add(t, "bare", 1, True, runaway=True))
        bad.append(fx.add(t, "claude-md", 1, True, result="   "))
        bad.append(fx.add(t, "claude-md", 2, True, ws=False))
        bad.append(fx.add(t, "bare", 2, "yes"))
        # no rubric
        (fx.tasks / "alpha/t91").mkdir(parents=True)
        (fx.tasks / "alpha/t91/prompt.md").write_text("p")
        for r in RUNGS:
            bad.append(fx.add("alpha/t91", r, 1, True))
        # synthetic majority record pointing at a real transcript
        maj = dict(fx.scores[0], file="[majority:2] " + fx.scores[0]["file"], repeat_majority=True,
                   is_repeat_individual=False)
        fx.scores.append(maj)
        fx.scores.append(dict(fx.scores[0], repeat_majority=True, is_repeat_individual=False))  # flag only
        for seed in range(5):
            _, _, key = fx.build(seed=seed, ts=f"E{seed}")
            used = {s for e in key.values() for s in e["stems"].values()}
            check(f"seed {seed} no excluded stems", used & set(bad), set())
            assert not any("majority" in s for s in used)
        # task with only invalid runs contributes nothing
        runs = deck.load_runs(fx.scores, fx.runs, fx.tasks)
        check("no duplicate stems", len(runs), len({r["stem"] for r in runs}))
        check("runs from bad tasks", [r for r in runs if r["task"] in ("alpha/t90", "alpha/t91")], [])


def test_already_rated_and_skip_prior():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=12)
        _, dk, key = fx.build(seed=3, n=6, ts="T1")
        ids = list(key)
        rated, skipped = ids[0], ids[1]
        fx.pick(rated, "A")
        fx.pick(skipped, "skip")
        ident_rated = frozenset(key[rated]["stems"].values())
        ident_skipped = frozenset(key[skipped]["stems"].values())
        check("rated identity found", deck.rated_identities(fx.human), {ident_rated})
        hit_rated = hit_skipped = False
        for seed in range(30):
            _, _, k2 = fx.build(seed=seed, n=6, ts=f"R{seed}")
            idents = {frozenset(e["stems"].values()) for e in k2.values()}
            assert ident_rated not in idents, "rated pair came back"
            hit_skipped |= ident_skipped in idents
        check("skipped pair may return", hit_skipped, True)
        # unordered identity: the flipped orientation counts as the same pair
        a, b = key[rated]["stems"]["A"], key[rated]["stems"]["B"]
        check("identity unordered", frozenset((b, a)), ident_rated)


def test_determinism():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp)
        r1 = fx.build(seed=7, ts="D1")[1:]
        r2 = fx.build(seed=7, ts="D2")[1:]
        r3 = fx.build(seed=8, ts="D3")[1:]
        assert r1 == r2
        print("  ok  same seed same deck+key")
        assert r1 != r3
        print("  ok  different seed differs")
        ids = [p["id"] for p in r1[0]]
        check("ids unique", len(set(ids)), len(ids))
        stems = {s for e in r1[1].values() for s in e["stems"].values()}
        assert not any(i in s or s in i for i in ids for s in stems)
        assert all(re.fullmatch(r"p[0-9a-f]{10}", i) for i in ids)


def test_side_balance():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp)
        a_low = total = 0
        for seed in range(200):
            _, _, key = fx.build(seed=seed, ts="B", human=Path(tmp) / f"h{seed}")
            for e in key.values():
                if e["layers"]["A"] != e["layers"]["B"]:
                    total += 1
                    a_low += RUNGS.index(e["layers"]["A"]) < RUNGS.index(e["layers"]["B"])
        frac = a_low / total
        assert 0.40 <= frac <= 0.60, frac
        print(f"  ok  lower-rung-on-A fraction over 200 seeds: {frac:.3f} (n={total})")
        # null/flipped pairs also randomize which stem is A
        a_first = n_null = 0
        for seed in range(200):
            key = json.loads((Path(tmp) / f"h{seed}/rounds/B/key.json").read_text())["pairs"]
            for e in key.values():
                if e["stratum"] == "null":
                    n_null += 1
                    a_first += e["stems"]["A"] < e["stems"]["B"]
        assert 0.40 <= a_first / n_null <= 0.60, a_first / n_null


def test_flipped_null_when_no_repeat():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=12)
        fx.scores = [r for r in fx.scores if r["repeat_index"] == 1]  # single run per cell
        _, _, key = fx.build()
        nulls = [e for e in key.values() if e["stratum"] == "null"]
        assert nulls
        assert all(e["stems"]["A"] == e["stems"]["B"] for e in nulls)
        print(f"  ok  {len(nulls)} flipped null pairs")


def test_html_blind():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp)
        _, dk, key = fx.build()
        html = "".join(deck.render(p, i, len(dk)) for i, p in enumerate(dk))
        html += deck.render(None, len(dk), len(dk))
        low = html.lower()
        for word in RUNGS + ["sonnet", "opus", "haiku", "cost", "token", ".json", "evalws", "workspace", "alpha/"]:
            assert word not in low, f"leak: {word}"
        for e in key.values():
            for stem in e["stems"].values():
                assert stem not in html and stem.split("Z_", 1)[1] not in html
        assert not re.search(r"(?<![\w-])(low|medium|high|xhigh|max)(?![\w-])", low), "effort word"
        assert "#000" not in low and "black" not in low
        assert "#3a3f44" in low
        check("title is neutral", "<title>Pair rating</title>" in html, True)
        assert "var sent=false" in html and "if(sent)return" in html, "in-flight guard missing"
        # escaping
        h = deck.render({"id": "p1", "prompt": "<script>x</script>", "A": "a & b", "B": "\"q\""}, 0, 1)
        assert "<script>x</script>" not in h and "&lt;script&gt;" in h and "a &amp; b" in h
        print("  ok  html escaped")


def test_artifact_normalization():
    ws = Path(tempfile.mkdtemp())
    rf, td = ws / "r.json", ws / "tasks"
    run = {"path": rf, "transcript": {"_meta": {"task": "x/y", "workspace_dir": str(ws)}}}
    digest = "\n\n## Tool-use digest\n- Agent subagent_type=dt-engineer model=opus\n- Skill ponytail"
    orig, calls = deck.artifact_text, []
    try:
        def fake(run_file, tasks_dir):
            calls.append((run_file, tasks_dir))
            return "## Final response\nok " + str(ws) + "\n[... truncated]" + digest, True
        deck.artifact_text = fake
        out = deck._artifact(run, td)
        check("provider gets (run file, tasks dir)", calls, [(rf, td)])
        check("marker not doubled", out.count("[... truncated]"), 1)
        assert str(ws) not in out and "[workspace]" in out, out
        for leak in ("digest", "subagent_type", "dt-engineer", "ponytail", "opus", "Agent"):
            assert leak not in out, f"leak via digest: {leak}"
        deck.artifact_text = lambda rf_, td_: "just str" + digest
        check("str form + digest cut", deck._artifact(run, td), "just str")
        deck.artifact_text = lambda rf_, td_: ("no digest here", False)
        check("no digest untouched", deck._artifact(run, td), "no digest here")
    finally:
        deck.artifact_text = orig
    # a real build hands real run files to the provider: each side contains its own run's result
    # (substring, not prefix: judge.artifact_text puts a "## Final response" header in front)
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=6)
        _, dk, key = fx.build(n=4)
        said = {stem: f"Widget answer {int(task[-2:])} version {rung[:1]}{k}."
                for (task, rung, k), stem in fx.stems.items()}
        assert dk, dk
        for p in dk:
            for side in ("A", "B"):
                want = said[key[p["id"]]["stems"][side]]
                assert want in p[side], (side, want, p[side])
    # local equivalent reads judge_files, diffs against seed/
    if not hasattr(deck, "_judge_files"):  # item 1.5's judge.artifact_text is in use
        return
    t = td / "x" / "y"
    t.mkdir(parents=True)
    (t / "meta.yaml").write_text("category: x\njudge_files: [out.txt, sub/b.txt]\ndescription: |\n  judge_files: nope\n")
    check("judge_files parse", deck._judge_files(t), ["out.txt", "sub/b.txt"])
    (ws / "out.txt").write_text("new\n")
    (ws / "seed").mkdir()
    (ws / "seed" / "out.txt").write_text("old\n")
    rf.write_text(json.dumps({"result": "text here", "_meta": {"task": "x/y", "workspace_dir": str(ws)}}))
    text, trunc = deck.artifact_text(rf, td)
    assert "text here" in text and "-old" in text and "+new" in text and not trunc, text
    rf.write_text(json.dumps({"result": "z" * 9000, "_meta": {"task": "x/y", "workspace_dir": str(ws)}}))
    text, trunc = deck.artifact_text(rf, td)
    check("8KB cap + marker", (len(text), trunc, text.endswith("\n[... truncated]")),
          (8192 + len("\n[... truncated]"), True, True))
    check("_artifact keeps one marker", deck._artifact(run, td).count("[... truncated]"), 1)


def test_kappa():
    L = ["A", "B", "tie"]
    check("perfect", deck.kappa(L * 4, L * 4), 1.0)
    check("perfect mixed", deck.kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]), 1.0)
    check("worst two-class", deck.kappa(["A", "B"] * 4, ["B", "A"] * 4), -1.0)
    # independent labels: every human/judge combination once -> exactly chance
    h = [a for a in L for _ in L]
    j = [b for _ in L for b in L]
    assert abs(deck.kappa(h, j)) < 1e-12
    print("  ok  chance = 0")
    # textbook 2x2: 20/5/10/15 -> po=.7, pe=.5, kappa=.4
    h = ["A"] * 25 + ["B"] * 25
    j = ["A"] * 20 + ["B"] * 5 + ["A"] * 10 + ["B"] * 15
    assert abs(deck.kappa(h, j) - 0.4) < 1e-12
    print("  ok  textbook 0.4")
    check("empty undefined", deck.kappa([], []), None)
    check("single label undefined", deck.kappa(["A", "A"], ["A", "A"]), None)
    try:
        deck.kappa(["A"], [])
        raise AssertionError("length mismatch accepted")
    except ValueError:
        print("  ok  length mismatch raises")


def test_kappa_records():
    """stats.py shape: kappa(raw picks.jsonl dicts, {stem: score}) -> {"kappa", "n"}, joined via key.json."""
    with tempfile.TemporaryDirectory() as tmp:
        human = Path(tmp) / "human"
        rows = [("p1", "A", 3, 1), ("p2", "B", 1, 3), ("p3", "tie", 2, 2), ("p4", "A", 5, 0),
                ("p5", "B", 0, 4), ("p6", "skip", 1, 2), ("p7", "A", None, None), ("p8", "A", 2, 9)]
        _write_round(human, "R1", {pid: (f"{pid}a", "memory", f"{pid}b", "skills") for pid, *_ in rows})
        scores = {}
        for pid, _, sa, sb in rows:
            if sa is not None:
                scores[f"{pid}a"], scores[f"{pid}b"] = sa, sb
        picks = [{"round": "R1", "pair": pid, "pick": pk, "note": "", "ts": "x"} for pid, pk, _, _ in rows]
        picks.append({"round": "R1", "pair": "p8", "pick": "B", "note": "", "ts": "y"})  # last pick wins
        picks.append({"round": "R1", "pair": "p1", "pick": "skip", "ts": "z"})  # re-rated as a skip: dropped
        picks.append({"round": "R1", "pair": "zzz", "pick": "A"})  # unknown pair
        picks.append({"round": "R9", "pair": "p2", "pick": "A"})  # unknown round
        res = deck.kappa(picks, scores, human_dir=human)
        # kept: p2 B/B, p3 tie/tie, p4 A/A, p5 B/B, p8 B/B (p1 skip, p6 skip, p7 no score)
        check("perfect agreement", res, {"kappa": 1.0, "n": 5})
        # same data through label-list mode and through report()'s sidecar join
        check("= label-list result", res["kappa"], deck.kappa(["B", "tie", "A", "B", "B"], ["B", "tie", "A", "B", "B"]))
        picks.append({"round": "R1", "pair": "p4", "pick": "B", "ts": "w"})  # human now disagrees on p4
        res = deck.kappa(picks, scores, human_dir=human)
        check("disagreement matches label-list", res,
              {"kappa": deck.kappa(["B", "tie", "B", "B", "B"], ["B", "tie", "A", "B", "B"]), "n": 5})
        assert res["kappa"] < 1.0
        check("generator picks ok", deck.kappa(iter(picks), scores, human_dir=human), res)
        check("no picks", deck.kappa([], scores, human_dir=human), {"kappa": None, "n": 0})
        check("no judge scores", deck.kappa(picks, {}, human_dir=human), {"kappa": None, "n": 0})
        # default human_dir is <repo>/human
        orig, deck.REPO = deck.REPO, Path(tmp)
        try:
            check("default human dir", deck.kappa(picks, scores), res)
        finally:
            deck.REPO = orig
        # label-list mode is unchanged
        check("labels still float", deck.kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]), 1.0)
    with tempfile.TemporaryDirectory() as tmp:  # report() on sidecars and record mode agree
        human, runs = Path(tmp) / "human", Path(tmp) / "runs"
        runs.mkdir()
        _write_round(human, "R1", {"q1": ("q1a", "memory", "q1b", "skills"), "q2": ("q2a", "skills", "q2b", "full"),
                                   "q3": ("q3a", "memory", "q3b", "skills")})
        sc = {"q1a": 1, "q1b": 3, "q2a": 4, "q2b": 1, "q3a": 2, "q3b": 2}
        for stem, v in sc.items():
            (runs / f"{stem}.judge.jsonl").write_text(json.dumps({"score": v}) + "\n")
        for pid, pk in (("q1", "A"), ("q2", "A"), ("q3", "tie")):
            with open(human / "picks.jsonl", "a") as f:
                f.write(json.dumps({"round": "R1", "pair": pid, "pick": pk}) + "\n")
        rep = deck.report("R1", human, runs)
        got = deck.kappa(deck._jsonl(human / "picks.jsonl"), sc, human_dir=human)
        check("report == record mode", (rep["kappa"], rep["n"]), (got["kappa"], got["n"]))


def test_sign_test():
    check("0/0", deck.sign_test_p(0, 0), None)
    assert abs(deck.sign_test_p(5, 0) - 2 / 32) < 1e-12
    assert abs(deck.sign_test_p(4, 4) - 1.0) < 1e-12
    assert abs(deck.sign_test_p(9, 1) - 2 * 11 / 1024) < 1e-12
    print("  ok  binomial sign test")


def _write_round(human, ts, pairs):
    """pairs: {pid: (stemA, layerA, stemB, layerB)}"""
    (human / "rounds" / ts).mkdir(parents=True)
    key = {pid: {"stems": {"A": a, "B": c}, "layers": {"A": la, "B": lc}, "task": "t", "stratum": "s"}
           for pid, (a, la, c, lc) in pairs.items()}
    (human / "rounds" / ts / "key.json").write_text(json.dumps({"round": ts, "pairs": key}))


def test_report():
    with tempfile.TemporaryDirectory() as tmp:
        human, runs = Path(tmp) / "human", Path(tmp) / "runs"
        runs.mkdir()
        # (pid, layers A/B, human pick, judge scores A/B)
        rows = [("p1", "memory", "skills", "A", 3, 1),    # human A=memory (lower), judge A
                ("p2", "memory", "skills", "B", 1, 3),    # human B=skills (higher), judge B
                ("p3", "skills", "memory", "A", 2, 2),    # human A=skills (higher), judge tie
                ("p4", "skills", "memory", "tie", 1, 3),  # human tie, judge B
                ("p5", "skills", "full", "B", 4, 0),      # human full wins, judge A
                ("p6", "skills", "full", "skip", 1, 1),   # skipped, excluded
                ("p7", "skills", "full", "A", None, None)]  # no sidecar: out of kappa, in win rates
        pairs = {}
        for pid, la, lb, pick, sa, sb in rows:
            pairs[pid] = (f"{pid}a", la, f"{pid}b", lb)
            if sa is not None:
                (runs / f"{pid}a.judge.jsonl").write_text(json.dumps({"score": 0}) + "\n" + json.dumps({"score": sa}) + "\n")
                (runs / f"{pid}b.judge.jsonl").write_text(json.dumps({"score": sb}) + "\n")
        _write_round(human, "R1", pairs)
        for pid, _, _, pick, _, _ in rows:
            with open(human / "picks.jsonl", "a") as f:
                f.write(json.dumps({"round": "R1", "pair": pid, "pick": pick, "note": "", "ts": "x"}) + "\n")
        # a re-rating of p1 (last wins), an unknown pair and another round are ignored for R1
        with open(human / "picks.jsonl", "a") as f:
            f.write(json.dumps({"round": "R1", "pair": "zzz", "pick": "A"}) + "\n")
            f.write(json.dumps({"round": "R2", "pair": "p1", "pick": "B"}) + "\n")
        r = deck.report("R1", human, runs)
        check("n", r["n"], 5)
        check("n_picks", r["n_picks"], 6)
        # human: A B A tie B ; judge: A B tie B A  -> agree on first two
        check("raw", r["raw_agreement"], 2 / 5)
        check("decisive", r["decisive_agreement"], 2 / 3)  # pairs 1,2,5 decisive; 1,2 agree
        exp = deck.kappa(["A", "B", "A", "tie", "B"], ["A", "B", "tie", "B", "A"])
        check("kappa", r["kappa"], exp)
        wr = r["win_rates"]
        check("memory>skills", (wr["memory>skills"]["higher"], wr["memory>skills"]["lower"], wr["memory>skills"]["tie"]),
              (2, 1, 1))  # p1 lower(memory A), p2 higher, p3 higher(skills A), p4 tie
        check("skills>full", (wr["skills>full"]["higher"], wr["skills>full"]["lower"]), (1, 1))
        assert abs(wr["memory>skills"]["higher_win_rate"] - 2 / 3) < 1e-12
        assert abs(wr["memory>skills"]["p"] - 1.0) < 1e-12
        assert set(r) >= {"kappa", "n", "raw_agreement", "decisive_agreement", "win_rates"}
        # round=None joins all rounds (R2's pick on p1 lives in no key -> ignored)
        check("all-rounds n", deck.report(None, human, runs)["n"], 5)
        check("empty report", deck.report("nope", human, runs)["kappa"], None)


def _req(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_server():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=12)
        _, dk, key = fx.build(n=4)
        # one pair loses its workspace: it must not be served
        gone = key[dk[0]["id"]]["stems"]["A"]
        meta = json.loads((fx.runs / f"{gone}.json").read_text())["_meta"]
        Path(meta["workspace_dir"]).rmdir()
        srv = deck.make_server("T1", fx.human, fx.runs)
        check("gone pair dropped", len(srv.pairs), 3)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            assert srv.server_address[0] == "127.0.0.1"
            code, body = _req(base + "/")
            check("GET /", code, 200)
            check("progress shown", "Pair 1 of 3" in body, True)
            first = srv.pairs[0]["id"]
            check("first pair id", f'dataset.pair="{first}"' in body, True)
            post = lambda d, **h: _req(base + "/pick", json.dumps(d).encode(), {"Content-Type": "application/json", **h})
            check("bad pick", post({"pair": first, "pick": "Z"})[0], 400)
            check("bad pair", post({"pair": "nope", "pick": "A"})[0], 400)
            check("not json", _req(base + "/pick", b"xx")[0], 400)
            check("too big", post({"pair": first, "pick": "A", "note": "x" * 40000})[0], 413)
            check("bad host", post({"pair": first, "pick": "A"}, Host="evil.example")[0], 403)
            check("bad origin", post({"pair": first, "pick": "A"}, Origin="http://evil.example")[0], 403)
            check("nothing written yet", (fx.human / "picks.jsonl").exists(), False)
            check("good pick", post({"pair": first, "pick": "tie", "note": "hm"})[0], 200)
            rows = [json.loads(x) for x in (fx.human / "picks.jsonl").read_text().splitlines()]
            check("picks row", [(r["round"], r["pair"], r["pick"], r["note"]) for r in rows],
                  [("T1", first, "tie", "hm")])
            assert "ts" in rows[0]
            _, body = _req(base + "/")
            check("advances", "Pair 2 of 3" in body and first not in body, True)
            # only the current unanswered pair takes a pick: a double send can't turn a rating into a skip
            second, third = srv.pairs[1]["id"], srv.pairs[2]["id"]
            check("re-send answered pair rejected", post({"pair": first, "pick": "skip"})[0], 409)
            check("future pair rejected", post({"pair": third, "pick": "A"})[0], 409)
            check("rejections wrote nothing", len((fx.human / "picks.jsonl").read_text().splitlines()), 1)
            for p in srv.pairs[1:]:
                check(f"in-order pick {p['id'][:4]}", post({"pair": p["id"], "pick": "skip"})[0], 200)
            _, body = _req(base + "/")
            check("done page", "All 3 pairs answered" in body, True)
            check("nothing left to pick", post({"pair": second, "pick": "A"})[0], 409)
            check("rows after rejections", len((fx.human / "picks.jsonl").read_text().splitlines()), 3)
        finally:
            srv.shutdown()
            srv.server_close()


def test_server_threaded():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fixture(tmp, ntasks=12)
        fx.build(n=4)
        srv = deck.make_server("T1", fx.human, fx.runs)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        base = f"http://127.0.0.1:{port}"
        idle = socket.create_connection(("127.0.0.1", port))  # a browser's pre-opened, silent socket
        try:
            urllib.request.urlopen(base + "/", timeout=3).read()  # single-threaded server: stalls here
            print("  ok  GET served while an idle socket is open")
            first, codes = srv.pairs[0]["id"], []
            body = json.dumps({"pair": first, "pick": "A"}).encode()

            def go():
                codes.append(_req(base + "/pick", body, {"Content-Type": "application/json"})[0])
            ts = [threading.Thread(target=go) for _ in range(12)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            check("12 simultaneous sends: one wins", sorted(codes), [200] + [409] * 11)
            check("one row", len((fx.human / "picks.jsonl").read_text().splitlines()), 1)
        finally:
            idle.close()
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    test_candidates_no_rebind()
    test_quotas_literal()
    test_strata_quotas()
    test_strata_default_unchanged()
    test_strata_parse()
    test_preset_quotas()
    test_preset_mutual_exclusion()
    test_preset_build_and_report()
    test_preset_one_repeat()
    test_fill_forward()
    test_build_zero_pairs()
    test_exclusions()
    test_already_rated_and_skip_prior()
    test_determinism()
    test_side_balance()
    test_flipped_null_when_no_repeat()
    test_html_blind()
    test_artifact_normalization()
    test_kappa()
    test_kappa_records()
    test_sign_test()
    test_report()
    test_server()
    test_server_threaded()
    print("ALL PASS")
