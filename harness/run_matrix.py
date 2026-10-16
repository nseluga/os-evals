#!/usr/bin/env python3
"""
harness/run_matrix.py

Loops task x layer x os-sha x model -> claude -p -> saves transcript JSON + tool trace.

Contract:
  Each run invokes: claude -p <flags> --output-format stream-json --verbose < prompt.md
  and saves runs/<id>.trace.jsonl (every event) beside runs/<id>.json (the result event).
  Env vars and flags come from configs/<sha>/<layer>/rung.env and rung.flags.
  Transcript JSON is saved to runs/{timestamp}_{task}_{rung}_{model}.json, where the
  `rung` label is the layer name (one --os-sha) or `layer@sha` (several, A/B mode).

Inputs:
  --tasks  comma-separated task names under tasks/ (default: all non-_ dirs)
  --layers comma-separated layers (default: bare,full)
  --os-sha os sha built by build_configs.sh (repeatable; default: the only dir in configs/)
  --models comma-separated model IDs or aliases (default: opus)
  --max-budget-usd per-run spend cap passed to the CLI (default: 1.50)
  --dry-run print the matrix + command per layer (token redacted) and exit; runs nothing
  --config-dir path to configs/ (default: <repo>/configs)
  --tasks-dir  path to tasks/ (default: <repo>/tasks)
  --runs-dir   path to runs/ (default: <repo>/runs)
  --jobs N     run one-shot tasks in a pool of N threads (default 1); multi-turn tasks
               always run serially after the pool. N=1 keeps the plain serial order.
  --ws-root    dir that holds the per-run dirs (default: env EVAL_WS_ROOT, else
               /Users/Shared/evalws: outside the repo and $HOME, so the model cannot walk up
               to tasks/ or an ancestor .claude/). Each run gets an opaque
               w-<10 hex of sha1(run id)>/ holding w/ (the cwd, = WORKSPACE_DIR) and cfg/ (its
               own CLAUDE_CONFIG_DIR, a clean copy of the layer template: no other run's
               transcripts or state). Transcripts stay in --runs-dir.
  --repeat N   run every task N times, overriding each task's meta.yaml `repeat`
               (default: unset, use meta).

meta.yaml keys read here: timeout_sec, multi_turn, curated_skill, sentinel, repeat,
default (false => skipped unless named in --tasks), tools (none => `--tools ""`).
max_budget_usd (overrides --max-budget-usd for that task), layer_neutral (bare only, kept in the frontier),
judge_files / signals (passed through to _meta).
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contamination import contamination_rules, find_contamination, scrub_env, workspace_name  # noqa: E402

DEFAULT_WS_ROOT = "/Users/Shared/evalws"
KNOWN_LAYERS = ("bare", "claude-md", "memory", "skills", "full")
REPO_ROOT = Path(__file__).parent.parent
EFFORTS = ("low", "medium", "high", "xhigh", "max")  # the CLI's --effort set


KEYCHAIN_ITEM = "os-evals-claude-token"
_TOKEN = None  # read once per process by oauth_token(); run_one injects it into the claude env


def oauth_token() -> str:
    """CLAUDE_CODE_OAUTH_TOKEN from the environment (non-Mac/CI override), else the keychain item.
    Cached for the process. Raises RuntimeError (no token in the message) if neither has one."""
    global _TOKEN
    if _TOKEN is None:
        tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
        if not tok:
            try:
                r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_ITEM, "-w"],
                                   capture_output=True, text=True)
                tok = r.stdout.strip() if r.returncode == 0 else ""
            except OSError:
                tok = ""
        if not tok:
            raise RuntimeError(f"no auth token: keychain item {KEYCHAIN_ITEM!r} missing and CLAUDE_CODE_OAUTH_TOKEN unset; "
                               f"fix: security add-generic-password -a os-evals -s {KEYCHAIN_ITEM} -w <token>")
        _TOKEN = tok
    return _TOKEN


def find_tasks(tasks_dir: Path, include_non_default: bool = True) -> list[str]:
    """Task ids are paths (relative to tasks_dir) of any dir holding a prompt.md.

    Supports both flat tasks (tasks/print-date) and category-grouped tasks
    (tasks/coding/launchd-service). Any path segment starting with '_' is skipped
    (e.g. tasks/_example). Tasks with `default: false` are dropped unless
    include_non_default."""
    tasks = []
    for prompt in tasks_dir.rglob("prompt.md"):
        rel = prompt.parent.relative_to(tasks_dir)
        if any(seg.startswith("_") for seg in rel.parts):
            continue
        if not include_non_default and not read_task_meta(prompt.parent)["default"]:
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
      timeout_sec  — per-task wall-clock budget (default 1800). One retry on timeout.
      multi_turn   — if true, capture the full event stream (stream-json) and give
                     the run a real git repo so orchestrator skills can branch/worktree.
      default      — false => excluded from the no-`--tasks` default set (still runs if named).
      tools        — `none` => claude gets `--tools ""` (no tools at all).
      curated_skill— the skill this task is meant to exercise; used to detect whether
                     that skill actually fired (routing check).
    """
    out = {"timeout_sec": 1800, "multi_turn": False, "curated_skill": "", "sentinel": False, "repeat": 1,
           "default": True, "tools": "", "layer_neutral": False, "max_budget_usd": None,
           "judge_files": "", "signals": ""}
    meta_file = task_dir / "meta.yaml"
    if not meta_file.exists():
        return out
    for line in meta_file.read_text().splitlines():
        # Only genuine top-level scalar keys sit at column 0. Anything indented is
        # inside a block (e.g. the description: literal block, or a wrapped plain
        # scalar), so prose like "  multi_turn: git-repo'd ..." can't shadow the
        # real key. In YAML a block scalar's content must be indented past its key,
        # so a column-0 "key: value" is always a top-level field.
        if line[:1] in (" ", "\t"):
            continue
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
        elif s.startswith("sentinel:"):
            out["sentinel"] = s.split(":", 1)[1].strip().lower().startswith("true")
        elif s.startswith("layer_neutral:"):
            out["layer_neutral"] = s.split(":", 1)[1].strip().lower().startswith("true")
        elif s.startswith("max_budget_usd:"):  # per-task cap, overrides the CLI default (C1 needs 6)
            try:
                out["max_budget_usd"] = float(s.split(":", 1)[1].split("#", 1)[0].strip())
            except ValueError:
                pass
        elif s.startswith(("judge_files:", "signals:")):  # passed through to _meta; other items parse them
            k, v = s.split(":", 1)
            out[k] = v.split(" #", 1)[0].strip().strip("'\"")
        elif s.startswith("default:"):
            out["default"] = not s.split(":", 1)[1].split("#", 1)[0].strip().lower().startswith("false")
        elif s.startswith("tools:"):
            out["tools"] = s.split(":", 1)[1].split("#", 1)[0].strip().strip("'\"").lower()
        elif s.startswith("repeat:"):
            val = s.split(":", 1)[1].split("#", 1)[0].strip()
            try:
                out["repeat"] = int(val)
            except ValueError:
                pass
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
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):  # a bare `123` / `[]` / `"x"` line is not an event
            events.append(ev)

    result_events = [e for e in events if e.get("type") == "result"]
    if result_events:
        return result_events[-1], events

    # No terminal result: build a stand-in. Salvage the last assistant usage if any.
    last_usage = {}
    for e in events:
        u = (e.get("message") or {}).get("usage")
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


def _iter_tool_uses(events: list[dict]):
    """Yield (name, input_dict) for every tool_use block across assistant events."""
    for e in events:
        content = (e.get("message") or {}).get("content") if isinstance(e, dict) else None
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
        if name in ("Task", "Agent"):  # the spawn tool is named Agent in current CLIs
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

    The token read from the keychain/env at start is a long-lived setup-token, so a mid-run
    401 means it was revoked or rotated; that failure is infra, not evidence about
    the skill. score.py maps this to the check_rc==2 (unscoreable) convention.
    """
    t = transcript if isinstance(transcript, dict) else {}
    parts = [stderr or ""]
    if stdout and not _is_json_text(stdout):
        parts.append(stdout)
    if t.get("is_error"):  # a successful answer that merely mentions "401" is not an infra error
        parts.append(str(t.get("result") or ""))
    hay = "\n".join(parts).lower()
    return any(p in hay for p in _AUTH_ERR_PATTERNS)


_RATE_LIMIT_RE = re.compile(
    r"\b429\b|rate[ _]limit|exceed your account|overloaded_error|request rejected",
    re.IGNORECASE,
)


def _is_json_text(text: str) -> bool:
    for line in text.splitlines():
        try:
            if isinstance(json.loads(line), (dict, list)):
                return True
        except ValueError:
            continue
    return False


def looks_like_rate_limit(stdout: str, stderr: str, transcript: dict) -> bool:
    """Detect a 429 rate-limit failure so it can be flagged infra (not a task fail).

    Only error surfaces are inspected: stderr, the transcript's error fields, and its
    result text when the run is flagged as an error. Raw stdout is JSON/stream-json
    (UUIDs, token counts, tool output) and is scanned only when it is plain non-JSON
    text (a CLI crash message). Works with transcript alone (stdout=stderr="") so
    score.py can reclassify stored run JSONs. A clean rc-0 run that produced output
    tokens is never rate-limited.
    """
    t = transcript if isinstance(transcript, dict) else {}
    usage = t.get("usage") if isinstance(t.get("usage"), dict) else {}
    meta = t.get("_meta") if isinstance(t.get("_meta"), dict) else {}
    if (usage.get("output_tokens") or 0) > 0 and not t.get("is_error") \
            and meta.get("returncode", 0) == 0:
        return False
    parts = [stderr or ""]
    if stdout and not _is_json_text(stdout):
        parts.append(stdout)
    sub = t.get("subtype")
    if t.get("is_error"):  # answer text of a non-error result is never inspected
        parts.append(str(t.get("result") or ""))
    if isinstance(sub, str) and sub.startswith("error"):
        parts.append(sub)
    err = t.get("error")
    if err:
        parts.append(json.dumps(err) if isinstance(err, (dict, list)) else str(err))
    if t.get("api_error_status") in (429, "429"):
        return True
    return bool(_RATE_LIMIT_RE.search("\n".join(parts)))


RATE_LIMIT_MAX_RETRIES = 3
TIMEOUT_MAX_RETRIES = 1


def rate_limit_backoff_seconds(attempt: int) -> float:
    """Exponential backoff delay for a rate-limited retry attempt (0-indexed).

    attempt=0 → 30s, attempt=1 → 60s, attempt=2 → 120s.
    Capped at 120s so a 3-retry sequence costs at most ~3.5 minutes of wall time.
    Each delay has a ±20% jitter to spread concurrent runs' retry storms.
    """
    import random
    base = min(30 * (2 ** attempt), 120)
    jitter = base * 0.2 * (2 * random.random() - 1)
    return max(1.0, base + jitter)


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


def rung_dir(configs_dir: Path, layer, os_sha: str = "") -> Path:
    """configs/<sha>/<layer>/ (configs/<layer>/ if no sha): the layer's template config dir."""
    return configs_dir / os_sha / str(layer) if os_sha else configs_dir / str(layer)


RUN_CONFIG_FILES = ("CLAUDE.md", "settings.json")
RUN_CONFIG_LINKS = ("skills", "agents", "output-styles")
# configs/<sha>/ built before item 1.8 still carry these; the token now comes only from keychain/env.
STALE_TOKEN_LINES = ("CLAUDE_CODE_OAUTH_TOKEN=", "ANTHROPIC_AUTH_TOKEN=")


def build_run_config(template: Path, cfg: Path) -> None:
    """(Re)create cfg as a fresh per-run CLAUDE_CONFIG_DIR from the layer template.

    Allowlist only: the static config files are copied and the skills/agents/output-styles
    symlinks recreated with the same targets. Everything else Claude Code writes into a
    config dir (projects/*.jsonl transcripts, sessions/, backups/, .claude.json, ...) and
    rung.flags stay behind, so no run sees another run's answers. rung.env is rewritten with
    CLAUDE_CONFIG_DIR=cfg: the memory hook sources "$CLAUDE_CONFIG_DIR/rung.env" for HOME/config
    dir (the token comes from the keychain, never this file), and its nested session must stay per-run."""
    import shutil
    shutil.rmtree(cfg, ignore_errors=True)
    cfg.mkdir(parents=True)
    for name in RUN_CONFIG_FILES:
        if (template / name).is_file():
            shutil.copy2(template / name, cfg / name)
    for name in RUN_CONFIG_LINKS:
        if (template / name).is_symlink():
            target = os.readlink(template / name)
            os.symlink(os.path.join(template, target), cfg / name)  # join is a no-op for an absolute target
    env_file = template / "rung.env"
    if env_file.is_file():
        lines = [ln for ln in env_file.read_text().splitlines() if not ln.startswith(("CLAUDE_CONFIG_DIR=", *STALE_TOKEN_LINES))]
        fd = os.open(cfg / "rung.env", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join([f"CLAUDE_CONFIG_DIR={cfg}", *lines]) + "\n")


def load_rung(configs_dir: Path, layer, os_sha: str = "") -> tuple[dict[str, str], list[str]]:
    """Returns (env_vars, extra_flags) for configs/<sha>/<layer>/ (configs/<layer>/ if no sha)."""
    rdir = rung_dir(configs_dir, layer, os_sha)
    if not rdir.is_dir():
        raise FileNotFoundError(f"layer config dir missing (unknown or unbuilt layer?): {rdir}")
    env_file = rdir / "rung.env"
    flags_file = rdir / "rung.flags"

    env_vars: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith(STALE_TOKEN_LINES):
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()

    flags: list[str] = []
    if flags_file.exists():
        for line in flags_file.read_text().splitlines():
            line = line.strip()
            if line:
                flags.extend(line.split())

    return env_vars, flags


def is_pre18_snapshot(template: Path) -> bool:
    """True if the layer's settings.json wires the memory hook but not the keychain token re-read.

    Pre-1.8 snapshots' hook wrapper takes the token from rung.env, which is filtered now, so the hook's
    nested `claude -p` is "Not logged in" and silently injects nothing. Keyed on settings.json, not on
    token lines, so it still holds after the rung.env cleanup."""
    try:
        s = (template / "settings.json").read_text()
    except OSError:
        return False
    return "memory-relevance-hook" in s and KEYCHAIN_ITEM not in s


def build_cmd(model: str, extra_flags: list[str], task_meta: dict,
              max_budget_usd: float | None = None, effort: str | None = None) -> list[str]:
    """argv for one claude run (pure; run_one adds cwd/env/stdin)."""
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model]
    cmd.extend(extra_flags)
    if effort:
        cmd.extend(["--effort", effort])
    if task_meta.get("tools") == "none":
        cmd.extend(["--tools", ""])
    if task_meta.get("max_budget_usd") is not None:  # meta.yaml max_budget_usd beats the CLI default
        max_budget_usd = task_meta["max_budget_usd"]
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    cmd.extend(["--dangerously-skip-permissions"])
    return cmd


def run_one(
    task: str,
    layer,
    model: str,
    tasks_dir: Path,
    configs_dir: Path,
    runs_dir: Path,
    repeat_index: int = 0,
    repeat_total: int = 1,
    os_sha: str = "",
    rung=None,
    max_budget_usd: float | None = None,
    ws_root: Path | None = None,
    effort: str = "high",
) -> Path:
    """Run claude -p for one task/layer/model combo. Returns path to saved transcript.

    `rung` is the label recorded in _meta (default: the layer name)."""
    rung = layer if rung is None else rung
    task_dir = tasks_dir / task
    prompt_file = task_dir / "prompt.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt.md not found: {prompt_file}")

    env_vars, extra_flags = load_rung(configs_dir, layer, os_sha)
    task_meta = read_task_meta(task_dir)
    multi_turn = task_meta["multi_turn"]
    timeout_sec = task_meta["timeout_sec"]
    intended_skill = task_meta["curated_skill"]

    # Every run captures the whole turn-by-turn event stream (stream-json): it feeds the
    # contamination check and shows sub-agent spawns and skill activation. The terminal
    # result event is normalized into the transcript shape score.py reads.
    cmd = build_cmd(model, extra_flags, task_meta, max_budget_usd, effort)

    # Only the claude subprocess gets the scrubbed env (setup.sh/restore keep the real one).
    env = {**scrub_env(dict(os.environ), set(env_vars)), **env_vars}
    if _TOKEN:  # set by main(); bare also gets ANTHROPIC_AUTH_TOKEN (unconfirmed whether --bare reads the OAuth name)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = _TOKEN
        if layer == "bare":
            env["ANTHROPIC_AUTH_TOKEN"] = _TOKEN

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_run_id = f"{ts}_{_slug(task)}_{str(rung).replace('@', '-')}_{model.replace('-', '_')}_{effort}"
    run_id = f"{base_run_id}_r{repeat_index}" if repeat_total > 1 else base_run_id

    # Every run gets its OWN per-run dir <ws_root>/w-<hex>/ holding w/ (the cwd) and cfg/
    # (its CLAUDE_CONFIG_DIR). If the task ships a frozen workspace (workspace.ref and/or
    # seed/), it's restored into w/ so files the model writes are inspectable by check.sh
    # (via WORKSPACE_DIR). If the task has NEITHER, w/ is left empty — a leak guard so
    # text-only analysis/writing tasks never run in (and read from) the eval repo itself.
    # cfg/ is a clean copy of the shared layer template: Claude Code writes session
    # transcripts and state into its config dir, which must never be shared between runs.
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(os.path.abspath((ws_root or runs_dir) / workspace_name(run_id)))
    ws_dir = run_dir / "w"
    cfg_dir = run_dir / "cfg"
    template_dir = rung_dir(configs_dir, layer, os_sha)
    run_dir.mkdir(parents=True, exist_ok=True)
    build_run_config(template_dir, cfg_dir)
    env["CLAUDE_CONFIG_DIR"] = str(cfg_dir)
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

    print(f"  running: {rung} task={task} model={model} effort={effort}", flush=True)
    print(f"    flags: {extra_flags}", flush=True)
    print(f"    env overrides: {list(env_vars.keys())}", flush=True)
    print(f"    mode: {'multi-turn' if multi_turn else 'one-shot'} timeout={timeout_sec}s", flush=True)

    with open(prompt_file) as f:
        prompt_text = f.read()

    stdout = stderr = ""
    returncode = -1
    events: list[dict] = []
    transcript: dict = {}

    _attempt = 0          # total attempts so far (drives the workspace rebuild)
    _rl_retries = 0       # rate-limit retries used
    timeout_retries = 0   # timeout retries used (max TIMEOUT_MAX_RETRIES)
    while True:
        if _attempt > 0:
            # A retry must not inherit files the failed attempt wrote: rebuild w/ and cfg/.
            import shutil
            shutil.rmtree(ws_dir, ignore_errors=True)
            build_run_config(template_dir, cfg_dir)
            if has_ref or has_seed:
                restore_workspace(task_dir, ws_dir)
            else:
                ws_dir.mkdir(parents=True, exist_ok=True)
            if multi_turn:
                _ensure_git_repo(ws_dir)
        _attempt += 1
        # Timing, timeout state, stdout and events all describe the FINAL attempt only.
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

        # Normalize output into the transcript shape score.py expects so we can
        # detect whether a rate-limit error occurred before deciding to retry.
        transcript, events = _parse_stream(stdout, stderr)

        if timed_out and timeout_retries < TIMEOUT_MAX_RETRIES:
            timeout_retries += 1
            print(f"    TIMEOUT — retry {timeout_retries}/{TIMEOUT_MAX_RETRIES}", flush=True)
            continue

        # If the run hit a rate limit (not an auth error), back off and retry.
        if (looks_like_rate_limit(stdout, stderr, transcript)
                and not looks_like_auth_error(stdout, stderr, transcript)
                and not timed_out
                and _rl_retries < RATE_LIMIT_MAX_RETRIES):
            delay = rate_limit_backoff_seconds(_rl_retries)
            _rl_retries += 1
            print(f"    rate-limit (429) detected — retry {_rl_retries}/{RATE_LIMIT_MAX_RETRIES} "
                  f"in {delay:.0f}s", flush=True)
            time.sleep(delay)
            continue
        break

    elapsed_sec = round(time.monotonic() - _t0, 1)

    skill_fired = detect_skill_fired(events, intended_skill)  # None when the task has no curated_skill
    isolated = "HOME" in env_vars
    forbidden, allowed, tilde_root = contamination_rules(
        REPO_ROOT, Path.home(), configs_dir, task_dir, layer, os_sha, str(run_dir), isolated,
        ws_root=str(run_dir.parent), run_home=env_vars.get("HOME"))
    hits = find_contamination(events, forbidden, allowed, tilde_root)
    auth_error = looks_like_auth_error(stdout, stderr, transcript)
    rate_limited = looks_like_rate_limit(stdout, stderr, transcript)

    no_result = not timed_out and not any(e.get("type") == "result" for e in events)
    raw_events = list(events)
    transcript = dict(transcript)  # never alias a stream event: _meta must not leak into the trace
    transcript["_meta"] = {
        "task": task,
        "rung": rung,
        "layer": str(layer),
        "os_sha": os_sha,
        "model": model,
        "effort": effort,
        "model_resolved": next((e.get("model") for e in events
                                if e.get("type") == "system" and e.get("subtype") == "init"), None),
        "returncode": returncode,
        "stderr": stderr[:2000] if stderr else "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(ws_dir) if ws_dir else "",
        "elapsed_sec": elapsed_sec,
        "multi_turn": multi_turn,
        "timeout_sec": timeout_sec,
        "timed_out": timed_out,
        "timeout_retries": timeout_retries,
        "no_result": no_result,
        "intended_skill": intended_skill,
        "skill_fired": skill_fired,
        "layer_neutral": task_meta["layer_neutral"],
        "judge_files": task_meta["judge_files"],
        "signals": task_meta["signals"],
        "auth_error": auth_error,
        "rate_limited": rate_limited,
        "num_events": len(events),
        "home_isolated": isolated,
        "contaminated": bool(hits),
        "contamination_hits": hits,
        "repeat_index": repeat_index if repeat_total > 1 else None,
        "repeat_total": repeat_total if repeat_total > 1 else None,
    }

    out_file = runs_dir / f"{run_id}.json"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(transcript, indent=2))
    print(f"    saved: {out_file.name}", flush=True)

    # Persist the full turn-by-turn trace alongside the normalized transcript so the
    # tool calls / sub-agent spawns are auditable without bloating the scored transcript.
    if raw_events:
        trace_file = runs_dir / f"{run_id}.trace.jsonl"
        trace_file.write_text("\n".join(json.dumps(e) for e in raw_events))
        print(f"    trace: {trace_file.name} ({len(raw_events)} events)", flush=True)

    return out_file


def redact_env(env_vars: dict[str, str]) -> dict[str, str]:
    return {k: ("***" if any(w in k for w in ("TOKEN", "KEY", "SECRET")) else v)
            for k, v in env_vars.items()}


def plan_cells(layers: list[str], shas: list[str]) -> list[tuple[str, str, str]]:
    """(layer, sha, rung label). One sha: label = layer. Several (A/B): label = layer@sha."""
    return [(layer, sha, layer if len(shas) <= 1 else f"{layer}@{sha}")
            for sha in shas for layer in layers]


def load_history(scorecards_dir: Path) -> list[list[dict]]:
    """Score lists from scorecards/*.scores.json, most recently written first."""
    files = sorted(scorecards_dir.glob("*.scores.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text()).get("scores", []))
        except (ValueError, AttributeError):
            continue
    return out


def estimate_cost(history: list[list[dict]], run_counts: dict[str, int], multi_turn: set[str]) -> dict:
    """Estimate cost and serial wall time from past runs.

    Per task: mean cost_usd and mean wall_clock_sec over the non-infra records of the most
    recent history entry (newest first) that has the task. Tasks with no history get the
    median of the other tasks' means and are listed in `no_history`."""
    per_task = {}
    for task in run_counts:
        for scores in history:
            recs = [r for r in scores if r.get("task") == task and not r.get("infra_error")]
            if recs:
                per_task[task] = (statistics.mean(r.get("cost_usd") or 0 for r in recs),
                                  statistics.mean(r.get("wall_clock_sec") or 0 for r in recs))
                break
    no_history = sorted(t for t in run_counts if t not in per_task)
    med = (statistics.median(c for c, _ in per_task.values()),
           statistics.median(w for _, w in per_task.values())) if per_task else (0.0, 0.0)
    cost = secs_one = secs_multi = 0.0
    for task, n in run_counts.items():
        c, w = per_task.get(task, med)
        cost += c * n
        if task in multi_turn:
            secs_multi += w * n
        else:
            secs_one += w * n
    return {"cost": cost, "secs_one": secs_one, "secs_multi": secs_multi, "no_history": no_history}


def execute_items(items: list, runner, jobs: int = 1) -> tuple[list, int]:
    """Run items via runner(item) -> result; returns (results, failures).

    jobs=1: plain serial, in item order. jobs>1: one-shot items (item["multi_turn"] false)
    go through a thread pool, then multi-turn items run serially after it. Each run writes
    only its own workspace/transcript files; the results list and failure count are shared,
    so they are only touched under a lock (or from the main thread)."""
    results, failures, lock = [], 0, threading.Lock()

    def one(item):
        nonlocal failures
        try:
            r = runner(item)
        except Exception as e:
            with lock:
                print(f"  ERROR: {item['label_id']}: {e}", file=sys.stderr, flush=True)
                failures += 1
            return
        with lock:
            results.append(r)

    if jobs <= 1:
        for item in items:
            one(item)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(one, [i for i in items if not i["multi_turn"]]))
        for item in items:
            if item["multi_turn"]:
                one(item)
    return results, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="")
    parser.add_argument("--layers", default="bare,full")
    parser.add_argument("--os-sha", action="append", default=[])
    parser.add_argument("--models", default="opus")
    parser.add_argument("--max-budget-usd", type=float, default=1.50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "configs"))
    parser.add_argument("--tasks-dir", default=str(REPO_ROOT / "tasks"))
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--ws-root", default=os.environ.get("EVAL_WS_ROOT", "") or DEFAULT_WS_ROOT)
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--effort", default="high", help=f"comma-separated, from {','.join(EFFORTS)}")
    args = parser.parse_args()
    efforts = [e for e in args.effort.split(",") if e]
    bad_e = [e for e in efforts if e not in EFFORTS]
    if bad_e or not efforts:
        print(f"run_matrix: ERROR unknown --effort {bad_e or args.effort!r}; known: {', '.join(EFFORTS)}", file=sys.stderr)
        return 2
    if args.repeat is not None and args.repeat < 1:
        print(f"run_matrix: ERROR --repeat must be >= 1 (got {args.repeat})", file=sys.stderr)
        return 2

    tasks_dir = Path(args.tasks_dir)
    configs_dir = Path(args.config_dir)
    runs_dir = Path(args.runs_dir)

    ws_root = Path(args.ws_root)
    jobs = max(1, args.jobs)

    if args.tasks:
        tasks = args.tasks.split(",")
    else:
        tasks = find_tasks(tasks_dir, include_non_default=False)
        skipped = sorted(set(find_tasks(tasks_dir)) - set(tasks))
        if skipped:
            print(f"excluded (default: false; name in --tasks to run): {', '.join(skipped)}")
    layers = [l for l in args.layers.split(",") if l]
    bad = [l for l in layers if l not in KNOWN_LAYERS]
    if bad:
        print(f"run_matrix: ERROR unknown layer(s) {bad}; known: {', '.join(KNOWN_LAYERS)}", file=sys.stderr)
        return 2
    drafts = [t for t in tasks if t and any(seg.startswith("_") for seg in Path(t).parts)]
    if drafts:
        print(f"run_matrix: ERROR task {drafts[0]!r} is a draft (path component starts with '_'); "
              "drafts must be promoted out of _draft first", file=sys.stderr)
        return 2
    shas = args.os_sha or [""]
    cells = plan_cells(layers, shas)
    models = args.models.split(",")

    for layer, sha, _label in cells:
        rdir = rung_dir(configs_dir, layer, sha)
        if is_pre18_snapshot(rdir):
            msg = (f"pre-1.8 snapshot {rdir}: its hook wrapper reads the token from rung.env; "
                   "rebuild - rerun without --no-build")
            if not args.dry_run:
                print(f"run_matrix: ERROR {msg}", file=sys.stderr)
                return 2
            print(f"run_matrix: WARNING {msg} (a real run would refuse)")

    tasks = [t for t in tasks if t]

    print(f"run_matrix: tasks={tasks} cells={[c[2] for c in cells]} models={models}")

    # Sentinel tasks are difficulty anchors: run on the bare layer only (never in A/B).
    plan = []
    for task in tasks:
        task_meta = read_task_meta(tasks_dir / task)
        task_cells = [c for c in cells if c[0] == "bare" or not task_meta["sentinel"]]
        if task_meta["sentinel"] and len(task_cells) < len(cells):
            print(f"  sentinel: {task} — bare layer only" if task_cells else f"  sentinel: {task} — skipped (no bare layer)")
        if task_meta["layer_neutral"]:  # bare only like a sentinel, but kept in the frontier/cost tables
            task_cells = [c for c in task_cells if c[0] == "bare"]
            print(f"  layer_neutral: {task} — bare layer only")
        plan.append((task, task_cells, args.repeat if args.repeat is not None else task_meta.get("repeat", 1)))

    if args.dry_run:
        ne = len(efforts)
        total = sum(len(tc) * len(models) * ne * rep for _, tc, rep in plan)
        print(f"matrix ({len(tasks)} tasks x {len(cells)} cells x {len(models)} models x {ne} efforts):")
        for task, tc, rep in plan:
            for effort in efforts:
                print(f"  {task}: {len(tc)} cells x {len(models)} models x {rep} repeat = {len(tc) * len(models) * rep}  [effort={effort}]")
        for layer, sha, label in cells:
            env_vars, flags = load_rung(configs_dir, layer, sha)
            env = redact_env(env_vars)
            print(f"command [{label}]: claude -p --output-format stream-json --verbose --model <model> {' '.join(flags)} "
                  f"--effort <effort> --max-budget-usd {args.max_budget_usd} --dangerously-skip-permissions")
            print(f"  env: {env}")
            print(f"  HOME: {env.get('HOME', '(real HOME, not isolated)')}")
            gone = sorted(set(os.environ) - set(scrub_env(dict(os.environ), set(env_vars))))
            print(f"  env scrub: {len(gone)} variables removed" + (f" ({', '.join(gone)})" if gone else ""))
        print(f"total runs: {total}")
        metas = {t: read_task_meta(tasks_dir / t) for t, _, _ in plan}
        no_tools = sorted(t for t, m in metas.items() if m["tools"] == "none")
        if no_tools:
            print(f'--tools "" added for: {", ".join(no_tools)}')
        counts = {t: len(tc) * len(models) * len(efforts) * rep for t, tc, rep in plan}
        history = load_history(REPO_ROOT / "scorecards")
        est = estimate_cost(history, counts,
                            {t for t, m in metas.items() if m["multi_turn"]})
        wall_par = est["secs_one"] / jobs + est["secs_multi"]
        print(f"estimate from past Sonnet runs: ${est['cost']:.2f}, serial wall "
              f"{(est['secs_one'] + est['secs_multi']) / 60:.0f} min; with --jobs {jobs}: {wall_par / 60:.0f} min")
        from stats import model_ratios  # lazy: stats imports score, which imports this module
        ratios = model_ratios([x for h in history for x in h])
        for m in (m for m in models if "sonnet" not in m.lower()):
            r = ratios.get(m, "UNMEASURED")
            print(f"measured cost ratio {m} vs sonnet: " + (r if isinstance(r, str) else f"{r:.2f}x (median, matched cells)"))
        if est["no_history"]:
            print(f"  no history (median of others used): {', '.join(est['no_history'])}")
        print(f"jobs: {jobs}  workspaces: {os.path.abspath(ws_root)}")
        return 0

    try:
        oauth_token()  # fail fast, before any workspace is made; --dry-run above never needs it
    except RuntimeError as e:
        print(f"run_matrix: ERROR {e}", file=sys.stderr)
        return 2

    ws_root.mkdir(parents=True, exist_ok=True)

    items = [
        {"task": task, "layer": layer, "sha": sha, "label": label, "model": model, "effort": effort, "i": i,
         "repeat": repeat, "multi_turn": read_task_meta(tasks_dir / task)["multi_turn"],
         "label_id": f"{task}/{label}/{model}/{effort}/r{i}"}
        for task, task_cells, repeat in plan
        for layer, sha, label in task_cells
        for model in models
        for effort in efforts
        for i in range(1, repeat + 1)
    ]

    def runner(it):
        return run_one(
            it["task"], it["layer"], it["model"], tasks_dir, configs_dir, runs_dir,
            repeat_index=it["i"], repeat_total=it["repeat"],
            os_sha=it["sha"], rung=it["label"], max_budget_usd=args.max_budget_usd,
            ws_root=ws_root, effort=it["effort"],
        )

    _, failures = execute_items(items, runner, jobs)

    print(f"run_matrix: done. failures={failures}")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
