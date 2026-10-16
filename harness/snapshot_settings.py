"""Pure settings.json transforms for snapshot-built eval layers (no I/O).

Live ~/.claude/settings.json is shaped for Nate's interactive machine: side-effect hooks
(sounds, chat-history saves, maintenance, digest), plugins, notifications, and paths
into ~/os. An eval layer keeps the behavior-shaping parts and rewrites ~/os paths to the
snapshot root so it reads the snapshot, not live state.
"""
import copy
import os
import pwd
import re

MEMORY_HOOK_MARK = "memory-relevance-hook"
# Live settings name the hook as ~/.claude/memory-relevance-hook.py (a symlink into ~/os).
_LIVE_HOOK_RE = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/Users/[^/\s]+)/\.claude/memory-relevance-hook\.py")
_OS_PATH_RE = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/Users/[^/\s]+)/os(?=/|\s|$|\")")
# Keys with side effects or machine-only meaning; never carried into an eval layer.
DROP_KEYS = ("enabledPlugins", "extraKnownMarketplaces", "statusLine",
             "inputNeededNotifEnabled", "agentPushNotifEnabled")


def rewrite_paths(value, snap_root):
    """Recursively rewrite ~/os, $HOME/os, /Users/x/os (and the live hook path) to snap_root."""
    snap_root = str(snap_root).rstrip("/")
    if isinstance(value, str):
        value = _LIVE_HOOK_RE.sub(f"{snap_root}/scripts/memory-relevance-hook.py", value)
        return _OS_PATH_RE.sub(lambda _m: snap_root, value)
    if isinstance(value, list):
        return [rewrite_paths(v, snap_root) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_paths(v, snap_root) for k, v in value.items()}
    return value


# Claude Code strips CLAUDE_CODE_OAUTH_TOKEN from hook subprocess envs (CLAUDE_CONFIG_DIR survives),
# so the hook's nested `claude -p` would be "Not logged in". Re-source the layer's rung.env (HOME,
# CLAUDE_CONFIG_DIR; no token on disk) and re-read the token from the keychain. The hook runs under
# the isolated HOME, where `security` finds no default keychain, so the real user's login keychain
# path is baked in (a path, not a secret). pw_dir, not $HOME: HOME may already be isolated here.
_LOGIN_KEYCHAIN = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, "Library/Keychains/login.keychain-db")
_ENV_WRAP = ('bash -c \'set -a; . "$CLAUDE_CONFIG_DIR/rung.env"; set +a; '
             't=$(security find-generic-password -s os-evals-claude-token -w "' + _LOGIN_KEYCHAIN + '" 2>/dev/null); '
             '[ -n "$t" ] && export CLAUDE_CODE_OAUTH_TOKEN="$t"; exec ')


def _wrap_env(cmd):
    if cmd.startswith(_ENV_WRAP) or "'" in cmd:  # already wrapped (idempotent) / unquotable
        return cmd
    return f"{_ENV_WRAP}{cmd}'"


def memory_hooks_only(hooks):
    """Keep exactly the UserPromptSubmit memory-relevance hook (env-wrapped); drop every other hook."""
    kept = []
    for group in (hooks or {}).get("UserPromptSubmit", []):
        cmds = [{**h, "command": _wrap_env(h["command"])}
                for h in group.get("hooks", []) if MEMORY_HOOK_MARK in h.get("command", "")]
        if cmds:
            kept.append({**{k: v for k, v in group.items() if k != "hooks"}, "hooks": cmds})
    return {"UserPromptSubmit": kept} if kept else {}


def strip_settings(settings, snap_root):
    """Full-layer settings: live-shaped, side effects stripped, ~/os paths -> snap_root."""
    out = copy.deepcopy(settings)
    for k in DROP_KEYS:
        out.pop(k, None)
    # Effort is an explicit run axis (--effort); settings must not set it behind the harness's back.
    out.pop("effortLevel", None)
    for ms in (out.get("modelSettings") or {}).values():
        if isinstance(ms, dict):
            ms.pop("effortLevel", None)
    hooks = memory_hooks_only(out.get("hooks"))
    if hooks:
        out["hooks"] = hooks
    else:
        out.pop("hooks", None)
    return rewrite_paths(out, snap_root)


def layer_settings(layer, settings, snap_root):
    """settings.json content for a layer (claude-md / memory / skills / full)."""
    snap_root = str(snap_root).rstrip("/")
    if layer == "full":
        return strip_settings(settings, snap_root)
    if layer == "claude-md":
        return {"autoMemoryEnabled": False}
    out = {"autoMemoryEnabled": True, "autoMemoryDirectory": f"{snap_root}/knowledge/memory"}
    hooks = memory_hooks_only(strip_settings(settings, snap_root).get("hooks"))
    if hooks:
        out["hooks"] = hooks
    return out
