#!/bin/bash
# check.sh — memory-terse-response-policy
# Tests whether the model says NOT to add trailing summaries when the user can see
# diffs/tool output. Pass if it recommends against it; fail if it endorses summaries.
set -uo pipefail

input=$(cat)

# FAIL condition: recommends adding a summary (the wrong answer)
# Patterns: "yes, add", "should include", "good practice to summarize", "helpful to list"
if echo "$input" | grep -qiE "(yes.*summar|should.*(add|include|end with|include).*summar|summar.*good practice|good to summar|helpful to.*summar|recommend.*summar)"; then
    echo "FAIL: response recommends adding a trailing summary" >&2
    exit 1
fi

# PASS condition: must explicitly say no, skip, omit, avoid, or don't add trailing summary
if ! echo "$input" | grep -qiE "(no.*summar|skip.*summar|omit.*summar|avoid.*summar|don.t.*summar|not.*add.*summar|unnecessary.*summar|summar.*unnecessary|user.*can.*see|already.*see|can.*see.*diff|see.*diff|redundant|concise|terse)"; then
    echo "FAIL: response does not clearly recommend against trailing summaries" >&2
    exit 1
fi

echo "PASS: response correctly advises against trailing summaries when diffs/output are visible"
exit 0
