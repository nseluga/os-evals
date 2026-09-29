DOMAIN = 1_000_000


class LiveStats:
    def __init__(self):
        self._v = []

    def record(self, v):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > DOMAIN:
            raise ValueError("bad score")
        self._v.append(v)

    def count_below(self, q):
        return sum(1 for x in self._v if x < q)

    def sum_below(self, q):
        return sum(x for x in self._v if x < q)
