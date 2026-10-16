"""Retry helper used by log uploads."""
import time


def with_backoff(fn, tries=4, base=0.5):
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(base * 2**i)
