Implement a **safe workspace path resolver** for a file-serving service. Untrusted
clients supply relative paths (e.g. from an HTTP request) that must be resolved
*inside* a fixed base directory and never allowed to escape it.

This is a small Python package under `src/pathguard/`. Files:

- `src/pathguard/errors.py` — define two exception types:
  - `PathValidationError(ValueError)` — the input is malformed (empty, wrong type,
    contains a NUL byte, or is an absolute path).
  - `PathSecurityError(ValueError)` — the input is well-formed but resolves to a
    location outside the base directory (traversal or symlink escape).
- `src/pathguard/resolver.py` — implement and export:

  ```python
  def resolve(base_dir: str, user_path: str) -> str:
      ...
  ```

  It returns the **absolute, fully-resolved** path that `user_path` refers to
  *within* `base_dir`. Contract:

  - `base_dir` is trusted (your own configured root). `user_path` is UNTRUSTED.
  - A normal relative path resolves normally:
    `resolve("/srv/data", "reports/q1.csv")` → the absolute path to
    `<realpath of /srv/data>/reports/q1.csv`.
  - `""`, `"."`, and `"./"` resolve to the base directory itself.
  - **Reject with `PathValidationError`**: a non-string `user_path`, an empty-after-strip
    input that is not `.`/`./`, a `user_path` containing a NUL byte (`"\x00"`), or an
    **absolute** `user_path` (e.g. `"/etc/passwd"`).
  - **Reject with `PathSecurityError`**: any `user_path` whose resolved location is not
    inside `base_dir` — this includes `"../"` traversal (`"../../etc/passwd"`,
    `"a/b/../../../.."`), AND the case where a component inside the base is a **symlink
    that points outside the base** (the resolved target escapes, so it must be rejected).
  - The base-containment check must be exact: a sibling directory whose name merely
    shares a prefix with the base (base `/srv/data`, target `/srv/data-evil/x`) is
    OUTSIDE the base and must be rejected. A naive `startswith` comparison is wrong here.
  - The function must be pure and read-only: it must NOT create, move, delete, or open
    files, and must NOT shell out. Resolving must not require the target file to exist
    (a not-yet-created file under the base is a valid resolve), but symlink components
    that DO exist must be followed for the containment decision.

Match the surrounding style (type hints, no `any`-style escapes, small focused
functions). Keep it dependency-free (Python standard library only).
