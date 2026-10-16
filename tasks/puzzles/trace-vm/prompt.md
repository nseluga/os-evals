A small stack machine has three registers R0, R1, R2 (all start at 0, integers) and an initially empty stack. Instructions are numbered from 0 and execution starts at instruction 0. After each instruction the machine moves on to the next one, unless a jump says otherwise.

Instructions:
- PUSH x: push x on the stack; x is an integer literal, or a register name (push that register's current value)
- POP r: pop the top of the stack into register r
- ADD / SUB / MUL: pop b (top), then pop a, push a+b / a-b / a*b
- DUP: push a copy of the top value
- SWAP: exchange the top two values
- INC r / DEC r: add 1 to / subtract 1 from register r
- JMP off: jump to instruction (current index + off)
- JZ off: pop the top of the stack; if it is 0, jump to instruction (current index + off), otherwise continue with the next instruction
- HALT: stop

Programme:

 0: PUSH 5
 1: POP R0
 2: PUSH 2
 3: POP R1
 4: PUSH 4
 5: POP R2
 6: PUSH 2
 7: PUSH R0
 8: JZ 8
 9: DEC R1
10: PUSH R1
11: PUSH 5
12: SUB
13: POP R1
14: DEC R0
15: JMP -8
16: PUSH R2
17: DUP
18: MUL
19: POP R2
20: DEC R1
21: PUSH R1
22: PUSH 27
23: SUB
24: JZ 5
25: PUSH R1
26: DUP
27: MUL
28: POP R1
29: HALT

The programme halts without error. Simulate it exactly. What are the final values of the three registers, and how many values are on the stack at HALT?

End your reply with one final line in exactly this form (integers only):

R0=<n> R1=<n> R2=<n> depth=<n>
