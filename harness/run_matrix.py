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
    """Task ids are paths (relative to tasks_dir) of any dir holding a prompt.md.

    Supports both flat tasks (tasks/print-date) and category-grouped tasks
    (tasks/coding/launchd-service). Any path segment starting with '_' is skipped
    (e.g. tasks/_example)."""
    tasks = []
    for prompt in tasks_dir.rglob("prompt.md"):
        rel = prompt.parent.relative_to(tasks_dir)
        if any(seg.startswith("_") for seg in rel.parts):
            continue
        tasks.append(rel.as_posix())
    return sorted(tasks)


def _slug(task: str) -> str:
    """Filesystem-safe token for a task id (which may contain '/')."""
    return task.replace("/", "-")


def restore_workspace(task_dir: Path, dest: Path) -> None:
    """Materialize a task's frozen workspace into dest, per its workspace.ref.

    Parses the first `origin:` (abs path to a local git repo) and first `sha:`
    (base ref) from workspace.ref and does `git archive <sha> | tar -x`. node_modules
    / venvs are intentionally NOT in the archive — provision them via setup.sh."""
    ref = task_dir / "workspace.ref"
    origin = sha = None
    for line in ref.read_text().splitlines():
        s = line.strip()
        if origin is None and s.startswith("origin:"):
            origin = s.split(":", 1)[1].strip()
        elif sha is None and s.startswith("sha:"):
            sha = s.split(":", 1)[1].split("#", 1)[0].strip()
    if not origin or not sha:
        raise ValueError(f"workspace.ref missing origin/sha: {ref}")

    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", origin, "archive", "--format=tar", sha],
        capture_output=True, check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)

    setup = (task_dir / "setup.sh").resolve()
    if setup.exists():
        print(f"    workspace: running setup.sh in {dest}", flush=True)
        subprocess.run(["bash", str(setup)], cwd=str(dest), check=True, timeout=1200)


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
    task_dir = tasks_dir / task
    prompt_file = task_dir / "prompt.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt.md not found: {prompt_file}")

    env_vars, extra_flags = load_rung(configs_dir, rung)

    cmd = ["claude", "-p", "--output-format", "json", "--model", model]
    cmd.extend(extra_flags)
    cmd.extend(["--dangerously-skip-permissions"])

    env = {**os.environ, **env_vars}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{_slug(task)}_rung{rung}_{model.replace('-', '_')}"

    # If the task ships a frozen workspace, restore it and run claude inside it so
    # the files the model writes are inspectable by check.sh (via WORKSPACE_DIR).
    ws_dir = None
    cwd = None
    if (task_dir / "workspace.ref").exists():
        ws_dir = runs_dir / f"{run_id}.ws"
        runs_dir.mkdir(parents=True, exist_ok=True)
        print(f"    restoring workspace -> {ws_dir}", flush=True)
        restore_workspace(task_dir, ws_dir)
        cwd = str(ws_dir)

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
        cwd=cwd,
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
        "workspace_dir": str(ws_dir) if ws_dir else "",
    }

    out_file = runs_dir / f"{run_id}.json"
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
