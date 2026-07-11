"""pathguard exception types."""


class PathValidationError(ValueError):
    """The input is malformed: empty, wrong type, NUL byte, or an absolute path."""


class PathSecurityError(ValueError):
    """The input is well-formed but resolves outside the base directory."""
