#!/usr/bin/env python3
"""Build a GLASSLYCFW runtime image for the NIMO 1.1.5.1 application.

Applies a string-edit manifest (patches/glasslycfw-*/1.1.5.1.json) with the
version tag set to GLASSLYCFW/<revision>, compiles runtime/nimo/ for the XIP
address just past the stock application body, patches each hook after checking
its witness bytes, appends the blob, and repacks the OTA. Offline only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cfw  # noqa: E402
import nimo_ota  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin"
RUNTIME = ROOT / "runtime/nimo"
SOURCES = ["entry.S", "glassly.c"]
APP_TYPE = 0x20
LOAD = 0x041B4020
VERSION_OLD = "v1.1.5.1-20261027111705-8e6f7a-Debug"
# Each hook replaces exactly the witnessed bytes with `auipc t1; jalr x0, t1` into a gate.
HOOKS = [
    {"name": "router-unrouted", "address": 0x0426E02E, "witness": "378637044a87d287",
     "target": "glassly_router_gate"},
]
FLAGS = ["-march=rv32imac", "-mabi=ilp32", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0",
         "-Os", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie", "-fno-stack-protector",
         "-fno-tree-loop-distribute-patterns", "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-nostdlib", "-std=c11"]


def tool(name):
    return str(TOOLS / f"riscv-none-elf-{name}")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


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


def compile_runtime(origin, limit, revision, out):
    out.mkdir(parents=True, exist_ok=True)
    script = out / "runtime.ld"
    script.write_text(linker_script(origin, limit))
    elf = out / "runtime.elf"
    run(tool("gcc"), *FLAGS, f"-DGLASSLY_CFW_REVISION={revision}", *[str(RUNTIME / s) for s in SOURCES],
        "-T", str(script), "-Wl,--gc-sections,--no-relax,--build-id=none,--fatal-warnings",
        f"-Wl,-Map={out / 'runtime.map'}", "-o", str(elf))
    undefined = run(tool("nm"), "-u", str(elf)).split()
    nimo_ota.require(not undefined, f"undefined symbols: {undefined}")
    blob_path = out / "runtime.bin"
    run(tool("objcopy"), "-O", "binary", "--only-section=.text", str(elf), str(blob_path))
    (out / "runtime.asm").write_text(run(tool("objdump"), "-d", "-M", "no-aliases", str(elf)))
    symbols = {}
    for line in run(tool("nm"), str(elf)).splitlines():
        value, kind, name = line.split()
        if kind in "Tt":
            symbols[name] = int(value, 16)
    return blob_path.read_bytes(), symbols


def jump(at, target):
    offset = target - at
    hi = (offset + 0x800) >> 12
    lo = offset - (hi << 12)
    auipc = ((hi & 0xFFFFF) << 12) | (6 << 7) | 0x17          # auipc t1, hi
    jalr = ((lo & 0xFFF) << 20) | (6 << 15) | 0x67            # jalr x0, lo(t1)
    return struct.pack("<II", auipc, jalr)


def build(source, strings, revision, out):
    nimo_ota.require(nimo_ota.sha(source) == strings["source"]["sha256"], "Source differs from the manifest")
    tag = f"v1.1.5.1-GLASSLYCFW/{revision}"
    edits = [dict(e, new=tag) if e["old"] == VERSION_OLD else e for e in strings["edits"]]
    nimo_ota.require(any(e["old"] == VERSION_OLD for e in edits), "Manifest lacks the version tag edit")
    _, streams = nimo_ota.unpack_ota(source)
    rows = [s for s in streams if s["info"].get("partition_type") == APP_TYPE]
    nimo_ota.require(len(rows) == 1, "No unique application component")
    app = rows[0]
    nimo_ota.require(app["info"]["load_address_candidate"] == LOAD, "Unexpected application load address")
    body = bytearray(build_cfw.apply_edits(app["raw"][32:], edits))
    edited = bytes(body)

    origin = (LOAD + len(body) + 15) & ~15
    limit = LOAD - 32 + (app["info"]["flash_end"] - app["info"]["flash_start"]) - origin
    blob, symbols = compile_runtime(origin, limit, revision, out)
    nimo_ota.require(origin + len(blob) <= origin + limit, "Runtime exceeds the application allocation")

    hooks = []
    for hook in HOOKS:
        at = hook["address"] - LOAD
        nimo_ota.require(body[at:at + 8].hex() == hook["witness"], f"{hook['name']}: witness bytes differ")
        target = symbols[hook["target"]]
        body[at:at + 8] = jump(hook["address"], target)
        hooks.append({"name": hook["name"], "address": hex(hook["address"]), "witness": hook["witness"],
                      "patched": body[at:at + 8].hex(), "target": hook["target"], "target_address": hex(target)})

    new_body = bytes(body) + bytes(origin - LOAD - len(body)) + blob
    image = nimo_ota.replace_body(source, app["info"]["index"], new_body)

    _, rebuilt = nimo_ota.unpack_ota(image)
    got = rebuilt[app["info"]["index"]]["raw"][32:]
    nimo_ota.require(got == new_body, "Rebuilt application body differs")
    changed = [i for i in range(len(edited)) if got[i] != edited[i]]
    allowed = {h["address"] - LOAD + k for h in HOOKS for k in range(8)}
    nimo_ota.require(set(changed) <= allowed, "Bytes outside the hooks changed")

    report = {
        "revision": revision, "version_tag": tag, "source_sha256": nimo_ota.sha(source),
        "output_sha256": nimo_ota.sha(image), "output_size": len(image),
        "runtime_origin": hex(origin), "runtime_bytes": len(blob), "runtime_room": limit,
        "runtime_sha256": hashlib.sha256(blob).hexdigest(), "hooks": hooks,
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
    parser.add_argument("--out", type=Path, default=ROOT / "captures/build")
    args = parser.parse_args()
    out = args.out / f"glasslycfw-{args.revision}"
    try:
        image, report = build(args.source.read_bytes(), json.loads(args.strings.read_text()), args.revision, out)
    except (ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or ""
        parser.exit(1, f"error: {error}\n{detail}")
    target = ROOT / "captures/firmware" / f"ota-1.1.5.1-glasslycfw-{args.revision}.bin"
    target.write_bytes(image)
    print(json.dumps(report, indent=2))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
