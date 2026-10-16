Schedule 8 jobs on 2 identical machines, M1 and M2, both free from time 0.

Durations (time units):
J1: 7
J2: 2
J3: 8
J4: 7
J5: 3
J6: 4
J7: 2
J8: 3

Precedence constraints (A -> B means B cannot start until A has finished):
J3 -> J2
J3 -> J7
J4 -> J2
J4 -> J3
J4 -> J7
J5 -> J1
J6 -> J3
J8 -> J5
J8 -> J7

Rules: each job runs without interruption on exactly one machine; a machine runs one job at a time; start times are non-negative integers; a job may start the moment its last predecessor finishes. The makespan is the time the last job finishes.

Find a schedule with the smallest possible makespan.

End your reply with one line per job in exactly this form, then the makespan:

J3: M1 @ 4
(one such line for each of J1..J8)
makespan=<n>
