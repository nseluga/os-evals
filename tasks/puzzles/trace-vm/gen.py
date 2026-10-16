#!/usr/bin/env python3
"""gen.py --seed N [--key] -- trace-vm puzzle instance (stdlib only).
Builds a 30-instruction stack-machine programme (preamble, counted loop, tail), simulates it,
prints the prompt; with --key also prints the answer key after a marker line."""
import argparse
import random

LEN, MAX_STEPS = 30, 500


def run(prog):
    """Return (regs, stack, steps, taken_jumps). Raises ValueError on a bad programme."""
    regs, st, pc, steps, taken = {"R0": 0, "R1": 0, "R2": 0}, [], 0, 0, 0
    while True:
        if not 0 <= pc < len(prog) or steps >= MAX_STEPS:
            raise ValueError("ran off programme or too long")
        op, *arg = prog[pc].split()
        steps += 1
        nxt = pc + 1
        if op == "HALT":
            return regs, st, steps, taken
        if op == "PUSH":
            st.append(regs[arg[0]] if arg[0] in regs else int(arg[0]))
        elif op == "POP":
            regs[arg[0]] = st.pop()
        elif op in ("ADD", "SUB", "MUL"):
            b, a = st.pop(), st.pop()
            st.append(a + b if op == "ADD" else a - b if op == "SUB" else a * b)
        elif op == "DUP":
            st.append(st[-1])
        elif op == "SWAP":
            st[-1], st[-2] = st[-2], st[-1]
        elif op == "INC":
            regs[arg[0]] += 1
        elif op == "DEC":
            regs[arg[0]] -= 1
        elif op == "JMP":
            nxt, taken = pc + int(arg[0]), taken + 1
        elif op == "JZ":
            if st.pop() == 0:
                nxt, taken = pc + int(arg[0]), taken + 1
        pc = nxt


def snippet(rng, loop=False):
    """A stack-balanced fragment (net depth 0)."""
    r, r2 = rng.choice(["R0", "R1", "R2"]), rng.choice(["R1", "R2"])
    a, b = rng.randint(2, 9), rng.randint(1, 6)
    opts = [[f"PUSH {r2}", f"PUSH {a}", rng.choice(["ADD", "SUB"]), f"POP {r2}"],
            [f"PUSH {a}", f"PUSH {b}", "SWAP", "SUB", f"POP {r2}"],
            [f"INC {r2}"], [f"DEC {r2}"]]
    if not loop:
        opts += [[f"PUSH {r2}", "DUP", "MUL", f"POP {r2}"], [f"PUSH {a}", f"PUSH {b}", "MUL", f"POP {r2}"]]
    return rng.choice(opts)


def build(rng):
    n_iter = rng.randint(3, 6)
    pre = [f"PUSH {n_iter}", "POP R0", f"PUSH {rng.randint(1, 5)}", "POP R1", f"PUSH {rng.randint(1, 5)}", "POP R2"]
    for _ in range(rng.randint(1, 2)):  # values left on the stack for the whole run
        pre += [f"PUSH {rng.randint(1, 9)}"]
    body = []
    for _ in range(rng.randint(2, 3)):
        body += snippet(rng, loop=True)
    # loop: PUSH R0 ; JZ -> after loop ; body ; DEC R0 ; JMP back
    loop_len = 2 + len(body) + 2
    loop = ["PUSH R0", f"JZ {loop_len - 1}"] + body + ["DEC R0", f"JMP {-(loop_len - 1)}"]
    # data-dependent skip: PUSH R1 ; PUSH k ; SUB ; JZ +len(skipped)+1 ; skipped fragment
    k = rng.randint(1, 30)
    skipped = snippet(rng)
    tail = ["PUSH R1", f"PUSH {k}", "SUB", f"JZ {len(skipped) + 1}"] + skipped
    used = len(pre) + len(loop) + len(tail) + 1
    if used > LEN:
        raise ValueError("too long")
    pad = []
    while len(pad) < LEN - used:
        s = snippet(rng)
        if len(pad) + len(s) <= LEN - used:
            pad += s
        else:
            pad.append(rng.choice(["INC R2", "DEC R1", "INC R0"]))
    return pre + loop + pad + tail + ["HALT"]


def make(seed):
    rng = random.Random(seed)
    while True:
        try:
            prog = build(rng)
            if len(prog) != LEN:
                continue
            regs, st, steps, taken = run(prog)
        except (ValueError, IndexError):
            continue
        if taken >= 2 and steps <= MAX_STEPS and st and max(map(abs, [*regs.values(), *st])) < 10**6:
            return prog, regs, st, steps, taken


PROMPT = """A small stack machine has three registers R0, R1, R2 (all start at 0, integers) and an initially empty stack. Instructions are numbered from 0 and execution starts at instruction 0. After each instruction the machine moves on to the next one, unless a jump says otherwise.

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

{listing}

The programme halts without error. Simulate it exactly. What are the final values of the three registers, and how many values are on the stack at HALT?

End your reply with one final line in exactly this form (integers only):

R0=<n> R1=<n> R2=<n> depth=<n>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key", action="store_true")
    a = ap.parse_args()
    prog, regs, st, steps, taken = make(a.seed)
    print(PROMPT.format(listing="\n".join(f"{i:>2}: {ins}" for i, ins in enumerate(prog))))
    if a.key:
        print("\n=== KEY ===")
        print(f"R0={regs['R0']} R1={regs['R1']} R2={regs['R2']} depth={len(st)}")
        print(f"steps={steps} taken_jumps={taken} stack={st}")
