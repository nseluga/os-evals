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

Outputs:
  JSON scores object to stdout
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def extract_stats(transcript: dict) -> dict:
    """Pull process stats from a transcript JSON."""
    usage = transcript.get("usage", {})
    input_tok = usage.get("input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    output_tok = usage.get("output_tokens", 0)
    total_input = input_tok + cache_read + cache_create

    return {
        "turns": transcript.get("num_turns", 0),
        "input_tokens": input_tok,
        "cache_read_tokens": cache_read,
        "cache_create_tokens": cache_create,
        "total_input_tokens": total_input,
        "output_tokens": output_tok,
        "total_tokens": total_input + output_tok,
        "cost_usd": transcript.get("total_cost_usd", 0),
        "is_error": transcript.get("is_error", False),
        "stop_reason": transcript.get("stop_reason", ""),
    }


def run_check(
    task: str, transcript_text: str, tasks_dir: Path, workspace_dir: str = ""
) -> tuple[bool, str]:
    """Run tasks/{task}/check.sh with transcript on stdin. Returns (passed, output).

    For coding tasks, workspace_dir (from transcript _meta) is passed as WORKSPACE_DIR
    so filesystem/test-based checks can inspect what the model wrote. Text-only checks
    ignore it (they read only stdin), keeping the original contract a strict subset."""
    check_sh = tasks_dir / task / "check.sh"
    if not check_sh.exists():
        return False, f"check.sh not found: {check_sh}"

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

    meta = transcript.get("_meta", {})
    task = meta.get("task") or run_file.stem.split("_")[1]
    rung = meta.get("rung", 0)
    model = meta.get("model", "unknown")

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

    # Auth/OAuth-expiry or 429 rate-limit detected mid-run is infra, not a task failure.
    # Map both to check_rc==2 (unscoreable) WITHOUT running check.sh — neither tells us
    # anything about the task. Rate-limit is checked first; auth takes precedence if both.
    #
    # For transcripts produced before run_matrix stamped _meta.rate_limited (iter 4 and
    # earlier), fall back to inline detection on the result text so a re-score of existing
    # runs correctly reclassifies the 27 iter-4 Opus 429s as infra.
    _rate_limit_patterns = ("rate limit", "rate_limit", "429", "exceed your account",
                            "overloaded_error", "request rejected")
    _result_lower = transcript.get("result", "").lower()
    rate_limited = (
        meta["rate_limited"]  # new transcripts: trust the stamped flag
        if "rate_limited" in meta
        else any(p in _result_lower for p in _rate_limit_patterns)  # old transcripts: detect inline
    )
    infra_label = (
        "rate-limit (429) detected mid-run — infra, not a task fail"
        if rate_limited and not meta.get("auth_error")
        else "auth/OAuth error detected mid-run (see _meta.stderr)"
        if meta.get("auth_error")
        else None
    )
    if infra_label:
        repeat_index = meta.get("repeat_index")
        repeat_total = meta.get("repeat_total")
        if repeat_index is None:
            m = re.search(r"_r(\d+)\.json$", run_file.name)
            if m:
                repeat_index = int(m.group(1))
        is_repeat_individual = repeat_index is not None
        return {
            "file": run_file.name,
            "task": task,
            "rung": rung,
            "model": model,
            "passed": False,
            "check_rc": 2,
            "infra_error": True,
            "check_output": infra_label,
            "result_snippet": transcript.get("result", "")[:200],
            "curated_skill": task_meta["curated_skill"],
            "category": task_meta["category"],
            "contaminated": task_meta["contaminated"],
            "group": task_meta["group"],
            "sentinel": task_meta["sentinel"],
            "wall_clock_sec": meta.get("elapsed_sec", 0),
            "multi_turn": multi_turn,
            "timed_out": timed_out,
            "skill_fired": skill_fired,
            "is_repeat_individual": is_repeat_individual,
            "repeat_index": repeat_index,
            "repeat_total": repeat_total,
            **stats,
        }

    passed, check_output, check_rc = run_check(task, transcript_text, tasks_dir, workspace_dir)

    # Detect if this is a repeat run (either via _meta or filename suffix _r{N})
    repeat_index = meta.get("repeat_index")
    repeat_total = meta.get("repeat_total")
    if repeat_index is None:
        m = re.search(r"_r(\d+)\.json$", run_file.name)
        if m:
            repeat_index = int(m.group(1))
    is_repeat_individual = repeat_index is not None

    return {
        "file": run_file.name,
        "task": task,
        "rung": rung,
        "model": model,
        "passed": passed,
        "check_rc": check_rc,
        "infra_error": check_rc == 2,
        "check_output": check_output,
        "result_snippet": transcript.get("result", "")[:200],
        "curated_skill": task_meta["curated_skill"],
        "category": task_meta["category"],
        "contaminated": task_meta["contaminated"],
        "group": task_meta["group"],
        "sentinel": task_meta["sentinel"],
        "wall_clock_sec": meta.get("elapsed_sec", 0),
        "multi_turn": multi_turn,
        "timed_out": timed_out,
        "skill_fired": skill_fired,
        "is_repeat_individual": is_repeat_individual,
        "repeat_index": repeat_index,
        "repeat_total": repeat_total,
        **stats,
    }


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
    for f in run_files:
        try:
            record = score_run(f, tasks_dir)
            scores.append(record)
            status = "PASS" if record["passed"] else "FAIL"
            repeat_tag = f" [r{record['repeat_index']}]" if record.get("repeat_index") else ""
            print(
                f"  {status}{repeat_tag} rung{record['rung']} {record['task']} "
                f"({record['total_tokens']} tok, ${record['cost_usd']:.4f})",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"  ERROR scoring {f.name}: {e}", file=sys.stderr)

    # Post-process: emit majority-vote synthetic records for repeated tasks.
    # Group individual repeat records by (task, rung, model).
    repeat_groups: dict[tuple, list[dict]] = {}
    for rec in scores:
        if rec.get("is_repeat_individual"):
            key = (rec["task"], rec["rung"], rec.get("model", ""))
            repeat_groups.setdefault(key, []).append(rec)

    majority_records = []
    for (task, rung, model), group in repeat_groups.items():
        n = len(group)
        # Use the first record as a template for non-aggregated fields.
        template = group[0]
        declared_total = template.get("repeat_total") or n
        # Do not emit majority until all expected repeats are present.
        if n < declared_total:
            continue
        pass_count = sum(1 for r in group if r["passed"])
        majority_passed = pass_count >= math.ceil(n / 2)
        total_cost = sum(r.get("cost_usd") or 0 for r in group)
        total_tokens = sum(r.get("total_tokens") or 0 for r in group)
        majority_record = {
            **template,
            "file": f"[majority:{n}] " + re.sub(r"_r\d+\.json$", ".json", template["file"]),
            "passed": majority_passed,
            "cost_usd": total_cost,
            "total_tokens": total_tokens,
            "is_repeat_individual": False,
            "repeat_majority": True,
            "repeat_pass_count": pass_count,
            "check_output": f"{pass_count}/{n} passed",
            "check_rc": 0 if majority_passed else 1,
            "repeat_total": declared_total,
            "repeat_index": None,
        }
        majority_records.append(majority_record)
        print(
            f"  MAJORITY({'PASS' if majority_passed else 'FAIL'}) rung{rung} {task} "
            f"({pass_count}/{n} passed, ${total_cost:.4f} total)",
            file=sys.stderr,
        )

    all_scores = scores + majority_records

    output = {
        "os_sha": args.os_sha,
        "run_count": len(all_scores),
        "scores": all_scores,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
