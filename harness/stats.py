#!/usr/bin/env python3
"""
harness/stats.py

Paired sign-test across tasks per rung-pair.

Inputs:
  scores JSON from score.py (stdin or --scores-file)

Outputs:
  Markdown scorecard to stdout.
  Sign-test: per rung-pair, count tasks where higher rung won.
  "Rung 4 beat rung 1 on X/N tasks" format.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

RUNG_PAIRS = [(1, 2), (2, 3), (3, 4), (1, 4)]
ACTION_THRESHOLD = 7  # wins <= this two runs in a row -> prune candidate


def sign_test(a_wins: int, b_wins: int, ties: int) -> str:
    n = a_wins + b_wins
    if n == 0:
        return "n/a (no discriminating tasks)"
    # One-sided: did higher rung beat lower rung more than half the time?
    return f"{b_wins}/{n} (ties={ties})"


def compute_stats(scores: list[dict]) -> dict:
    """Group scores by task+rung, compute per-rung-pair sign tests."""
    by_task_rung: dict[tuple, dict] = {}
    for s in scores:
        key = (s["task"], s["rung"], s.get("model", ""))
        by_task_rung[key] = s

    tasks = sorted({s["task"] for s in scores})
    models = sorted({s.get("model", "") for s in scores})

    results = {}
    for model in models:
        pair_results = {}
        for lo, hi in RUNG_PAIRS:
            wins_hi = 0
            wins_lo = 0
            ties = 0
            task_verdicts = []
            for task in tasks:
                lo_score = by_task_rung.get((task, lo, model))
                hi_score = by_task_rung.get((task, hi, model))
                if lo_score is None or hi_score is None:
                    task_verdicts.append({"task": task, "verdict": "missing"})
                    continue
                if hi_score["passed"] and not lo_score["passed"]:
                    wins_hi += 1
                    verdict = f"rung{hi} wins"
                elif lo_score["passed"] and not hi_score["passed"]:
                    wins_lo += 1
                    verdict = f"rung{lo} wins"
                else:
                    ties += 1
                    verdict = "tie"
                task_verdicts.append({"task": task, "verdict": verdict})

            pair_results[f"rung{lo}_vs_rung{hi}"] = {
                "higher_wins": wins_hi,
                "lower_wins": wins_lo,
                "ties": ties,
                "sign_test": sign_test(wins_lo, wins_hi, ties),
                "action_flag": wins_hi <= ACTION_THRESHOLD if (wins_hi + wins_lo) >= 3 else False,
                "task_verdicts": task_verdicts,
            }
        results[model] = pair_results

    return {"tasks": tasks, "rung_pairs": results}


def token_summary(scores: list[dict]) -> dict:
    """Average tokens by rung."""
    by_rung: dict[int, list] = defaultdict(list)
    for s in scores:
        by_rung[s["rung"]].append(s.get("total_tokens", 0))
    return {
        f"rung{r}": {
            "avg_tokens": round(sum(v) / len(v)) if v else 0,
            "n": len(v),
        }
        for r, v in sorted(by_rung.items())
    }


def render_markdown(data: dict, stats: dict, token_stats: dict) -> str:
    lines = ["# Eval Scorecard", ""]
    os_sha = data.get("os_sha", "unknown")
    lines += [f"os SHA: `{os_sha}`", f"runs: {data['run_count']}", ""]

    lines += ["## Token Usage by Rung", ""]
    lines += ["| Rung | Avg tokens | N runs |", "|------|-----------|--------|"]
    for rung, ts in token_stats.items():
        lines.append(f"| {rung} | {ts['avg_tokens']:,} | {ts['n']} |")
    lines.append("")

    lines += ["## Pass/Fail by Rung", ""]
    by_rung: dict[int, dict] = defaultdict(lambda: {"pass": 0, "fail": 0})
    for s in data["scores"]:
        if s["passed"]:
            by_rung[s["rung"]]["pass"] += 1
        else:
            by_rung[s["rung"]]["fail"] += 1
    lines += ["| Rung | Pass | Fail |", "|------|------|------|"]
    for r, counts in sorted(by_rung.items()):
        lines.append(f"| rung{r} | {counts['pass']} | {counts['fail']} |")
    lines.append("")

    lines += ["## Paired Sign-Test", ""]
    lines += [
        f"Action threshold: ≤{ACTION_THRESHOLD} wins on ≥3 tasks = prune candidate", ""
    ]
    for model, pairs in stats["rung_pairs"].items():
        lines += [f"### Model: {model}", ""]
        for pair_name, pr in pairs.items():
            flag = " ⚠️ PRUNE CANDIDATE" if pr["action_flag"] else ""
            lines += [
                f"**{pair_name}**: higher rung won {pr['sign_test']}{flag}",
                "",
            ]
            for tv in pr.get("task_verdicts", []):
                lines.append(f"  - {tv['task']}: {tv['verdict']}")
            lines.append("")

    lines += ["## Per-Run Results", ""]
    lines += ["| Task | Rung | Pass | Tokens | Cost |", "|------|------|------|--------|------|"]
    for s in data["scores"]:
        p = "✓" if s["passed"] else "✗"
        lines.append(
            f"| {s['task']} | rung{s['rung']} | {p} | {s.get('total_tokens', 0):,} | ${s.get('cost_usd', 0):.4f} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores-file", default="")
    args = parser.parse_args()

    if args.scores_file:
        data = json.loads(Path(args.scores_file).read_text())
    else:
        data = json.loads(sys.stdin.read())

    scores = data.get("scores", [])
    if not scores:
        print("stats.py: no scores to analyze", file=sys.stderr)
        return 1

    stats = compute_stats(scores)
    token_stats = token_summary(scores)
    md = render_markdown(data, stats, token_stats)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
