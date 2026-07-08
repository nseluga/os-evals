#!/usr/bin/env python3
"""
harness/run_matrix.py

Loops task x rung x model -> claude -p -> saves transcript JSON.

Contract:
  Each run invokes: claude -p <flags> --output-format json < prompt.md
  Env vars and flags come from configs/rung{N}/rung.env and rung.flags.
  Transcript JSON is saved to runs/{timestamp}_{task}_{rung}_{model}.json.

Inputs:
  --tasks  comma-separated task names under tasks/ (default: all non-_ dirs)
  --rungs  comma-separated rung numbers (default: 1,2,3,4)
  --models comma-separated model IDs (default: claude-sonnet-4-6)
  --config-dir path to configs/ (default: <repo>/configs)
  --tasks-dir  path to tasks/ (default: <repo>/tasks)
  --runs-dir   path to runs/ (default: <repo>/runs)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def find_tasks(tasks_dir: Path) -> list[str]:
    return sorted(
        d.name for d in tasks_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def load_rung(configs_dir: Path, rung: int) -> tuple[dict[str, str], list[str]]:
    """Returns (env_vars, extra_flags) for the rung."""
    rung_dir = configs_dir / f"rung{rung}"
    env_file = rung_dir / "rung.env"
    flags_file = rung_dir / "rung.flags"

    env_vars: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()

    flags: list[str] = []
    if flags_file.exists():
        for line in flags_file.read_text().splitlines():
            line = line.strip()
            if line:
                flags.extend(line.split())

    return env_vars, flags


def run_one(
    task: str,
    rung: int,
    model: str,
    tasks_dir: Path,
    configs_dir: Path,
    runs_dir: Path,
) -> Path:
    """Run claude -p for one task/rung/model combo. Returns path to saved transcript."""
    prompt_file = tasks_dir / task / "prompt.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt.md not found: {prompt_file}")

    env_vars, extra_flags = load_rung(configs_dir, rung)

    cmd = ["claude", "-p", "--output-format", "json", "--model", model]
    cmd.extend(extra_flags)
    cmd.extend(["--dangerously-skip-permissions"])

    env = {**os.environ, **env_vars}

    print(f"  running: rung{rung} task={task} model={model}", flush=True)
    print(f"    flags: {extra_flags}", flush=True)
    print(f"    env overrides: {list(env_vars.keys())}", flush=True)

    with open(prompt_file) as f:
        prompt_text = f.read()

    result = subprocess.run(
        cmd,
        input=prompt_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    # Parse and enrich transcript
    try:
        transcript = json.loads(result.stdout)
    except json.JSONDecodeError:
        transcript = {
            "type": "result",
            "is_error": True,
            "result": result.stdout or result.stderr,
            "raw_stdout": result.stdout,
            "raw_stderr": result.stderr,
        }

    transcript["_meta"] = {
        "task": task,
        "rung": rung,
        "model": model,
        "returncode": result.returncode,
        "stderr": result.stderr[:2000] if result.stderr else "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = runs_dir / f"{ts}_{task}_rung{rung}_{model.replace('-', '_')}.json"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(transcript, indent=2))
    print(f"    saved: {out_file.name}", flush=True)
    return out_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="")
    parser.add_argument("--rungs", default="1,2,3,4")
    parser.add_argument("--models", default="claude-sonnet-4-6")
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "configs"))
    parser.add_argument("--tasks-dir", default=str(REPO_ROOT / "tasks"))
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    args = parser.parse_args()

    tasks_dir = Path(args.tasks_dir)
    configs_dir = Path(args.config_dir)
    runs_dir = Path(args.runs_dir)

    tasks = args.tasks.split(",") if args.tasks else find_tasks(tasks_dir)
    rungs = [int(r) for r in args.rungs.split(",")]
    models = args.models.split(",")

    tasks = [t for t in tasks if t]

    print(f"run_matrix: tasks={tasks} rungs={rungs} models={models}")

    failures = 0
    for task in tasks:
        for rung in rungs:
            for model in models:
                try:
                    run_one(task, rung, model, tasks_dir, configs_dir, runs_dir)
                except Exception as e:
                    print(f"  ERROR: {task}/rung{rung}/{model}: {e}", file=sys.stderr)
                    failures += 1

    print(f"run_matrix: done. failures={failures}")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
