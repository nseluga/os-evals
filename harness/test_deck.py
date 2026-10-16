"""Tests for deck.py: strata, exclusions, determinism, side balance, blind HTML, kappa, win rates, server.

Run: python3 harness/test_deck.py
"""
import json
import re
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
        # escaping
        h = deck.render({"id": "p1", "prompt": "<script>x</script>", "A": "a & b", "B": "\"q\""}, 0, 1)
        assert "<script>x</script>" not in h and "&lt;script&gt;" in h and "a &amp; b" in h
        print("  ok  html escaped")


def test_artifact_normalization():
    ws = Path(tempfile.mkdtemp())
    run = {"result": "text here", "_meta": {"task": "x/y", "workspace_dir": str(ws)}}
    orig = deck.artifact_text
    try:
        deck.artifact_text = lambda r: ("plain " + str(ws), True)
        out = deck._artifact(run, ws)
        assert str(ws) not in out and out.endswith("[... truncated]"), out
        deck.artifact_text = lambda r: "just str"
        check("str form", deck._artifact(run, ws), "just str")
    finally:
        deck.artifact_text = orig
    # local equivalent reads judge_files, diffs against seed/
    if not hasattr(deck, "_judge_files"):  # item 1.5's judge.artifact_text is in use
        return
    td = ws / "tasks" / "x" / "y"
    td.mkdir(parents=True)
    (td / "meta.yaml").write_text("category: x\njudge_files: [out.txt, sub/b.txt]\ndescription: |\n  judge_files: nope\n")
    check("judge_files parse", deck._judge_files(td), ["out.txt", "sub/b.txt"])
    (ws / "out.txt").write_text("new\n")
    (ws / "seed").mkdir()
    (ws / "seed" / "out.txt").write_text("old\n")
    deck.TASKS_DIR = ws / "tasks"
    text, trunc = deck.artifact_text(run)
    assert "text here" in text and "-old" in text and "+new" in text and not trunc, text
    run["result"] = "z" * 9000
    text, trunc = deck.artifact_text(run)
    check("8KB cap", (len(text), trunc), (8192, True))


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
            for p in srv.pairs[1:]:
                post({"pair": p["id"], "pick": "skip"})
            _, body = _req(base + "/")
            check("done page", "All 3 pairs answered" in body, True)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    test_quotas_literal()
    test_strata_quotas()
    test_fill_forward()
    test_exclusions()
    test_already_rated_and_skip_prior()
    test_determinism()
    test_side_balance()
    test_flipped_null_when_no_repeat()
    test_html_blind()
    test_artifact_normalization()
    test_kappa()
    test_sign_test()
    test_report()
    test_server()
    print("ALL PASS")
