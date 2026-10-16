#!/usr/bin/env python3
"""Blind human deck: build A/B pairs from scored runs, serve them for rating, report agreement.

  deck.py build  --scores-file F [--seed N] [--n 20]   -> human/rounds/<ts>/{deck,key}.json
  deck.py serve  --round TS [--port P]                 -> http.server on 127.0.0.1, appends human/picks.jsonl
  deck.py report [--round TS]                          -> kappa / agreement / per-layer-pair human win rates

deck.json holds only displayed text (opaque pair id, prompt, A, B). key.json holds the
side map, run stems, layers and stratum. The HTML is built from deck.json alone.
Stdlib only.
"""
import argparse
import difflib
import json
import math
import random
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

RUNGS = ["bare", "claude-md", "memory", "skills", "full"]  # adjacency order
# (name, quota at n=20). Order = fill-forward order: a shortage rolls into the next stratum.
STRATA = [("memory-vs-skills", 6), ("skills-vs-full", 6), ("adjacent-tie", 4),
          ("check-disagree", 2), ("null", 2)]
MAX_PER_TASK = 2
ARTIFACT_CAP = 8192
PICKS = {"A": "A", "B": "B", "tie": "tie", "skip": "skip"}
MAX_BODY = 16 * 1024
MAX_NOTE = 2000


# --------------------------------------------------------------------------- artifact text
TASKS_DIR = REPO / "tasks"  # set per build; only the local artifact_text reads it

try:
    from judge import artifact_text  # item 1.5; may return str or (str, truncated)
except ImportError:
    def _judge_files(task_dir):
        """Column-0 `judge_files:` in meta.yaml: inline `a, b` / `[a, b]`, or `- x` list lines."""
        try:
            lines = (Path(task_dir) / "meta.yaml").read_text().splitlines()
        except OSError:
            return []
        for i, line in enumerate(lines):
            if line[:1] in (" ", "\t") or not line.startswith("judge_files:"):
                continue
            val = line.split(":", 1)[1].split("#", 1)[0].strip().strip("[]")
            if val:
                return [v.strip().strip("'\"") for v in val.split(",") if v.strip()]
            out = []
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if s.startswith("- "):
                    out.append(s[2:].split("#", 1)[0].strip().strip("'\""))
                elif s and not s.startswith("#"):
                    break
            return out
        return []

    def artifact_text(run):
        """Result text + files named by task meta `judge_files:` (diff vs seed/ when present).

        Returns (text, truncated); 8 KB cap. Same signature as judge.artifact_text.
        """
        meta = run.get("_meta") or {}
        parts = [run.get("result") or ""]
        ws = Path(meta.get("workspace_dir") or "")
        for rel in _judge_files(TASKS_DIR / (meta.get("task") or "_")):
            f, seed = ws / rel, ws / "seed" / rel
            if ".." in Path(rel).parts or not f.is_file():
                continue
            body = f.read_text(errors="replace")
            if seed.is_file():
                body = "".join(difflib.unified_diff(seed.read_text(errors="replace").splitlines(True),
                                                    body.splitlines(True), "", ""))
            parts.append(body)
        text = "\n\n---\n\n".join(p for p in parts if p)
        return text[:ARTIFACT_CAP], len(text) > ARTIFACT_CAP


def _artifact(run, tasks_dir):
    """Normalize artifact_text output (str or (str, bool)) and scrub paths that name files."""
    global TASKS_DIR
    TASKS_DIR = Path(tasks_dir)
    out = artifact_text(run)
    text, trunc = out if isinstance(out, tuple) else (out, False)
    meta = run.get("_meta") or {}
    ws = meta.get("workspace_dir")
    if ws:
        text = text.replace(ws, "[workspace]")
    if trunc:
        text += "\n[... truncated]"
    return text


# --------------------------------------------------------------------------- candidates
def _valid_record(r):
    f = r.get("file") or ""
    if f.startswith("[") or r.get("repeat_majority"):
        return False  # synthetic majority-vote record
    bad = ("infra_error", "is_error", "timed_out", "budget_exceeded", "contaminated",
           "runaway", "runaway_output")
    if any(r.get(k) for k in bad):
        return False
    return isinstance(r.get("passed"), bool) and r.get("rung") in RUNGS and f.endswith(".json")


def load_runs(scores, runs_dir, tasks_dir):
    """Valid, rubric-task runs: dicts with stem/task/rung/model/effort/passed/cell/transcript."""
    runs_dir, tasks_dir = Path(runs_dir), Path(tasks_dir)
    out = []
    for r in scores:
        if not _valid_record(r) or not (tasks_dir / r["task"] / "rubric.md").exists():
            continue
        try:
            t = json.loads((runs_dir / r["file"]).read_text())
        except (OSError, ValueError):
            continue
        meta = t.get("_meta") or {}
        ws = meta.get("workspace_dir")
        if not (t.get("result") or "").strip() or not ws or not Path(ws).is_dir():
            continue
        effort = r.get("effort", meta.get("effort"))
        out.append({"stem": r["file"][:-5], "task": r["task"], "rung": r["rung"],
                    "model": r.get("model"), "effort": effort, "passed": r["passed"],
                    "cell": (r["task"], r.get("model"), effort), "transcript": t})
    return sorted(out, key=lambda x: x["stem"])


def stratum_of(a, b):
    """Stratum index for two runs of one cell, or None. Null (same rung) -> 4."""
    if a["cell"] != b["cell"]:
        return None
    if a["rung"] == b["rung"]:
        return 4 if a["stem"] != b["stem"] else None
    lo, hi = sorted((a["rung"], b["rung"]), key=RUNGS.index)
    if RUNGS.index(hi) - RUNGS.index(lo) != 1:
        return None
    if a["passed"] != b["passed"]:
        return 3
    if (lo, hi) == ("memory", "skills"):
        return 0 if a["passed"] else None
    if (lo, hi) == ("skills", "full"):
        return 1 if a["passed"] else None
    return 2 if (lo, hi) in (("bare", "claude-md"), ("claude-md", "memory")) else None


def candidates(runs):
    """Per-stratum sorted lists of (run, run) with run.rung order lo->hi (null: stem order)."""
    strata = [[] for _ in STRATA]
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            s = stratum_of(a, b)
            if s is None:
                continue
            if s != 4 and RUNGS.index(a["rung"]) > RUNGS.index(b["rung"]):
                a, b = b, a
            strata[s].append((a, b))
    if not strata[4]:  # no second valid repeat anywhere: "flipped" -- the same run on both sides
        strata[4] = [(r, r) for r in runs]
    for lst in strata:
        lst.sort(key=lambda p: (p[0]["stem"], p[1]["stem"]))
    return strata


def quotas(n):
    base = [q * n // 20 for _, q in STRATA]
    for i in range(n - sum(base)):
        base[i % len(base)] += 1
    return base


def pair_identity(a, b):
    return frozenset((a["stem"], b["stem"]))


def select(strata, n, rng, rated=frozenset()):
    """Pick up to n pairs. Uniform within a stratum; a shortage rolls into the next stratum
    (then the one after); leftovers top up from any stratum with candidates remaining.
    Returns [(stratum_idx, (a, b))]. Fewer than n only if the whole pool is exhausted."""
    task_n, used, chosen = {}, set(), []

    def take(si, want):
        got = 0
        pool = list(strata[si])
        rng.shuffle(pool)
        for a, b in pool:
            if got >= want:
                break
            if (pair_identity(a, b) in rated or task_n.get(a["task"], 0) >= MAX_PER_TASK
                    or a["stem"] in used or b["stem"] in used):
                continue
            task_n[a["task"]] = task_n.get(a["task"], 0) + 1
            used.update((a["stem"], b["stem"]))
            chosen.append((si, (a, b)))
            got += 1
        return got

    carry = 0
    for si, q in enumerate(quotas(n)):
        want = q + carry
        carry = want - take(si, want)
    for si in range(len(STRATA)):
        if len(chosen) >= n:
            break
        take(si, n - len(chosen))
    return chosen


# --------------------------------------------------------------------------- picks / rounds
def _jsonl(path):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def load_keys(human_dir):
    """{round_ts: key dict} for every round on disk."""
    keys = {}
    for k in sorted((Path(human_dir) / "rounds").glob("*/key.json")):
        try:
            keys[k.parent.name] = json.loads(k.read_text())
        except ValueError:
            pass
    return keys


def rated_identities(human_dir):
    """Unordered stem-pairs already rated A/B/tie in any round (a skip is not a rating)."""
    keys, out = load_keys(human_dir), set()
    for p in _jsonl(Path(human_dir) / "picks.jsonl"):
        if p.get("pick") in ("A", "B", "tie"):
            e = keys.get(p.get("round"), {}).get("pairs", {}).get(p.get("pair"))
            if e:
                out.add(frozenset(e["stems"].values()))
    return out


def build(scores_file, seed=0, n=20, runs_dir=None, tasks_dir=None, human_dir=None, ts=None):
    runs_dir, tasks_dir = Path(runs_dir or REPO / "runs"), Path(tasks_dir or REPO / "tasks")
    human_dir = Path(human_dir or REPO / "human")
    scores = json.loads(Path(scores_file).read_text())["scores"]
    runs = load_runs(scores, runs_dir, tasks_dir)
    rng = random.Random(seed)
    chosen = select(candidates(runs), n, rng, rated_identities(human_dir))
    rng.shuffle(chosen)
    ts = ts or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = human_dir / "rounds" / ts
    if rdir.exists():
        raise SystemExit(f"round exists: {rdir}")
    deck, key, ids = [], {}, set()
    for si, (a, b) in chosen:
        if rng.random() < 0.5:
            a, b = b, a
        pid = f"p{rng.getrandbits(40):010x}"
        while pid in ids:
            pid = f"p{rng.getrandbits(40):010x}"
        ids.add(pid)
        prompt = (tasks_dir / a["task"] / "prompt.md").read_text()
        deck.append({"id": pid, "prompt": prompt, "A": _artifact(a["transcript"], tasks_dir),
                     "B": _artifact(b["transcript"], tasks_dir)})
        key[pid] = {"stems": {"A": a["stem"], "B": b["stem"]}, "layers": {"A": a["rung"], "B": b["rung"]},
                    "task": a["task"], "stratum": STRATA[si][0]}
    rdir.mkdir(parents=True)
    (rdir / "deck.json").write_text(json.dumps({"round": ts, "pairs": deck}, indent=1))
    (rdir / "key.json").write_text(json.dumps({"round": ts, "seed": seed, "pairs": key}, indent=1))
    return ts, deck, key


# --------------------------------------------------------------------------- html / server
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair rating</title>
<style>
:root{--ink:#3a3f44;--muted:#6b7177;--bg:#f6f6f4;--card:#fff;--line:#d9dad6;--accent:#3d6b8a}
@media (prefers-color-scheme:dark){:root{--ink:#d3d6d9;--muted:#9aa0a6;--bg:#1d2023;--card:#26292d;--line:#3a3e43;--accent:#8fb4cf}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
.wrap{width:min(1200px,100%);margin:0 auto}
h2{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:16px 0 6px}
.bar{display:flex;justify-content:space-between;color:var(--muted);font-size:14px}
pre{margin:0;padding:12px;background:var(--card);border:1px solid var(--line);border-radius:6px;color:var(--ink);
white-space:pre-wrap;word-break:break-word;font:13px/1.45 ui-monospace,Menlo,monospace;overflow:auto}
.prompt{overflow:auto}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:760px){.cols{grid-template-columns:1fr}}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;align-items:center}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px 14px;cursor:pointer}
button:hover,button:focus-visible{border-color:var(--accent);outline:none}
kbd{color:var(--muted);font-size:12px;margin-left:6px}
input{flex:1;min-width:180px;font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px}
</style></head><body><div class="wrap">
<div class="bar"><span>@@PROGRESS@@</span><span>a / b / t / s &middot; Esc leaves the note box</span></div>
@@BODY@@
</div>
<script>
var pair=document.body.dataset.pair;
function send(p){var n=document.getElementById('note');
fetch('/pick',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({pair:pair,pick:p,note:n?n.value:''})}).then(function(){location.reload()})}
document.addEventListener('keydown',function(e){
var t=e.target;if(t&&t.id==='note'){if(e.key==='Escape')t.blur();return}
if(!pair||e.ctrlKey||e.metaKey||e.altKey)return;
var m={a:'A',b:'B',t:'tie',s:'skip'}[e.key.toLowerCase()];if(m){e.preventDefault();send(m)}});
Array.prototype.forEach.call(document.querySelectorAll('button[data-pick]'),function(b){
b.addEventListener('click',function(){send(b.dataset.pick)})});
</script></body></html>"""


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def render(pair, done, total):
    if pair is None:
        body = f"<h2>Done</h2><p>All {total} pairs answered.</p>"
        return PAGE.replace("@@PROGRESS@@", f"{done} / {total}").replace("@@BODY@@", body).replace(
            "<script>", '<script>document.body.dataset.pair="";', 1)
    body = (f'<h2>Prompt</h2><pre class="prompt" style="max-height:30vh">{esc(pair["prompt"])}</pre>'
            f'<div class="cols"><div><h2>A</h2><pre>{esc(pair["A"])}</pre></div>'
            f'<div><h2>B</h2><pre>{esc(pair["B"])}</pre></div></div>'
            '<div class="actions"><button data-pick="A">A better<kbd>a</kbd></button>'
            '<button data-pick="B">B better<kbd>b</kbd></button>'
            '<button data-pick="tie">Tie<kbd>t</kbd></button>'
            '<button data-pick="skip">Skip<kbd>s</kbd></button>'
            '<input id="note" maxlength="2000" placeholder="Optional note"></div>')
    html = PAGE.replace("@@PROGRESS@@", f"Pair {done + 1} of {total}").replace("@@BODY@@", body)
    return html.replace("<script>", f'<script>document.body.dataset.pair="{pair["id"]}";', 1)


def _answered(picks_path, ts):
    return {p.get("pair") for p in _jsonl(picks_path) if p.get("round") == ts}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _local(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (origin is None or origin in {f"http://{h}" for h in hosts})

    def do_GET(self):
        if not self._local():
            return self._send(403, "forbidden", "text/plain")
        if self.path.split("?")[0] != "/":
            return self._send(404, "not found", "text/plain")
        s = self.server
        done = _answered(s.picks_path, s.round_ts)
        nxt = next((p for p in s.pairs if p["id"] not in done), None)
        self._send(200, render(nxt, sum(p["id"] in done for p in s.pairs), len(s.pairs)))

    def do_POST(self):
        if not self._local():
            return self._send(403, "forbidden", "text/plain")
        if self.path != "/pick":
            return self._send(404, "not found", "text/plain")
        try:
            ln = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, "length required", "text/plain")
        if not 0 < ln <= MAX_BODY:
            return self._send(413, "bad size", "text/plain")
        try:
            d = json.loads(self.rfile.read(ln))
            pair, pick, note = d["pair"], d["pick"], d.get("note", "")
        except (ValueError, KeyError, TypeError):
            return self._send(400, "bad json", "text/plain")
        s = self.server
        if (not isinstance(pair, str) or pair not in {p["id"] for p in s.pairs}
                or pick not in PICKS or not isinstance(note, str)):
            return self._send(400, "bad pick", "text/plain")
        rec = {"round": s.round_ts, "pair": pair, "pick": pick, "note": note[:MAX_NOTE],
               "ts": datetime.now(timezone.utc).isoformat()}
        s.picks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(s.picks_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        self._send(200, '{"ok":true}', "application/json")


def make_server(round_ts, human_dir, runs_dir, port=0):
    """HTTPServer for a built round. Pairs whose workspace dir is gone are not served."""
    human_dir, runs_dir = Path(human_dir), Path(runs_dir)
    rdir = human_dir / "rounds" / round_ts
    deck = json.loads((rdir / "deck.json").read_text())["pairs"]
    key = json.loads((rdir / "key.json").read_text())["pairs"]
    ok = []
    for p in deck:
        for stem in set(key[p["id"]]["stems"].values()):
            try:
                ws = json.loads((runs_dir / f"{stem}.json").read_text())["_meta"]["workspace_dir"]
            except (OSError, ValueError, KeyError):
                ws = ""
            if not ws or not Path(ws).is_dir():
                print(f"skipping pair {p['id']}: workspace gone", file=sys.stderr)
                break
        else:
            ok.append(p)
    if not ok:
        raise SystemExit("no servable pairs")
    srv = HTTPServer(("127.0.0.1", port), Handler)
    srv.pairs, srv.round_ts, srv.picks_path = ok, round_ts, human_dir / "picks.jsonl"
    return srv


# --------------------------------------------------------------------------- report
def kappa(picks, judge):
    """3-class Cohen's kappa over labels in {"A","B","tie"}. Equal-length sequences.
    Returns None when undefined: no items, or chance agreement is 1 (a single label throughout)."""
    picks, judge = list(picks), list(judge)
    if len(picks) != len(judge):
        raise ValueError("picks and judge must be the same length")
    n = len(picks)
    if n == 0:
        return None
    po = sum(a == b for a, b in zip(picks, judge)) / n
    pe = sum((picks.count(c) / n) * (judge.count(c) / n) for c in ("A", "B", "tie"))
    return None if pe >= 1 else (po - pe) / (1 - pe)


def sign_test_p(wins, losses):
    """Two-sided exact binomial (p=0.5); None when there are no decisive pairs."""
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def judge_label(runs_dir, stems):
    """Side with the higher score in the last line of each stem's judge sidecar; None if missing."""
    sc = {}
    for side, stem in stems.items():
        rows = _jsonl(Path(runs_dir) / f"{stem}.judge.jsonl")
        if not rows or not isinstance(rows[-1].get("score"), (int, float)):
            return None
        sc[side] = rows[-1]["score"]
    return "tie" if sc["A"] == sc["B"] else ("A" if sc["A"] > sc["B"] else "B")


def report(round_ts=None, human_dir=None, runs_dir=None):
    """Join picks + key + judge sidecars. Keys: n (kappa-eligible pairs), n_picks, kappa,
    raw_agreement, decisive_agreement, win_rates {"lo>hi": {...}} (None where undefined)."""
    human_dir, runs_dir = Path(human_dir or REPO / "human"), Path(runs_dir or REPO / "runs")
    keys, last = load_keys(human_dir), {}
    for p in _jsonl(human_dir / "picks.jsonl"):
        if round_ts and p.get("round") != round_ts:
            continue
        last[(p.get("round"), p.get("pair"))] = p  # re-rating overwrites
    hum, jdg, wins = [], [], {}
    n_picks = 0
    for (r, pid), p in sorted(last.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        e = keys.get(r, {}).get("pairs", {}).get(pid)
        if e is None or p.get("pick") not in ("A", "B", "tie"):
            continue  # unknown pair, or skip
        n_picks += 1
        pick = p["pick"]
        j = judge_label(runs_dir, e["stems"])
        if j is not None:
            hum.append(pick)
            jdg.append(j)
        la, lb = e["layers"]["A"], e["layers"]["B"]
        if la != lb:
            lo, hi = sorted((la, lb), key=RUNGS.index)
            w = wins.setdefault(f"{lo}>{hi}", {"higher": 0, "lower": 0, "tie": 0})
            if pick == "tie":
                w["tie"] += 1
            else:
                w["higher" if e["layers"][pick] == hi else "lower"] += 1
    dec = [(a, b) for a, b in zip(hum, jdg) if a != "tie" and b != "tie"]
    win_rates = {}
    for k, w in sorted(wins.items()):
        d = w["higher"] + w["lower"]
        win_rates[k] = {**w, "n": d + w["tie"], "higher_win_rate": w["higher"] / d if d else None,
                        "p": sign_test_p(w["higher"], w["lower"])}
    return {"round": round_ts, "n_picks": n_picks, "n": len(hum), "kappa": kappa(hum, jdg),
            "raw_agreement": sum(a == b for a, b in zip(hum, jdg)) / len(hum) if hum else None,
            "decisive_agreement": sum(a == b for a, b in dec) / len(dec) if dec else None,
            "win_rates": win_rates}


# --------------------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    com = argparse.ArgumentParser(add_help=False)
    com.add_argument("--runs-dir", default=str(REPO / "runs"))
    com.add_argument("--tasks-dir", default=str(REPO / "tasks"))
    com.add_argument("--human-dir", default=str(REPO / "human"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", parents=[com])
    b.add_argument("--scores-file", required=True)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--n", type=int, default=20)
    s = sub.add_parser("serve", parents=[com])
    s.add_argument("--round", required=True)
    s.add_argument("--port", type=int, default=0)
    r = sub.add_parser("report", parents=[com])
    r.add_argument("--round")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        ts, deck, key = build(a.scores_file, a.seed, a.n, a.runs_dir, a.tasks_dir, a.human_dir)
        counts = {}
        for e in key.values():
            counts[e["stratum"]] = counts.get(e["stratum"], 0) + 1
        print(f"round {ts}: {len(deck)} pairs (requested {a.n}) {counts}")
        if len(deck) < a.n:
            print(f"warning: candidate pool exhausted at {len(deck)} pairs", file=sys.stderr)
    elif a.cmd == "serve":
        srv = make_server(a.round, a.human_dir, a.runs_dir, a.port)
        print(f"http://127.0.0.1:{srv.server_address[1]}/", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        print(json.dumps(report(a.round, a.human_dir, a.runs_dir), indent=1))


if __name__ == "__main__":
    main()
