import os

from .errors import PathSecurityError, PathValidationError


def resolve(base, user_path):
    if not isinstance(user_path, str):
        raise PathValidationError("user_path must be a str")
    if "\x00" in user_path:
        raise PathValidationError("NUL byte in path")
    if os.path.isabs(user_path):
        raise PathValidationError("absolute path not allowed")
    realbase = os.path.realpath(base)
    cand = os.path.realpath(os.path.join(realbase, user_path))
    if os.path.commonpath([realbase, cand]) != realbase:
        raise PathSecurityError("path escapes base")
    return cand
