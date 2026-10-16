#!/bin/bash
set -uo pipefail
# check.sh — memory-artifact-text-color (knowledge; text-only, reads transcript JSON on stdin)
# Numeric: at least one hex labelled text/ink/body with mean channel 42-110, and none under 42; label-scoped so a charcoal used as a background does not count.
# Exit: 0=PASS, 1=FAIL, 2=infra.

TRANSCRIPT="$(cat)"
TMPFILE="$(mktemp)"
echo "$TRANSCRIPT" > "$TMPFILE"

python3 - "$TMPFILE" <<'PY'
import sys, json, re

try:
    data = json.load(open(sys.argv[1]))
    result = data.get("result", "")
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr)
    sys.exit(2)

rl = result.lower()

def expand(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

TEXTY = re.compile(r"text|ink|foreground|\bfg\b|body|copy|font|type|prose")
NOT_TEXT = re.compile(r"background|\bbg\b|surface|border|accent|link|button|shadow|divider|card|highlight")

text_hexes = []
for m in re.finditer(r"#(?:[0-9a-f]{6}|[0-9a-f]{3})\b", rl):
    label = rl[max(0, m.start() - 40):m.start()]
    label = re.split(r"[;\n,]", label)[-1]          # only the label directly in front of this hex
    if TEXTY.search(label) and not NOT_TEXT.search(label):
        text_hexes.append((m.group(0), sum(expand(m.group(0))) / 3))

# "black" / "rgb(0,0,0)" spelled out as the text color is also a hard fail
spelled = re.search(r"(?:text|ink|body|foreground|color)[^.\n]{0,25}:\s*(?:black|rgb\(\s*0\s*,\s*0\s*,\s*0\s*\))", rl)

if not text_hexes:
    print("FAIL: no hex value given for a body/text token", file=sys.stderr)
    sys.exit(1)
if spelled:
    print("FAIL: text color spelled as black", file=sys.stderr)
    sys.exit(1)

too_dark = [(h, round(v)) for h, v in text_hexes if v < 42]      # rule: nothing under roughly #2a2a2a
soft = [(h, round(v)) for h, v in text_hexes if 42 <= v <= 110]  # a soft dark charcoal
if too_dark:
    print(f"FAIL: text token is pure/near-black (mean channel < 42): {too_dark}", file=sys.stderr)
    sys.exit(1)
if not soft:
    print(f"FAIL: no text token in the soft dark charcoal range: {text_hexes}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: text tokens are soft charcoal, none near-black: {soft}")
sys.exit(0)
PY
