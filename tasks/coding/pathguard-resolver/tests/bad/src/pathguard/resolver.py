import os

from .errors import PathSecurityError, PathValidationError


def resolve(base, user_path):
    if not isinstance(user_path, str):
        raise PathValidationError("user_path must be a str")
    if "\x00" in user_path:
        raise PathValidationError("NUL byte in path")
    if os.path.isabs(user_path):
        raise PathValidationError("absolute path not allowed")
    cand = os.path.normpath(os.path.join(base, user_path))
    if not cand.startswith(base):  # naive: sibling-prefix + symlink bypass
        raise PathSecurityError("path escapes base")
    return cand
