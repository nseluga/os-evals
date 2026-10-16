#!/usr/bin/env python3
"""
harness/judge.py

Quarantined LLM judge: grades a run's artifact against the task's rubric.md with a
bare-config Opus judge and appends the verdict to a sidecar runs/<stem>.judge.jsonl.
score.py joins the sidecar; stats.judge_appendix renders it LAST, outside every headline
number. The judge sees the rubric and the artifact only: never the rung, model, effort,
path or file stem.

  python3 harness/judge.py --runs-dir runs --tasks-dir tasks --configs-dir configs [--jobs 4]
  python3 harness/judge.py --validate --task writing/plain-explainer   # judges tests/good + tests/bad

Sidecar line: {ts, rubric_sha, model, effort, score, rationale, leak, truncated, cost_usd}.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contamination import scrub_env  # noqa: E402
from run_matrix import _iter_tool_uses, build_run_config, execute_items, load_rung, rung_dir  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
JUDGE_MODEL = "opus"
JUDGE_EFFORT = "medium"
JUDGE_BUDGET_USD = 0.50
ARTIFACT_CAP = 8 * 1024      # chars of result + files; digest has its own cap below
DIGEST_CAP = 2 * 1024
SCHEMA = ('{"type":"object","properties":{"score":{"type":"integer"},"rationale":{"type":"string"}},'
          '"required":["score","rationale"]}')
SYSTEM_PROMPT = (
    "You are a strict, impartial grader. You receive a rubric and an artifact produced by an unknown "
    "author. Score the artifact from 0 to 5 using only the rubric and the artifact text. Do not guess "
    "how it was produced and do not reward length. Reply with JSON only: an integer score and a "
    "rationale of at most three sentences that cites the rubric anchors."
)


class JudgeError(Exception):
    pass


# --- task metadata (own parser: no edits to the run_matrix / score parsers) ---

def read_judge_meta(task_dir: Path) -> dict:
    """category + judge_files (comma-separated, column-0 keys only) from meta.yaml."""
    out = {"category": "", "judge_files": []}
    f = Path(task_dir) / "meta.yaml"
    if not f.exists():
        return out
    for line in f.read_text().splitlines():
        if line[:1] in (" ", "\t"):
            continue
        s = line.strip()
        if s.startswith("category:"):
            out["category"] = s.split(":", 1)[1].split("#")[0].strip()
        elif s.startswith("judge_files:"):
            val = s.split(":", 1)[1].split("#")[0]
            out["judge_files"] = [x.strip() for x in val.split(",") if x.strip()]
    return out


def rubric_sha(task_dir: Path):
    r = Path(task_dir) / "rubric.md"
    return hashlib.sha1(r.read_bytes()).hexdigest()[:12] if r.is_file() else None


# --- artifact ---

def _norm_tool(name: str) -> str:
    return "Agent" if name in ("Agent", "Task") else name


def trace_digest(events: list) -> str:
    """One line per tool_use: tool, subagent_type, model, description. Agent == Task."""
    lines = []
    for name, inp in _iter_tool_uses(events):
        parts = [_norm_tool(name)]
        for k in ("subagent_type", "model"):
            if inp.get(k):
                parts.append(f"{k}={inp[k]}")
        desc = inp.get("description") or inp.get("skill") or inp.get("command") or ""
        if desc:
            parts.append(str(desc).replace("\n", " ")[:120])
        lines.append("- " + " ".join(parts))
    text = "\n".join(lines)
    return text[:DIGEST_CAP] + ("\n[digest truncated]" if len(text) > DIGEST_CAP else "")


def _file_section(rel: str, ws: Path, seed: Path) -> str:
    p = ws / rel
    if not p.is_file():
        return f"## File: {rel}\n(not present)"
    new = p.read_text(errors="replace")
    old_p = seed / rel
    if old_p.is_file():
        old = old_p.read_text(errors="replace")
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            f"a/{rel}", f"b/{rel}"))
        return f"## File: {rel} (diff against the starting version)\n" + (diff or "(unchanged)")
    return f"## File: {rel}\n{new}"


def build_artifact(result: str, judge_files: list, ws: Path | None, seed: Path, events=None,
                   process: bool = False) -> tuple[str, bool]:
    """(artifact_text, truncated). Pure of run identity: only result, named files, trace digest."""
    parts = []
    if (result or "").strip():
        parts.append("## Final response\n" + result.strip())
    for rel in judge_files:
        parts.append(_file_section(rel, ws, seed) if ws else f"## File: {rel}\n(not present)")
    body = "\n\n".join(parts)
    truncated = len(body) > ARTIFACT_CAP
    if truncated:
        body = body[:ARTIFACT_CAP] + "\n[... truncated]"
    if process and events:
        body += "\n\n## Tool-use digest\n" + trace_digest(events)
    return body, truncated


def artifact_text(run_file: Path, tasks_dir: Path) -> tuple[str, bool]:
    """Artifact for one run transcript: result + judge_files from its workspace (diff vs the
    task's seed/ when present) + a trace digest for category: process tasks."""
    run_file = Path(run_file)
    t = json.loads(run_file.read_text())
    meta = t.get("_meta") or {}
    task_dir = Path(tasks_dir) / meta.get("task", "")
    jm = read_judge_meta(task_dir)
    ws = Path(meta["workspace_dir"]) if meta.get("workspace_dir") else None
    events = []
    trace = run_file.with_name(run_file.stem + ".trace.jsonl")
    if jm["category"] == "process" and trace.is_file():
        for ln in trace.read_text().splitlines():
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            if isinstance(ev, dict):
                events.append(ev)
    return build_artifact(str(t.get("result") or ""), jm["judge_files"], ws, task_dir / "seed",
                          events, jm["category"] == "process")


def build_judge_prompt(rubric: str, artifact: str) -> str:
    """Rubric + artifact only. Nothing about the run (rung, model, effort, path, stem)."""
    return (f"<rubric>\n{rubric.strip()}\n</rubric>\n\n<artifact>\n{artifact}\n</artifact>\n\n"
            "Score the artifact against the rubric.")


# --- claude subprocess ---

def judge_cmd(system_prompt: str = SYSTEM_PROMPT) -> list[str]:
    return ["claude", "-p", "--output-format", "json", "--model", JUDGE_MODEL, "--effort", JUDGE_EFFORT,
            "--bare", "--tools", "", "--no-session-persistence", "--system-prompt", system_prompt,
            "--json-schema", SCHEMA, "--max-budget-usd", str(JUDGE_BUDGET_USD)]


def latest_sha(configs_dir: Path, preferred: str = "") -> str:
    """preferred os sha if its bare layer is built, else the newest configs/<sha> that has one."""
    configs_dir = Path(configs_dir)
    if preferred and (rung_dir(configs_dir, "bare", preferred) / "rung.env").is_file():
        return preferred
    cands = [d for d in configs_dir.iterdir() if (d / "bare" / "rung.env").is_file()] if configs_dir.is_dir() else []
    if not cands:
        raise JudgeError(f"no built bare layer under {configs_dir}")
    return max(cands, key=lambda d: d.stat().st_mtime).name


def judge_env(configs_dir: Path, os_sha: str, cfg_dir: Path) -> dict:
    """Env of a bare-layer run (isolated HOME, token via rung.env, per-call config dir): the
    judge never inherits Nate's memory, skills or CLAUDE.md."""
    env_vars, _flags = load_rung(Path(configs_dir), "bare", os_sha)
    build_run_config(rung_dir(Path(configs_dir), "bare", os_sha), cfg_dir)
    env = {**scrub_env(dict(os.environ), set(env_vars)), **env_vars}
    env["CLAUDE_CONFIG_DIR"] = str(cfg_dir)
    return env


def parse_judge_output(stdout: str) -> dict:
    """{score, rationale, cost_usd}: structured_output first, then the last JSON object in
    `result` that carries a score, else JudgeError."""
    try:
        env = json.loads(stdout)
    except ValueError:
        raise JudgeError(f"judge output is not JSON: {stdout[:120]!r}")
    if not isinstance(env, dict):
        raise JudgeError("judge output is not a JSON object")
    if env.get("is_error"):
        raise JudgeError(f"judge call errored: {str(env.get('result'))[:200]}")
    obj = env.get("structured_output")
    if not (isinstance(obj, dict) and "score" in obj):
        obj = None
        text = env.get("result") if isinstance(env.get("result"), str) else ""
        dec = json.JSONDecoder()
        for m in re.finditer(r"\{", text):
            try:
                cand, _ = dec.raw_decode(text[m.start():])
            except ValueError:
                continue
            if isinstance(cand, dict) and "score" in cand:
                obj = cand
    if obj is None:
        raise JudgeError("no score in judge output")
    score = obj["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or score != int(score) or not 0 <= score <= 5:
        raise JudgeError(f"score out of range: {score!r}")
    cost = env.get("total_cost_usd")
    return {"score": int(score), "rationale": str(obj.get("rationale", "")),
            "cost_usd": cost if isinstance(cost, (int, float)) else 0.0}


def call_judge(prompt: str, configs_dir: Path, os_sha: str, timeout: int = 300) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="judge-"))
    try:
        env = judge_env(configs_dir, os_sha, tmp / "cfg")
        (tmp / "cwd").mkdir()
        r = subprocess.run(judge_cmd(), input=prompt, capture_output=True, text=True, env=env,
                           cwd=str(tmp / "cwd"), timeout=timeout)
        if not r.stdout.strip():
            raise JudgeError(f"judge produced no output (rc={r.returncode}): {r.stderr[:200]}")
        return parse_judge_output(r.stdout)
    except subprocess.TimeoutExpired:
        raise JudgeError(f"judge timed out after {timeout}s")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- leaks, sidecar, skip rules ---

def skill_names(configs_dir: Path, os_sha: str) -> list[str]:
    d = Path(configs_dir) / os_sha / "src" / "skills"
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("_")) if d.is_dir() else []


def leak_terms(rationale: str, skills: list[str]) -> list[str]:
    """Terms in a rationale that hint the judge knew the setup: skill names, CLAUDE.md, 'my memory'.
    Hyphenated skill names match as words; plain-word names (quote, map, ...) only as `/name` or
    next to the word 'skill', since they are ordinary English otherwise."""
    # ponytail: substring heuristic for plain-word skill names — upgrade when the leak count shows false negatives
    low = rationale.lower()
    hits = []
    for s in skills:
        n = re.escape(s.lower())
        pat = rf"(?<![\w-]){n}(?![\w-])" if "-" in s else rf"/{n}\b|\b{n} skill\b|\bskill {n}\b"
        if re.search(pat, low):
            hits.append(s)
    for term in ("claude.md", "my memory"):
        if term in low:
            hits.append(term)
    return hits


def sidecar_path(run_file: Path) -> Path:
    return Path(run_file).with_name(Path(run_file).stem + ".judge.jsonl")


def read_sidecar(path: Path) -> list[dict]:
    out = []
    if Path(path).is_file():
        for ln in Path(path).read_text().splitlines():
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if isinstance(e, dict):
                out.append(e)
    return out


def skip_reason(transcript: dict, task_dir: Path, sidecar: list[dict]):
    """Why this run is not judged (None = judge it)."""
    meta = transcript.get("_meta") or {}
    if transcript.get("is_error") or not str(transcript.get("result") or "").strip():
        return "no result"
    if meta.get("contaminated"):
        return "contaminated"
    sha = rubric_sha(task_dir)
    if sha is None:
        return "no rubric"
    if read_judge_meta(task_dir)["judge_files"] and not Path(meta.get("workspace_dir") or "/nonexistent").is_dir():
        return "workspace gone"   # nothing to grade: an empty artifact would score as a fail
    if any(e.get("rubric_sha") == sha and e.get("model") == JUDGE_MODEL and e.get("effort") == JUDGE_EFFORT
           for e in sidecar):
        return "already judged"
    return None


def judge_run(run_file: Path, tasks_dir: Path, configs_dir: Path, os_sha: str = "", force: bool = False):
    """Judge one run; append to its sidecar. Returns the entry, or a str skip reason."""
    run_file = Path(run_file)
    t = json.loads(run_file.read_text())
    meta = t.get("_meta") or {}
    task_dir = Path(tasks_dir) / meta.get("task", "")
    side = sidecar_path(run_file)
    why = skip_reason(t, task_dir, [] if force else read_sidecar(side))
    if why:
        return why
    sha = latest_sha(configs_dir, os_sha or meta.get("os_sha", ""))
    art, truncated = artifact_text(run_file, tasks_dir)
    res = call_judge(build_judge_prompt((task_dir / "rubric.md").read_text(), art), configs_dir, sha)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "rubric_sha": rubric_sha(task_dir),
             "model": JUDGE_MODEL, "effort": JUDGE_EFFORT, "score": res["score"],
             "rationale": res["rationale"], "leak": leak_terms(res["rationale"], skill_names(configs_dir, sha)),
             "truncated": truncated, "cost_usd": res["cost_usd"]}
    with open(side, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def judge_runs(runs_dir: Path, tasks_dir: Path, configs_dir: Path, os_sha: str = "", jobs: int = 4,
               force: bool = False) -> int:
    files = sorted(f for f in Path(runs_dir).glob("*.json") if ".judge." not in f.name)
    items = [{"label_id": f.name, "multi_turn": False, "file": f} for f in files]
    results, failures = execute_items(
        items, lambda i: (i["label_id"], judge_run(i["file"], tasks_dir, configs_dir, os_sha, force)), jobs)
    judged = [r for r in results if isinstance(r[1], dict)]
    skipped: dict = {}
    for _, r in results:
        if isinstance(r, str):
            skipped[r] = skipped.get(r, 0) + 1
    cost = sum(r["cost_usd"] for _, r in judged)
    print(f"judge: judged={len(judged)} skipped={skipped} errors={failures} cost=${cost:.4f}", flush=True)
    return 1 if failures else 0


# --- fixture validation ---

def validate_task(task: str, tasks_dir: Path, configs_dir: Path, os_sha: str = "") -> int:
    """Judge tests/good (want >= 4) and tests/bad (want <= 2). No sidecars are written."""
    task_dir = Path(tasks_dir) / task
    rubric = task_dir / "rubric.md"
    if not rubric.is_file():
        print(f"validate {task}: no rubric.md", file=sys.stderr)
        return 2
    sha = latest_sha(configs_dir, os_sha)
    jm = read_judge_meta(task_dir)
    scores, cost = {}, 0.0
    for side in ("good", "bad"):
        d = task_dir / "tests" / side
        tj = d / "transcript.json"
        result = ""
        if tj.is_file():
            try:
                result = str(json.loads(tj.read_text()).get("result") or "")
            except ValueError:
                pass
        art, _ = build_artifact(result, jm["judge_files"], d, task_dir / "seed")
        res = call_judge(build_judge_prompt(rubric.read_text(), art), configs_dir, sha)
        scores[side], cost = res["score"], cost + res["cost_usd"]
        print(f"  {side}: score={res['score']}  {res['rationale'][:160]}")
    ok = scores["good"] >= 4 and scores["bad"] <= 2
    print(f"{'OK' if ok else 'MISMATCH'}: {task} good={scores['good']} (want >=4) bad={scores['bad']} "
          f"(want <=2) cost=${cost:.4f}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    ap.add_argument("--tasks-dir", default=str(REPO_ROOT / "tasks"))
    ap.add_argument("--configs-dir", default=str(REPO_ROOT / "configs"))
    ap.add_argument("--os-sha", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="re-judge even when the sidecar has a matching entry")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--task", default="")
    a = ap.parse_args()
    try:
        if a.validate:
            if not a.task:
                ap.error("--validate needs --task <category/name>")
            return validate_task(a.task, Path(a.tasks_dir), Path(a.configs_dir), a.os_sha)
        return judge_runs(Path(a.runs_dir), Path(a.tasks_dir), Path(a.configs_dir), a.os_sha, a.jobs, a.force)
    except JudgeError as e:
        print(f"judge: ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
