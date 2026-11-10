#!/usr/bin/env python3
"""Static checks of a linked GLASSLYCFW runtime listing (objdump -d -M no-aliases).

  isa        every instruction is RV32IMC: the NIMO core runs stock code built
             without the A extension (no AMO/LR/SC anywhere in the stock
             functions), so an AMO traps as an illegal instruction
  packet     multi-byte loads/stores whose base register derives from packet
             bytes (the router payload or a UI job's copy), by register and
             stack-slot dataflow over each function's control flow and into the
             callees the tainted pointers are passed to
  stack      deepest static frame chain from each entry point (stock callees
             not included; indirect calls go to every address-taken function)

Used by build_runtime.py (the build fails on an ISA or packet finding) and by
tests/rv32/runtime_emulator_test.py. Offline only. MIT.
"""
import argparse
import json
from pathlib import Path
import re

BASE = {"lui", "auipc", "jal", "jalr", "beq", "bne", "blt", "bge", "bltu", "bgeu", "lb", "lh", "lw",
        "lbu", "lhu", "sb", "sh", "sw", "addi", "slti", "sltiu", "xori", "ori", "andi", "slli", "srli",
        "srai", "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and", "fence", "ecall",
        "ebreak", "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu"}
COMPRESSED_FP = {"c.flw", "c.fsw", "c.flwsp", "c.fswsp", "c.fld", "c.fsd", "c.fldsp", "c.fsdsp"}
LOADS = {"lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4, "c.lw": 4, "c.lwsp": 4}
STORES = {"sb": 1, "sh": 2, "sw": 4, "c.sw": 4, "c.swsp": 4}
BRANCHES = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "c.beqz", "c.bnez"}
ARGS = [f"a{i}" for i in range(8)]
CALLER_SAVED = {"ra", *ARGS, *(f"t{i}" for i in range(7))}
# Packet pointers on entry: the router gate's s5 (payload) and the UI side's
# copy, which nimo_ui_scene passes to the session as job->data.
PACKET_SEEDS = {"glassly_router_gate": {"s5"}, "mm_scene_session_dispatch": {"a1"}}
UI_ENTRIES = ("nimo_ui_scene", "nimo_ui_acquire", "nimo_ui_release", "nimo_ui_brightness",
              "nimo_ui_draw_test", "pump")
ROUTER_ENTRIES = ("glassly_router_gate",)


def code_files(readelf_symbols):
    """{start: object file} for every code symbol (FILE symbols open each
    object's locals; globals belong to the object whose locals surround them)."""
    current, spans, rows = None, {}, []
    for line in readelf_symbols.splitlines():
        f = line.split()
        if len(f) < 8 or not f[0].endswith(":"):
            continue
        if f[3] == "FILE":
            current = f[7]
            continue
        if f[6] != "1" or f[3] not in ("FUNC", "NOTYPE"):
            continue
        value = int(f[1], 16)
        if f[4] == "LOCAL" and current:
            lo, hi = spans.get(current, (value, value))
            spans[current] = (min(lo, value), max(hi, value))
        rows.append(value)
    files = {}
    ordered = sorted(spans.items(), key=lambda kv: kv[1][0])
    for value in rows:
        owner = None
        for name, (lo, _) in ordered:
            if lo <= value:
                owner = name
        files[value] = (owner or "").rsplit(".", 1)[0]
    return files


# An indirect call reaches the hooks the layer above stored: the portable
# scene core calls scene_session.c's platform adapters, which call display.c's
# session hooks. Runtime code reaches stock only through constant addresses.
HOOK_OWNER = {"scene_session": "display"}
CORE_HOOK_OWNER = "scene_session"


def code_ranges(readelf_symbols):
    """{start: end} of every code symbol, from `readelf -sW runtime.elf`: FUNC
    symbols by their size, the assembly gates (NOTYPE globals) up to the next
    symbol. Strings merged into .text have no symbol and are excluded."""
    rows = []
    for line in readelf_symbols.splitlines():
        f = line.split()
        if len(f) >= 8 and f[0].endswith(":") and f[6] == "1" and not f[7].startswith("$"):
            rows.append((int(f[1], 16), int(f[2]), f[3], f[4], f[7]))
    starts = sorted({r[0] for r in rows})
    ranges = {}
    for value, size, kind, bind, name in rows:
        if kind == "FUNC" and size:
            ranges[value] = value + size
        elif kind == "NOTYPE" and bind == "GLOBAL":
            later = [s for s in starts if s > value]
            ranges[value] = later[0] if later else value
    return ranges


def parse_listing(text, ranges=None):
    """Functions by start address: name, instructions (address, mnemonic, operands, target).
    With ranges (code_ranges), only symbols that are code, and only their bytes."""
    funcs, current = {}, None
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{8}) <([^>]+)>:$", line)
        if m:
            start = int(m.group(1), 16)
            current = {"name": m.group(2), "start": start, "insns": []}
            funcs[start] = current
            continue
        fields = line.split("\t")
        if current is None or len(fields) < 3 or not re.match(r"^\s*[0-9a-f]+:$", fields[0]):
            continue
        address = int(fields[0].strip()[:-1], 16)
        mnemonic = fields[2].strip()
        rest = "\t".join(fields[3:])
        operands, _, comment = rest.partition("#")
        target = None
        m = re.match(r"\s*([0-9a-f]+)(?:\s|$)", comment) if comment else None
        if m:
            target = int(m.group(1), 16)
        elif mnemonic in BRANCHES | {"jal", "c.j", "c.jal"}:
            m = re.search(r"([0-9a-f]+) <", operands)
            if m:
                target = int(m.group(1), 16)
        if ranges is None or address < ranges.get(current["start"], 0):
            current["insns"].append((address, mnemonic, operands.strip(), target))
    if ranges is not None:
        funcs = {a: f for a, f in funcs.items() if a in ranges}
    return {a: f for a, f in funcs.items() if f["insns"]}


def isa_violations(funcs):
    bad = []
    for f in funcs.values():
        for address, mnemonic, operands, _ in f["insns"]:
            ok = mnemonic in BASE or (mnemonic.startswith("c.") and mnemonic not in COMPRESSED_FP)
            if not ok:
                bad.append({"address": hex(address), "function": f["name"], "insn": f"{mnemonic} {operands}"})
    return bad


def _ops(operands):
    return [o.strip() for o in operands.split(",")] if operands else []


def _mem(operand):
    m = re.match(r"(-?\d+)\((\w+)\)", operand)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def _blocks(f):
    insns = f["insns"]
    index = {a: i for i, (a, *_rest) in enumerate(insns)}
    succ = {}
    for i, (address, mnemonic, operands, target) in enumerate(insns):
        nxt = [i + 1] if i + 1 < len(insns) else []
        if mnemonic in BRANCHES:
            succ[i] = nxt + ([index[target]] if target in index else [])
        elif mnemonic == "c.j" or (mnemonic == "jal" and _ops(operands)[:1] == ["zero"]):
            succ[i] = [index[target]] if target in index else []
        elif mnemonic == "c.jr" or (mnemonic == "jalr" and _ops(operands)[:1] == ["zero"]):
            succ[i] = []
        else:
            succ[i] = nxt
    return succ


def _call(mnemonic, operands):
    ops = _ops(operands)
    if mnemonic in ("c.jalr", "c.jal"):
        return True
    return mnemonic in ("jal", "jalr") and ops[:1] == ["ra"]


def _taint_function(f, entry, sink, calls):
    """Forward dataflow: state = (tainted registers, tainted sp slots)."""
    insns = f["insns"]
    succ = _blocks(f)
    states = {0: (frozenset(entry), frozenset())}
    work = [0]
    while work:
        i = work.pop()
        regs, slots = (set(s) for s in states[i])
        address, mnemonic, operands, target = insns[i]
        ops = _ops(operands)
        if mnemonic in LOADS:
            off, base = _mem(ops[1]) if mnemonic != "c.lwsp" else _mem(ops[1])
            if LOADS[mnemonic] > 1 and base in regs:
                sink(f, insns[i])
            regs.discard(ops[0])
            if base == "sp" and off in slots:
                regs.add(ops[0])
        elif mnemonic in STORES:
            off, base = _mem(ops[1])
            if STORES[mnemonic] > 1 and base in regs:
                sink(f, insns[i])
            if base == "sp":
                (slots.add if ops[0] in regs else slots.discard)(off)
        elif _call(mnemonic, operands):
            tainted_args = {a for a in ARGS if a in regs}
            callee = target
            if tainted_args and callee is not None:
                calls.append((callee, tainted_args))
            regs -= CALLER_SAVED
        elif mnemonic in ("addi", "c.addi", "c.mv", "c.addi4spn", "c.addi16sp"):
            src = ops[0] if mnemonic == "c.addi" else ops[1]
            (regs.add if src in regs else regs.discard)(ops[0])
        elif mnemonic in ("add", "c.add"):
            srcs = ops[1:3] if mnemonic == "add" else ops[0:2]
            (regs.add if any(s in regs for s in srcs) else regs.discard)(ops[0])
        elif mnemonic == "sub":
            (regs.add if ops[1] in regs and ops[2] not in regs else regs.discard)(ops[0])
        elif ops and mnemonic not in BRANCHES and mnemonic not in ("c.j", "c.jr", "jal", "jalr", "fence",
                                                                      "ecall", "ebreak", "c.nop", "c.ebreak"):
            regs.discard(ops[0])
        state = (frozenset(regs), frozenset(slots))
        for j in succ[i]:
            old = states.get(j)
            new = state if old is None else (old[0] | state[0], old[1] | state[1])
            if new != old:
                states[j] = new
                work.append(j)


def packet_accesses(funcs, seeds=PACKET_SEEDS):
    by_name = {}
    for f in funcs.values():
        by_name.setdefault(f["name"], []).append(f)
    entry = {}
    for name, regs in seeds.items():
        for f in by_name.get(name, []):
            entry[f["start"]] = set(regs)
    flagged, done = {}, {}
    work = list(entry)
    while work:
        start = work.pop()
        regs = frozenset(entry[start])
        if done.get(start) == regs:
            continue
        done[start] = regs
        calls = []

        def sink(f, insn):
            flagged[insn[0]] = {"address": hex(insn[0]), "function": f["name"], "insn": f"{insn[1]} {insn[2]}"}
        _taint_function(funcs[start], regs, sink, calls)
        for callee, args in calls:
            if callee in funcs:
                merged = entry.setdefault(callee, set()) | args
                if merged != entry[callee] or callee not in done:
                    entry[callee] = merged
                    work.append(callee)
    reached = sorted({funcs[s]["name"] for s in done})
    return sorted(flagged.values(), key=lambda r: r["address"]), reached


def frame_bytes(f):
    total = 0
    for _, mnemonic, operands, _ in f["insns"]:
        ops = _ops(operands)
        if mnemonic in ("addi", "c.addi", "c.addi16sp") and ops[:1] == ["sp"]:
            value = int(ops[-1], 0)
            if value < 0:
                total -= value
    return total


def _jump_register(mnemonic, operands):
    """Register an indirect call or jump goes through, or None."""
    ops = _ops(operands)
    if mnemonic in ("c.jalr", "c.jr"):
        return ops[0]
    if mnemonic == "jalr":
        return _mem(ops[1])[1] if len(ops) > 1 and "(" in ops[1] else ops[-1]
    return None


def call_graph(funcs, files=None):
    """Edges between runtime functions, stock calls per function, and the
    functions whose address is stored to memory (hooks: indirect targets),
    by the object that stores them."""
    files = files or {}
    taken, edges, stock = {}, {}, {}
    for start, f in funcs.items():
        consts, out, calls_stock, indirect = {}, set(), set(), False
        for address, mnemonic, operands, target in f["insns"]:
            ops = _ops(operands)
            jump = mnemonic == "c.j" or (mnemonic == "jal" and ops[:1] == ["zero"])
            reg = _jump_register(mnemonic, operands)
            if _call(mnemonic, operands) or reg is not None or jump:
                if mnemonic == "c.jr" and ops == ["ra"]:
                    continue
                dest = target if target is not None else consts.get(reg)
                if jump and (dest is None or dest in range(start, start + 1 << 20) and dest not in funcs):
                    continue                                   # a jump inside this function
                if dest in funcs:
                    if dest != start:
                        out.add(dest)
                elif dest is not None:
                    calls_stock.add(dest)
                else:
                    indirect = True
                if _call(mnemonic, operands):
                    consts = {r: v for r, v in consts.items() if r not in CALLER_SAVED}
                continue
            if mnemonic in STORES and ops[0] in consts and consts[ops[0]] in funcs:
                taken.setdefault(files.get(start, ""), set()).add(consts[ops[0]])
            if mnemonic in ("addi", "c.addi") and target is not None:
                consts[ops[0]] = target
            elif mnemonic == "c.mv" and ops[1] in consts:
                consts[ops[0]] = consts[ops[1]]
            elif ops and mnemonic not in STORES and mnemonic not in BRANCHES:
                consts.pop(ops[0], None)
        edges[start] = (out, indirect)
        stock[start] = calls_stock
    every = set().union(*taken.values()) if taken else set()

    def hooks(start):
        if not files:
            return every
        owner = HOOK_OWNER.get(files.get(start), CORE_HOOK_OWNER)
        return taken.get(owner, set())
    return {s: o | (hooks(s) if ind else set()) for s, (o, ind) in edges.items()}, stock, taken


def stack_chains(funcs, entries, files=None):
    edges, stock, taken = call_graph(funcs, files)
    edges = {s: e - {s} for s, e in edges.items()}
    memo, cycles = {}, []

    def depth(start, stack):
        """(bytes, chain, cut): cut when a cycle was broken below, so the value
        depends on the path and is not memoized."""
        if start in memo:
            return memo[start]
        if start in stack:
            cycles.append([funcs[s]["name"] for s in stack[stack.index(start):]] + [funcs[start]["name"]])
            return (0, [], True)
        best, cut = (0, []), False
        for callee in sorted(edges[start]):
            d = depth(callee, stack + [start])
            cut |= d[2]
            if d[0] > best[0]:
                best = d[:2]
        frame = frame_bytes(funcs[start])
        value = (frame + best[0], [f"{funcs[start]['name']}:{frame}"] + best[1], cut)
        if not cut:
            memo[start] = value
        return value

    result = {}
    for name in entries:
        for start, f in funcs.items():
            if f["name"] == name:
                d, path, _ = depth(start, [])
                result[name] = {"bytes": d, "chain": path}
    return result, sorted({" > ".join(c) for c in cycles})


def scan(asm_text, readelf_symbols):
    funcs = parse_listing(asm_text, code_ranges(readelf_symbols))
    packet, reached = packet_accesses(funcs)
    stacks, cycles = stack_chains(funcs, ROUTER_ENTRIES + UI_ENTRIES, code_files(readelf_symbols))
    return {"isa": isa_violations(funcs), "packet_wide_accesses": packet, "packet_functions": reached,
            "stack": stacks, "stack_cycles": cycles,
            "ui_max": max((v["bytes"] for k, v in stacks.items() if k in UI_ENTRIES), default=0),
            "router_max": max((v["bytes"] for k, v in stacks.items() if k in ROUTER_ENTRIES), default=0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("build", type=Path, help="build_runtime.py output directory (runtime.asm, symbols.txt)")
    args = parser.parse_args()
    print(json.dumps(scan((args.build / "runtime.asm").read_text(), (args.build / "symbols.txt").read_text()), indent=2))


if __name__ == "__main__":
    main()
