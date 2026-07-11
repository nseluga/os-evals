"""Safe resolution of untrusted client paths inside a fixed base directory."""
import os

from pathguard.errors import PathSecurityError, PathValidationError


def resolve(base_dir: str, user_path: str) -> str:
    """Resolve ``user_path`` inside ``base_dir``, refusing every escape.

    Returns the absolute, fully-resolved path. Raises PathValidationError for
    malformed input and PathSecurityError for anything that escapes the base.
    """
    if not isinstance(user_path, str):
        raise PathValidationError("user_path must be a string")
    if "\x00" in user_path:
        raise PathValidationError("user_path contains a NUL byte")

    real_base = os.path.realpath(base_dir)

    stripped = user_path.strip()
    if stripped in ("", ".", "./"):
        return real_base

    if os.path.isabs(user_path):
        raise PathValidationError("user_path must be relative")

    # realpath follows symlink components (unlike normpath), so a symlink inside
    # the base that points outside is caught by the containment check below.
    candidate = os.path.realpath(os.path.join(real_base, user_path))

    # commonpath is exact: /srv/data-evil does NOT share commonpath /srv/data,
    # so the sibling-prefix bypass that fools str.startswith is rejected here.
    try:
        if os.path.commonpath([real_base, candidate]) != real_base:
            raise PathSecurityError("resolved path escapes the base directory")
    except ValueError:
        # Different roots/drives -> definitely not contained.
        raise PathSecurityError("resolved path escapes the base directory")

    return candidate
