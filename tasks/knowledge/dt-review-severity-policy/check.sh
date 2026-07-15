#!/bin/bash
# check.sh — dt-review-severity-policy
#
# Key discriminator: Critical AND Important both block exit (require re-QA);
# Minor is applied once by dt-fix without looping. Generic advice hedges
# Important as situational, only Critical firmly blocks.
set -uo pipefail

input=$(cat)

python3 - "$input" <<'PY'
import sys, re

text = sys.argv[1].lower()
sentences = re.split(r'[.!?\n]', text)

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

if "critical" not in text:
    fail("response does not mention Critical findings")

# KEY DISCRIMINATOR: Important must appear in a sentence that contains a blocking
# keyword (block, must, require, loop, re-qa) WITHOUT hedging words (optional,
# situational, discretion, might, may, allow, depends, exceptions, generally).
BLOCK_WORDS = re.compile(r'\b(block|blocks|must|require|requires|loop|re.qa|re-run|prevents|cannot mark done)\b')
HEDGE_WORDS  = re.compile(r'\b(optional|situational|discretion|exception|allow|might|may|could|depends|up to|generally|typical)\b')

important_blocks = False
for s in sentences:
    if "important" in s and BLOCK_WORDS.search(s) and not HEDGE_WORDS.search(s):
        important_blocks = True
        break

# Also accept: "critical and important" or "important and critical" close together
# in the SAME sentence with a blocking word in that sentence.
if not important_blocks:
    for s in sentences:
        if "critical" in s and "important" in s and BLOCK_WORDS.search(s):
            important_blocks = True
            break

if not important_blocks:
    fail("Important not described as blocking — generic advice hedges Important as situational; Nate's loop treats both Critical and Important as blocking (must re-QA)")

if "minor" not in text:
    fail("response does not mention Minor severity tier")

# Minor must appear in a sentence describing it as applied without a QA loop.
APPLIED_WORDS = re.compile(r'\b(applied|fix|once|without|no loop|skip|non.blocking|dont loop|doesn.t loop|no re.qa)\b')
LOOP_WORDS    = re.compile(r'\b(must|require|loops back|re.qa|blocks|block)\b')

minor_no_loop = False
for s in sentences:
    if "minor" in s and APPLIED_WORDS.search(s) and not LOOP_WORDS.search(s):
        minor_no_loop = True
        break

if not minor_no_loop:
    fail("Minor not described as applied once without looping back — response should say Minor findings are applied by dt-fix without another QA pass")

print("PASS: response correctly shows Critical+Important block (re-QA required) and Minor applied without loop")
sys.exit(0)
PY
