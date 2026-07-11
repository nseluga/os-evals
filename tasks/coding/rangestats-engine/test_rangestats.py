#!/usr/bin/env python3
"""Vendored gate for the rangestats-engine task (authored by the harness, not the model).

Three gates on the model's LiveStats in WORKSPACE_DIR:
  1. CORRECTNESS — interleaved record/query vs a brute-force oracle (+ validation, boundaries).
  2. PERFORMANCE — a large interleaved workload must finish under PERF_BUDGET seconds.
     A too-slow (O(N)-per-query) design is interrupted by SIGALRM and fails fast.
  3. SCALABILITY — elapsed at 4x the size must grow sub-quadratically (ratio < 8;
     linearithmic ~4x, quadratic ~16x).

Exit: 0 = all pass, 1 = a real failure, 2 = infra (workspace/module missing).
Stdlib only; deterministic (seeded RNG); no network, no running app.
"""
import importlib
import os
import random
import signal
import sys
import time
from pathlib import Path

PERF_BUDGET = 15.0   # seconds for the 200k-op interleaved workload (good soln: ~1-3s)
BIG_OPS = 200_000
DOMAIN = 1_000_000

WS = os.environ.get("WORKSPACE_DIR", "")
if not WS or not os.path.isdir(WS):
    print("INFRA: WORKSPACE_DIR unset or missing", file=sys.stderr)
    sys.exit(2)

live_py = Path(WS) / "src" / "rangestats" / "live_stats.py"
if not live_py.is_file():
    print(f"FAIL: expected src/rangestats/live_stats.py under {WS}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(WS) / "src"))
try:
    importlib.import_module("rangestats")
    LiveStats = importlib.import_module("rangestats.live_stats").LiveStats
except Exception as e:
    print(f"FAIL: could not import model's LiveStats: {e!r}", file=sys.stderr)
    sys.exit(1)

failures = []
def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)

class _Timeout(Exception):
    pass

def _alarm(signum, frame):
    raise _Timeout()

# ------------------------------------------------------------ 1. correctness
rng = random.Random(1234)
ls = LiveStats()
seen = []
mismatch = False
for _ in range(3000):
    if seen and rng.random() < 0.5:
        q = rng.randint(0, DOMAIN + 1)
        if ls.count_below(q) != sum(1 for s in seen if s < q):
            mismatch = True; break
        if ls.sum_below(q) != sum(s for s in seen if s < q):
            mismatch = True; break
    else:
        v = rng.randint(0, DOMAIN)
        ls.record(v); seen.append(v)
ok("interleaved record/count_below/sum_below match brute-force oracle", not mismatch)

ls = LiveStats()
ok("empty stream count_below == 0", ls.count_below(500) == 0)
ok("empty stream sum_below == 0", ls.sum_below(500) == 0)
ls.record(0); ls.record(10); ls.record(10); ls.record(1_000_000)
ok("strictly-less-than excludes equals (count_below(10)==1)", ls.count_below(10) == 1)
ok("sum_below(11) includes the two 10s and the 0", ls.sum_below(11) == 20)
ok("count_below(0) == 0 boundary", ls.count_below(0) == 0)
ok("count_below(1_000_001) includes all", ls.count_below(1_000_001) == 4)

def expect_valueerror(name, fn):
    try:
        fn(); ok(name, False)
    except ValueError:
        ok(name, True)
    except Exception as e:
        ok(name + f" (raised {type(e).__name__})", False)

ls = LiveStats()
expect_valueerror("record rejects out-of-range (>domain)", lambda: ls.record(DOMAIN + 1))
expect_valueerror("record rejects negative", lambda: ls.record(-1))
expect_valueerror("record rejects non-int (float)", lambda: ls.record(3.5))
expect_valueerror("record rejects bool", lambda: ls.record(True))

# ------------------------------------------------------------ helper: timed workload
def run_workload(n_ops, seed):
    rng = random.Random(seed)
    ls = LiveStats()
    n_recorded = 0
    t0 = time.perf_counter()
    for _ in range(n_ops):
        if n_recorded and rng.random() < 0.5:
            ls.count_below(rng.randint(0, DOMAIN + 1))
            ls.sum_below(rng.randint(0, DOMAIN + 1))
        else:
            ls.record(rng.randint(0, DOMAIN)); n_recorded += 1
    return time.perf_counter() - t0

# ------------------------------------------------------------ 2. performance (alarm-guarded)
signal.signal(signal.SIGALRM, _alarm)
signal.setitimer(signal.ITIMER_REAL, PERF_BUDGET)
perf_elapsed = None
try:
    perf_elapsed = run_workload(BIG_OPS, seed=42)
    signal.setitimer(signal.ITIMER_REAL, 0)
except _Timeout:
    signal.setitimer(signal.ITIMER_REAL, 0)
ok(f"performance: {BIG_OPS} interleaved ops under {PERF_BUDGET}s "
   f"(elapsed={perf_elapsed:.2f}s)" if perf_elapsed is not None
   else f"performance: {BIG_OPS} ops did NOT finish within {PERF_BUDGET}s (O(N)-per-query?)",
   perf_elapsed is not None)

# ------------------------------------------------------------ 3. scalability (ratio, alarm-guarded)
small_elapsed = big_elapsed = None
signal.setitimer(signal.ITIMER_REAL, PERF_BUDGET * 2)
try:
    small_elapsed = run_workload(50_000, seed=7)
    big_elapsed = run_workload(200_000, seed=7)
    signal.setitimer(signal.ITIMER_REAL, 0)
except _Timeout:
    signal.setitimer(signal.ITIMER_REAL, 0)

if small_elapsed and big_elapsed and small_elapsed > 0:
    ratio = big_elapsed / small_elapsed
    ok(f"scalability: 4x size grows sub-quadratically "
       f"(ratio={ratio:.1f}, small={small_elapsed:.3f}s big={big_elapsed:.3f}s, want <8)",
       ratio < 8.0)
else:
    ok("scalability: 4x-size run did not complete (too slow / quadratic)", False)

print()
if failures:
    print("FAILURES: " + "; ".join(failures), file=sys.stderr)
    sys.exit(1)
print("ALL CHECKS PASSED")
sys.exit(0)
