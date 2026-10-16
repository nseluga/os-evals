Here is a 10x10 grid. Rows are numbered 1-10 from the top, columns 1-10 from the left.

     1 2 3 4 5 6 7 8 9 10
r1   S . . . . B . # # .
r2   # . . # . . . . . .
r3   # . . . . . . . A .
r4   . . . . . . . . . .
r5   . . # . . . . # . .
r6   . # . . . . . . . .
r7   . . . . . # . . . #
r8   . . . . . # . . . .
r9   . . . . # . . . . .
r10  . . . . . . . . . E

Legend: S = start, row 1 col 1. E = end, row 10 col 10. # = blocked cell, which a path may never enter. . = open cell. A and B are two marked checkpoint cells (open): A is (row 3, col 9) and B is (row 1, col 6).

Blocked cells: (row 1, col 8), (row 1, col 9), (row 2, col 1), (row 2, col 4), (row 3, col 1), (row 5, col 3), (row 5, col 8), (row 6, col 2), (row 7, col 6), (row 7, col 10), (row 8, col 6), (row 9, col 5).

A path starts at S and ends at E. Each step moves exactly one cell right or one cell down, and never enters a blocked cell. Count the paths that pass through EXACTLY ONE of the two checkpoints A and B: they visit A or B but not both.

Work it out however you like. End your reply with one final line in exactly this form, with a plain integer:

ANSWER: <number>
