# pathguard

A tiny library that resolves untrusted, client-supplied relative paths inside a
fixed base directory for a file-serving service — without allowing escapes.

Layout:

```
src/pathguard/
  __init__.py     # package marker + public API docstring (provided)
  errors.py       # PathValidationError, PathSecurityError   (implement)
  resolver.py     # resolve(base_dir, user_path) -> str        (implement)
```

Standard library only. See the task prompt for the full contract.
