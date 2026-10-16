#!/bin/bash
set -uo pipefail
# check.sh — writing/quote-deluxe-notes
# Reads transcript JSON on stdin ({"result": ...}) AND the workspace (WORKSPACE_DIR).
# The deliverable = result text + any .md/.txt/.html written to the workspace, minus the seed file.
# Exit: 0 pass, 1 fail, 2 infra (WORKSPACE_DIR unset or missing).

if [ -z "${WORKSPACE_DIR:-}" ] || [ ! -d "$WORKSPACE_DIR" ]; then
  echo "INFRA: WORKSPACE_DIR unset or not a directory" >&2
  exit 2
fi

IN="$(mktemp)"; trap 'rm -f "$IN"' EXIT
cat >"$IN"

python3 - "$IN" "$WORKSPACE_DIR" <<'PY'
import json, os, re, sys

stdin_file, ws = sys.argv[1], sys.argv[2]
SEED = "old-quote-2026-07.md"

try:
    result = json.load(open(stdin_file)).get("result", "") or ""
except Exception:
    result = ""

parts = [result]
for root, dirs, files in os.walk(ws):
    dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
    for f in files:
        if f == SEED or not f.lower().endswith((".md", ".txt", ".html", ".htm")):
            continue
        try:
            parts.append(open(os.path.join(root, f), errors="replace").read())
        except OSError:
            pass
text = "\n".join(parts)
lc = text.lower()

if not lc.strip():
    print("FAIL: no quote text in result or workspace", file=sys.stderr)
    sys.exit(1)

fails = []

# --- required pricing ---
if not re.search(r"\$\s?200(?:\.00)?\b[^\n]{0,30}?(/\s?mo|per month|a month|monthly)", lc):
    fails.append("missing $200 with /mo or per month")
if not re.search(r"\$\s?5,?000\b", lc):
    fails.append("missing $5,000")
if not re.search(r"\$\s?300\b", lc):
    fails.append("missing $300")

# --- stale pricing (sentence-level; sentences that disown it are fine) ---
DISOWN = re.compile(r"\b(retired|no longer|not|no|never|instead|stale|outdated|superseded|without|don't|doesn't|isn't)\b|n't\b")
STALE = {
    "$250/month": r"\$\s?250\b[^\n]{0,25}?(/\s?mo|per month|a month|monthly)",
    "$3,000 Standard": r"(\$\s?3,?000\b[^\n]{0,60}standard|standard[^\n]{0,60}\$\s?3,?000\b)",
    "hourly": r"\bhourly\b|/\s?hour\b|per hour\b",
    "Standard tier": r"\bstandard (tier|build|package|plan)\b|\badvanced (tier|build|package|plan)\b",
}
for label, pat in STALE.items():
    for m in re.finditer(pat, lc):
        s = max(lc.rfind(c, 0, m.start()) for c in ".!?\n") + 1
        ends = [i for i in (lc.find(c, m.end()) for c in ".!?\n") if i != -1]
        sentence = lc[s:min(ends) if ends else len(lc)]
        if not DISOWN.search(sentence):
            fails.append(f"stale pricing present: {label}")
            break

# --- structure: at least 7 of 10 section cues ---
CUES = ["executive summary", "scope", "timeline", "pricing", "terms",
        "assumptions", "next steps", "deliverables", "support", "payment"]
hit = [c for c in CUES if c in lc]
if len(hit) < 7:
    fails.append(f"only {len(hit)}/10 section cues ({', '.join(hit)})")

# --- no personal name on the bcns side ---
if re.search(r"\bnate\b|\bseluga\b", lc):
    fails.append("contains a personal name (Nate/Seluga)")

if fails:
    print("FAIL: " + "; ".join(fails), file=sys.stderr)
    sys.exit(1)
print(f"PASS: current pricing, no stale tiers, {len(hit)}/10 section cues")
PY
