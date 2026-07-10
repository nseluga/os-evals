# Canonical BUGGY implementation (does NOT clamp pct). Used only by check.sh; never
# shown to the model as the gradable answer — seed/bank.py is a copy of this.
def apply_discount(price, pct):
    """Apply a percentage discount to price. pct clamped to 0-100 (per contract)."""
    return price * (1 - pct / 100)
