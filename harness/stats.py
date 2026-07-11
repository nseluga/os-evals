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
    """Average tokens + cost by rung."""
    tok_by_rung: dict[int, list] = defaultdict(list)
    cost_by_rung: dict[int, list] = defaultdict(list)
    for s in scores:
        tok_by_rung[s["rung"]].append(s.get("total_tokens", 0))
        cost_by_rung[s["rung"]].append(s.get("cost_usd", 0) or 0)
    return {
        f"rung{r}": {
            "avg_tokens": round(sum(v) / len(v)) if v else 0,
            "avg_cost": (sum(cost_by_rung[r]) / len(cost_by_rung[r])) if cost_by_rung[r] else 0,
            "total_cost": sum(cost_by_rung[r]),
            "n": len(v),
        }
        for r, v in sorted(tok_by_rung.items())
    }


LAYER_NAMES = {
    (1, 2): "CLAUDE.md / knowledge routing",
    (2, 3): "memory (behavior instructions)",
    (3, 4): "curated skills",
    (1, 4): "full setup vs. bare",
}


def _pass_map(scores: list[dict], model: str) -> dict[tuple, bool]:
    """(task, rung) -> passed, for one model."""
    return {
        (s["task"], s["rung"]): bool(s["passed"])
        for s in scores
        if s.get("model", "") == model
    }


def verdict_section(data: dict, scores: list[dict]) -> list[str]:
    """Plain-English verdict: layer-transition wins, per-task rung matrix, per-skill lift."""
    lines: list[str] = ["## Verdict — does the setup earn its keep?", ""]
    models = sorted({s.get("model", "") for s in scores})
    tasks = sorted({s["task"] for s in scores})
    # task -> curated_skill (first non-empty seen)
    skill_of = {}
    cat_of = {}
    for s in scores:
        skill_of.setdefault(s["task"], s.get("curated_skill", "") or "")
        cat_of.setdefault(s["task"], s.get("category", "") or "")

    for model in models:
        pm = _pass_map(scores, model)
        rungs = sorted({r for (_, r) in pm.keys()})
        lines += [f"### Model: {model}", ""]

        # Per-rung pass rate
        lines += ["**Pass rate by rung:**", ""]
        for r in rungs:
            vals = [pm.get((t, r)) for t in tasks if (t, r) in pm]
            p = sum(1 for v in vals if v)
            lines.append(f"- rung{r}: {p}/{len(vals)} passed")
        lines.append("")

        # Layer-transition wins (fail->pass minus pass->fail on the shared tasks)
        lines += ["**What each added layer bought (fail→pass flips on the next rung):**", ""]
        for lo, hi in [(1, 2), (2, 3), (3, 4), (1, 4)]:
            if lo not in rungs or hi not in rungs:
                continue
            up = down = 0
            flipped_tasks = []
            for t in tasks:
                a, b = pm.get((t, lo)), pm.get((t, hi))
                if a is None or b is None:
                    continue
                if b and not a:
                    up += 1; flipped_tasks.append(t)
                elif a and not b:
                    down += 1
            net = up - down
            label = LAYER_NAMES.get((lo, hi), f"rung{lo}→rung{hi}")
            detail = f" ({', '.join(flipped_tasks)})" if flipped_tasks else ""
            lines.append(
                f"- **{label}** (rung{lo}→{hi}): +{up} / −{down} = net {net:+d}{detail}"
            )
        lines.append("")

        # Per-skill attribution: rung3 -> rung4
        if 3 in rungs and 4 in rungs:
            lines += ["**Per-skill lift (rung3→rung4 — did the specific skill earn its keep?):**", ""]
            lines += ["| Task | Curated skill | rung3 | rung4 | Verdict |",
                      "|------|---------------|-------|-------|---------|"]
            prune = []
            wins = []
            for t in tasks:
                sk = skill_of.get(t, "")
                a, b = pm.get((t, 3)), pm.get((t, 4))
                if a is None or b is None:
                    continue
                av = "✓" if a else "✗"
                bv = "✓" if b else "✗"
                if b and not a:
                    verdict = "skill WON"; wins.append((t, sk))
                elif a and not b:
                    verdict = "regressed ⚠️"
                elif a and b:
                    verdict = "both pass (no lift needed)"
                else:
                    verdict = "both fail — skill did not help"
                    if sk and sk.lower() != "none":
                        prune.append((t, sk))
                lines.append(f"| {t} | {sk or '—'} | {av} | {bv} | {verdict} |")
            lines.append("")
            if wins:
                lines.append("Skills that flipped a task fail→pass at rung4: "
                             + ", ".join(f"`{sk}` ({t})" for t, sk in wins) + ".")
            if prune:
                lines.append("Prune candidates (skill present but task still failed at rung4): "
                             + ", ".join(f"`{sk}` ({t})" for t, sk in prune) + ".")
            lines.append("")

        # Per-task full rung matrix
        lines += ["**Per-task pass matrix:**", ""]
        header = "| Task | Skill | " + " | ".join(f"r{r}" for r in rungs) + " |"
        sep = "|------|-------|" + "|".join("---" for _ in rungs) + "|"
        lines += [header, sep]
        for t in tasks:
            cells = " | ".join("✓" if pm.get((t, r)) else ("✗" if (t, r) in pm else "·") for r in rungs)
            lines.append(f"| {t} | {skill_of.get(t,'') or '—'} | {cells} |")
        lines.append("")

    return lines


def _find_model(scores: list[dict], needle: str) -> str:
    """First model id containing `needle` (e.g. 'sonnet', 'opus'), else ''."""
    for m in sorted({s.get("model", "") for s in scores}):
        if needle in m.lower():
            return m
    return ""


def _cell_pass(scores: list[dict], model: str, rung: int) -> dict[str, bool]:
    """task -> passed, for one (model, rung) cell."""
    return {
        s["task"]: bool(s["passed"])
        for s in scores
        if s.get("model", "") == model and s["rung"] == rung
    }


def cross_model_section(scores: list[dict]) -> list[str]:
    """Cross-model, cross-rung comparisons the per-model ladders can't show.

    Headline question: can a cheaper model with the scaffolding reach what a stronger
    model reaches bare? Compares specific (model, rung) cells per task instead of
    treating each model as an isolated ladder."""
    sonnet = _find_model(scores, "sonnet")
    opus = _find_model(scores, "opus")
    lines: list[str] = ["## Cross-Model Comparison", ""]
    if not (sonnet and opus):
        lines += [
            "_Skipped: need both a sonnet-tier and an opus-tier model in the run set "
            f"(found sonnet={sonnet or 'none'}, opus={opus or 'none'})._",
            "",
        ]
        return lines

    # Comparisons: (label, boosted/cheaper cell A, reference cell B, note)
    comparisons = [
        ("Skill-boosted Sonnet (r4) vs bare Opus (r1)", (sonnet, 4), (opus, 1),
         "Does the full scaffolding let Sonnet reach where bare Opus lands?"),
        ("Full-setup Sonnet (r4) vs full-setup Opus (r4)", (sonnet, 4), (opus, 4),
         "With the same scaffolding, how much raw model headroom remains?"),
        ("Bare Sonnet (r1) vs bare Opus (r1)", (sonnet, 1), (opus, 1),
         "Baseline model gap with no scaffolding on either side."),
    ]

    tasks = sorted({s["task"] for s in scores})
    for label, (m_a, r_a), (m_b, r_b), note in comparisons:
        a = _cell_pass(scores, m_a, r_a)   # boosted / cheaper side
        b = _cell_pass(scores, m_b, r_b)   # reference side
        shared = [t for t in tasks if t in a and t in b]
        if not shared:
            continue
        lines += [f"### {label}", "", f"_{note}_", ""]
        lines += ["| Task | boosted (A) | reference (B) | verdict |",
                  "|------|-------------|---------------|---------|"]
        a_ahead = b_ahead = both_pass = both_fail = 0
        ref_passed = matched_ref = 0
        for t in shared:
            av, bv = a[t], b[t]
            if bv:
                ref_passed += 1
                if av:
                    matched_ref += 1
            if av and bv:
                verdict = "both pass"; both_pass += 1
            elif av and not bv:
                verdict = "**A ahead**"; a_ahead += 1
            elif bv and not av:
                verdict = "B ahead"; b_ahead += 1
            else:
                verdict = "both fail"; both_fail += 1
            lines.append(f"| {t} | {'✓' if av else '✗'} | {'✓' if bv else '✗'} | {verdict} |")
        n = len(shared)
        a_pass = both_pass + a_ahead
        b_pass = both_pass + b_ahead
        reach = "matches or beats" if matched_ref == ref_passed else "falls short of"
        lines += [
            "",
            f"- A (boosted) passed **{a_pass}/{n}**; B (reference) passed **{b_pass}/{n}**.",
            f"- Of the **{ref_passed}** tasks B passed, A also passed **{matched_ref}** "
            f"→ boosted side {reach} the reference on its own passes.",
            f"- A ahead on {a_ahead}, B ahead on {b_ahead}, both pass {both_pass}, both fail {both_fail}.",
            "",
        ]
    return lines


def render_markdown(data: dict, stats: dict, token_stats: dict) -> str:
    lines = ["# Eval Scorecard", ""]
    os_sha = data.get("os_sha", "unknown")
    lines += [f"os SHA: `{os_sha}`", f"runs: {data['run_count']}", ""]

    lines += ["## Token & Cost Usage by Rung", ""]
    lines += ["| Rung | Avg tokens | Avg cost | Total cost | N runs |",
              "|------|-----------|----------|-----------|--------|"]
    grand_total = 0.0
    for rung, ts in token_stats.items():
        grand_total += ts.get("total_cost", 0)
        lines.append(
            f"| {rung} | {ts['avg_tokens']:,} | ${ts.get('avg_cost',0):.4f} | "
            f"${ts.get('total_cost',0):.4f} | {ts['n']} |"
        )
    lines.append(f"| **all** | | | **${grand_total:.4f}** | |")
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

    lines += verdict_section(data, data["scores"])

    lines += cross_model_section(data["scores"])

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
