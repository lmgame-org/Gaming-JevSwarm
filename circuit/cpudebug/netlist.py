"""The CPU as a netlist of 96 blocks, a cycle simulator, fault injection and the test runner.

Every block has named input ports wired to nets (a net is "<driver block>.<port>"), output ports with bit widths, a
`params` dict that defines its specified behaviour, and a pure function from (params, inputs, state) to outputs.
Registers and memories also have a next-state function. A bug is one changed entry in one block's params: a stuck-at
bit on an output, two swapped mux inputs, a wrong forwarding or hazard path, or an off-by-one. Fixing a bug means
putting that one param back to its specified value.

Stages: IF -> IF/ID -> ID -> ID/EX -> EX -> EX/MEM -> MEM -> MEM/WB -> WB. Branches resolve in EX (predict not
taken, flush two younger instructions); EX/MEM and MEM/WB forward to EX; WB bypasses to the ID register read; a
load followed by a dependent instruction stalls one cycle.
"""
import copy

from .isa import MEM_SIZE, NOP, disasm

STAGES = ["IF", "IF/ID", "ID", "ID/EX", "EX", "EX/MEM", "MEM", "MEM/WB", "WB"]
BUG_TYPES = {"stuck_at": "stuck-at wire", "swapped_mux": "swapped mux inputs",
             "wrong_forwarding": "wrong forwarding / hazard path", "off_by_one": "off-by-one"}


def mask(w):
    return (1 << w) - 1


class Block:
    def __init__(self, name, stage, group, ins, outs, fn, spec, params=None, nxt=None, init=None, deps=None,
                 relevant=None, faults=None, trusted=False, stuck=True):
        self.name, self.stage, self.group = name, stage, group
        self.ins = dict(ins)            # port -> net
        self.outs = dict(outs)          # port -> width
        self.fn, self.nxt, self.init = fn, nxt, init
        self.spec = spec
        self.params = dict(params or {})
        self.seq = nxt is not None
        self.deps = list(self.ins) if deps is None else deps   # inputs the outputs depend on within a cycle
        self.relevant = relevant        # (inputs, state) -> ports that carried the output's value, or None (all)
        self.trusted = trusted          # registers, memories and the ROM: verified IP, never the bug site
        self.faults = list(faults or [])
        if stuck and not trusted:
            for port, w in self.outs.items():
                for bit in range(w):
                    self.params[f"stuck:{port}:{bit}"] = None
                    for v in (0, 1):
                        self.faults.append({"key": f"stuck:{port}:{bit}", "value": v, "type": "stuck_at", "port": port,
                                            "desc": f"output {port} bit {bit} stuck at {v}"})
        for f in self.faults:
            self.params.setdefault(f["key"], None)

    def net(self, port):
        return f"{self.name}.{port}"

    def eval(self, p, inp, state):
        out = self.fn(p, inp, state)
        for port, bit, v in p.get("_stuck", ()):
            out[port] = (out[port] | (1 << bit)) if v else (out[port] & ~(1 << bit))
        return {k: int(v) & mask(self.outs[k]) for k, v in out.items()}

    def eff(self, fault=None):
        """Params with `fault` (one {block, key, value} or a list of them) applied where they are in this block;
        active stuck-at bits precomputed."""
        p = dict(self.params)
        for f in (fault if isinstance(fault, list) else [fault] if fault else []):
            if f["block"] == self.name:
                p[f["key"]] = f["value"]
        p["_stuck"] = [(k.split(":")[1], int(k.split(":")[2]), v) for k, v in p.items()
                       if v is not None and k.startswith("stuck:")]
        return p

    def public(self):
        return {"name": self.name, "stage": self.stage, "group": self.group, "spec": self.spec,
                "ins": self.ins, "outs": self.outs, "trusted": self.trusted, "seq": self.seq}


# ------------------------------------------------------------------------------------------- block constructors
def mux(name, stage, group, sel, inputs, width, spec, swaps=None):
    ins = {"sel": sel}
    ins.update({f"in{k}": n for k, n in enumerate(inputs)})
    n = len(inputs)
    faults = [{"key": f"swap:{a}:{b}", "value": True, "type": "swapped_mux", "port": "out",
               "desc": f"inputs in{a} and in{b} swapped"} for a, b in (swaps or [(0, 1)])]

    def order(p):
        o = list(range(n))
        for k, v in p.items():
            if v and k.startswith("swap:"):
                _, a, b = k.split(":")
                o[int(a)], o[int(b)] = o[int(b)], o[int(a)]
        return o

    def fn(p, i, s):
        k = i["sel"]
        return {"out": i[f"in{order(p)[k]}"] if k < n else 0}
    return Block(name, stage, group, ins, {"out": width}, fn, spec, faults=faults,
                 relevant=lambda i, s: ["sel", f"in{i['sel']}"] if i["sel"] < n else ["sel"])


def field(name, src, lo, width, spec, shift_fault=True):
    faults = []
    if shift_fault:
        for d in (-1, 1):
            if 0 <= lo + d and lo + d + width <= 16:
                faults.append({"key": f"lo_{'m' if d < 0 else 'p'}1", "value": True, "type": "off_by_one", "port": "out",
                               "desc": f"field taken from bit {lo + d} instead of bit {lo}"})

    def fn(p, i, s):
        l = lo - 1 if p.get("lo_m1") else lo + 1 if p.get("lo_p1") else lo
        return {"out": (i["instr"] >> l) & mask(width)}
    return Block(name, "ID", "decoder", {"instr": src}, {"out": width}, fn, spec, faults=faults)


def decode(name, group, op_set, width, spec, value=None):
    """Control decoder on the opcode: 1 when op in op_set (or value(op) when given)."""
    def fn(p, i, s):
        return {"out": value(i["op"]) if value else int(i["op"] in op_set)}
    return Block(name, "ID", group, {"op": "dec_op.out"}, {"out": width}, fn, spec)


def reg(name, stage, d, width, spec, en=None, flush=None, flush_val=0, group="pipeline"):
    ins = {"d": d}
    if en:
        ins["en"] = en
    if flush:
        ins["flush"] = flush

    def nxt(p, i, s):
        if i.get("flush", 0):
            return flush_val
        if i.get("en", 1):
            return i["d"]
        return s

    def rel(i, s):
        if i.get("flush", 0):
            return ["flush"]
        return [k for k in ("d", "en", "flush") if k in i] if i.get("en", 1) else [k for k in ("en", "flush") if k in i]
    return Block(name, stage, group, ins, {"q": width}, lambda p, i, s: {"q": s}, spec, nxt=nxt,
                 init=lambda: flush_val if flush else 0, deps=[], relevant=rel, trusted=True)


# ------------------------------------------------------------------------------------------------ the CPU itself
def build_cpu():
    B = []
    add = B.append
    W = 8

    # ---------------------------------------------------------------- IF
    add(Block("tie_hi", "IF", "fetch", {}, {"one": 1}, lambda p, i, s: {"one": 1}, "constant 1", trusted=True))
    add(reg("pc", "IF", "pc_mux.out", W, "program counter: loads pc_mux.out when en=1 (en=0 holds during a stall)",
            en="hazard.go", group="fetch"))
    add(Block("imem", "IF", "fetch", {"pc": "pc.q"}, {"instr": 16},
              lambda p, i, s: {"instr": s[i["pc"]] if i["pc"] < len(s) else NOP},
              "instruction ROM: instr = program[pc] (NOP past the end)", nxt=lambda p, i, s: s, init=lambda: [],
              deps=["pc"], trusted=True))
    add(Block("pc_inc", "IF", "fetch", {"pc": "pc.q"}, {"out": W}, lambda p, i, s: {"out": i["pc"] + p["inc"]},
              "pc + 1", params={"inc": 1},
              faults=[{"key": "inc", "value": 2, "type": "off_by_one", "port": "out", "desc": "adds 2 instead of 1"}]))
    add(mux("pc_mux", "IF", "fetch", "br_decide.taken", ["pc_inc.out", "br_target.out"], W,
            "next pc: in0 = pc+1 when sel=0, in1 = branch target when sel=1 (branch taken)"))

    # ---------------------------------------------------------------- IF/ID
    add(reg("ifid_instr", "IF/ID", "imem.instr", 16, "IF/ID instruction latch (flush -> NOP, en=0 holds)",
            en="hazard.go", flush="br_decide.taken", flush_val=NOP))
    add(reg("ifid_pc", "IF/ID", "pc.q", W, "IF/ID pc latch", en="hazard.go", flush="br_decide.taken"))
    add(reg("ifid_valid", "IF/ID", "tie_hi.one", 1, "IF/ID valid bit (0 after a flush)", en="hazard.go",
            flush="br_decide.taken"))

    # ---------------------------------------------------------------- ID: instruction fields
    I = "ifid_instr.q"
    add(field("dec_op", I, 12, 4, "opcode = instr[15:12]", shift_fault=False))
    add(field("dec_rd", I, 9, 3, "rd / rt field = instr[11:9]"))
    add(field("dec_rs1", I, 6, 3, "rs1 field = instr[8:6]"))
    add(field("dec_rs2", I, 3, 3, "rs2 field = instr[5:3]"))
    add(field("dec_funct", I, 0, 3, "funct = instr[2:0] (ALU operation for R-type)"))
    add(Block("sext6", "ID", "decoder", {"instr": I}, {"out": W},
              lambda p, i, s: {"out": ((i["instr"] & 63) | (0xC0 if (i["instr"] >> p["sign_bit"]) & 1 else 0))
                               if p["sign_bit"] == 5 else
                               ((i["instr"] & 31) | (0xE0 if (i["instr"] >> p["sign_bit"]) & 1 else 0))},
              "imm6 = instr[5:0] sign-extended to 8 bits (bit 5 is the sign)", params={"sign_bit": 5},
              faults=[{"key": "sign_bit", "value": 4, "type": "off_by_one", "port": "out",
                       "desc": "sign taken from bit 4 instead of bit 5"}]))
    add(field("imm8", I, 0, 8, "imm8 = instr[7:0] (LDI)", shift_fault=False))

    # ---------------------------------------------------------------- ID: control decoders
    add(decode("ctrl_regwrite", "control", {0, 1, 2, 3}, 1, "regwrite = 1 for R-type, ADDI, LDI, LD"))
    add(decode("ctrl_memread", "control", {3}, 1, "memread = 1 for LD"))
    add(decode("ctrl_memwrite", "control", {4}, 1, "memwrite = 1 for ST"))
    add(decode("ctrl_alusrc", "control", {1, 2, 3, 4}, 1, "alusrc = 1 (ALU B is the immediate) for ADDI, LDI, LD, ST"))
    add(Block("ctrl_aluop", "ID", "control", {"op": "dec_op.out", "funct": "dec_funct.out"}, {"out": 4},
              lambda p, i, s: {"out": i["funct"] if i["op"] == 0 else 8 if i["op"] == 2 else 1 if i["op"] in (5, 6, 7)
                               else 0},
              "aluop = funct for R-type, 8 (pass B) for LDI, 1 (SUB) for branches, else 0 (ADD)"))
    add(decode("ctrl_branch", "control", None, 2, "branch = 1 BEQ, 2 BNE, 3 BLT, else 0",
               value=lambda op: op - 4 if op in (5, 6, 7) else 0))
    add(decode("ctrl_halt", "control", {15}, 1, "halt = 1 for HALT"))
    add(decode("ctrl_usert", "control", {4, 5, 6, 7}, 1, "usert = 1 when register port B reads the rt field (ST, branches)"))
    add(decode("ctrl_immsel", "control", {2}, 1, "immsel = 1 for LDI (use imm8 instead of imm6)"))
    add(mux("regb_addr", "ID", "regfile", "ctrl_usert.out", ["dec_rs2.out", "dec_rd.out"], 3,
            "register port B address: in0 = rs2 when sel=0, in1 = rt (instr[11:9]) when sel=1"))
    add(mux("imm_mux", "ID", "decoder", "ctrl_immsel.out", ["sext6.out", "imm8.out"], W,
            "immediate: in0 = sign-extended imm6 when sel=0, in1 = imm8 when sel=1"))

    # ---------------------------------------------------------------- ID: register file
    for k in range(8):
        def rnxt(p, i, s, k=k):
            return i["d"] if (i["we"] >> k) & 1 else s
        add(Block(f"r{k}", "ID", "regfile", {"d": "wb_mux.out", "we": "wb_dec.onehot"}, {"q": W},
                  lambda p, i, s: {"q": s}, f"register r{k}: loads d when we bit {k} is 1", nxt=rnxt, init=lambda: 0,
                  deps=[], trusted=True,
                  relevant=lambda i, s, k=k: ["d", "we"] if (i["we"] >> k) & 1 else ["we"]))
    regs = [f"r{k}.q" for k in range(8)]
    add(mux("rf_read_a", "ID", "regfile", "dec_rs1.out", regs, W, "read port A: out = r[sel] (sel = rs1)",
            swaps=[(1, 2), (3, 4), (5, 6), (2, 3)]))
    add(mux("rf_read_b", "ID", "regfile", "regb_addr.out", regs, W, "read port B: out = r[sel] (sel = rs2 or rt)",
            swaps=[(1, 2), (3, 4), (5, 6), (2, 3)]))

    def bypass(name, rdata, raddr, port):
        def fn(p, i, s):
            hit = i["waddr"] == i["raddr"] and (i["we"] or p["ignore_we"])
            return {"out": i["wdata"] if hit and not p["disabled"] else i["rdata"]}

        def rel(i, s):
            hit = i["waddr"] == i["raddr"] and i["we"]
            return ["raddr", "waddr", "we", "wdata"] if hit else ["raddr", "waddr", "we", "rdata"]
        return Block(name, "ID", "forwarding", {"rdata": rdata, "raddr": raddr, "waddr": "memwb_rd.q",
                                                "we": "wb_guard.we", "wdata": "wb_mux.out"}, {"out": W}, fn,
                     f"WB-to-ID bypass for port {port}: out = wdata if we=1 and waddr == raddr, else rdata",
                     params={"disabled": False, "ignore_we": False}, relevant=rel,
                     faults=[{"key": "disabled", "value": True, "type": "wrong_forwarding", "port": "out",
                              "desc": "bypass never taken (reads the stale register)"},
                             {"key": "ignore_we", "value": True, "type": "wrong_forwarding", "port": "out",
                              "desc": "bypass taken on an address match even when nothing is written"}])
    add(bypass("rf_byp_a", "rf_read_a.out", "dec_rs1.out", "A"))
    add(bypass("rf_byp_b", "rf_read_b.out", "regb_addr.out", "B"))

    def hazard(p, i, s):
        hit = i["ex_memread"] and i["ex_rd"] != 0 and (
            (i["ex_rd"] == i["rs1"] and p["check_rs1"]) or (i["ex_rd"] == i["rb"] and p["check_rb"]))
        stall = int(bool(hit) and not i["taken"])
        return {"stall": stall, "go": 1 - stall}
    add(Block("hazard", "ID", "hazard", {"ex_memread": "idex_memread.q", "ex_rd": "idex_rd.q", "rs1": "dec_rs1.out",
                                          "rb": "regb_addr.out", "taken": "br_decide.taken"}, {"stall": 1, "go": 1},
              hazard, "load-use hazard: stall = 1 when the instruction in EX is a load whose rd (not r0) equals rs1 or "
                      "the port-B register of the instruction in ID, unless a branch is taken; go = not stall",
              params={"check_rs1": True, "check_rb": True},
              faults=[{"key": "check_rs1", "value": False, "type": "wrong_forwarding", "port": "stall",
                       "desc": "misses a load-use on rs1"},
                      {"key": "check_rb", "value": False, "type": "wrong_forwarding", "port": "stall",
                       "desc": "misses a load-use on the port-B register"}]))
    add(Block("idex_clear", "ID", "hazard", {"stall": "hazard.stall", "taken": "br_decide.taken"}, {"out": 1},
              lambda p, i, s: {"out": i["stall"] | i["taken"]}, "bubble: out = stall OR taken (clears ID/EX)"))

    # ---------------------------------------------------------------- ID/EX
    clr = "idex_clear.out"
    for nm, d, w in [("idex_regwrite", "ctrl_regwrite.out", 1), ("idex_memread", "ctrl_memread.out", 1),
                     ("idex_memwrite", "ctrl_memwrite.out", 1), ("idex_alusrc", "ctrl_alusrc.out", 1),
                     ("idex_aluop", "ctrl_aluop.out", 4), ("idex_branch", "ctrl_branch.out", 2),
                     ("idex_halt", "ctrl_halt.out", 1), ("idex_valid", "ifid_valid.q", 1),
                     ("idex_a", "rf_byp_a.out", W), ("idex_b", "rf_byp_b.out", W), ("idex_imm", "imm_mux.out", W),
                     ("idex_rs1", "dec_rs1.out", 3), ("idex_rb", "regb_addr.out", 3), ("idex_rd", "dec_rd.out", 3),
                     ("idex_pc", "ifid_pc.q", W)]:
        add(reg(nm, "ID/EX", d, w, f"ID/EX latch of {d} (cleared by a bubble)", flush=clr))

    # ---------------------------------------------------------------- EX: forwarding
    def fwd(p, i, s):
        ex = (i["exmem_rw"] or not p["use_regwrite"]) and i["exmem_rd"] != 0 and i["exmem_rd"] == i["rs"]
        wb = (i["memwb_rw"] or not p["use_regwrite"]) and i["memwb_rd"] != 0 and i["memwb_rd"] == i["rs"]
        if p["memwb_first"]:
            sel = 2 if wb else 1 if ex else 0
        else:
            sel = 1 if ex else 2 if wb else 0
        if p["swap_codes"] and sel:
            sel = 3 - sel
        return {"sel": sel}
    for side, rs in (("a", "idex_rs1.q"), ("b", "idex_rb.q")):
        add(Block(f"fwd_{side}", "EX", "forwarding",
                  {"rs": rs, "exmem_rd": "exmem_rd.q", "exmem_rw": "exmem_regwrite.q", "memwb_rd": "memwb_rd.q",
                   "memwb_rw": "memwb_regwrite.q"}, {"sel": 2}, fwd,
                  f"forwarding select for operand {side.upper()}: 1 (from EX/MEM) if EX/MEM writes rd != 0 and rd == rs; "
                  "else 2 (from MEM/WB) if MEM/WB writes rd != 0 and rd == rs; else 0 (register value). EX/MEM wins.",
                  params={"memwb_first": False, "swap_codes": False, "use_regwrite": True},
                  faults=[{"key": "memwb_first", "value": True, "type": "wrong_forwarding", "port": "sel",
                           "desc": "MEM/WB given priority over EX/MEM (forwards the older value)"},
                          {"key": "swap_codes", "value": True, "type": "wrong_forwarding", "port": "sel",
                           "desc": "EX/MEM and MEM/WB forwarding paths swapped"},
                          {"key": "use_regwrite", "value": False, "type": "wrong_forwarding", "port": "sel",
                           "desc": "forwards from instructions that do not write a register (stores, branches)"}]))
    add(mux("fwd_mux_a", "EX", "forwarding", "fwd_a.sel", ["idex_a.q", "exmem_alu.q", "wb_mux.out"], W,
            "operand A: in0 = register value (sel 0), in1 = EX/MEM ALU result (sel 1), in2 = WB value (sel 2)",
            swaps=[(0, 1), (1, 2), (0, 2)]))
    add(mux("fwd_mux_b", "EX", "forwarding", "fwd_b.sel", ["idex_b.q", "exmem_alu.q", "wb_mux.out"], W,
            "operand B / store data / branch rt: in0 = register value, in1 = EX/MEM ALU result, in2 = WB value",
            swaps=[(0, 1), (1, 2), (0, 2)]))
    add(mux("alu_src", "EX", "alu", "idex_alusrc.q", ["fwd_mux_b.out", "idex_imm.q"], W,
            "ALU B input: in0 = forwarded register B when sel=0, in1 = immediate when sel=1"))
    A, Bn = "fwd_mux_a.out", "alu_src.out"

    # ---------------------------------------------------------------- EX: ALU
    def nib(hi):
        def fn(p, i, s):
            sh = 4 if hi else 0
            t = ((i["a"] >> sh) & 15) + ((i["b"] >> sh) & 15) + (i["cin"] if hi else p["cin"])
            return {"s": t & 15, "c": t >> 4}
        return fn
    add(Block("alu_add_lo", "EX", "alu", {"a": A, "b": Bn}, {"s": 4, "c": 1}, nib(False),
              "low nibble adder: s = (a[3:0] + b[3:0]) mod 16, c = carry out", params={"cin": 0},
              faults=[{"key": "cin", "value": 1, "type": "off_by_one", "port": "s",
                       "desc": "carry-in tied to 1 (adds one extra)"}]))
    add(Block("alu_add_hi", "EX", "alu", {"a": A, "b": Bn, "cin": "alu_add_lo.c"}, {"s": 4, "c": 1}, nib(True),
              "high nibble adder: s = (a[7:4] + b[7:4] + cin) mod 16, c = carry out"))
    add(Block("alu_add", "EX", "alu", {"lo": "alu_add_lo.s", "hi": "alu_add_hi.s"}, {"out": W},
              lambda p, i, s: {"out": (i["hi"] << 4) | i["lo"]}, "sum = hi << 4 | lo"))
    add(Block("alu_sub", "EX", "alu", {"a": A, "b": Bn}, {"out": W},
              lambda p, i, s: {"out": (i["a"] - i["b"] + p["bias"]) & 255}, "a - b (mod 256)", params={"bias": 0},
              faults=[{"key": "bias", "value": 1, "type": "off_by_one", "port": "out", "desc": "computes a - b + 1"},
                      {"key": "bias", "value": -1, "type": "off_by_one", "port": "out", "desc": "computes a - b - 1"}]))
    add(Block("alu_and", "EX", "alu", {"a": A, "b": Bn}, {"out": W}, lambda p, i, s: {"out": i["a"] & i["b"]}, "a AND b"))
    add(Block("alu_or", "EX", "alu", {"a": A, "b": Bn}, {"out": W}, lambda p, i, s: {"out": i["a"] | i["b"]}, "a OR b"))
    add(Block("alu_xor", "EX", "alu", {"a": A, "b": Bn}, {"out": W}, lambda p, i, s: {"out": i["a"] ^ i["b"]}, "a XOR b"))
    add(Block("alu_slt", "EX", "alu", {"a": A, "b": Bn}, {"out": 1},
              lambda p, i, s: {"out": int(i["a"] <= i["b"]) if p["le"] else int(i["a"] < i["b"])},
              "1 if a < b (unsigned) else 0", params={"le": False},
              faults=[{"key": "le", "value": True, "type": "off_by_one", "port": "out", "desc": "computes a <= b"}]))
    add(Block("alu_shl", "EX", "alu", {"a": A, "b": Bn}, {"out": W},
              lambda p, i, s: {"out": (i["a"] << ((i["b"] & 7) + p["bias"])) & 255},
              "a << (b mod 8)", params={"bias": 0},
              faults=[{"key": "bias", "value": 1, "type": "off_by_one", "port": "out", "desc": "shifts one place too far"}]))
    add(Block("alu_shr", "EX", "alu", {"a": A, "b": Bn}, {"out": W},
              lambda p, i, s: {"out": i["a"] >> ((i["b"] & 7) + p["bias"])},
              "a >> (b mod 8), logical", params={"bias": 0},
              faults=[{"key": "bias", "value": 1, "type": "off_by_one", "port": "out", "desc": "shifts one place too far"}]))
    add(mux("alu_res", "EX", "alu", "idex_aluop.q",
            ["alu_add.out", "alu_sub.out", "alu_and.out", "alu_or.out", "alu_xor.out", "alu_slt.out", "alu_shl.out",
             "alu_shr.out", Bn], W,
            "ALU result by aluop: 0 add, 1 sub, 2 and, 3 or, 4 xor, 5 slt, 6 shl, 7 shr, 8 pass B",
            swaps=[(0, 1), (2, 3), (3, 4), (6, 7), (0, 8)]))

    # ---------------------------------------------------------------- EX: branch unit
    Bv = "fwd_mux_b.out"
    add(Block("br_eq", "EX", "branch", {"a": A, "b": Bv}, {"out": 1}, lambda p, i, s: {"out": int(i["a"] == i["b"])},
              "1 if operand A == forwarded register B"))
    add(Block("br_lt", "EX", "branch", {"a": A, "b": Bv}, {"out": 1},
              lambda p, i, s: {"out": int(i["a"] <= i["b"]) if p["le"] else int(i["a"] < i["b"])},
              "1 if operand A < forwarded register B (unsigned)", params={"le": False},
              faults=[{"key": "le", "value": True, "type": "off_by_one", "port": "out", "desc": "computes A <= B"}]))

    def decide(p, i, s):
        t = i["type"]
        c = i["eq"] if t == 1 else (1 - i["eq"]) if t == 2 else i["lt"] if t == 3 else 0
        return {"taken": int(bool(i["valid"] and c))}
    add(Block("br_decide", "EX", "branch", {"type": "idex_branch.q", "eq": "br_eq.out", "lt": "br_lt.out",
                                             "valid": "idex_valid.q"}, {"taken": 1}, decide,
              "taken = valid AND (type 1: eq, type 2: not eq, type 3: lt, else 0)",
              relevant=lambda i, s: ["type", "valid"] + (["eq"] if i["type"] in (1, 2) else ["lt"] if i["type"] == 3 else [])))
    add(Block("br_target", "EX", "branch", {"pc": "idex_pc.q", "imm": "idex_imm.q"}, {"out": W},
              lambda p, i, s: {"out": i["pc"] + p["plus"] + i["imm"]}, "branch target = pc + 1 + imm (mod 256)",
              params={"plus": 1},
              faults=[{"key": "plus", "value": 0, "type": "off_by_one", "port": "out", "desc": "target = pc + imm"},
                      {"key": "plus", "value": 2, "type": "off_by_one", "port": "out", "desc": "target = pc + 2 + imm"}]))

    # ---------------------------------------------------------------- EX/MEM
    for nm, d, w in [("exmem_alu", "alu_res.out", W), ("exmem_sd", "fwd_mux_b.out", W), ("exmem_rd", "idex_rd.q", 3),
                     ("exmem_regwrite", "idex_regwrite.q", 1), ("exmem_memread", "idex_memread.q", 1),
                     ("exmem_memwrite", "idex_memwrite.q", 1), ("exmem_halt", "idex_halt.q", 1),
                     ("exmem_valid", "idex_valid.q", 1), ("exmem_pc", "idex_pc.q", W)]:
        add(reg(nm, "EX/MEM", d, w, f"EX/MEM latch of {d}"))

    # ---------------------------------------------------------------- MEM
    def dnxt(p, i, s):
        if i["we"]:
            s = list(s)
            s[i["addr"] % MEM_SIZE] = i["wdata"]
        return s
    add(Block("dmem", "MEM", "memory", {"addr": "exmem_alu.q", "wdata": "exmem_sd.q", "we": "exmem_memwrite.q"},
              {"rdata": W}, lambda p, i, s: {"rdata": s[i["addr"] % MEM_SIZE]},
              "data memory (64 bytes): rdata = mem[addr mod 64]; writes wdata at the clock edge when we=1",
              nxt=dnxt, init=lambda: [0] * MEM_SIZE, deps=["addr"], trusted=True, relevant=lambda i, s: ["addr"]))

    # ---------------------------------------------------------------- MEM/WB
    for nm, d, w in [("memwb_alu", "exmem_alu.q", W), ("memwb_mem", "dmem.rdata", W), ("memwb_rd", "exmem_rd.q", 3),
                     ("memwb_regwrite", "exmem_regwrite.q", 1), ("memwb_memread", "exmem_memread.q", 1),
                     ("memwb_halt", "exmem_halt.q", 1), ("memwb_valid", "exmem_valid.q", 1),
                     ("memwb_pc", "exmem_pc.q", W)]:
        add(reg(nm, "MEM/WB", d, w, f"MEM/WB latch of {d}"))

    # ---------------------------------------------------------------- WB
    add(mux("wb_mux", "WB", "writeback", "memwb_memread.q", ["memwb_alu.q", "memwb_mem.q"], W,
            "write-back value: in0 = ALU result when sel=0, in1 = loaded data when sel=1 (LD)"))
    add(Block("wb_guard", "WB", "writeback", {"rw": "memwb_regwrite.q", "rd": "memwb_rd.q"}, {"we": 1},
              lambda p, i, s: {"we": int(bool(i["rw"]) and i["rd"] != 0)}, "we = regwrite AND rd != 0 (r0 stays 0)"))
    add(Block("wb_dec", "WB", "writeback", {"addr": "memwb_rd.q", "en": "wb_guard.we"}, {"onehot": 8},
              lambda p, i, s: {"onehot": (1 << i["addr"]) if i["en"] else 0},
              "write decoder: onehot = 1 << addr when en=1, else 0"))
    return B


# --------------------------------------------------------------------------------------------------- simulator
def trig_active(inp, m):
    """A rare-trigger fault misbehaves only when this hash of the block's inputs is 0 mod m."""
    if not m:
        return True
    h = 7
    for k in sorted(inp):
        h = (h * 131 + inp[k] + 1) % 1000003
    return h % m == 0


class CPU:
    def __init__(self, blocks, fault=None):
        self.blocks = blocks
        self.by = {b.name: b for b in blocks}
        self.faults = list(fault) if isinstance(fault, list) else ([fault] if fault else [])
        self.fault = self.faults[0] if self.faults else None
        self.trig = {f["block"]: f.get("trigger") for f in self.faults if f.get("trigger")}
        self.drivers = {}
        for b in blocks:
            for port in b.outs:
                self.drivers[b.net(port)] = (b.name, port)
        self.order = self._topo()

    def params(self, b):
        return b.eff(self.faults)

    def eval_block(self, b, inp, state=None, p=None, spec=None):
        """Evaluate one block as built (faults applied, rare triggers respected)."""
        if b.name in self.trig and not trig_active(inp, self.trig[b.name]):
            return b.eval(spec or b.eff(None), inp, state)
        return b.eval(p or self.params(b), inp, state)

    def _topo(self):
        seen, out = set(), []

        def visit(b, stack=()):
            if b.name in seen:
                return
            assert b.name not in stack, f"combinational loop through {b.name}"
            for port in b.deps:
                d = self.drivers[b.ins[port]][0]
                visit(self.by[d], stack + (b.name,))
            seen.add(b.name)
            out.append(b)
        for b in self.blocks:
            visit(b)
        return out

    def run(self, prog, data=None, max_cycles=400):
        """Simulate until HALT retires or max_cycles. Returns a Trace."""
        state = {b.name: b.init() for b in self.blocks if b.seq}
        state["imem"] = list(prog)
        mem = [0] * MEM_SIZE
        for a, v in (data or {}).items():
            mem[a % MEM_SIZE] = v & 255
        state["dmem"] = mem
        P = {b.name: self.params(b) for b in self.blocks}
        SP = {name: self.by[name].eff(None) for name in self.trig}
        vals, states, halted = [], [], None
        for c in range(max_cycles):
            v = {}
            for b in self.order:
                inp = {port: v.get(n, 0) for port, n in b.ins.items()}
                if b.name in SP and not trig_active(inp, self.trig[b.name]):
                    out = b.eval(SP[b.name], inp, state.get(b.name))
                else:
                    out = b.eval(P[b.name], inp, state.get(b.name))
                for port, x in out.items():
                    v[b.net(port)] = x
            vals.append(v)
            states.append({k: (tuple(s) if isinstance(s, list) else s) for k, s in state.items() if k != "imem"})
            for b in self.blocks:
                if b.seq:
                    inp = {port: v[n] for port, n in b.ins.items()}
                    state[b.name] = b.nxt(P[b.name], inp, state[b.name])
            if v["memwb_halt.q"] and v["memwb_valid.q"]:
                halted = c
                break
        final = {b.name: (list(s) if isinstance(s, list) else s) for b in self.blocks if b.seq
                 for s in [state[b.name]]}
        return Trace(self, prog, vals, states, halted, final)


class Trace:
    def __init__(self, cpu, prog, vals, states, halted, final):
        self.cpu, self.prog, self.vals, self.states, self.halted = cpu, prog, vals, states, halted
        self.regs = [final[f"r{k}"] for k in range(8)]
        self.regs[0] = 0 if self.regs[0] is None else self.regs[0]
        self.mem = final["dmem"]
        self.n = len(vals)

    def inputs(self, block, c):
        b = self.cpu.by[block]
        return {port: self.vals[c][n] for port, n in b.ins.items()}

    def outputs(self, block, c):
        b = self.cpu.by[block]
        return {port: self.vals[c][b.net(port)] for port in b.outs}

    def state(self, block, c):
        return self.states[c].get(block)

    def instr_at(self, stage, c):
        """Which pc / instruction occupies a pipeline stage at cycle c (None for a bubble)."""
        v = self.vals[c]
        if stage == "IF":
            pc = v["pc.q"]
        elif stage in ("IF/ID", "ID"):
            pc = v["ifid_pc.q"] if v["ifid_valid.q"] else None
        elif stage in ("ID/EX", "EX"):
            pc = v["idex_pc.q"] if v["idex_valid.q"] else None
        elif stage in ("EX/MEM", "MEM"):
            pc = v["exmem_pc.q"] if v["exmem_valid.q"] else None
        else:
            pc = v["memwb_pc.q"] if v["memwb_valid.q"] else None
        if pc is None:
            return None
        return {"pc": pc, "text": disasm(self.prog[pc]) if pc < len(self.prog) else "NOP"}

    def retire(self):
        """The retire stream as the golden interpreter writes it (NOPs and bubbles skipped)."""
        out, stores = [], {}
        for c, v in enumerate(self.vals):
            if v["exmem_valid.q"] and v["exmem_memwrite.q"]:
                stores.setdefault(v["exmem_pc.q"], []).append((v["exmem_alu.q"] % MEM_SIZE, v["exmem_sd.q"]))
            if not v["memwb_valid.q"]:
                continue
            pc = v["memwb_pc.q"]
            w = self.prog[pc] if pc < len(self.prog) else NOP
            if (w >> 12) == 14:
                continue
            rec = {"pc": pc, "text": disasm(w), "cycle": c}
            if v["memwb_regwrite.q"]:
                rec.update(rd=v["memwb_rd.q"], value=v["wb_mux.out"])
            if stores.get(pc):
                a, d = stores[pc].pop(0)
                rec.update(addr=a, data=d)
            out.append(rec)
        return out


def run_test(cpu, t, slack=40):
    g = t["golden"]
    tr = cpu.run(t["prog"], t["data"], max_cycles=3 * len(g["retire"]) + slack)
    ok = tr.halted is not None and tr.regs == g["regs"] and tr.mem == g["mem"]
    return ok, tr


def retire_diff(tr, g):
    """First divergence between the pipeline's retire stream and the golden one."""
    got, exp = tr.retire(), g["retire"]
    keys = ("pc", "rd", "value", "addr", "data")
    for k, e in enumerate(exp):
        if k >= len(got):
            return {"index": k, "expected": e, "got": None, "cycle": tr.n - 1, "kind": "missing"}
        r = got[k]
        if any(r.get(x) != e.get(x) for x in keys):
            kind = "pc" if r["pc"] != e["pc"] else "value" if "rd" in e and r.get("rd") == e.get("rd") and \
                r.get("value") != e.get("value") else "store" if "addr" in e or "addr" in r else "rd"
            return {"index": k, "expected": e, "got": r, "cycle": r["cycle"], "kind": kind}
    if tr.regs != g["regs"] or tr.mem != g["mem"]:
        return {"index": len(exp), "expected": None, "got": None, "cycle": tr.n - 1, "kind": "final"}
    return None


def apply_fix(fault, fix):
    """The faults left after fixes ({block, key} or a list): a fix removes the fault whose param it puts back."""
    faults = list(fault) if isinstance(fault, list) else ([fault] if fault else [])
    fixes = list(fix) if isinstance(fix, list) else ([fix] if fix else [])
    left = [f for f in faults if not any(x and x.get("block") == f["block"] and x.get("key") == f["key"] for x in fixes)]
    if isinstance(fault, list):
        return left
    return left[0] if left else None


def all_faults(blocks):
    out = []
    for b in blocks:
        for f in b.faults:
            out.append(dict(f, block=b.name))
    return out


def clone(blocks):
    return copy.deepcopy(blocks)
