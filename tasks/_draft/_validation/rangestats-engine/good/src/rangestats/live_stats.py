"""LiveStats — online order-statistics over a bounded integer score domain.

Two parallel Fenwick (binary-indexed) trees keyed on the score value give
O(log domain) record / count_below / sum_below and O(domain) memory, so the engine
stays sub-linear as the interleaved stream grows.
"""

DOMAIN = 1_000_000


class LiveStats:
    def __init__(self) -> None:
        # 1-based Fenwick trees over value positions 1..DOMAIN+1 (value v -> index v+1).
        self._size = DOMAIN + 1
        self._count = [0] * (self._size + 1)
        self._sum = [0] * (self._size + 1)

    def record(self, score: int) -> None:
        """Ingest one score. ValueError if not an int in [0, DOMAIN]."""
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError("score must be an int")
        if score < 0 or score > DOMAIN:
            raise ValueError("score out of range [0, %d]" % DOMAIN)
        i = score + 1
        while i <= self._size:
            self._count[i] += 1
            self._sum[i] += score
            i += i & (-i)

    @staticmethod
    def _prefix(tree, idx: int) -> int:
        total = 0
        while idx > 0:
            total += tree[idx]
            idx -= idx & (-idx)
        return total

    def count_below(self, score: int) -> int:
        """Number of recorded scores strictly less than ``score``."""
        idx = min(max(score, 0), self._size)
        return self._prefix(self._count, idx)

    def sum_below(self, score: int) -> int:
        """Sum of recorded scores strictly less than ``score``."""
        idx = min(max(score, 0), self._size)
        return self._prefix(self._sum, idx)
