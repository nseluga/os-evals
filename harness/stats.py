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

RUNG_PAIRS = [(1, 2), (2, 3), (3, 4), (1, 4)]   # legacy int rungs (pre-layers runs)
LADDER = ["bare", "claude-md", "memory", "skills", "full"]


def _rl(r) -> str:
    """Rung label: legacy int rungs render as rung<N>; layer names render as-is."""
    return f"rung{r}" if isinstance(r, int) else str(r)


def _rung_key(r):
    """Sort key: legacy ints first, then layers in ladder order, then anything else by name."""
    if isinstance(r, int):
        return (0, r, "")
    base = str(r).split("@")[0]
    return (1, LADDER.index(base) if base in LADDER else len(LADDER), str(r))


def select_pairs(rungs, order=None) -> list[tuple]:
    """Which (lo, hi) rung pairs to compare.

    Legacy int rungs keep RUNG_PAIRS. Layer names: A/B (`full@A`, `full@B`) pairs the two
    shas in the order given. Otherwise adjacent entries of the ORDER THE USER PASSED are
    paired, wherever they sit in the full ladder (`bare,skills` -> [(bare, skills)]); with
    no order, ladder order is used. Fewer than two layers -> []."""
    present = set(rungs)
    if present and all(isinstance(r, int) for r in present):
        return [(lo, hi) for lo, hi in RUNG_PAIRS if lo in present and hi in present]
    given = list(dict.fromkeys(r for r in (order or []) if r in present))
    ab = [r for r in given if "@" in str(r)]
    if len(ab) < 2:
        ab = sorted((r for r in present if "@" in str(r)), key=_rung_key)
    if len(ab) >= 2:
        return [(ab[0], ab[1])]
    ordered = given if order else sorted(present, key=_rung_key)
    return list(zip(ordered, ordered[1:]))


ACTION_THRESHOLD = 7  # wins <= this two runs in a row -> prune candidate


def sign_test(a_wins: int, b_wins: int, ties: int) -> str:
    n = a_wins + b_wins
    if n == 0:
        return "n/a (no discriminating tasks)"
    # One-sided: did higher rung beat lower rung more than half the time?
    return f"{b_wins}/{n} (ties={ties})"


def _is_sentinel(s: dict) -> bool:
    return bool(s.get("sentinel", False))


def _is_repeat_individual(s: dict) -> bool:
    return bool(s.get("is_repeat_individual", False))


def _is_infra(s: dict) -> bool:
    return bool(s.get("infra_error", False))


def _effective_scores(scores: list[dict]) -> list[dict]:
    """Return scores with individual repeat records replaced by their majority records.

    Individual repeat records (is_repeat_individual=True) are excluded; majority-vote
    records (repeat_majority=True) are included in their place. Non-repeat records pass
    through unchanged."""
    return [s for s in scores if not _is_repeat_individual(s)]


def compute_stats(scores: list[dict], order=None) -> dict:
    """Group scores by task+rung, compute per-rung-pair sign tests.

    Sentinel tasks are excluded — they only run at rung1 and serve as difficulty
    anchors, not as evidence about layer transitions."""
    scored = [s for s in _effective_scores(scores) if not _is_sentinel(s)]

    # infra_error runs are excluded from `by_task_rung` (so they can never win/lose a
    # pairwise comparison) but tracked separately so a comparison touching one is
    # labeled "infra (excluded)" rather than the ambiguous "missing".
    by_task_rung: dict[tuple, dict] = {}
    infra_trm: set[tuple] = set()
    for s in scored:
        key = (s["task"], s["rung"], s.get("model", ""))
        if _is_infra(s):
            infra_trm.add(key)
        else:
            by_task_rung[key] = s

    tasks = sorted({s["task"] for s in scored})
    models = sorted({s.get("model", "") for s in scored})
    pairs = select_pairs({s["rung"] for s in scored}, order)

    results = {}
    for model in models:
        pair_results = {}
        for lo, hi in pairs:
            wins_hi = 0
            wins_lo = 0
            ties = 0
            task_verdicts = []
            for task in tasks:
                if (task, lo, model) in infra_trm or (task, hi, model) in infra_trm:
                    task_verdicts.append({"task": task, "verdict": "infra (excluded)"})
                    continue
                lo_score = by_task_rung.get((task, lo, model))
                hi_score = by_task_rung.get((task, hi, model))
                if lo_score is None or hi_score is None:
                    task_verdicts.append({"task": task, "verdict": "missing"})
                    continue
                if hi_score["passed"] and not lo_score["passed"]:
                    wins_hi += 1
                    verdict = f"{_rl(hi)} wins"
                elif lo_score["passed"] and not hi_score["passed"]:
                    wins_lo += 1
                    verdict = f"{_rl(lo)} wins"
                else:
                    ties += 1
                    verdict = "tie"
                task_verdicts.append({"task": task, "verdict": verdict})

            pair_results[f"{_rl(lo)}_vs_{_rl(hi)}"] = {
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
    """Average tokens + cost by rung. Excludes sentinel tasks, individual repeat records and infra rows."""
    scored = [s for s in _effective_scores(scores) if not _is_sentinel(s) and not _is_infra(s)]
    tok_by_rung: dict[int, list] = defaultdict(list)
    cost_by_rung: dict[int, list] = defaultdict(list)
    for s in scored:
        tok_by_rung[s["rung"]].append(s.get("total_tokens") or 0)
        cost_by_rung[s["rung"]].append(s.get("cost_usd", 0) or 0)
    return {
        _rl(r): {
            "avg_tokens": round(sum(v) / len(v)) if v else 0,
            "avg_cost": (sum(cost_by_rung[r]) / len(cost_by_rung[r])) if cost_by_rung[r] else 0,
            "total_cost": sum(cost_by_rung[r]),
            "n": len(v),
        }
        for r, v in sorted(tok_by_rung.items(), key=lambda kv: _rung_key(kv[0]))
    }


LAYER_NAMES = {
    (1, 2): "CLAUDE.md / knowledge routing",
    (2, 3): "memory (behavior instructions)",
    (3, 4): "curated skills",
    (1, 4): "full setup vs. bare",
    ("bare", "full"): "full setup vs. bare",
    ("bare", "claude-md"): "CLAUDE.md / knowledge routing",
    ("claude-md", "memory"): "memory (behavior instructions)",
    ("memory", "skills"): "skills + agents",
    ("skills", "full"): "output style + full settings",
}


def _pass_map(scores: list[dict], model: str) -> dict[tuple, bool]:
    """(task, rung) -> passed, for one model. Excludes individual repeat records and
    infra_error runs (an infra run is not evidence either way, so it must never look
    like a fail or feed a flip/prune/regressed verdict)."""
    return {
        (s["task"], s["rung"]): bool(s["passed"])
        for s in _effective_scores(scores)
        if s.get("model", "") == model and not _is_infra(s)
    }


def _infra_map(scores: list[dict], model: str) -> set[tuple]:
    """(task, rung) pairs where this model's run was infra_error, for one model."""
    return {
        (s["task"], s["rung"])
        for s in _effective_scores(scores)
        if s.get("model", "") == model and _is_infra(s)
    }


def _repeat_annotation_map(scores: list[dict], model: str) -> dict[tuple, str]:
    """(task, rung) -> annotation string like '(2/3)' for majority-vote records."""
    result = {}
    for s in scores:
        if s.get("repeat_majority") and s.get("model", "") == model:
            k = s.get("repeat_pass_count", 0)
            n = s.get("repeat_total", 0)
            result[(s["task"], s["rung"])] = f"({k}/{n})"
    return result


def verdict_section(data: dict, scores: list[dict]) -> list[str]:
    """Plain-English verdict: layer-transition wins, per-task rung matrix, per-skill lift.

    Sentinel tasks are excluded from all pass-rate counts and sign-test analysis.
    Individual repeat records are excluded; majority-vote records are used instead."""
    scored = [s for s in _effective_scores(scores) if not _is_sentinel(s)]
    sentinel_count = len({s["task"] for s in scores if _is_sentinel(s)})

    lines: list[str] = ["## Verdict — does the setup earn its keep?", ""]

    # Loud warning when the suite has zero discriminating signal.
    # A rung-pair discriminates if ANY task flips pass/fail between its two rungs.
    # If no pair discriminates across any model, the suite cannot attribute value to any layer.
    _by_tr = {(s["task"], s["rung"], s.get("model", "")): s["passed"]
              for s in scored if not _is_infra(s)}
    _all_tasks = sorted({s["task"] for s in scored})
    _all_models = sorted({s.get("model", "") for s in scored})
    _pairs = select_pairs({s["rung"] for s in scored}, data.get("layer_order"))
    _has_any_flip = any(
        _by_tr.get((t, hi, m)) != _by_tr.get((t, lo, m))
        and (t, lo, m) in _by_tr and (t, hi, m) in _by_tr
        for m in _all_models
        for lo, hi in _pairs
        for t in _all_tasks
    )
    if not _pairs:
        lines.append("No rung pairs to compare: fewer than two layers with results, so no "
                     "comparison or discrimination verdict was made.")
        lines.append("")
    elif not _has_any_flip and _all_tasks and _all_models:
        lines.append(
            "⚠️ SUITE HAS NO DISCRIMINATING SIGNAL — every task ties at every rung. "
            "Add tasks bare Claude fails but a scaffolded rung passes."
        )
        lines.append("")

    if sentinel_count:
        lines.append(
            f"_{sentinel_count} task(s) excluded as difficulty anchors "
            f"(fail at every rung including Opus)._"
        )
        lines.append("")

    models = sorted({s.get("model", "") for s in scored})
    tasks = sorted({s["task"] for s in scored})
    # task -> curated_skill (first non-empty seen)
    skill_of = {}
    cat_of = {}
    for s in scored:
        skill_of.setdefault(s["task"], s.get("curated_skill", "") or "")
        cat_of.setdefault(s["task"], s.get("category", "") or "")

    for model in models:
        pm = _pass_map(scored, model)
        infra_map = _infra_map(scored, model)
        repeat_ann = _repeat_annotation_map(scores, model)
        # Rungs come from all scored data (not just pm) so a rung that is 100% infra
        # for this model still gets a row instead of silently vanishing.
        rungs = sorted({s["rung"] for s in scored if s.get("model", "") == model}, key=_rung_key)
        lines += [f"### Model: {model}", ""]

        # Per-rung pass rate. Denominator counts only valid (non-infra) runs; infra
        # runs are called out as a separate count so they're visible without inflating
        # either the pass or fail side.
        lines += ["**Pass rate by rung:**", ""]
        for r in rungs:
            vals = [pm.get((t, r)) for t in tasks if (t, r) in pm]
            p = sum(1 for v in vals if v)
            infra_n = sum(1 for t in tasks if (t, r) in infra_map)
            infra_note = f", {infra_n} infra" if infra_n else ""
            lines.append(f"- {_rl(r)}: {p}/{len(vals)} passed{infra_note}")
        lines.append("")

        # Layer-transition wins (fail->pass minus pass->fail on the shared tasks)
        lines += ["**What each added layer bought (fail→pass flips on the next rung):**", ""]
        for lo, hi in _pairs:
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
            label = LAYER_NAMES.get((lo, hi), f"{_rl(lo)}→{_rl(hi)}")
            detail = f" ({', '.join(flipped_tasks)})" if flipped_tasks else ""
            lines.append(
                f"- **{label}** ({_rl(lo)}→{_rl(hi)}): +{up} / −{down} = net {net:+d}{detail}"
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
        header = "| Task | Skill | " + " | ".join(f"r{r}" if isinstance(r, int) else str(r) for r in rungs) + " |"
        sep = "|------|-------|" + "|".join("---" for _ in rungs) + "|"
        lines += [header, sep]
        for t in tasks:
            def _cell(t: str, r: int) -> str:
                if (t, r) in infra_map:
                    return "infra"
                if (t, r) not in pm:
                    return "·"
                sym = "✓" if pm[(t, r)] else "✗"
                ann = repeat_ann.get((t, r), "")
                return f"{sym}{ann}" if ann else sym
            cells = " | ".join(_cell(t, r) for r in rungs)
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
        if s.get("model", "") == model and s["rung"] == rung and not _is_infra(s)
    }


def cross_model_section(scores: list[dict]) -> list[str]:
    """Cross-model, cross-rung comparisons the per-model ladders can't show.

    Headline question: can a cheaper model with the scaffolding reach what a stronger
    model reaches bare? Compares specific (model, rung) cells per task instead of
    treating each model as an isolated ladder. Sentinel tasks are excluded."""
    scores = _effective_scores(scores)
    scored = [s for s in scores if not _is_sentinel(s)]
    sonnet = _find_model(scored, "sonnet")
    opus = _find_model(scored, "opus")
    layered = any(isinstance(s["rung"], str) for s in scored)
    bare, full = ("bare", "full") if layered else (1, 4)
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
        ("Skill-boosted Sonnet (r4) vs bare Opus (r1)", (sonnet, full), (opus, bare),
         "Does the full scaffolding let Sonnet reach where bare Opus lands?"),
        ("Full-setup Sonnet (r4) vs full-setup Opus (r4)", (sonnet, full), (opus, full),
         "With the same scaffolding, how much raw model headroom remains?"),
        ("Bare Sonnet (r1) vs bare Opus (r1)", (sonnet, bare), (opus, bare),
         "Baseline model gap with no scaffolding on either side."),
    ]

    tasks = sorted({s["task"] for s in scored})
    for label, (m_a, r_a), (m_b, r_b), note in comparisons:
        a = _cell_pass(scored, m_a, r_a)   # boosted / cheaper side
        b = _cell_pass(scored, m_b, r_b)   # reference side
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


def difficulty_anchors_section(scores: list[dict]) -> list[str]:
    """Render a 'Difficulty Anchors' section for sentinel tasks (rung1 result only).

    No layer attribution — sentinels are expected to fail at all rungs including Opus.
    They serve as a calibration floor, not as scored suite members."""
    sentinel_scores = [s for s in scores if _is_sentinel(s)]
    if not sentinel_scores:
        return []

    lines: list[str] = ["## Difficulty Anchors", ""]
    lines.append(
        "_These tasks are expected to fail at every rung including Opus. "
        "They are excluded from pass/fail counts, sign-test, and cost tables above._"
    )
    lines.append("")
    rung1_scores = [s for s in sentinel_scores if s["rung"] in (1, "bare")]
    if not rung1_scores:
        lines.append("_no rung-1 data for this anchor_")
        lines.append("")
        return lines

    lines += ["| Task | Model | rung1 result | Tokens | Cost |",
              "|------|-------|-------------|--------|------|"]
    for s in sorted(rung1_scores, key=lambda x: (x["task"], x.get("model", ""))):
        p = "infra" if _is_infra(s) else ("✓" if s["passed"] else "✗")
        lines.append(
            f"| {s['task']} | {s.get('model', '—')} | {p} | "
            f"{s.get('total_tokens', 0):,} | ${s.get('cost_usd', 0):.4f} |"
        )
    lines.append("")
    return lines


def render_markdown(data: dict, stats: dict, token_stats: dict,
                    matrix_exit=None, planned=None) -> str:
    all_scores = data["scores"]
    scored = [s for s in _effective_scores(all_scores) if not _is_sentinel(s)]

    lines = ["# Eval Scorecard", ""]
    present = len(data.get("scored_run_ids") or [])
    short = planned is not None and present < planned
    if (matrix_exit not in (None, 0)) or short:
        of = f" of {planned} planned" if planned is not None else " (planned count unavailable)"
        code = f"run_matrix exited with code {matrix_exit}; " if matrix_exit not in (None, 0) else ""
        lines += [f"> ⚠️ **INCOMPLETE MATRIX**: {code}{present} runs present{of}. "
                  f"Everything below covers only the runs that finished.", ""]
    os_sha = data.get("os_sha", "unknown")
    n_anchors = len([s for s in all_scores if _is_sentinel(s)])
    anchor_note = f" (+{n_anchors} anchors)" if n_anchors else ""
    lines += [f"os SHA: `{os_sha}`", f"runs: {len(scored)}{anchor_note}", ""]

    run_ids = data.get("scored_run_ids") or []
    if run_ids:
        stamps = sorted(r.split("_")[0] for r in run_ids)
        lines += [f"scored run ids: {len(run_ids)} ({stamps[0]} to {stamps[-1]})", ""]

    by_reason: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in _effective_scores(all_scores):
        if _is_infra(s):
            by_reason[s.get("infra_reason") or "unspecified"][s["task"]] += 1
    for reason, counts in sorted(by_reason.items(), key=lambda kv: (kv[0] == "contaminated", kv[0])):
        detail = ", ".join(f"{t} ({n})" for t, n in sorted(counts.items()))
        tail = f"({sum(counts.values())} runs across {len(counts)} tasks): {detail}"
        if reason == "contaminated":
            lines += [f"⚠️ contaminated runs (tool calls reached outside the workspace) excluded like infra {tail}", ""]
        else:
            lines += [f"⚠️ infra runs excluded [{reason}] from all comparisons and pass denominators {tail}", ""]

    single = sorted(
        f"{s['task']} @ {_rl(s['rung'])} [{s.get('model', '')}]"
        for s in all_scores
        if s.get("repeat_majority") and not _is_infra(s) and s.get("valid_repeats") == 1
        and (s.get("repeat_total") or 0) > 1
    )
    if single:
        lines += [f"⚠️ cells decided by a single valid repeat ({len(single)}): {', '.join(single)}", ""]

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
    by_rung: dict[int, dict] = defaultdict(lambda: {"pass": 0, "fail": 0, "infra": 0})
    for s in scored:
        if _is_infra(s):
            by_rung[s["rung"]]["infra"] += 1
        elif s["passed"]:
            by_rung[s["rung"]]["pass"] += 1
        else:
            by_rung[s["rung"]]["fail"] += 1
    lines += ["| Rung | Pass | Fail | Infra |", "|------|------|------|-------|"]
    for r, counts in sorted(by_rung.items(), key=lambda kv: _rung_key(kv[0])):
        lines.append(f"| {_rl(r)} | {counts['pass']} | {counts['fail']} | {counts['infra']} |")
    lines.append("")

    lines += ["## Paired Sign-Test", ""]
    lines += [
        f"Action threshold: ≤{ACTION_THRESHOLD} wins on ≥3 tasks = prune candidate", ""
    ]
    if not any(stats["rung_pairs"].values()):
        lines += ["No rung pairs to compare: fewer than two layers with results.", ""]
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

    lines += verdict_section(data, all_scores)

    lines += cross_model_section(all_scores)

    lines += ["## Per-Run Results", ""]
    lines += ["| Task | Rung | Pass | Tokens | Cost |", "|------|------|------|--------|------|"]
    for s in scored:
        p = "infra" if _is_infra(s) else ("✓" if s["passed"] else "✗")
        lines.append(
            f"| {s['task']} | {_rl(s['rung'])} | {p} | {s.get('total_tokens', 0):,} | ${s.get('cost_usd', 0):.4f} |"
        )
    lines.append("")

    lines += difficulty_anchors_section(all_scores)

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores-file", default="")
    parser.add_argument("--matrix-exit", type=int, default=None, help="run_matrix.py exit code")
    parser.add_argument("--planned-runs", type=int, default=None, help="runs run_matrix planned")
    parser.add_argument("--layers", default="", help="layer/rung order for pairing (as given to run.sh)")
    args = parser.parse_args()

    raw = Path(args.scores_file).read_text() if args.scores_file else sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        print("stats.py: scores input is empty or not valid JSON", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("stats.py: scores input is not a JSON object", file=sys.stderr)
        return 1

    scores = data.get("scores", [])
    if not scores:
        print("stats.py: no scores to analyze", file=sys.stderr)
        return 1

    scored = [s for s in _effective_scores(scores) if not _is_sentinel(s)]
    stats = compute_stats(scored, args.layers.split(",") if args.layers else None)
    token_stats = token_summary(scored)
    if args.layers:
        data["layer_order"] = args.layers.split(",")
    md = render_markdown(data, stats, token_stats, args.matrix_exit, args.planned_runs)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
