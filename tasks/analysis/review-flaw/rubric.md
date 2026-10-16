# Rubric: code review of a small service module

The author was asked to review a Python module (`user_service.py`) before it ships, covering security, efficiency and reliability, reporting concrete issues most serious first and, for each, what it is and why it matters, without rewriting the file. The module builds a SQL query with string formatting from a caller-supplied username, hard-codes a live API key in source and sends it to a billing endpoint, and joins users to orders with a nested loop (quadratic). It also never closes its database connection and calls `requests.post` with no timeout or error handling.

Judge only the artifact.

## Scale
- 5: Identifies the SQL injection as the most serious issue and explains the exploit or consequence and the fix (parameterised query); also identifies the hard-coded secret and the quadratic join with why each matters; ordering reflects severity; adds at least one further real reliability issue (no timeout, unclosed connection, no error handling); no false claims.
- 4: Names SQL injection prominently, marked most serious, with the correct fix, and at least one of the other two planted issues with a reason (a stated complexity or consequence, or a correct remedy, counts as a reason); a terse but accurate review can earn a 4; may be thin on reliability or ordering.
- 3: Names SQL injection but gives little explanation and no other issue with a reason, or names the secret and the quadratic loop but treats injection as minor or misses its fix.
- 2: Identifies only secondary issues (for example only the loop), or lists issues with no reasoning.
- 1: Generic review advice ("add tests", "improve naming") with no concrete flaw tied to the code.
- 0: Says the code is fine, is empty, or rewrites the file instead of reviewing it.

## Does not earn points
- Style nits (naming, docstrings, formatting) presented as findings.
- Claimed flaws that are not in the code.
- A full rewrite of the module in place of a review.
- Listing issues without saying why they matter.
