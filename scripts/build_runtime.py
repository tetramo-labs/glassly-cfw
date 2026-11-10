#!/usr/bin/env python3
"""Build a GLASSLYCFW runtime image for the NIMO 1.1.5.1 application.

Applies a string-edit manifest (patches/glasslycfw-*/1.1.5.1.json) with the
version tag set to GLASSLYCFW/<revision>, compiles runtime/nimo/ and the
portable scene core for the XIP address just past the stock application body,
applies each witnessed data patch and code hook, appends the blob, repacks the
OTA, and checks the result: every patched site is disassembled and decoded,
no stock branch lands inside a hook, and no other byte changed. Offline only.
"""
import argparse
import functools
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cfw  # noqa: E402
import nimo_ota  # noqa: E402
import runtime_scan  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin"
RUNTIME = ROOT / "runtime/nimo"
PORTABLE = ROOT / "runtime/portable"
SOURCES = [RUNTIME / n for n in ("entry.S", "glassly.c", "display.c", "scene_session.c", "freestanding.c")] + \
          [PORTABLE / n for n in ("scene.c", "geometry.c", "vector.c", "rle.c", "raster_commands.c",
                                  "rect_copy_commands.c")]
APP_TYPE = 0x20
LOAD = 0x041B4020
VERSION_OLD = "v1.1.5.1-20261027111705-8e6f7a-Debug"
# Code hooks replace exactly the witnessed 8 bytes. A jump hook is
# `auipc t1; jalr x0, t1` (the gate leaves on its own); a call hook is
# `auipc ra; jalr ra, ra` (the gate returns to address+8). `function` is the
# containing stock function, scanned so no branch lands inside the hook.
HOOKS = [
    {"name": "router-unrouted", "kind": "jump", "address": 0x0426E02E, "witness": "378637044a87d287",
     "target": "glassly_router_gate", "function": [0x0426DFA8, 384],
     "replay": ["lui\ta2,0x4378", "c.mv\ta4,s2", "c.mv\ta5,s4"]},
    {"name": "frame-flush", "kind": "call", "address": 0x041FD63C, "witness": "4a8781499c4b8297",
     "target": "glassly_flush_gate", "function": [0x041FD3E2, 1830],
     "replay": ["c.mv\ta4,s2", "c.li\ts3,0"]},
    {"name": "frame-kick", "kind": "jump", "address": 0x041F703C, "witness": "83c7514891cf0111",
     "target": "glassly_kick_gate", "function": [0x041F703C, 122],
     "replay": ["lbu\ta5,1157(gp)", "c.addi\tsp,-32"]},
    {"name": "ui-dispatch", "kind": "jump", "address": 0x04208DD2, "witness": "1971a2dca6daced6",
     "target": "glassly_input_gate", "function": [0x04208DD2, 7686], "listing": 40,
     "replay": ["c.addi16sp\tsp,-128", "c.swsp\ts0,120(sp)", "c.swsp\ts1,116(sp)", "c.swsp\ts3,108(sp)"]},
]
# The lease borrows one of the two stock framebuffers (runtime/nimo/stock.h).
# Every stock function that forms an address inside them, and what it does
# there; the build fails if the set changes. Only the commit (reached through
# the gated kick) writes the buffer the index bytes do not name.
FRAMEBUFFERS = (0x0202F064, 0x02053F04)
FB_INDEX = {"back": 0x020120FB, "front": 0x0201198A}
FB_USERS = [
    (0x041B4084, 0xFA3C, "startup copy source of the RAM code (never executed in place)"),
    (0x0200023A, 0x294, "LVGL flush: L8 to GRAY4 into the back buffer"),
    (0x041FCD42, 348, "commit helper: scroller band into a named buffer"),
    (0x041FD2C4, 286, "commit helper: back copied to front"),
    (0x041FD3E2, 1830, "frame task: clears margins of the buffer it flushes"),
    (0x041FDB08, 1826, "commit: copies back to front, flips the indices"),
    (0x041FE23E, 606, "scroller: draws into the back buffer"),
    (0x041FE51C, 470, "scroller: reads the back buffer"),
    (0x041FE6F2, 40, "returns the front buffer (screenshot, read only)"),
    (0x041FEBB2, 60, "clear: zeroes the back buffer"),
]
FB_INDEX_WRITERS = [(0x041FDB08, 1826)]   # the commit
FB_INDEX_READ_ONLY_TAKES = [0x041FD330]  # address of the front index in a register, loads only
# Byte replacements with witness bytes. The heap carve gives the runtime
# RAM_BLOCK and CRUMBS: the only heap region starts 4.25 KiB later and the boot
# .bss clear runs 4 KiB further, so the block is zeroed every boot, the
# breadcrumbs survive a reset, and no stock code allocates either.
STOCK_HEAP_START, HEAP_END = 0x0209BE74, 0x020FEFC0
RAM_BLOCK = (0x0209BE74, 0x0209CE74)
CRUMBS = (0x0209CE74, 0x0209CF74)
DATA_PATCHES = [
    {"name": "heap-region-start", "address": 0x04414F5C,
     "witness": "74be09024c31060002000000", "patched": "74cf09024c20060002000000"},
    {"name": "bss-clear-end", "address": 0x041C3B96, "witness": "b7c70902", "patched": "b7d70902"},
]
BSS_CLEAR_ADDI = 0x041C3B9A
RAM_CODE = (0x041B4084, 0x02000000, 0xFA3C)   # XIP source, RAM address, bytes (startup copy)
# Scene capacities: 128 objects, 128 assets and a 64 KiB store fit the heap left
# after the lease (about 193 KB free, 48 KB kept for the stock firmware).
DEFINES = ["-DMM_SCENE_STEREO_EYES", "-DMM_SCENE_FIXED_EYE", "-DMM_RASTER_COMMANDS",
           "-DMM_COMMAND_BUNDLES", "-DMM_RECT_COPY", "-DCFW_CACHE_OBJECTS=128u", "-DCFW_CACHE_ASSETS=128u",
           "-DCFW_TEXTURE_CACHE_SIZE=65536u"]
# RV32IMC: the core has no A extension (no AMO/LR/SC anywhere in the stock
# code; it masks interrupts instead), and wide accesses stay aligned.
FLAGS = ["-march=rv32imc", "-mabi=ilp32", "-mstrict-align", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0",
         "-Os", "-ffreestanding", "-fno-builtin", "-fno-common", "-fno-pic", "-fno-pie", "-fno-stack-protector",
         "-fno-tree-loop-distribute-patterns", "-fno-jump-tables", "-ffunction-sections", "-fdata-sections",
         "-fstack-usage", "-Wall", "-Wextra", "-Werror", "-nostdlib", "-std=c11"]
MAX_FRAME = 512
# mm_scene_memcpy copies words only when both pointers are 4-aligned (tested
# at run time); every other packet read is bytewise.
PACKET_WIDE_REVIEWED = ("mm_scene_memcpy",)
# The GUI task (gui_task, created at 0x04207004 from the attributes at
# 0x0430d148) has a 32 KiB stack; its loop and async drain take 576 B above a
# posted job and send_response's static chain about 1.4 KiB.
UI_TASK_STACK = 32768
UI_STACK_BUDGET = 8192
# The router task already runs build_response with a 608-byte frame; the
# command handler's 500-byte reply buffer lives there too (as in revision 4).
FRAME_ALLOWANCE = {"glassly_command": 640}


def tool(name):
    return str(TOOLS / f"riscv-none-elf-{name}")


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True).stdout


def linker_script(origin, limit):
    return f"""
MEMORY {{ rx (rx) : ORIGIN = {origin:#x}, LENGTH = {limit:#x} }}
SECTIONS {{
  .text : {{
    KEEP(*(.text.entry))
    *(.text .text.*)
    *(.rodata .rodata.* .srodata .srodata.*)
  }} > rx
  .data : {{ *(.data .data.* .sdata .sdata.*) }} > rx
  .bss : {{ *(.bss .bss.* .sbss .sbss.* COMMON) }} > rx
  /DISCARD/ : {{ *(.comment) *(.note*) *(.riscv.attributes) *(.eh_frame*) }}
}}
ASSERT(SIZEOF(.data) == 0, "the runtime runs from flash: no writable statics")
ASSERT(SIZEOF(.bss) == 0, "the runtime runs from flash: no writable statics")
"""


def size_breakdown(map_text):
    """Bytes each object contributes to the linked .text (after gc-sections)."""
    sizes = {}
    output = False
    pending = None
    for line in map_text.splitlines():
        if line.startswith(".text"):
            output = True
            continue
        if output and line and not line.startswith(" "):
            output = line.startswith(".text")
            continue
        if not output:
            continue
        m = re.match(r"^ (\.\S+)?\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+\.o)$", line)
        if m and (m.group(1) or pending):
            sizes[Path(m.group(4)).stem] = sizes.get(Path(m.group(4)).stem, 0) + int(m.group(3), 16)
            pending = None
            continue
        pending = re.match(r"^ \.\S+$", line)
    return dict(sorted(sizes.items(), key=lambda kv: -kv[1]))


def compile_runtime(origin, limit, revision, out):
    out.mkdir(parents=True, exist_ok=True)
    script = out / "runtime.ld"
    script.write_text(linker_script(origin, limit))
    include = ["-I" + str(RUNTIME), "-I" + str(PORTABLE)]
    objects = []
    for source in SOURCES:
        obj = out / (source.stem + ".o")
        extra = ["-Wno-unused-function"] if source.parent == PORTABLE else ["-Wcast-align=strict"]
        run(tool("gcc"), *FLAGS, *extra, *DEFINES, *include, f"-DGLASSLY_CFW_REVISION={revision}",
            "-c", source, "-o", obj)
        objects.append(obj)
    elf = out / "runtime.elf"
    run(tool("gcc"), *FLAGS, "-T", script, "-Wl,--gc-sections,--no-relax,--build-id=none,--fatal-warnings",
        f"-Wl,-Map={out / 'runtime.map'}", *objects, "-o", elf)
    undefined = run(tool("nm"), "-u", elf).split()
    nimo_ota.require(not undefined, f"undefined symbols: {undefined}")
    blob_path = out / "runtime.bin"
    run(tool("objcopy"), "-O", "binary", "--only-section=.text", elf, blob_path)
    asm = run(tool("objdump"), "-d", "-M", "no-aliases", elf)
    (out / "runtime.asm").write_text(asm)
    readelf = run(tool("readelf"), "-sW", elf)
    (out / "symbols.txt").write_text(readelf)
    symbols = {}
    for line in run(tool("nm"), elf).splitlines():
        value, kind, name = line.split()
        if kind in "Tt":
            symbols[name] = int(value, 16)
    frames = []
    for su in sorted(out.glob("*.su")):
        for row in su.read_text().splitlines():
            where, size, kind = row.split("\t")
            frames.append({"function": where, "bytes": int(size), "kind": kind})
    bad = [f for f in frames if f["kind"] != "static" or
           f["bytes"] > FRAME_ALLOWANCE.get(f["function"].rsplit(":", 1)[-1], MAX_FRAME)]
    nimo_ota.require(not bad, f"stack frames over {MAX_FRAME} bytes or dynamic: {bad}")
    largest = sorted(frames, key=lambda f: -f["bytes"])[:5]
    breakdown = size_breakdown((out / "runtime.map").read_text())
    scan = runtime_scan.scan(asm, readelf)
    nimo_ota.require(not scan["isa"], f"instructions outside RV32IMC: {scan['isa'][:8]}")
    packet = [a for a in scan["packet_wide_accesses"] if not a["function"].startswith(PACKET_WIDE_REVIEWED)]
    nimo_ota.require(not packet, f"multi-byte accesses through packet pointers: {packet}")
    nimo_ota.require(scan["ui_max"] <= UI_STACK_BUDGET, f"UI-task frame chain {scan['ui_max']} B over {UI_STACK_BUDGET}")
    return blob_path.read_bytes(), symbols, asm, breakdown, largest, scan


def auipc_pair(at, target, rd, rs_jalr, rd_jalr):
    offset = target - at
    hi = (offset + 0x800) >> 12
    lo = offset - (hi << 12)
    auipc = ((hi & 0xFFFFF) << 12) | (rd << 7) | 0x17
    jalr = ((lo & 0xFFF) << 20) | (rs_jalr << 15) | (rd_jalr << 7) | 0x67
    return struct.pack("<II", auipc, jalr)


def hook_bytes(hook, target):
    if hook["kind"] == "jump":
        return auipc_pair(hook["address"], target, 6, 6, 0)      # auipc t1; jalr x0, lo(t1)
    return auipc_pair(hook["address"], target, 1, 1, 1)          # auipc ra; jalr ra, lo(ra)


def disassemble(data, address):
    return list(_disassemble(bytes(data), address))


@functools.lru_cache(maxsize=8)
def _disassemble(data, address):
    with tempfile.NamedTemporaryFile(suffix=".bin") as f:
        f.write(data)
        f.flush()
        text = run(tool("objdump"), "-D", "-b", "binary", "-m", "riscv:rv32", "-M", "no-aliases",
                   f"--adjust-vma={address:#x}", f.name)
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$", line)
        if m:
            rows.append((int(m.group(1), 16), m.group(3), m.group(4).split("#")[0].strip()))
    return tuple(rows)


def decode_auipc_pair(rows):
    (a0, m0, o0), (a1, m1, o1) = rows[0], rows[1]
    nimo_ota.require(m0 == "auipc" and m1 == "jalr", f"not an auipc/jalr pair: {rows[:2]}")
    rd, hi = o0.split(",")
    m = re.match(r"(\w+),(-?\d+)\((\w+)\)", o1)
    nimo_ota.require(m is not None, f"unexpected jalr operands {o1}")
    hi = int(hi, 0)
    target = (a0 + (hi << 12) + int(m.group(2))) & 0xFFFFFFFF
    return rd, m.group(1), m.group(3), target


def branch_targets(rows):
    targets = []
    for address, mnemonic, operands in rows:
        if mnemonic.startswith(("b", "c.b", "jal", "c.j")) and not mnemonic.startswith(("jalr", "c.jr", "c.jalr")):
            last = operands.split(",")[-1]
            if re.fullmatch(r"0x[0-9a-f]+", last):
                targets.append((address, int(last, 16)))
    return targets


def gate_listing(asm, symbol, count):
    lines = asm.split(f"<{symbol}>:\n", 1)[1].splitlines()
    rows = []
    for line in lines:
        m = re.match(r"^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)\s*(.*)$", line)
        if not m:
            break
        rows.append(f"{m.group(2)}\t{m.group(3).split('#')[0].strip()}".rstrip())
        if len(rows) == count:
            break
    return rows


def ram_header_constants():
    text = (RUNTIME / "ram.h").read_text()
    values = [int(re.search(rf"#define {name} (0x[0-9a-f]+)", text).group(1), 16)
              for name in ("NIMO_RAM_BASE", "NIMO_RAM_BYTES", "NIMO_CRUMB_BASE", "NIMO_CRUMB_BYTES")]
    return tuple(values)


NO_DEST = {"sb", "sh", "sw", "c.sw", "c.swsp", "fsw", "c.fsw", "c.fswsp", "c.fsd", "c.fsdsp",
           "beq", "bne", "blt", "bge", "bltu", "bgeu", "c.beqz", "c.bnez", "c.j", "c.jr"}


def stock_references(body, lo, hi):
    """Stock instructions that compute an address in [lo, hi) (lui/auipc plus
    addi or a load/store offset), XIP code and the startup RAM-code copy."""
    hits = []
    xip, ram, size = RAM_CODE
    for data, vma in ((bytes(body), LOAD), (bytes(body[xip - LOAD:xip - LOAD + size]), ram)):
        upper = {}
        for address, mnemonic, operands in disassemble(data, vma):
            ops = [o.strip() for o in operands.split(",")] if operands else []
            if mnemonic == "lui" and len(ops) == 2:
                upper[ops[0]] = int(ops[1], 0) << 12
                continue
            if mnemonic == "auipc" and len(ops) == 2:
                upper[ops[0]] = (address + (int(ops[1], 0) << 12)) & 0xFFFFFFFF
                continue
            base = imm = None
            if mnemonic == "addi" and len(ops) == 3 and ops[1] in upper:
                base, imm = ops[1], int(ops[2], 0)
            m = re.match(r"(-?\d+)\((\w+)\)", ops[-1]) if ops else None
            if m and m.group(2) in upper:
                base, imm = m.group(2), int(m.group(1))
            if base is not None and lo <= (upper[base] + imm) & 0xFFFFFFFF < hi:
                hits.append((address, mnemonic, operands, (upper[base] + imm) & 0xFFFFFFFF))
            if ops and mnemonic not in NO_DEST:
                upper.pop(ops[0], None)
    return hits


GP = 0x02011B20


def gp_references(body, targets):
    """Stock instructions that reach one of `targets` through gp: a load or
    store with a gp base, or `addi rd, gp, imm` taking the address."""
    hits = []
    xip, ram, size = RAM_CODE
    for data, vma in ((bytes(body), LOAD), (bytes(body[xip - LOAD:xip - LOAD + size]), ram)):
        for address, mnemonic, operands in disassemble(data, vma):
            ops = [o.strip() for o in operands.split(",")] if operands else []
            value = None
            if mnemonic in ("addi", "c.addi") and len(ops) == 3 and ops[1] == "gp":
                value = GP + int(ops[2], 0)
            m = re.match(r"(-?\d+)\(gp\)", ops[-1]) if ops else None
            if m:
                value = GP + int(m.group(1))
            if value in targets:
                hits.append((address, mnemonic, operands, value))
    return hits


def in_ranges(address, ranges):
    return any(start <= address < start + size for start, size in ranges)


def check_framebuffers(body):
    users = {}
    for address, mnemonic, operands, value in stock_references(body, *FRAMEBUFFERS):
        owner = next((u for u in FB_USERS if u[0] <= address < u[0] + u[1]), None)
        nimo_ota.require(owner is not None, f"unlisted stock framebuffer user at {address:#x}: {mnemonic} {operands}")
        users.setdefault(owner[2], []).append(f"{address:#010x} {mnemonic} {operands} -> {value:#x}")
    nimo_ota.require(len(users) == len(FB_USERS), f"listed framebuffer users no longer reach them: {sorted(users)}")
    for name, address in FB_INDEX.items():
        nimo_ota.require(not stock_references(body, address, address + 1), f"{name} index formed without gp")
    index = gp_references(body, set(FB_INDEX.values()))
    for address, mnemonic, operands, value in index:
        load = mnemonic in ("lbu", "lb", "c.lbu")
        nimo_ota.require(load or in_ranges(address, FB_INDEX_WRITERS) or address in FB_INDEX_READ_ONLY_TAKES,
                         f"stock code outside the commit writes or takes a framebuffer index: "
                         f"{address:#x} {mnemonic} {operands}")
    return {"users": users, "index_references": [f"{a:#010x} {m} {o} -> {v:#x}" for a, m, o, v in index]}


def check_data_patches(body):
    start, size, caps = struct.unpack_from("<III", body, 0x04414F5C - LOAD)
    nimo_ota.require((start, caps) == (CRUMBS[1], 2) and start + size == HEAP_END,
                     "heap region does not start past the breadcrumbs and keep its end")
    rows = disassemble(bytes(body[0x041C3B96 - LOAD:0x041C3B96 - LOAD + 8]), 0x041C3B96)
    nimo_ota.require([r[1] for r in rows[:2]] == ["lui", "addi"], "bss clear end is not lui/addi")
    hi = int(rows[0][2].split(",")[1], 0)
    lo = int(rows[1][2].split(",")[2], 0)
    nimo_ota.require(((hi << 12) + lo) & 0xFFFFFFFF == RAM_BLOCK[1], "bss clear does not end at the RAM block end")
    base, ram_bytes, crumb_base, crumb_bytes = ram_header_constants()
    nimo_ota.require((base, base + ram_bytes) == RAM_BLOCK and (crumb_base, crumb_base + crumb_bytes) == CRUMBS,
                     "runtime/nimo/ram.h disagrees with the carve")
    # No stock instruction addresses the carve except the clear's end bound.
    refs = stock_references(body, STOCK_HEAP_START - 16, CRUMBS[1] + 16)
    nimo_ota.require([(a, v) for a, _, _, v in refs] == [(BSS_CLEAR_ADDI, RAM_BLOCK[1])],
                     f"stock code addresses the runtime RAM: {[(hex(a), m, o, hex(v)) for a, m, o, v in refs]}")
    return {"heap_region": [hex(start), hex(size), caps], "crumbs": [hex(CRUMBS[0]), hex(CRUMBS[1])],
            "stock_references": [f"{a:#010x} {m} {o} -> {v:#x}" for a, m, o, v in refs],
            "bss_clear_end": hex(((hi << 12) + lo) & 0xFFFFFFFF),
            "bss_clear_listing": [f"{a:#010x} {m} {o}" for a, m, o in rows[:2]]}


def build(source, strings, revision, out):
    nimo_ota.require(nimo_ota.sha(source) == strings["source"]["sha256"], "Source differs from the manifest")
    tag = f"v1.1.5.1-GLASSLYCFW/{revision}"
    edits = [dict(e, new=tag) if e["old"] == VERSION_OLD else e for e in strings["edits"]]
    nimo_ota.require(any(e["old"] == VERSION_OLD for e in edits), "Manifest lacks the version tag edit")
    layout, streams = nimo_ota.unpack_ota(source)
    rows = [s for s in streams if s["info"].get("partition_type") == APP_TYPE]
    nimo_ota.require(len(rows) == 1, "No unique application component")
    app = rows[0]
    nimo_ota.require(app["info"]["load_address_candidate"] == LOAD, "Unexpected application load address")
    stock = app["raw"][32:]
    body = bytearray(build_cfw.apply_edits(stock, edits))
    edited = bytes(body)

    origin = (LOAD + len(body) + 15) & ~15
    limit = LOAD - 32 + (app["info"]["flash_end"] - app["info"]["flash_start"]) - origin
    blob, symbols, asm, breakdown, frames, scan = compile_runtime(origin, limit, revision, out)
    nimo_ota.require(len(blob) <= limit, f"Runtime ({len(blob)} B) exceeds the {limit} B after the stock body")

    allowed = set()
    patches = []
    for patch in DATA_PATCHES:
        at = patch["address"] - LOAD
        witness, new = bytes.fromhex(patch["witness"]), bytes.fromhex(patch["patched"])
        nimo_ota.require(len(witness) == len(new), f"{patch['name']}: length differs")
        nimo_ota.require(body[at:at + len(witness)] == witness, f"{patch['name']}: witness bytes differ")
        body[at:at + len(new)] = new
        allowed.update(range(at, at + len(new)))
        patches.append({"name": patch["name"], "address": hex(patch["address"]),
                        "witness": patch["witness"], "patched": patch["patched"]})

    hooks = []
    everywhere = branch_targets(disassemble(stock, LOAD))
    for hook in HOOKS:
        at = hook["address"] - LOAD
        nimo_ota.require(body[at:at + 8].hex() == hook["witness"], f"{hook['name']}: witness bytes differ")
        start, length = hook["function"]
        inside = [(src, dst) for src, dst in branch_targets(disassemble(stock[start - LOAD:start - LOAD + length], start))
                  if hook["address"] < dst < hook["address"] + 8]
        nimo_ota.require(not inside, f"{hook['name']}: stock branches land inside the hook: {inside}")
        anywhere = [(src, dst) for src, dst in everywhere if hook["address"] < dst < hook["address"] + 8]
        nimo_ota.require(not anywhere, f"{hook['name']}: stock branches land inside the hook: {anywhere}")
        original = disassemble(stock[at:at + 8], hook["address"])
        target = symbols[hook["target"]]
        body[at:at + 8] = hook_bytes(hook, target)
        allowed.update(range(at, at + 8))
        patched = disassemble(bytes(body[at:at + 8]), hook["address"])
        rd, link, base, decoded = decode_auipc_pair(patched)
        expected = ("t1", "zero", "t1") if hook["kind"] == "jump" else ("ra", "ra", "ra")
        nimo_ota.require((rd, link, base) == expected and decoded == target,
                         f"{hook['name']}: patched site decodes to {rd},{link},{base} -> {decoded:#x}")
        gate = gate_listing(asm, hook["target"], hook.get("listing", 24))
        replay = [g for g in gate if g in hook["replay"]]
        nimo_ota.require(replay == hook["replay"], f"{hook['name']}: gate does not replay {hook['replay']}: {gate}")
        hooks.append({"name": hook["name"], "kind": hook["kind"], "address": hex(hook["address"]),
                      "witness": hook["witness"], "patched": body[at:at + 8].hex(),
                      "returns": hex(hook["address"] + 8) if hook["kind"] == "call" else None,
                      "target": hook["target"], "target_address": hex(target),
                      "stock_listing": [f"{a:#010x} {m} {o}" for a, m, o in original],
                      "patched_listing": [f"{a:#010x} {m} {o}" for a, m, o in patched],
                      "gate_listing": gate})
    data = check_data_patches(body)
    framebuffers = check_framebuffers(stock)

    new_body = bytes(body) + bytes(origin - LOAD - len(body)) + blob
    image = nimo_ota.replace_body(source, app["info"]["index"], new_body)

    _, rebuilt = nimo_ota.unpack_ota(image)
    got = rebuilt[app["info"]["index"]]["raw"][32:]
    nimo_ota.require(got == new_body, "Rebuilt application body differs")
    changed = {i for i in range(len(edited)) if got[i] != edited[i]}
    nimo_ota.require(changed <= allowed, "Bytes outside the hooks and data patches changed")
    # The metadata row carries the new body size; every other stream is untouched.
    for index, stream in enumerate(rebuilt):
        if index not in (app["info"]["index"], layout["metadata_row"]):
            nimo_ota.require(stream["raw"] == streams[index]["raw"], f"Stream {index} changed")

    report = {
        "revision": revision, "version_tag": tag, "source_sha256": nimo_ota.sha(source),
        "output_sha256": nimo_ota.sha(image), "output_size": len(image),
        "runtime_origin": hex(origin), "runtime_bytes": len(blob), "runtime_room": limit,
        "runtime_free": limit - len(blob), "runtime_sha256": hashlib.sha256(blob).hexdigest(),
        "size_breakdown": breakdown, "largest_stack_frames": frames,
        "ram_block": [hex(RAM_BLOCK[0]), hex(RAM_BLOCK[1])], "crumbs": [hex(CRUMBS[0]), hex(CRUMBS[1])],
        "data_patches": patches, "data_checks": data,
        "isa": "rv32imc", "stack_chains": scan["stack"], "stack_chain_ui_max": scan["ui_max"],
        "stack_chain_router_max": scan["router_max"], "stack_chain_cycles": scan["stack_cycles"],
        "ui_task_stack": UI_TASK_STACK,
        "packet_wide_accesses": scan["packet_wide_accesses"],
        "hooks": hooks, "changed_body_bytes": len(changed), "framebuffers": framebuffers,
        "symbols": {k: hex(v) for k, v in sorted(symbols.items(), key=lambda kv: kv[1])},
        "string_edits": len(edits),
    }
    (out / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    return image, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Stock 1.1.5.1 OTA")
    parser.add_argument("revision", type=int)
    parser.add_argument("--strings", type=Path, default=ROOT / "patches/glasslycfw-2/1.1.5.1.json")
    parser.add_argument("--out", type=Path, default=ROOT / "captures/build", help="Build directory parent")
    parser.add_argument("--image", type=Path, help="Output image (default captures/firmware/ota-1.1.5.1-glasslycfw-<rev>.bin)")
    args = parser.parse_args()
    out = args.out / f"glasslycfw-{args.revision}"
    try:
        image, report = build(args.source.read_bytes(), json.loads(args.strings.read_text()), args.revision, out)
    except (ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or ""
        parser.exit(1, f"error: {error}\n{detail}")
    target = args.image or ROOT / "captures/firmware" / f"ota-1.1.5.1-glasslycfw-{args.revision}.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image)
    summary = {k: v for k, v in report.items() if k != "symbols"}
    print(json.dumps(summary, indent=2))
    print(f"wrote {target}")
    print(f"output sha256 {report['output_sha256']}")


if __name__ == "__main__":
    main()
