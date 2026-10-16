# Rubric: tests for a function with a documented contract

The author was given `bank.py` with `apply_discount(price, pct)`, whose docstring says the percentage is clamped to the range 0-100, and asked to write `test_solution.py`: a thorough test file, runnable as `python3 test_solution.py`, that exits non-zero on any failed check, uses no third-party packages, covers normal and edge cases implied by the docstring (a percentage above 100 or below 0), and does not modify `bank.py`. A correct implementation must pass the tests; one that does not honour the documented clamping must fail them.

The artifact is the content of `test_solution.py`. Judge only the artifact.

## Scale
- 5: Exercises both out-of-range directions (above 100 and below 0) and the exact boundaries (0 and 100), plus ordinary mid-range values; expected values are computed from the documented contract (clamp, then discount) and are numerically correct; failures make the script exit non-zero; stdlib only; reads as focused and maintainable.
- 4: Covers both out-of-range directions with correct expected values and at least one boundary; minor gaps (e.g. no price-zero or float case) or small style problems.
- 3: Covers only one out-of-range direction, or covers both but with an expected value that is wrong or ambiguous; otherwise sound.
- 2: Happy-path and one trivial boundary only; the documented clamping is not really exercised, or a failing check would not make the script exit non-zero.
- 1: A token test that cannot distinguish a clamping implementation from a non-clamping one.
- 0: Missing, does not run, imports a third-party package, or modifies the module under test instead of testing it.

## Does not earn points
- Number of assertions: ten happy-path checks are worth no more than two.
- Tests whose expected values are derived by copying the buggy behaviour (for example expecting a negative price).
- Wrapping failures in try/except so the script exits zero.
- Comments praising the tests; judge what they assert.
