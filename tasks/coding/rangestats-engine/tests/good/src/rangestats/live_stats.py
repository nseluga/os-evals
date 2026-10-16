DOMAIN = 1_000_000


class LiveStats:
    def __init__(self):
        self._n = DOMAIN + 2
        self._cnt = [0] * (self._n + 1)
        self._sum = [0] * (self._n + 1)

    def record(self, v):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > DOMAIN:
            raise ValueError("bad score")
        i = v + 1
        while i <= self._n:
            self._cnt[i] += 1
            self._sum[i] += v
            i += i & -i

    def _q(self, t, q):
        if q <= 0:
            return 0
        i = min(q, DOMAIN + 1)  # values < q  <=> index <= q (1-based)
        s = 0
        while i > 0:
            s += t[i]
            i -= i & -i
        return s

    def count_below(self, q):
        return self._q(self._cnt, q)

    def sum_below(self, q):
        return self._q(self._sum, q)
