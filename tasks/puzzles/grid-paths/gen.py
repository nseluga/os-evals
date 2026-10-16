#!/usr/bin/env python3
"""gen.py --seed N [--key] -- grid-paths puzzle instance (stdlib only).
Prints the prompt for seed N; with --key also prints the answer key after a marker line."""
import argparse
import random

N, BLOCKED = 10, 12


def solve(blocked, a, b):
    s, e = (0, 0), (N - 1, N - 1)

    def paths(x, y, bad):
        if x in bad or y in bad or y[0] < x[0] or y[1] < x[1]:
            return 0
        dp = {x: 1}
        for r in range(x[0], y[0] + 1):
            for c in range(x[1], y[1] + 1):
                if (r, c) != x and (r, c) not in bad:
                    dp[(r, c)] = dp.get((r - 1, c), 0) + dp.get((r, c - 1), 0)
        return dp.get(y, 0)

    bad = set(blocked)
    via = lambda m: paths(s, m, bad) * paths(m, e, bad)
    pa, pb = via(a), via(b)
    both = paths(s, a, bad) * paths(a, b, bad) * paths(b, e, bad) + paths(s, b, bad) * paths(b, a, bad) * paths(a, e, bad)
    neither = paths(s, e, bad | {a, b})
    return {"exactly_one": pa + pb - 2 * both, "either": pa + pb - both, "both": both, "neither": neither,
            "total": paths(s, e, bad)}


def make(seed):
    rng = random.Random(seed)
    cells = [(r, c) for r in range(N) for c in range(N) if (r, c) not in ((0, 0), (N - 1, N - 1))]
    while True:
        pick = rng.sample(cells, BLOCKED + 2)
        blocked, a, b = pick[:BLOCKED], pick[BLOCKED], pick[BLOCKED + 1]
        k = solve(blocked, a, b)
        # non-trivial, and the answer differs from each distractor reading
        if k["exactly_one"] > 100 and len({k["exactly_one"], k["either"], k["both"], k["neither"]}) == 4 and k["both"] > 0 and k["neither"] > 0:
            return blocked, a, b, k


def render(blocked, a, b):
    g = [["." for _ in range(N)] for _ in range(N)]
    for r, c in blocked:
        g[r][c] = "#"
    g[a[0]][a[1]], g[b[0]][b[1]] = "A", "B"
    g[0][0], g[N - 1][N - 1] = "S", "E"
    hdr = "     " + " ".join(str(c + 1) for c in range(N - 1)) + " 10"
    rows = [f"r{r + 1:<2}  " + " ".join(g[r]) for r in range(N)]
    return "\n".join([hdr] + rows)


def prompt(blocked, a, b):
    rc = lambda p: f"(row {p[0] + 1}, col {p[1] + 1})"
    return f"""Here is a 10x10 grid. Rows are numbered 1-10 from the top, columns 1-10 from the left.

{render(blocked, a, b)}

Legend: S = start, row 1 col 1. E = end, row 10 col 10. # = blocked cell, which a path may never enter. . = open cell. A and B are two marked checkpoint cells (open): A is {rc(a)} and B is {rc(b)}.

Blocked cells: {", ".join(rc(p) for p in sorted(blocked))}.

A path starts at S and ends at E. Each step moves exactly one cell right or one cell down, and never enters a blocked cell. Count the paths that pass through EXACTLY ONE of the two checkpoints A and B: they visit A or B but not both.

Work it out however you like. End your reply with one final line in exactly this form, with a plain integer:

ANSWER: <number>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key", action="store_true")
    a = ap.parse_args()
    blocked, ca, cb, k = make(a.seed)
    print(prompt(blocked, ca, cb))
    if a.key:
        print("\n=== KEY ===")
        for name in ("exactly_one", "either", "both", "neither", "total"):
            print(f"{name}={k[name]}")
