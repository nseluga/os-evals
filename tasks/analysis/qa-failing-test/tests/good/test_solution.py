from bank import apply_discount

assert apply_discount(100, 50) == 50
assert apply_discount(100, 150) == 0      # clamped to 100
assert apply_discount(100, -50) == 100    # clamped to 0
