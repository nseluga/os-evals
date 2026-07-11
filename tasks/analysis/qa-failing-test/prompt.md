This workspace has a module `bank.py` with a function `apply_discount(price, pct)`. Its
docstring says the discount percentage is clamped to the range 0–100.

Write a thorough test file `test_solution.py` in the workspace root that imports
`apply_discount` from `bank` and verifies the function actually behaves as documented,
including the boundary and out-of-range cases. A correct implementation must pass your
tests; an implementation that fails to honor the documented contract must fail them.

Requirements for the test file:
- It must be runnable as `python3 test_solution.py` and **exit non-zero if any check
  fails** (use `assert` statements, or `unittest` with `unittest.main()`). Do **not**
  require pytest or any third-party package.
- Test the normal cases AND the edge cases implied by the docstring (e.g. a percentage
  above 100 or below 0).
- Do not modify `bank.py`. Only write `test_solution.py`.
