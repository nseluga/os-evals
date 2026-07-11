#!/bin/bash
set -uo pipefail

# check.sh — coding/dashboard-a11y (dt-ui)
# Parse the remediated index.html with the stdlib and assert four objective a11y fixes.

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi

HTML="$WS/index.html"
[ -f "$HTML" ] || { echo "FAIL: index.html missing from workspace" >&2; exit 1; }

WS="$WS" python3 - <<'PY'
import os, sys
from html.parser import HTMLParser

html = open(os.path.join(os.environ["WS"], "index.html"), encoding="utf-8").read()

class A11y(HTMLParser):
    def __init__(self):
        super().__init__()
        self.problems = []
        self.btn_stack = []        # (attrs_dict, accumulated_text, had_child_control)
        self.labels_for = set()    # <label for="..."> targets
        self.inputs = []           # list of input attr dicts
        self.clickable_bare = 0    # bare non-interactive elements with onclick

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "img":
            if not a.get("alt", "").strip():
                self.problems.append("an <img> has no non-empty alt text")
        elif tag == "label" and a.get("for", "").strip():
            self.labels_for.add(a["for"].strip())
        elif tag == "input":
            if a.get("type", "text").lower() not in ("hidden", "submit", "button", "reset", "image"):
                self.inputs.append(a)
        elif tag == "button":
            self.btn_stack.append([a, ""])
        elif tag in ("div", "span"):
            if a.get("onclick", "").strip():
                role = a.get("role", "").strip().lower()
                has_tabindex = "tabindex" in a
                if role not in ("button", "link") or not has_tabindex:
                    self.clickable_bare += 1

    def handle_data(self, data):
        if self.btn_stack:
            self.btn_stack[-1][1] += data

    def handle_endtag(self, tag):
        if tag == "button" and self.btn_stack:
            a, text = self.btn_stack.pop()
            named = bool(text.strip()) or any(
                a.get(k, "").strip() for k in ("aria-label", "aria-labelledby", "title")
            )
            if not named:
                self.problems.append("an icon-only <button> has no accessible name")

p = A11y()
p.feed(html)

# inputs: each needs aria-label/title, or a <label for> tied to its id
for a in p.inputs:
    named = any(a.get(k, "").strip() for k in ("aria-label", "aria-labelledby", "title"))
    iid = a.get("id", "").strip()
    if iid and iid in p.labels_for:
        named = True
    if not named:
        p.problems.append("a text input has no associated label")

if p.clickable_bare:
    p.problems.append(f"{p.clickable_bare} clickable bare element(s) (div/span with onclick, not a real control)")

if p.problems:
    for msg in p.problems:
        print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)
print("PASS: images, controls, inputs, and click targets are all accessible")
sys.exit(0)
PY
rc=$?
[ "$rc" -eq 0 ] && echo "PASS: dashboard-a11y remediation meets all criteria"
exit $rc
