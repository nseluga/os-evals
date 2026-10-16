# Rubric drafts for the LLM judge (item 1.5) — post-hoc approval

The judge is an appendix only (`stats.judge_appendix`): an unapproved rubric cannot move a headline number. Approve, edit, or delete each file; editing changes `rubric_sha`, so earlier judge entries are re-judged on the next `--judge` run and the human-deck calibration must be redone. Fixture check: `python3 harness/judge.py --validate --task <cat>/<name>` (good >= 4, bad <= 2; real Opus calls, about $0.10 per task).

| Task | Rubric | Artifact the judge sees | Notes |
|---|---|---|---|
| analysis/map-module | tasks/analysis/map-module/rubric.md | final response | Rewards file+function naming and the mutex seam. |
| analysis/qa-failing-test | tasks/analysis/qa-failing-test/rubric.md | `test_solution.py` (meta `judge_files`) | Mirrors the discriminating check, adds readability. |
| analysis/review-flaw | tasks/analysis/review-flaw/rubric.md | final response | Also credits real unplanted issues (no timeout, unclosed connection). |
| analysis/usage-audit | tasks/analysis/usage-audit/rubric.md | final response | Names the toolset by description, not by skill name. |
| coding/apply-review-fixes | tasks/coding/apply-review-fixes/rubric.md | response + diff of `handler.py` vs `seed/` | Penalises unrequested changes. |
| coding/dashboard-a11y | tasks/coding/dashboard-a11y/rubric.md | response + diff of `index.html` vs `seed/` | Judges alt/label quality, which the parser check cannot. |
| writing/baseball-methodology-critique | tasks/writing/baseball-methodology-critique/rubric.md | final response | Three core flaws, severity order. |
| writing/plain-explainer | tasks/writing/plain-explainer/rubric.md | final response | Brevity counts for the asker. |
| writing/portfolio-writeup | tasks/writing/portfolio-writeup/rubric.md | final response | Penalises invented facts: the existing `tests/good` fixture invents file names and validation steps, so expect it to score about 2-3; this task is `default: false` and was not validated. |

Open questions for Nate
- Scale anchors: 4 vs 5 hinges on one extra point per rubric; tighten if the deck shows the judge saturating.
- Rubrics carry no layer or skill names; the usage-audit prompt itself names its subject (the multi-agent toolset), so judge rationales may mention it. `leak` flags only skill names in rationales, and for plain-word skill names only `/name` or "<name> skill".
- review-flaw rubric: tier 4 clarified after validation (terse but accurate review can earn a 4; fixture first scored 3). Validation: plain-explainer good=4 bad=2; review-flaw good=4 bad=0; spend about $0.08.
