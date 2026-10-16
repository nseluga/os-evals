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
lines = lc.splitlines()
if not any(re.search(r"\$\s?200(?:\.00)?\b", l) and re.search(r"/\s?mo\b|/\s?month|\bmonth|\bmonthly\b", l) for l in lines):
    fails.append("missing $200 with /mo or per month")
if not re.search(r"\$\s?5,?000\b|\$\s?5k\b|\b5,?000\s?(usd|dollars)\b|\bfive thousand\b", lc):
    fails.append("missing $5,000")
if not re.search(r"\$\s?300\b", lc):
    fails.append("missing $300")

# --- stale pricing (sentence-level; only sentences that disown it explicitly are fine) ---
DISOWN = re.compile(
    r"\b(retired|no longer|discontinued|stale|outdated|out of date|superseded|replaced|instead of|unlike|"
    r"old(?:er)? (?:quote|file|proposal|pricing)|previous (?:quote|pricing)|july)\b"
    r"|\b(?:no|not|never|without)\s+(?:\w+\s+){0,2}(?:hourly|by the hour|per hour|standard|advanced)\b"
    r"|n't\s+(?:\w+\s+){0,2}(?:hourly|by the hour|per hour|standard|advanced)\b")
HOURLY = r"\bhourly\b|/\s?(?:hour|hr)\b|\bper (?:hour|hr)\b|\ban hour\b|\bby the hour\b"
STALE = {
    "$250/month": r"\$\s?250\b",
    "$3,000 setup": r"\$\s?3,?000\b",
    "hourly": HOURLY,
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

# --- structure: at least 7 of 10 section cues (on heading lines only) ---
CUES = ["executive summary", "scope", "timeline", "pricing", "terms",
        "assumptions", "next steps", "deliverables", "support", "payment"]
# Cues count only on heading lines: markdown '#', bold '**', <h1-6>, or a short title-like plain line
# (<=50 chars, no trailing sentence punctuation, not a bullet or table row). Prose mentions do not count.
def is_heading(l):
    if re.match(r"\s*(#{1,6}\s|\*\*|<h[1-6])", l):
        return True
    t = l.strip()
    return bool(t) and len(t) <= 50 and not re.search(r"[.!?,;:]$", t) and not re.match(r"[|\-*+>]|\d+\)", t)
heads = "\n".join(l for l in lc.splitlines() if is_heading(l))
hit = [c for c in CUES if c in heads]
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
