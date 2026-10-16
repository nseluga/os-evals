#!/bin/bash
set -uo pipefail
# check.sh — writing/client-email-fee (text-only; reads transcript JSON on stdin)
# Floor for a humanized client email: no dashes-as-punctuation, <=1 apology, >=3 contractions,
# sign-off line, no AI-tell words, keeps $540 + Oct 30, and states the free/manual alternative.
# Exit: 0=PASS, 1=FAIL.

python3 -c '
import sys, json, re
try:
    r = json.load(sys.stdin).get("result", "") or ""
except Exception:
    r = ""
lc = r.lower()
fails = []

# dashes as punctuation: em dash, en dash not between digits, " -- ", " - " between words
dash = "—" in r or re.search(r"(?<!\d)–|–(?!\d)", r)
for m in re.finditer(r"(?<=\S)[ \t]+-{1,2}[ \t]+(?=\S)", r):
    if not (r[m.start() - 1].isdigit() and r[m.end()].isdigit()):
        dash = True
if dash:
    fails.append("dash used as punctuation")

n_apol = len(re.findall(r"\bsorry\b|\bapologi[sz](?:e|es|ed|ing)\b|\bapologies\b", lc))
if n_apol > 1:
    fails.append("apologies=%d" % n_apol)

n_con = len(re.findall(r"\b(?:i|you|we|it|that|there|they|he|she|what|let)(?:’|\x27)(?:m|re|ve|ll|d|s)\b|\b\w+n(?:’|\x27)t\b", lc))
if n_con < 3:
    fails.append("contractions=%d" % n_con)

if not re.search(r"^(?i:best regards|best|thanks|cheers|thank you|talk soon|all the best)[,!]?([ \t]+[A-Z][\w.]*([ \t]+[A-Z][\w.]*){0,2})?[ \t]*$", r, re.M):
    fails.append("no sign-off line")

bad = re.search(r"\bdelve|\bleverag|\bseamless|\brobust|\butiliz|\butilis|i hope this (?:email|message) finds you|reach(?:ing)? out|reached out", lc)
if bad:
    fails.append("AI-tell: " + bad.group(0))

if not re.search(r"\$\s?540\b", r):
    fails.append("missing $540")
if not re.search(r"\boct(?:ober|\.)?\s*30(?:th)?\b|\b10/30\b", lc):
    fails.append("missing Oct 30")

free = (re.search(r"\bfree\b(?!\s+to\b)", lc)
        or re.search(r"(?:admin|administrator)[^.]{0,80}(?:approv|allow)", lc)
        or re.search(r"manual(?:ly)?\s+approv", lc)
        or re.search(r"\bno[- ](?:fee|charge|cost)\b|\bcosts? nothing\b|\bwithout paying\b", lc))
if not free:
    fails.append("no free/manual alternative")

if fails:
    print("FAIL: " + "; ".join(fails), file=sys.stderr)
    sys.exit(1)
print("PASS: humanized email keeps $540, Oct 30, and the free path")
'
