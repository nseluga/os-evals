"""NAIVE reference (BAD): list + per-query linear scan.

Correct, but O(N) per query -> O(N^2) over an interleaved run. Passes the
correctness/validation gates, then blows the SIGALRM-guarded performance and
scalability budgets.
"""

DOMAIN = 1_000_000


class LiveStats:
    def __init__(self) -> None:
        self._scores = []

    def record(self, score: int) -> None:
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError("score must be an int")
        if score < 0 or score > DOMAIN:
            raise ValueError("score out of range [0, %d]" % DOMAIN)
        self._scores.append(score)

    def count_below(self, score: int) -> int:
        return sum(1 for s in self._scores if s < score)

    def sum_below(self, score: int) -> int:
        return sum(s for s in self._scores if s < score)
