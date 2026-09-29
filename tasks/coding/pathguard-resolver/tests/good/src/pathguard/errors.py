class PathValidationError(Exception):
    """Malformed input: non-str, NUL byte, or absolute path."""


class PathSecurityError(Exception):
    """Path resolves outside the base directory."""
