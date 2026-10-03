"""The toy CPU's instruction set: 16-bit instructions, eight 8-bit registers (r0 reads as 0), 64 bytes of data memory.

    R-type  op=0  rd[11:9] rs1[8:6] rs2[5:3] funct[2:0]   funct: ADD SUB AND OR XOR SLT SHL SHR
    ADDI    op=1  rd rs1 imm6            rd = rs1 + sext(imm6)
    LDI     op=2  rd imm8[7:0]           rd = imm8
    LD      op=3  rd rs1 imm6            rd = mem[rs1 + sext(imm6)]
    ST      op=4  rt[11:9] rs1 imm6      mem[rs1 + sext(imm6)] = rt
    BEQ/BNE/BLT op=5/6/7  rt rs1 imm6    if rs1 (==, !=, < unsigned) rt: pc = pc + 1 + sext(imm6)
    NOP     op=14                        HALT op=15

The golden interpreter below executes one instruction at a time; it is the architectural reference the pipelined
netlist is graded against (final registers and memory) and the source of the "expected" retire stream.
"""
import re

FUNCTS = ["ADD", "SUB", "AND", "OR", "XOR", "SLT", "SHL", "SHR"]
OPS = {"ADDI": 1, "LDI": 2, "LD": 3, "ST": 4, "BEQ": 5, "BNE": 6, "BLT": 7, "NOP": 14, "HALT": 15}
NOP = 14 << 12
MEM_SIZE = 64


def sext6(v):
    v &= 63
    return v - 64 if v & 32 else v


def enc(op, a=0, b=0, c=0, d=0):
    return ((op & 15) << 12) | ((a & 7) << 9) | ((b & 7) << 6) | ((c & 7) << 3) | (d & 7)


def assemble(src):
    """Two-pass assembler. Lines: `label:`, `ADD r1, r2, r3`, `ADDI r1, r1, -1`, `LDI r2, 10`, `LD r3, 2(r1)`,
    `ST r3, 0(r1)`, `BNE r1, r0, loop` (compares rs1 with rt), `NOP`, `HALT`. `;` starts a comment."""
    lines, labels = [], {}
    for raw in src.splitlines():
        line = raw.split(";")[0].strip()
        while ":" in line:
            lab, line = line.split(":", 1)
            labels[lab.strip()] = len(lines)
            line = line.strip()
        if line:
            lines.append(line)
    words = []
    for pc, line in enumerate(lines):
        m = line.split(None, 1)
        mn = m[0].upper()
        args = [a.strip() for a in re.split(r",", m[1])] if len(m) > 1 else []

        def reg(s):
            assert s.lower().startswith("r"), line
            return int(s[1:])

        def imm(s, lo, hi):
            v = labels[s] - (pc + 1) if s in labels else int(s, 0)
            assert lo <= v <= hi, f"immediate {v} out of range in {line!r}"
            return v
        if mn in FUNCTS:
            words.append(enc(0, reg(args[0]), reg(args[1]), reg(args[2]), FUNCTS.index(mn)))
        elif mn == "ADDI":
            words.append((1 << 12) | (reg(args[0]) << 9) | (reg(args[1]) << 6) | (imm(args[2], -32, 31) & 63))
        elif mn == "LDI":
            words.append((2 << 12) | (reg(args[0]) << 9) | (imm(args[1], 0, 255) & 255))
        elif mn in ("LD", "ST"):
            off, base = re.match(r"(-?\w+)\((r\d)\)", args[1].replace(" ", "")).groups()
            words.append((OPS[mn] << 12) | (reg(args[0]) << 9) | (reg(base) << 6) | (imm(off, -32, 31) & 63))
        elif mn in ("BEQ", "BNE", "BLT"):
            words.append((OPS[mn] << 12) | (reg(args[1]) << 9) | (reg(args[0]) << 6) | (imm(args[2], -32, 31) & 63))
        elif mn in ("NOP", "HALT"):
            words.append(OPS[mn] << 12)
        else:
            raise ValueError(f"unknown mnemonic in {line!r}")
    return words


def disasm(w):
    op = (w >> 12) & 15
    rd, rs1, rs2, f = (w >> 9) & 7, (w >> 6) & 7, (w >> 3) & 7, w & 7
    i6, i8 = sext6(w), w & 255
    if op == 0:
        return f"{FUNCTS[f]} r{rd}, r{rs1}, r{rs2}"
    if op == 1:
        return f"ADDI r{rd}, r{rs1}, {i6}"
    if op == 2:
        return f"LDI r{rd}, {i8}"
    if op == 3:
        return f"LD r{rd}, {i6}(r{rs1})"
    if op == 4:
        return f"ST r{rd}, {i6}(r{rs1})"
    if op in (5, 6, 7):
        return f"{['BEQ', 'BNE', 'BLT'][op - 5]} r{rs1}, r{rd}, {i6:+d}"
    if op == 15:
        return "HALT"
    return "NOP"


def alu(f, a, b):
    if f == 0:
        return (a + b) & 255
    if f == 1:
        return (a - b) & 255
    if f == 2:
        return a & b
    if f == 3:
        return a | b
    if f == 4:
        return a ^ b
    if f == 5:
        return int(a < b)
    if f == 6:
        return (a << (b & 7)) & 255
    return a >> (b & 7)


def golden(prog, data=None, max_steps=2000):
    """Run the reference interpreter. Returns {regs, mem, halted, steps, retire: [...]}; each retire record is
    {pc, text, rd, value} for register writes, {pc, text, addr, data} for stores, {pc, text} otherwise."""
    regs, mem = [0] * 8, [0] * MEM_SIZE
    for a, v in (data or {}).items():
        mem[a % MEM_SIZE] = v & 255
    pc, retire, halted = 0, [], False
    for _ in range(max_steps):
        w = prog[pc] if pc < len(prog) else NOP
        op = (w >> 12) & 15
        rd, rs1, rs2, f = (w >> 9) & 7, (w >> 6) & 7, (w >> 3) & 7, w & 7
        a, b = regs[rs1], regs[rs2]
        rec = {"pc": pc, "text": disasm(w)}
        nxt = (pc + 1) & 255
        if op == 0:
            rec.update(rd=rd, value=alu(f, a, b))
        elif op == 1:
            rec.update(rd=rd, value=(a + sext6(w)) & 255)
        elif op == 2:
            rec.update(rd=rd, value=w & 255)
        elif op == 3:
            rec.update(rd=rd, value=mem[(a + sext6(w)) % MEM_SIZE])
        elif op == 4:
            addr = ((a + sext6(w)) & 255) % MEM_SIZE
            rec.update(addr=addr, data=regs[rd])
            mem[addr] = regs[rd]
        elif op in (5, 6, 7):
            t = regs[rd]
            take = (a == t) if op == 5 else (a != t) if op == 6 else (a < t)
            if take:
                nxt = (pc + 1 + sext6(w)) & 255
        elif op == 15:
            retire.append(rec)
            halted = True
            break
        if op != 14:
            if "rd" in rec and rec["rd"] != 0:
                regs[rec["rd"]] = rec["value"]
            retire.append(rec)
        pc = nxt
    return {"regs": regs, "mem": mem, "halted": halted, "retire": retire}


# ---------------------------------------------------------------------------------------------- the test suite
# Each test is a short program; the expected result is whatever the golden interpreter produces.
TESTS = [
    ("arith_chain", "back-to-back adds and subtracts (forwarding from EX/MEM and MEM/WB)", """
        LDI r1, 5
        LDI r2, 7
        ADD r3, r1, r2      ; 12, needs both operands forwarded
        SUB r4, r3, r1      ; 7
        ADD r5, r4, r3      ; 19
        ADDI r6, r5, -3     ; 16
        ADDI r7, r6, 20     ; 36
        SUB r1, r7, r2      ; 29
        HALT"""),
    ("logic_shift", "AND, OR, XOR, shifts and set-less-than", """
        LDI r1, 202
        LDI r2, 92
        AND r3, r1, r2
        OR  r4, r1, r2
        XOR r5, r1, r2
        ST  r3, 0(r0)
        ST  r4, 1(r0)
        ST  r5, 2(r0)
        LDI r6, 3
        SHL r7, r2, r6
        SHR r3, r1, r6
        SLT r4, r2, r1
        SLT r5, r1, r2
        SLT r6, r6, r6
        HALT"""),
    ("load_store", "stores, loads and a load-use stall", """
        LDI r1, 8
        LDI r2, 77
        ST  r2, 0(r1)
        ST  r1, 1(r1)
        LD  r3, 0(r1)
        ADD r4, r3, r3      ; load-use: one bubble
        LD  r5, 1(r1)
        ST  r5, 2(r1)       ; store data needs the loaded value
        LD  r6, 2(r1)
        ADDI r7, r6, 1
        HALT"""),
    ("loop_sum", "sum 1..9 with a backward branch (flushes on every taken branch)", """
        LDI r1, 9
        LDI r2, 0
    loop:
        ADD r2, r2, r1
        ADDI r1, r1, -1
        BNE r1, r0, loop
        ST  r2, 5(r0)
        HALT"""),
    ("fibonacci", "first eight Fibonacci numbers written to memory", """
        LDI r1, 0
        LDI r2, 1
        LDI r3, 16          ; address
        LDI r4, 24          ; end address
    next:
        ST  r1, 0(r3)
        ADD r5, r1, r2
        ADD r1, r2, r0
        ADD r2, r5, r0
        ADDI r3, r3, 1
        BLT r3, r4, next
        HALT"""),
    ("max_scan", "find the largest of six numbers in memory with BLT and BEQ", """
        LDI r1, 32          ; pointer
        LDI r2, 38          ; end
        LDI r3, 0           ; max
    scan:
        LD  r4, 0(r1)
        BLT r4, r3, skip
        ADD r3, r4, r0
    skip:
        ADDI r1, r1, 1
        BEQ r1, r2, done
        BEQ r0, r0, scan
    done:
        ST  r3, 0(r2)
        HALT""", {32: 19, 33: 140, 34: 7, 35: 201, 36: 13, 37: 200}),
    ("reg_sweep", "write every register, then read them back in mixed order", """
        LDI r1, 17
        LDI r2, 34
        LDI r3, 51
        LDI r4, 68
        LDI r5, 85
        LDI r6, 102
        LDI r7, 119
        ADD r1, r7, r1
        ADD r2, r6, r2
        XOR r3, r5, r3
        OR  r4, r4, r1
        SUB r5, r2, r3
        ADD r0, r1, r2      ; writes to r0 are discarded
        ADD r6, r0, r6
        HALT"""),
    ("forward_mix", "same register written twice in a row, and stores whose rt field must not forward", """
        LDI r1, 3
        ADDI r1, r1, 1      ; 4
        ADDI r1, r1, 1      ; 5: the younger write must win (operand A)
        ADD r2, r1, r0
        ADDI r1, r1, 1      ; 6
        ADDI r1, r1, 1      ; 7: the younger write must win (operand B)
        ADD r3, r0, r1
        LDI r4, 40
        ST  r2, 0(r4)       ; rt = r2, but a store writes no register
        ADD r5, r4, r2      ; operand B must not come from the store
        ST  r5, 1(r4)
        ADD r6, r5, r0      ; operand A must not come from the store
        ADD r7, r0, r5      ; r5 read while the store sits in WB
        LDI r5, 9
        ADD r5, r0, r2      ; r2 read on port B while ST r2 sits in WB
        HALT"""),
    ("countdown_mul", "multiply 13 by 11 with a counted loop and shifts", """
        LDI r1, 13
        LDI r2, 11
        LDI r3, 0
        LDI r6, 1
    mul:
        ADD r3, r3, r1
        SUB r2, r2, r6
        BNE r2, r0, mul
        SHR r4, r3, r6
        SHL r5, r4, r6
        ST  r3, 9(r0)
        ST  r5, 10(r0)
        HALT"""),
]


def load_tests():
    out = []
    for t in TESTS:
        name, desc, src = t[0], t[1], t[2]
        data = t[3] if len(t) > 3 else {}
        prog = assemble(src)
        out.append({"name": name, "desc": desc, "prog": prog, "data": data, "src": src.strip("\n"),
                    "golden": golden(prog, data)})
    return out
