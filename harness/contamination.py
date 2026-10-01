"""
harness/contamination.py

Pure helpers that keep a run honest: detect tool calls that reach outside the run's own
workspace (task files, live ~/os, the origin repo holding the solution), pick opaque
workspace names, and scrub credentials out of the environment handed to `claude`.

find_contamination(events, forbidden, allowed) walks tool_use blocks in a stream-json
trace and reports every string in a tool INPUT that references a forbidden root and is
not under an allowed root. Text the model wrote in its answer is never inspected.
"""

import hashlib
import re
from pathlib import Path

HIT_MAX = 160
_PATH_CHAR = r"[\w.\-]"
_TOKEN_END = " \t\n'\"`;|&<>()"
# ~/x, $HOME/x, ${HOME}/x -> the HOME the run actually had (tilde_root)
_TILDE_RE = re.compile(r"(?<![\w.~$])(?:~|\$HOME|\$\{HOME\})(?=/)")


def workspace_name(run_id: str) -> str:
    """Opaque workspace dir name: leaks neither task, layer nor model."""
    return "w-" + hashlib.sha1(run_id.encode()).hexdigest()[:10]


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _tool_inputs(events):
    for e in events:
        content = (e.get("message") or {}).get("content") if isinstance(e, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("input") or {}


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/")
    if not root:
        return False
    return path == root or path.startswith(root + "/")


def _hits_in(s: str, forbidden: list[str], allowed: list[str]) -> bool:
    for root in forbidden:
        root = root.rstrip("/")
        # lookbehind leaves out "." so a relative climb (../../Users/x/os) still matches
        pat = re.compile(r"(?<![\w\-])" + re.escape(root) + r"(?!" + _PATH_CHAR + r")")
        for m in pat.finditer(s):
            end = m.end()
            while end < len(s) and s[end] not in _TOKEN_END:
                end += 1
            if not any(_under(s[m.start():end], a) for a in allowed):
                return True
    return False


def find_contamination(events, forbidden, allowed, tilde_root: str | None = None) -> list[str]:
    """Distinct tool-input strings (cut to 160 chars) that touch a forbidden root outside
    every allowed root. Roots match on path boundaries (`/h/os` never matches `/h/os-evals`).
    `tilde_root`: when set, `~/`, `$HOME/` and `${HOME}/` in an input are read as that dir
    (the HOME the run actually had); when None they are left as written."""
    hits: list[str] = []
    for inp in _tool_inputs(events):
        for s in _strings(inp):
            probe = _TILDE_RE.sub(lambda _m: tilde_root, s) if tilde_root else s
            if _hits_in(probe, list(forbidden), list(allowed)):
                short = s[:HIT_MAX]
                if short not in hits:
                    hits.append(short)
    return hits


def read_origin(task_dir: Path) -> str:
    """`origin:` path from a task's workspace.ref ('' if none)."""
    ref = Path(task_dir) / "workspace.ref"
    if ref.exists():
        for line in ref.read_text().splitlines():
            s = line.strip()
            if s.startswith("origin:"):
                return str(Path(s.split(":", 1)[1].split("#", 1)[0].strip()).expanduser())
    return ""


def contamination_rules(repo: Path, home: Path, configs_dir: Path, task_dir: Path, layer: str,
                        os_sha: str, ws_dir: str, isolated: bool, ws_root: str | None = None,
                        run_home: str | None = None, shared_cfg: bool = False):
    """(forbidden, allowed, tilde_root) for one run; feed them to find_contamination.

    `ws_dir` is this run's own dir: the per-run parent holding w/ (cwd) and cfg/ (its
    CLAUDE_CONFIG_DIR), or the flat workspace of a run made before that layout. It is the
    allowed exception under `ws_root` (the dir holding every run's dir, forbidden), so
    reading a sibling run's dir is a hit. `ws_root` defaults to the parent of ws_dir.

    Non-bare layers with an os_sha may also read all of configs/<sha> (the os snapshot
    src/, home/, the clean layer templates); bare may read only configs/<sha>/home-bare
    (its HOME), never src/ or another layer. `run_home` is the HOME the run was given:
    with isolation on, `~` resolves there; with it off (or run_home unknown) `~` is the
    real home, so `~/os` / `~/.claude` reads are hits.

    `shared_cfg`: the run used the shared template configs/<sha>/<layer>/ as its config
    dir (runs made before per-run cfg/): every layer dir then held other runs'
    transcripts, so non-bare may read only its own layer dir, src/ and home/."""
    repo, home = Path(repo), Path(home)
    forbidden = [str(repo / d) for d in ("tasks", "harness", "scorecards", "runs", "configs")]
    forbidden += [str(home / d) for d in ("os", "personal-os", ".claude")]
    origin = read_origin(task_dir)
    if origin:
        forbidden.append(origin)
    root = ws_root or (str(Path(ws_dir).parent) if ws_dir else "")
    if root and Path(root).is_absolute() and root.rstrip("/"):
        forbidden.append(root)
    allowed = [str(ws_dir)]
    cfg = Path(configs_dir)
    if str(layer) == "bare":
        if os_sha:
            allowed.append(str(cfg / os_sha / "home-bare"))
    elif os_sha and shared_cfg:
        allowed += [str(cfg / os_sha / d) for d in (str(layer), "src", "home")]
    else:
        allowed.append(str(cfg / os_sha if os_sha else cfg / str(layer)))
    tilde_root = str(run_home) if (isolated and run_home) else str(home)
    return forbidden, allowed, tilde_root


_SCRUB_RE = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_KEY|APIKEY|_KEY$|PRIVATE"
    r"|^SSH_AUTH_SOCK$|DATABASE_URL|_AUTH(?:_|$)|_DSN"
    r"|^(?:AWS_|GH_|GITHUB_|SUPABASE_|VERCEL_|RESEND_|OPENAI_|GOOGLE_APPLICATION_)",
    re.IGNORECASE,
)


def scrub_env(env: dict, keep: set[str]) -> dict:
    """Copy of env without credential-looking variables, except names in `keep`."""
    return {k: v for k, v in env.items() if k in keep or not _SCRUB_RE.search(k)}
