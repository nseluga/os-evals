# Eval System Design — Setup vs. Bare Claude

**Purpose:** an optimization loop that tells you which layers of the ~/os setup earn their keep — not a one-time verdict.

## Comparison arms — 4-rung ablation ladder (isolated via per-arm config dirs)
1. Bare Claude Code — no CLAUDE.md, no memory, no skills
2. + global CLAUDE.md / OS knowledge routing
3. + memory (behavior-instructions only — so rung 3's checks target working-style adherence and token efficiency; a small quality delta there means "memory doing its narrow job")
4. + skills (full setup)

## Task suite
12 tasks frozen from real work — 4 coding, 4 analysis, 4 writing/knowledge. Contaminated tasks (whose conclusions live in project READMEs / library notes) are allowed but flagged, with rung-2 results split into knowledge-informed vs. clean groups. Claude drafts all tasks and checks from session history; the user personally approves every check, watching specifically for setup-flattering drafts.

## Execution
Headless `claude -p` one-shots against frozen workspace states (git-SHA references, tarball fallback). Ladder runs on Sonnet 4.6 (48 runs = 12 tasks × 4 rungs); plus a bare-vs-full spot check on an Opus-tier model (+24 runs = 12 tasks × 2 rungs) to test whether a stronger model makes the scaffolding redundant. 72 runs per full iteration.

## Scoring — objective-first
- **Primary:** authored pass/fail checks (tests for code; assertions for analysis/writing)
- **Process:** hard transcript stats — turns, retries, reverted edits, tokens on abandoned paths, clarifying questions asked
- **Efficiency:** total tokens / cost
- **Secondary only:** blind pairwise LLM judgment on final artifacts, reported in a quarantined appendix, never merged into headline numbers

## Statistics
1 run per cell. Significance via paired sign-test across the 12 tasks per rung-pair ("rung 4 beat rung 1 on 10/12" is the evidence shape). Per-task and per-category verdicts treated as directional.

## Cadence & reporting
Manual runs after meaningful setup changes, stamped with the ~/os git SHA. Each run emits a markdown scorecard with pre-committed action thresholds (e.g., "layer wins ≤7/12 two runs in a row → prune candidate"), tuned after real variance is seen.

## Location
New ~/os-evals repo (harness, tasks, checks, scorecards) + pointer README in ~/os/projects/.

## Open build-time details (to resolve later)
- Exact config-dir isolation mechanics for each rung (CLAUDE_CONFIG_DIR).
- How `claude -p` bills on the current plan — set concrete threshold values once real variance is seen.
