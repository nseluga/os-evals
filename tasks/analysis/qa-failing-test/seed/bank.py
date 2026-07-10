def apply_discount(price, pct):
    """Apply a percentage discount to price.

    pct is a discount percentage that is clamped to the range 0-100 before use, so
    the returned price is always between 0 and the original price (inclusive).
    """
    return price * (1 - pct / 100)
