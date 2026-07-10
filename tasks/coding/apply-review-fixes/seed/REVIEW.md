# Code review — handler.py

Three issues must be fixed before this ships:

1. **SECURITY — hardcoded secret.** `TOKEN` is a live API secret committed in source.
   Read it from the environment (e.g. `os.environ`) instead of hardcoding it.

2. **SECURITY — `eval` on untrusted input.** `parse_payload` runs `eval(raw)` on request
   bodies, which is arbitrary code execution. Parse the payload safely instead
   (e.g. `json.loads`).

3. **RELIABILITY — no request timeout.** `fetch` calls `requests.get` with no timeout, so
   a hung server blocks the caller forever. Pass a `timeout`.
