#!/usr/bin/env python3
"""Vendored gate for the pathguard-resolver task (authored by the harness, not the model).

Loads the model's src/pathguard from WORKSPACE_DIR and runs a functional-correctness
battery plus a security attack battery (traversal, absolute path, NUL byte, symlink
escape, sibling-prefix bypass). Also greps the source for injection/shell-out patterns.

Exit: 0 = all pass, 1 = a real failure, 2 = infra (workspace/module missing).
Stdlib only; creates its own throwaway temp dirs (no network, no running app).
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

WS = os.environ.get("WORKSPACE_DIR", "")
if not WS or not os.path.isdir(WS):
    print("INFRA: WORKSPACE_DIR unset or missing", file=sys.stderr)
    sys.exit(2)

PKG = Path(WS) / "src" / "pathguard"
resolver_py = PKG / "resolver.py"
errors_py = PKG / "errors.py"
if not resolver_py.is_file() or not errors_py.is_file():
    print(f"FAIL: expected src/pathguard/resolver.py and errors.py under {WS}", file=sys.stderr)
    # Missing deliverable is a real task failure, not infra.
    sys.exit(1)

# Import the model's package from the workspace.
sys.path.insert(0, str(Path(WS) / "src"))
try:
    for mod in ("pathguard", "pathguard.errors", "pathguard.resolver"):
        importlib.import_module(mod)
    from pathguard.resolver import resolve
    from pathguard.errors import PathValidationError, PathSecurityError
except Exception as e:  # import/syntax error is a task failure
    print(f"FAIL: could not import model's pathguard: {e!r}", file=sys.stderr)
    sys.exit(1)

failures = []
def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)

def expect_raises(name, exc, fn):
    try:
        got = fn()
        ok(name + f" (expected {exc.__name__}, returned {got!r})", False)
    except exc:
        ok(name, True)
    except Exception as e:  # wrong exception type still counts as a miss
        ok(name + f" (raised {type(e).__name__}, wanted {exc.__name__})", False)

# ------------------------------------------------------------------ fixtures
base = Path(tempfile.mkdtemp(prefix="pg_base_"))
outside = Path(tempfile.mkdtemp(prefix="pg_out_"))
(base / "reports").mkdir()
(base / "reports" / "q1.csv").write_text("data")
# A sibling dir sharing a name prefix with base — for the startswith-bypass test.
sibling = Path(str(base) + "-evil")
sibling.mkdir(exist_ok=True)
(sibling / "secret.txt").write_text("top secret")
# A symlink INSIDE base that points OUTSIDE base.
escape_link = base / "escape"
try:
    escape_link.symlink_to(outside, target_is_directory=True)
    have_symlink = True
except OSError:
    have_symlink = False

realbase = os.path.realpath(base)

# ------------------------------------------------------------- correctness
r = resolve(str(base), "reports/q1.csv")
ok("resolve nested path is absolute + inside base",
   os.path.isabs(r) and os.path.realpath(r) == os.path.join(realbase, "reports", "q1.csv"))

r = resolve(str(base), "reports/does-not-exist-yet.csv")
ok("resolve non-existent file under base is allowed",
   os.path.realpath(r) == os.path.join(realbase, "reports", "does-not-exist-yet.csv"))

for emptyish in ("", ".", "./"):
    r = resolve(str(base), emptyish)
    ok(f"resolve({emptyish!r}) -> base itself", os.path.realpath(r) == realbase)

# ------------------------------------------------------------- validation errors
expect_raises("NUL byte -> PathValidationError", PathValidationError,
              lambda: resolve(str(base), "a\x00b"))
expect_raises("absolute path -> PathValidationError", PathValidationError,
              lambda: resolve(str(base), "/etc/passwd"))
expect_raises("non-string user_path -> PathValidationError", PathValidationError,
              lambda: resolve(str(base), 12345))

# ------------------------------------------------------------- security escapes
expect_raises("simple traversal -> PathSecurityError", PathSecurityError,
              lambda: resolve(str(base), "../../etc/passwd"))
expect_raises("mixed traversal -> PathSecurityError", PathSecurityError,
              lambda: resolve(str(base), "reports/../../.."))
# Sibling-prefix bypass: /srv/data vs /srv/data-evil — naive startswith passes this.
expect_raises("sibling-prefix escape -> PathSecurityError", PathSecurityError,
              lambda: resolve(str(base), "../" + Path(str(base) + "-evil").name + "/secret.txt"))
if have_symlink:
    expect_raises("symlink component escaping base -> PathSecurityError", PathSecurityError,
                  lambda: resolve(str(base), "escape/anything.txt"))
else:
    print("SKIP symlink escape (no symlink support on this fs)")

# ------------------------------------------------------------- source hygiene (no shell-out / injection)
src = (resolver_py.read_text() + "\n" + errors_py.read_text())
banned = ("os.system(", "subprocess.", "os.popen(", "eval(", "exec(", "__import__(", "commands.getoutput")
hit = [b for b in banned if b in src]
ok("resolver does not shell out / eval untrusted input", not hit)
if hit:
    print("   offending tokens: " + ", ".join(hit), file=sys.stderr)

print()
if failures:
    print("FAILURES: " + "; ".join(failures), file=sys.stderr)
    sys.exit(1)
print("ALL CHECKS PASSED")
sys.exit(0)
