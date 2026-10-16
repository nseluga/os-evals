#!/usr/bin/env python3
"""gen.py --seed N [--key] -- schedule-optimum puzzle instance (stdlib only).
8 jobs, 2 identical machines, precedence DAG; the optimum makespan comes from exhaustive
branch-and-bound. Prints the prompt; with --key also prints the optimum and one optimal schedule."""
import argparse
import random

NJ, NM = 8, 2


def optimum(dur, pred):
    """Exhaustive B&B over (next job in a topological order, machine). Left-shifting every job
    to its earliest start never hurts, so this covers all semi-active schedules. Returns (best, sched)."""
    best = [sum(dur) + 1, None]
    start, end, free = {}, {}, [0] * NM

    def rec(done, placed):
        if len(done) == NJ:
            ms = max(end.values())
            if ms < best[0]:
                best[0], best[1] = ms, dict((j, (m, start[j])) for j, m in placed)
            return
        seen_empty = False
        for j in range(NJ):
            if j in done or any(p not in done for p in pred[j]):
                continue
            for m in range(NM):
                if free[m] == 0:  # identical empty machines are interchangeable
                    if seen_empty:
                        continue
                    seen_empty = True
                s = max([free[m]] + [end[p] for p in pred[j]])
                if s + dur[j] >= best[0]:  # cannot beat the incumbent
                    continue
                old = free[m]
                start[j], end[j], free[m] = s, s + dur[j], s + dur[j]
                done.add(j); placed.append((j, m))
                rec(done, placed)
                done.discard(j); placed.pop(); free[m] = old
                del start[j], end[j]
            seen_empty = False

    rec(set(), [])
    return best[0], best[1]


def critical_path(dur, pred):
    fin = {}
    for j in range(NJ):  # edges always go low index -> high index
        fin[j] = dur[j] + max([fin[p] for p in pred[j]] + [0])
    return max(fin.values())


def make(seed):
    rng = random.Random(seed)
    while True:
        dur = [rng.randint(2, 9) for _ in range(NJ)]
        pairs = [(i, j) for i in range(NJ) for j in range(i + 1, NJ)]
        edges = sorted(rng.sample(pairs, rng.randint(7, 9)))
        pred = {j: [i for i, k in edges if k == j] for j in range(NJ)}
        opt, sched = optimum(dur, pred)
        # keep it non-trivial: neither the load bound nor the critical path alone gives the optimum
        if opt > max(-(-sum(dur) // NM), critical_path(dur, pred)):
            perm = list(range(NJ)); rng.shuffle(perm)  # hide the topological order in the labels
            return dur, edges, opt, sched, perm


def relabel(dur, edges, sched, perm):
    """Job i is shown as J(perm[i]+1)."""
    d = [0] * NJ
    for i in range(NJ):
        d[perm[i]] = dur[i]
    e = sorted((perm[i], perm[j]) for i, j in edges)
    s = {perm[j]: v for j, v in sched.items()}
    return d, e, s


PROMPT = """Schedule 8 jobs on 2 identical machines, M1 and M2, both free from time 0.

Durations (time units):
{durs}

Precedence constraints (A -> B means B cannot start until A has finished):
{edges}

Rules: each job runs without interruption on exactly one machine; a machine runs one job at a time; start times are non-negative integers; a job may start the moment its last predecessor finishes, and on the same machine a job may start the moment the previous one finishes (no gap needed). The makespan is the time the last job finishes.

Find a schedule with the smallest possible makespan.

End your reply with one line per job in exactly this form, then the makespan:

J<k>: M<m> @ <start>
(one such line for each of J1..J8)
makespan=<n>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key", action="store_true")
    a = ap.parse_args()
    dur, edges, opt, sched, perm = make(a.seed)
    d, e, s = relabel(dur, edges, sched, perm)
    print(PROMPT.format(durs="\n".join(f"J{j + 1}: {d[j]}" for j in range(NJ)),
                        edges="\n".join(f"J{i + 1} -> J{j + 1}" for i, j in e)))
    if a.key:
        print("\n=== KEY ===")
        print(f"makespan={opt}")
        for j in range(NJ):
            print(f"J{j + 1}: M{s[j][0] + 1} @ {s[j][1]}")
        print(f"sum/2={-(-sum(d) // NM)}")
