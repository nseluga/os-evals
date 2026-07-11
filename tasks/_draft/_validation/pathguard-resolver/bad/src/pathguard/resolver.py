"""NAIVE reference (BAD): join + normpath + str.startswith.

Passes the happy path, validation, and simple `../` traversal, but is bypassable
two ways the check probes: normpath does not follow symlinks (symlink escape),
and startswith treats /x/data-evil as inside /x/data (sibling-prefix bypass).
"""
import os

from pathguard.errors import PathSecurityError, PathValidationError


def resolve(base_dir: str, user_path: str) -> str:
    if not isinstance(user_path, str):
        raise PathValidationError("user_path must be a string")
    if "\x00" in user_path:
        raise PathValidationError("user_path contains a NUL byte")

    base = os.path.normpath(os.path.abspath(base_dir))

    stripped = user_path.strip()
    if stripped in ("", ".", "./"):
        return base

    if os.path.isabs(user_path):
        raise PathValidationError("user_path must be relative")

    candidate = os.path.normpath(os.path.join(base, user_path))
    if not candidate.startswith(base):
        raise PathSecurityError("resolved path escapes the base directory")
    return candidate
