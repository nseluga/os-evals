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
import time
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
    """Materialize a task's frozen workspace into dest.

    Two additive, composable sources (a task may use either or both):
      1. Git ref — if workspace.ref names an `origin:` (abs path to a local git repo)
         and a `sha:` (base ref), does `git archive <sha> | tar -x` into dest.
      2. Seed overlay — if the task ships a `seed/` dir, its contents are copied into
         dest (over the git tree if both are present). This lets self-contained
         analysis/writing tasks ship their own fixture files without a throwaway
         commit in a real repo.
    node_modules / venvs are intentionally NOT archived — provision them via setup.sh."""
    import shutil

    ref = task_dir / "workspace.ref"
    origin = sha = None
    if ref.exists():
        for line in ref.read_text().splitlines():
            s = line.strip()
            if origin is None and s.startswith("origin:"):
                origin = s.split(":", 1)[1].strip()
            elif sha is None and s.startswith("sha:"):
                sha = s.split(":", 1)[1].split("#", 1)[0].strip()

    seed = task_dir / "seed"
    if not (origin and sha) and not seed.is_dir():
        raise ValueError(f"workspace.ref names no origin/sha and no seed/ dir: {task_dir}")

    dest.mkdir(parents=True, exist_ok=True)

    if origin and sha:
        archive = subprocess.run(
            ["git", "-C", origin, "archive", "--format=tar", sha],
            capture_output=True, check=True,
        )
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)

    if seed.is_dir():
        for item in seed.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    setup = (task_dir / "setup.sh").resolve()
    if setup.exists():
        print(f"    workspace: running setup.sh in {dest}", flush=True)
        subprocess.run(["bash", str(setup)], cwd=str(dest), check=True, timeout=1200)


def read_task_meta(task_dir: Path) -> dict:
    """Best-effort parse of a task's meta.yaml (no yaml dep).

    Fields consumed by run_matrix:
      timeout_sec  — per-task wall-clock budget (default 300). Multi-turn skills
                     (dev-team / dev-team-auto) set this well above 300.
      multi_turn   — if true, capture the full event stream (stream-json) and give
                     the run a real git repo so orchestrator skills can branch/worktree.
      curated_skill— the skill this task is meant to exercise; used to detect whether
                     that skill actually fired (routing check).
    """
    out = {"timeout_sec": 300, "multi_turn": False, "curated_skill": ""}
    meta_file = task_dir / "meta.yaml"
    if not meta_file.exists():
        return out
    for line in meta_file.read_text().splitlines():
        s = line.strip()
        if s.startswith("timeout_sec:"):
            val = s.split(":", 1)[1].split("#", 1)[0].strip()
            try:
                out["timeout_sec"] = int(val)
            except ValueError:
                pass
        elif s.startswith("multi_turn:"):
            out["multi_turn"] = s.split(":", 1)[1].strip().lower().startswith("true")
        elif s.startswith("curated_skill:"):
            out["curated_skill"] = s.split(":", 1)[1].split("(")[0].split("#")[0].strip()
    return out


def _parse_stream(stdout: str, stderr: str) -> tuple[dict, list[dict]]:
    """Parse newline-delimited stream-json into (final_transcript, events).

    The terminal `{"type":"result",...}` event has the same shape score.py expects
    (result, is_error, num_turns, total_cost_usd, usage). If the run was killed before
    emitting it (timeout / crash), synthesize an error transcript so scoring still runs,
    salvaging any usage seen along the way.
    """
    events: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    result_events = [e for e in events if e.get("type") == "result"]
    if result_events:
        return result_events[-1], events

    # No terminal result: build a stand-in. Salvage the last assistant usage if any.
    last_usage = {}
    for e in events:
        u = e.get("message", {}).get("usage")
        if isinstance(u, dict):
            last_usage = u
    transcript = {
        "type": "result",
        "is_error": True,
        "result": stderr[:2000] or "no terminal result event (run truncated)",
        "usage": last_usage,
        "num_turns": sum(1 for e in events if e.get("type") == "assistant"),
    }
    return transcript, events


def _parse_single(stdout: str, stderr: str) -> dict:
    """Parse a single `--output-format json` result object (one-shot path)."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "type": "result",
            "is_error": True,
            "result": stdout or stderr,
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }


def _iter_tool_uses(events: list[dict]):
    """Yield (name, input_dict) for every tool_use block across assistant events."""
    for e in events:
        content = e.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name", ""), (block.get("input") or {})


def detect_skill_fired(events: list[dict], intended_skill: str):
    """Did the intended skill actually get invoked in this run?

    Returns True/False when there's an intended skill to check, else None (n/a).
    A skill fires via the Skill tool (name=="Skill", input.skill/input.command names it).
    The dev-team orchestrators also manifest by spawning their dt-* specialists as
    Task sub-agents, so a Task whose subagent/description names the skill counts too.
    Distinguishing a routing failure (skill never fired) from a skill failure is the
    whole point of rung 4 — a run where the skill never triggered is not evidence about
    the skill's value.
    """
    if not intended_skill:
        return None
    needle = intended_skill.lower()
    for name, inp in _iter_tool_uses(events):
        if name == "Skill":
            skill = str(inp.get("skill") or inp.get("command") or "").lower()
            if needle in skill:
                return True
        # Direct/slash-command style match on the tool name itself.
        if needle in name.lower():
            return True
        # Orchestrators fan out to dt-* specialists via Task sub-agents.
        if name == "Task":
            blob = f"{inp.get('subagent_type', '')} {inp.get('description', '')}".lower()
            if needle in blob:
                return True
    return False


_AUTH_ERR_PATTERNS = (
    "authentication_error",
    "invalid x-api-key",
    "invalid api key",
    "oauth token",
    "token expired",
    "token has expired",
    "please run /login",
    "unauthorized",
    "401",
)


def looks_like_auth_error(stdout: str, stderr: str, transcript: dict) -> bool:
    """Detect an auth/OAuth-expiry failure so it can be flagged infra (not a task fail).

    A single multi-turn run can approach the ~1hr OAuth token lifetime baked into
    rung.env; if the token expires mid-run the failure is infra, not evidence about
    the skill. score.py maps this to the check_rc==2 (unscoreable) convention.
    """
    hay = f"{stderr}\n{transcript.get('result', '')}".lower()
    return any(p in hay for p in _AUTH_ERR_PATTERNS)


def _ensure_git_repo(ws_dir: Path) -> None:
    """Make ws_dir a self-contained git repo so orchestrator skills can branch/worktree.

    dev-team-auto runs on its own experimental branch and often in a nested git worktree.
    A git-archive restore produces a tree with no .git, so seed one here. Everything the
    skill creates (branches, .claude/worktrees/*) stays inside ws_dir and is removed
    wholesale by run.sh's `rm -rf runs/*.ws`, so nested worktrees don't leak refs.
    """
    if (ws_dir / ".git").exists():
        return
    ident = ["-c", "user.name=os-evals", "-c", "user.email=evals@localhost"]
    subprocess.run(["git", "init", "-q"], cwd=str(ws_dir), check=True)
    subprocess.run(["git", *ident, "add", "-A"], cwd=str(ws_dir), check=True)
    subprocess.run(
        ["git", *ident, "commit", "-q", "-m", "eval baseline", "--allow-empty"],
        cwd=str(ws_dir), check=True,
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
    task_dir = tasks_dir / task
    prompt_file = task_dir / "prompt.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt.md not found: {prompt_file}")

    env_vars, extra_flags = load_rung(configs_dir, rung)
    task_meta = read_task_meta(task_dir)
    multi_turn = task_meta["multi_turn"]
    timeout_sec = task_meta["timeout_sec"]
    intended_skill = task_meta["curated_skill"]

    # One-shot tasks keep the single-object JSON path (backward compatible with the
    # score.py contract). Multi-turn tasks (dev-team / dev-team-auto) capture the whole
    # turn-by-turn event stream so sub-agent spawns, retries and skill activation are
    # inspectable — then normalize the terminal result event into the same shape.
    if multi_turn:
        out_flags = ["--output-format", "stream-json", "--verbose"]
    else:
        out_flags = ["--output-format", "json"]

    cmd = ["claude", "-p", *out_flags, "--model", model]
    cmd.extend(extra_flags)
    cmd.extend(["--dangerously-skip-permissions"])

    env = {**os.environ, **env_vars}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{_slug(task)}_rung{rung}_{model.replace('-', '_')}"

    # Every run gets its OWN isolated per-run dir as cwd. If the task ships a frozen
    # workspace (workspace.ref and/or seed/), it's restored there so files the model
    # writes are inspectable by check.sh (via WORKSPACE_DIR). If the task has NEITHER,
    # the dir is left empty — a leak guard so text-only analysis/writing tasks never
    # run in (and read from) the eval repo itself.
    runs_dir.mkdir(parents=True, exist_ok=True)
    ws_dir = runs_dir / f"{run_id}.ws"
    has_ref = (task_dir / "workspace.ref").exists()
    has_seed = (task_dir / "seed").is_dir()
    if has_ref or has_seed:
        print(f"    restoring workspace -> {ws_dir}", flush=True)
        restore_workspace(task_dir, ws_dir)
    else:
        ws_dir.mkdir(parents=True, exist_ok=True)

    # Multi-turn orchestrators branch/worktree inside the run workspace — it must be a
    # real git repo. (One-shot tasks are left untouched to preserve existing behavior.)
    if multi_turn:
        _ensure_git_repo(ws_dir)

    cwd = str(ws_dir)

    print(f"  running: rung{rung} task={task} model={model}", flush=True)
    print(f"    flags: {extra_flags}", flush=True)
    print(f"    env overrides: {list(env_vars.keys())}", flush=True)
    print(f"    mode: {'multi-turn' if multi_turn else 'one-shot'} timeout={timeout_sec}s", flush=True)

    with open(prompt_file) as f:
        prompt_text = f.read()

    _t0 = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            input=prompt_text,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=timeout_sec,
        )
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        # Salvage whatever streamed before the kill so a long multi-turn run is still
        # partially inspectable/scoreable rather than a total loss.
        timed_out = True
        stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode() if e.stdout else "")
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else "")
        returncode = -1
        print(f"    TIMEOUT after {timeout_sec}s", flush=True)
    elapsed_sec = round(time.monotonic() - _t0, 1)

    # Normalize both output formats into the single transcript shape score.py expects
    # (result, is_error, usage, num_turns, total_cost_usd).
    events: list[dict] = []
    if multi_turn:
        transcript, events = _parse_stream(stdout, stderr)
    else:
        transcript = _parse_single(stdout, stderr)

    skill_fired = detect_skill_fired(events, intended_skill) if multi_turn else None
    auth_error = looks_like_auth_error(stdout, stderr, transcript)

    transcript["_meta"] = {
        "task": task,
        "rung": rung,
        "model": model,
        "returncode": returncode,
        "stderr": stderr[:2000] if stderr else "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(ws_dir) if ws_dir else "",
        "elapsed_sec": elapsed_sec,
        "multi_turn": multi_turn,
        "timeout_sec": timeout_sec,
        "timed_out": timed_out,
        "intended_skill": intended_skill,
        "skill_fired": skill_fired,
        "auth_error": auth_error,
        "num_events": len(events),
    }

    out_file = runs_dir / f"{run_id}.json"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(transcript, indent=2))
    print(f"    saved: {out_file.name}", flush=True)

    # Persist the full turn-by-turn trace alongside the normalized transcript so the
    # sub-agent spawns / retries are auditable without bloating the scored transcript.
    if multi_turn and events:
        trace_file = runs_dir / f"{run_id}.trace.jsonl"
        trace_file.write_text("\n".join(json.dumps(e) for e in events))
        print(f"    trace: {trace_file.name} ({len(events)} events)", flush=True)

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
