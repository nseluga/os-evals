#!/bin/bash
set -uo pipefail

# check.sh — launchd-service (coding, clean)
#
# Reads transcript JSON from stdin (unused here except to drain it).
# Evaluates the WORKSPACE that `claude -p` modified.
#
# CONTRACT NOTE: this check requires WORKSPACE_DIR — the per-run restored workspace
# the model edited. The proven smoke-test harness does not yet set this (it only
# runs claude -p with a piped prompt and gives check.sh the transcript). See
# CONTRACT-NOTE.md for the minimal proposed extension. If WORKSPACE_DIR is unset,
# this check fails loudly rather than silently passing.

cat >/dev/null  # drain transcript on stdin (not needed for a filesystem check)

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract extension required)" >&2
    exit 2
fi

PLIST="$WS/com.nateseluga.project-dashboard.plist"
INSTALL="$WS/scripts/launchd-install.sh"
UNINSTALL="$WS/scripts/launchd-uninstall.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }

# --- 1. plist exists and is a valid plist, with required keys/values ---
[ -f "$PLIST" ] || fail "plist not found at repo root: com.nateseluga.project-dashboard.plist"

python3 - "$PLIST" <<'PY' || exit 1
import plistlib, sys
path = sys.argv[1]
try:
    with open(path, "rb") as f:
        d = plistlib.load(f)
except Exception as e:
    print(f"FAIL: plist does not parse as a valid plist: {e}", file=sys.stderr); sys.exit(1)

def req(cond, msg):
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr); sys.exit(1)

req(d.get("RunAtLoad") is True, "RunAtLoad must be true")
req(d.get("KeepAlive") in (True, {"SuccessfulExit": False}) or d.get("KeepAlive") is True,
    "KeepAlive must be true (keep process alive)")
req(d.get("StandardOutPath") == "/tmp/project-dashboard.log",
    "StandardOutPath must be /tmp/project-dashboard.log")
req(d.get("StandardErrorPath") == "/tmp/project-dashboard.err",
    "StandardErrorPath must be /tmp/project-dashboard.err")
req(isinstance(d.get("WorkingDirectory"), str) and d["WorkingDirectory"].strip() != "",
    "WorkingDirectory must be set")

args = d.get("ProgramArguments")
req(isinstance(args, list) and len(args) >= 2, "ProgramArguments must be a non-empty list")
joined = " ".join(args)
# Must launch astro via node's abs path, NOT `npm run dev` (prompt requirement:
# launchd has a minimal PATH and cannot find npm).
req("astro" in joined, "ProgramArguments must invoke astro")
req("npm" not in joined, "ProgramArguments must NOT use npm (launchd lacks PATH for npm)")
req(any(a.endswith("/node") or a == "node" or "/node" in a for a in args),
    "ProgramArguments must invoke node by absolute path")
req("Label" in d and isinstance(d["Label"], str), "plist should declare a Label")
print("plist OK", file=sys.stderr)
PY

# --- 2. install script: exists, executable, loads via launchctl ---
[ -f "$INSTALL" ]  || fail "scripts/launchd-install.sh not found"
[ -x "$INSTALL" ]  || fail "scripts/launchd-install.sh is not executable"
grep -q "launchctl load" "$INSTALL" || fail "install script must run 'launchctl load'"
grep -q "LaunchAgents"   "$INSTALL" || fail "install script must reference ~/Library/LaunchAgents"

# --- 3. uninstall script: exists, unloads + removes ---
[ -f "$UNINSTALL" ] || fail "scripts/launchd-uninstall.sh not found"
grep -qE "launchctl (unload|bootout|remove)" "$UNINSTALL" || fail "uninstall script must unload the service"
grep -qE "rm |unlink" "$UNINSTALL" || fail "uninstall script must remove the plist from LaunchAgents"

echo "PASS: launchd plist + install/uninstall scripts meet all criteria"
exit 0
