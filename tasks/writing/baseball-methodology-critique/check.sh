#!/bin/bash
set -uo pipefail

# check.sh — writing/baseball-methodology-critique (baseball-research-advisor)
# PASS iff the critique names >=2 of 3 planted flaws: (A) leakage from a random split
# on time-ordered data, (B) label/target leakage from same-season outcome features,
# (C) accuracy is the wrong metric on a 6%-positive imbalanced problem.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"
LC="$(printf '%s' "$RESULT" | tr '[:upper:]' '[:lower:]')"
has() { printf '%s' "$LC" | grep -Eiq "$1"; }

# A: temporal leakage / wrong split
A=0
if { has 'random split' && has 'leak'; } || has 'temporal' || has 'time.?based split' || \
   has 'forward.?chain' || has 'look.?ahead' || has 'time.?series split' || \
   { has 'shuffl' && has 'leak'; } || has 'train on future' || has 'future season'; then A=1; fi

# B: label / target leakage from same-season features
B=0
if has 'target leak' || has 'label leak' || has 'data leak' || \
   { has 'same season' && has 'leak'; } || { has 'outcome' && has 'feature'; } || \
   { has 'days on the injured' && has 'leak'; } || has 'leakage'; then B=1; fi

# C: accuracy wrong metric on imbalanced data
C=0
if { has 'accuracy' && { has 'imbalanc' || has 'baseline' || has 'rare' || has '6%' || has 'class' ; }; } || \
   has 'precision' || has 'recall' || has '\bauc\b' || has 'pr curve' || has 'roc' || \
   has 'f1'; then C=1; fi

score=$((A + B + C))
echo "signals: split_leak=$A label_leak=$B metric=$C  (need >=2)" >&2
if [ "$score" -ge 2 ]; then
    echo "PASS: critique named $score/3 of the serious methodology flaws"
    exit 0
fi
echo "FAIL: critique named only $score/3 flaws (need >=2)" >&2
exit 1
