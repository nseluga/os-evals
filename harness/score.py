#!/usr/bin/env python3
"""
harness/score.py

Runs each task's check.sh + parses transcript stats + tokens.

Contract for transcript JSON (from `claude -p --output-format json`):
  result          — final text output
  is_error        — bool
  usage.input_tokens / cache_read_input_tokens / cache_creation_input_tokens
  usage.output_tokens
  num_turns       — turn count
  total_cost_usd  — dollar cost
  usage.iterations — list of per-turn stats (may be empty)
  _meta.task / _meta.rung / _meta.model — injected by run_matrix.py
  _meta.contaminated — true => not scored (infra_reason "contaminated")

Outputs:
  JSON scores object to stdout
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Recompute rate_limited from the transcript itself (rather than trusting the stamped
# _meta.rate_limited flag) so a re-score always reflects run_matrix's current detector.
# _meta.rate_limited is used only as a fallback if run_matrix can't be imported.
try:
    from run_matrix import looks_like_rate_limit
except ImportError:
    looks_like_rate_limit = None


def _num(v, default=0):
    """Numeric field or default: null / missing / non-numeric never raises."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def extract_stats(transcript: dict) -> dict:
    """Pull process stats from a transcript JSON. Null or missing fields count as 0."""
    usage = _dict(transcript.get("usage"))
    input_tok = _num(usage.get("input_tokens"))
    cache_read = _num(usage.get("cache_read_input_tokens"))
    cache_create = _num(usage.get("cache_creation_input_tokens"))
    output_tok = _num(usage.get("output_tokens"))
    total_input = input_tok + cache_read + cache_create

    return {
        "turns": _num(transcript.get("num_turns")),
        "input_tokens": input_tok,
        "cache_read_tokens": cache_read,
        "cache_create_tokens": cache_create,
        "total_input_tokens": total_input,
        "output_tokens": output_tok,
        "total_tokens": total_input + output_tok,
        "cost_usd": _num(transcript.get("total_cost_usd")),
        "is_error": bool(transcript.get("is_error", False)),
        "stop_reason": transcript.get("stop_reason") or "",
    }


_API_ERROR_RE = re.compile(
    r"overloaded|api_error|connection (?:reset|refused|error)|econnreset|econnrefused"
    r"|network error|(?:api error|http|status(?: code)?|error)[^\n]{0,20}\b5\d\d\b"
    r"|\b5\d\d\b[^\n]{0,20}(?:error|overloaded|unavailable|bad gateway|gateway time|internal server)",
    re.IGNORECASE,
)


def _error_text(transcript: dict) -> str:
    parts = [str(transcript.get("result") or "")]
    err = transcript.get("error")
    if err:
        parts.append(json.dumps(err) if isinstance(err, (dict, list)) else str(err))
    sub = transcript.get("subtype")
    if isinstance(sub, str):
        parts.append(sub)
    return "\n".join(parts)


def is_budget_stop(transcript: dict) -> bool:
    """CLI stopped on --max-budget-usd. Shape is a GUESS (no stored example in runs/):
    is_error plus subtype or result text containing 'budget'."""
    if not transcript.get("is_error"):
        return False
    sub = transcript.get("subtype")
    return "budget" in (sub if isinstance(sub, str) else "").lower() or \
        "budget" in str(transcript.get("result") or "").lower()


def classify_infra(transcript: dict) -> str | None:
    """Infra reason for failures that say nothing about the task, else None.

    timeout: _meta.timed_out and no genuine terminal result (a real CLI result event carries
    a subtype; the synthesized stand-in does not). Timeouts were already retried once.
    no_result: stream ended with no final result event and no timeout.
    api_error: is_error AND the error text shows an API/transport failure. A model answer
    that merely mentions 503 with is_error false is NOT infra; a budget stop is not infra.
    (rate_limited / auth_error / contaminated are handled separately in score_run.)"""
    t = _dict(transcript)
    meta = _dict(t.get("_meta"))
    if meta.get("timed_out") and not t.get("subtype"):
        return "timeout"
    if meta.get("no_result"):
        return "no_result"
    if not t.get("is_error") or is_budget_stop(t):
        return None
    status = t.get("api_error_status")
    if isinstance(status, int) and 500 <= status <= 599:
        return "api_error"
    if isinstance(status, str) and re.fullmatch(r"5\d\d", status):
        return "api_error"
    return "api_error" if _API_ERROR_RE.search(_error_text(t)) else None


def run_check(
    task: str, transcript_text: str, tasks_dir: Path, workspace_dir: str = ""
) -> tuple[bool, str, int]:
    """Run tasks/{task}/check.sh with transcript on stdin. Returns (passed, output).

    For coding tasks, workspace_dir (from transcript _meta) is passed as WORKSPACE_DIR
    so filesystem/test-based checks can inspect what the model wrote. Text-only checks
    ignore it (they read only stdin), keeping the original contract a strict subset."""
    check_sh = tasks_dir / task / "check.sh"
    if not check_sh.exists():
        return False, f"check.sh not found: {check_sh}", 2

    env = {**os.environ}
    if workspace_dir:
        env["WORKSPACE_DIR"] = workspace_dir

    result = subprocess.run(
        [str(check_sh)],
        input=transcript_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    output = (result.stdout + result.stderr).strip()
    # rc convention: 0 = pass, 1 = real task failure, 2 = infra/unscoreable (e.g. the
    # workspace was not retained). Callers use rc to avoid counting an infra error as a
    # genuine failure.
    return result.returncode == 0, output, result.returncode


def read_task_meta(tasks_dir: Path, task: str) -> dict:
    """Pull curated_skill + category from a task's meta.yaml (best-effort, no yaml dep)."""
    meta_file = tasks_dir / task / "meta.yaml"
    out = {"curated_skill": "", "category": "", "contaminated": False, "group": "", "sentinel": False}
    if not meta_file.exists():
        return out
    for line in meta_file.read_text().splitlines():
        if line[:1] in (" ", "\t"):
            continue
        s = line.strip()
        for key in ("curated_skill", "category", "group"):
            if s.startswith(f"{key}:"):
                val = s.split(":", 1)[1].strip()
                # first token, strip any trailing parenthetical note
                out[key] = val.split("(")[0].split("#")[0].strip()
        if s.startswith("contaminated:"):
            out["contaminated"] = s.split(":", 1)[1].strip().lower().startswith("true")
        if s.startswith("sentinel:"):
            out["sentinel"] = s.split(":", 1)[1].strip().lower().startswith("true")
    return out


def score_run(run_file: Path, tasks_dir: Path) -> dict:
    """Score one transcript file. Returns a score record."""
    transcript_text = run_file.read_text()
    transcript = json.loads(transcript_text)

    if not isinstance(transcript, dict):
        raise ValueError(f"transcript is {type(transcript).__name__}, not an object")
    meta = _dict(transcript.get("_meta"))
    task = meta.get("task") or run_file.stem.split("_")[1]
    rung = meta.get("rung", 0)
    model = meta.get("model", "unknown")
    snippet = str(transcript.get("result") or "")[:200]

    stats = extract_stats(transcript)
    workspace_dir = meta.get("workspace_dir", "")
    task_meta = read_task_meta(tasks_dir, task)

    # Skill-activation instrumentation (multi-turn runs). skill_fired is:
    #   True  — the intended skill actually fired
    #   False — a ROUTING failure: the skill never triggered, so this run is NOT
    #           evidence about the skill's value (must be distinguishable, not silently
    #           counted as a skill failure)
    #   None  — not applicable (one-shot task, or no intended skill to check)
    skill_fired = meta.get("skill_fired")
    multi_turn = meta.get("multi_turn", False)
    timed_out = meta.get("timed_out", False)

    # Detect if this is a repeat run (either via _meta or filename suffix _r{N})
    repeat_index = meta.get("repeat_index")
    repeat_total = meta.get("repeat_total")
    if repeat_index is None:
        m = re.search(r"_r(\d+)\.json$", run_file.name)
        if m:
            repeat_index = int(m.group(1))
    is_repeat_individual = repeat_index is not None

    base = {
        "file": run_file.name,
        "task": task,
        "rung": rung,
        "model": model,
        "curated_skill": task_meta["curated_skill"],
        "category": task_meta["category"],
        "contaminated": task_meta["contaminated"],
        "group": task_meta["group"],
        "sentinel": task_meta["sentinel"],
        "wall_clock_sec": meta.get("elapsed_sec", 0),
        "multi_turn": multi_turn,
        "timed_out": timed_out,
        "skill_fired": skill_fired,
        "budget_exceeded": is_budget_stop(transcript),
        "is_repeat_individual": is_repeat_individual,
        "repeat_index": repeat_index,
        "repeat_total": repeat_total,
        **stats,
    }

    # A run whose tool calls reached outside its workspace (task files, live ~/os, the
    # origin repo) is contaminated: it is neither a model failure nor an infra failure.
    # It is reported as infra_error with infra_reason "contaminated" ONLY so the existing
    # infra exclusion applies; check.sh is not run, and the scorecard names it separately.
    if meta.get("contaminated"):
        hits = meta.get("contamination_hits") or []
        return {
            **base,
            "passed": False,
            "check_rc": 2,
            "infra_error": True,
            "infra_reason": "contaminated",
            "contamination_hits": hits,
            "check_output": f"contaminated: tool call reached outside workspace: {hits[:1]}",
            "result_snippet": snippet,
        }

    # Auth/OAuth-expiry or 429 rate-limit detected mid-run is infra, not a task failure.
    # Map both to check_rc==2 (unscoreable) WITHOUT running check.sh — neither tells us
    # anything about the task. Rate-limit is checked first; auth takes precedence if both.
    rate_limited = (
        looks_like_rate_limit("", "", transcript)
        if looks_like_rate_limit is not None
        else meta.get("rate_limited", False)  # fallback if run_matrix couldn't be imported
    )
    auth_error = meta.get("auth_error", False)
    if rate_limited and not auth_error:
        infra_reason = "rate_limited"
        infra_label = "rate-limit (429) detected mid-run — infra, not a task fail"
    elif auth_error:
        infra_reason = "auth_error"
        infra_label = "auth/OAuth error detected mid-run (see _meta.stderr)"
    else:
        infra_reason = None
        infra_label = None

    if infra_label:
        return {
            **base,
            "passed": False,
            "check_rc": 2,
            "infra_error": True,
            "infra_reason": infra_reason,
            "check_output": infra_label,
            "result_snippet": snippet,
        }

    infra_reason = classify_infra(transcript)
    if infra_reason:
        return {
            **base,
            "passed": False,
            "check_rc": 2,
            "infra_error": True,
            "infra_reason": infra_reason,
            "check_output": f"{infra_reason}: {_error_text(transcript)[:200] or 'stream ended without a result event'}",
            "result_snippet": snippet,
        }

    # If the task has a check.sh but the workspace it needs to inspect is gone (never
    # retained / already cleaned up), there is nothing to check — infra, not a task fail.
    check_sh = tasks_dir / task / "check.sh"
    if check_sh.exists() and workspace_dir and not Path(workspace_dir).exists():
        return {
            **base,
            "passed": False,
            "check_rc": 2,
            "infra_error": True,
            "infra_reason": "workspace_missing",
            "check_output": f"workspace_dir not found on disk: {workspace_dir}",
            "result_snippet": snippet,
        }

    unrunnable = None
    try:
        passed, check_output, check_rc = run_check(task, transcript_text, tasks_dir, workspace_dir)
    except subprocess.TimeoutExpired:
        passed, check_output, check_rc, unrunnable = False, "check.sh timed out", 2, "check_timeout"
    except OSError as e:  # FileNotFoundError, PermissionError, bad interpreter, ...
        passed, check_output, check_rc, unrunnable = False, f"check.sh could not launch: {e!r}", 2, "check_unrunnable"
    if check_rc in (126, 127):  # not executable / interpreter missing
        unrunnable = "check_unrunnable"
        check_rc = 2

    infra_reason = unrunnable or ("check_exit_2" if check_rc == 2 else None)
    return {
        **base,
        "passed": passed and not infra_reason,
        "check_rc": check_rc,
        "infra_error": infra_reason is not None,
        "infra_reason": infra_reason,
        "check_output": check_output,
        "result_snippet": snippet,
    }


def _meta_from_filename(name: str) -> dict:
    """Best-effort task/rung/model/repeat from `<ts>_<task>_<rung>_<model>[_rN].json`."""
    stem = re.sub(r"\.json$", "", name)
    rep = re.search(r"_r(\d+)$", stem)
    if rep:
        stem = stem[: rep.start()]
    parts = stem.split("_")
    task = parts[1] if len(parts) > 1 else stem
    rung = parts[2] if len(parts) > 2 else "unknown"
    m = re.fullmatch(r"rung(\d+)", rung)
    if m:
        rung = int(m.group(1))
    return {"task": task, "rung": rung, "model": "_".join(parts[3:]) or "unknown",
            "repeat_index": int(rep.group(1)) if rep else None}


def exception_record(run_file: Path, tasks_dir: Path, exc: Exception) -> dict:
    """Record for a run whose scoring raised: excluded and named, never dropped."""
    fn = _meta_from_filename(run_file.name)
    meta = {}
    try:
        meta = _dict(_dict(json.loads(run_file.read_text())).get("_meta"))
    except Exception:
        pass
    task = meta.get("task") or fn["task"]
    try:
        tm = read_task_meta(tasks_dir, task)
    except Exception:
        tm = {"curated_skill": "", "category": "", "contaminated": False, "group": "", "sentinel": False}
    ri = meta.get("repeat_index") if meta.get("repeat_index") is not None else fn["repeat_index"]
    return {
        "file": run_file.name, "task": task,
        "rung": meta.get("rung") if meta.get("rung") is not None else fn["rung"],
        "model": meta.get("model") or fn["model"],
        "curated_skill": tm["curated_skill"], "category": tm["category"],
        "contaminated": tm["contaminated"], "group": tm["group"], "sentinel": tm["sentinel"],
        "is_repeat_individual": ri is not None, "repeat_index": ri,
        "repeat_total": meta.get("repeat_total"),
        "total_tokens": 0, "cost_usd": 0, "turns": 0, "passed": False, "check_rc": 2,
        "infra_error": True, "infra_reason": "score_exception",
        "check_output": f"{type(exc).__name__}: {exc}",
        "result_snippet": "",
    }


def compute_majority_records(scores: list[dict]) -> list[dict]:
    """Emit majority-vote synthetic records for repeat: N task groups.

    Votes over non-infra repeats only — an infra run (rate limit, auth error, missing
    workspace, check.sh rc 2) tells us nothing about the task, so it must not count as
    a fail. A group is only infra if EVERY repeat in it is infra; otherwise the vote is
    majority-pass/fail among the valid (non-infra) repeats. `valid_repeats` and
    `infra_repeats` record the split so a scorecard can show what the vote was actually
    over.
    """
    repeat_groups: dict[tuple, list[dict]] = {}
    for rec in scores:
        if rec.get("is_repeat_individual"):
            key = (rec["task"], rec["rung"], rec.get("model", ""))
            repeat_groups.setdefault(key, []).append(rec)

    majority_records = []
    for (task, rung, model), group in repeat_groups.items():
        n = len(group)
        template = group[0]
        declared_total = template.get("repeat_total") or n
        # Do not emit majority until all expected repeats are present.
        if n < declared_total:
            continue

        valid_members = [r for r in group if not r.get("infra_error")]
        infra_members = [r for r in group if r.get("infra_error")]
        valid_repeats = len(valid_members)
        infra_repeats = len(infra_members)
        total_cost = sum(r.get("cost_usd") or 0 for r in group)
        total_tokens = sum(r.get("total_tokens") or 0 for r in group)
        new_file = f"[majority:{n}] " + re.sub(r"_r\d+\.json$", ".json", template["file"])

        if valid_repeats == 0:
            # Every repeat was infra: the group itself is infra, no vote to take.
            majority_passed = False
            pass_count = 0
            check_output = f"0/{n} valid ({n} infra)"
            check_rc = 2
            group_infra = True
            group_infra_reason = template.get("infra_reason") or "all_repeats_infra"
        else:
            pass_count = sum(1 for r in valid_members if r["passed"])
            check_output = f"{pass_count}/{valid_repeats} passed"
            if infra_repeats:
                check_output += f" ({infra_repeats} infra excluded)"
            if pass_count * 2 == valid_repeats:
                # Tie among valid repeats (only possible after infra dropouts). Formerly
                # ceil(valid/2) counted a tie as PASS. Now excluded and named.
                majority_passed = False
                check_rc = 2
                group_infra = True
                group_infra_reason = "no_majority"
                check_output += " (tie, no majority)"
            else:
                majority_passed = pass_count * 2 > valid_repeats
                check_rc = 0 if majority_passed else 1
                group_infra = False
                group_infra_reason = None

        majority_record = {
            **template,
            "file": new_file,
            "passed": majority_passed,
            "cost_usd": total_cost,
            "total_tokens": total_tokens,
            "is_repeat_individual": False,
            "repeat_majority": True,
            "repeat_pass_count": pass_count,
            "valid_repeats": valid_repeats,
            "infra_repeats": infra_repeats,
            "check_output": check_output,
            "check_rc": check_rc,
            "infra_error": group_infra,
            "infra_reason": group_infra_reason,
            "repeat_total": declared_total,
            "repeat_index": None,
        }
        majority_records.append(majority_record)
        tag = "INFRA" if group_infra else ("PASS" if majority_passed else "FAIL")
        print(
            f"  MAJORITY({tag}) rung{rung} {task} "
            f"({pass_count}/{valid_repeats} valid, {infra_repeats} infra, ${total_cost:.4f} total)",
            file=sys.stderr,
        )

    return majority_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    parser.add_argument("--tasks-dir", default=str(REPO_ROOT / "tasks"))
    parser.add_argument("--os-sha", default="")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    tasks_dir = Path(args.tasks_dir)

    run_files = sorted(runs_dir.glob("*.json"))
    if not run_files:
        print("score.py: no run files found", file=sys.stderr)
        return 1

    scores = []
    scored_run_ids = []
    for f in run_files:
        try:
            record = score_run(f, tasks_dir)
        except Exception as e:
            print(f"  ERROR scoring {f.name}: {e}", file=sys.stderr)
            record = exception_record(f, tasks_dir, e)
        scores.append(record)
        scored_run_ids.append(f.name)
        status = "INFRA" if record.get("infra_error") else ("PASS" if record["passed"] else "FAIL")
        repeat_tag = f" [r{record['repeat_index']}]" if record.get("repeat_index") else ""
        print(
            f"  {status}{repeat_tag} rung{record['rung']} {record['task']} "
            f"({record['total_tokens']} tok, ${record['cost_usd']:.4f})",
            file=sys.stderr,
        )

    majority_records = compute_majority_records(scores)
    all_scores = scores + majority_records

    output = {
        "os_sha": args.os_sha,
        "run_count": len(all_scores),
        "scored_run_ids": scored_run_ids,
        "scores": all_scores,
    }
    print(json.dumps(output, indent=2))

    infra_reasons = Counter(
        s["infra_reason"] for s in all_scores if s.get("infra_error") and s.get("infra_reason")
    )
    if infra_reasons:
        summary = " ".join(f"{reason}={n}" for reason, n in sorted(infra_reasons.items()))
        print(f"score.py: infra summary: {summary}", file=sys.stderr)
    if infra_reasons.get("workspace_missing") or infra_reasons.get("score_exception"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
