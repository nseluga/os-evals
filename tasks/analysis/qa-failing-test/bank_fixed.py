# Canonical CORRECT implementation (clamps pct to 0-100). Used only by check.sh.
def apply_discount(price, pct):
    """Apply a percentage discount to price. pct clamped to 0-100 (per contract)."""
    pct = max(0, min(100, pct))
    return price * (1 - pct / 100)
