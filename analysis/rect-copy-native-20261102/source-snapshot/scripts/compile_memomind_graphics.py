#!/usr/bin/env python3
"""Compile fixed RV32 graphics gates and C runtime; retain complete build evidence.

No OTA construction or device access. --gate-fixture uses clearly labeled
link-only C entry stubs for instruction/ABI testing before the runtime is ready.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT/".tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin"
FLAGS = ["-march=rv32imafc", "-mabi=ilp32f", "-mcmodel=medany", "-mno-relax",
         "-msmall-data-limit=0", "-O2", "-ffreestanding", "-fno-builtin", "-fno-common",
         "-fno-pic", "-fno-pie", "-fno-stack-protector", "-fno-unwind-tables",
         "-fno-asynchronous-unwind-tables", "-fno-ipa-icf", "-ffunction-sections",
         "-fdata-sections", "-fvisibility=hidden", "-fstack-usage", "-Wall", "-Wextra",
         "-Werror", "-nostdlib", "-std=c11"]
MAX_STATIC_FRAME = 512
MAX_BLOB_BYTES = 65536
SCENE_ENTRIES = ("mm_scene_session_init", "mm_scene_session_dispatch",
                 "mm_scene_session_pump", "mm_scene_session_dispose")
INPUT_ENTRIES = ("glassly_input_command", "glassly_input_observe")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(tool, *args):
    result = subprocess.run([str(COMPILER/f"riscv-none-elf-{tool}"), *map(str, args)],
                            capture_output=True, check=True)
    if result.stderr:
        print(result.stderr.decode(), end="")
    return result.stdout


def inspect_elf(data):
    if data[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 243:
        raise ValueError("Expected actual little-endian ELF32 EM_RISCV")
    if struct.unpack_from("<I", data, 24)[0] != 0x0439bea0:
        raise ValueError("ELF entry mismatch")
    if struct.unpack_from("<I", data, 36)[0] & 6 != 2:
        raise ValueError("ELF float ABI is not ilp32f")
    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    if phentsize != 32:
        raise ValueError("Unexpected ELF32 program table")
    loads = []
    for i in range(phnum):
        kind, offset, virtual, physical, filesz, memsz, flags, align = struct.unpack_from("<8I", data, phoff+i*32)
        if kind == 1:
            if (flags != 5 or filesz != memsz or virtual != physical or
                    not 0x0439bea0 <= virtual < virtual+memsz <= 0x0439bea0+MAX_BLOB_BYTES or
                    offset+filesz > len(data)):
                raise ValueError("Unexpected executable load segment")
            loads.append({"virtual_address": virtual, "physical_address": physical,
                          "file_offset": offset, "file_bytes": filesz, "memory_bytes": memsz,
                          "flags": "R E", "alignment": align})
    if len(loads) != 1 or loads[0]["virtual_address"] != 0x0439bea0:
        raise ValueError("Expected one load segment at pinned entry")
    shoff = struct.unpack_from("<I", data, 32)[0]
    shentsize, shnum = struct.unpack_from("<HH", data, 46)
    if shentsize != 40:
        raise ValueError("Unexpected ELF32 section table")
    for i in range(shnum):
        section = struct.unpack_from("<10I", data, shoff+i*shentsize)
        if section[5] and section[2] & 3 == 3:
            raise ValueError("Nonempty allocated writable section")
        if section[5] and section[2] & 2 and section[1] == 8:
            raise ValueError("Allocated NOBITS section requires unsupported initialization")
        if section[5] and section[1] in (4, 9):
            raise ValueError("Linked image retains relocation records")
    return loads


def check_stack_usage(rows):
    for row in rows:
        columns = row.split("\t")
        if len(columns) != 3 or columns[2] != "static" or not 0 <= int(columns[1]) <= MAX_STATIC_FRAME:
            raise ValueError("Nonstatic or oversized function stack frame: "+row)


def compile_graphics(output, *, gate_fixture=False, scene_session=False, input_observer=False, flash_reader=False, external_tail_reader=False, storage_diagnostics=False, full_store_reader=False, flash_canary=False, raster_commands=False, rect_copy=False):
    if rect_copy and not raster_commands:
        raise ValueError("Rectangle copy requires the raster-commands profile")
    if raster_commands and not scene_session:
        raise ValueError("Raster commands require the scene-session profile")
    if flash_canary and not full_store_reader:
        raise ValueError("Flash canary requires the full-store-reader profile")
    if full_store_reader and not storage_diagnostics:
        raise ValueError("Full store reader requires the storage-diagnostics profile")
    if storage_diagnostics and not external_tail_reader:
        raise ValueError("Storage diagnostics requires the external-tail-reader profile")
    if external_tail_reader and not flash_reader:
        raise ValueError("External tail reader requires the flash-reader profile")
    if flash_reader and not (scene_session and input_observer):
        raise ValueError("Flash reader requires scene-session and input-observer")
    if input_observer and not scene_session:
        raise ValueError("Input observer requires the scene-session profile")
    if gate_fixture and scene_session:
        raise ValueError("Gate fixture and scene session are separate build profiles")
    entry, linker = ROOT/"runtime/graphics/entry.S", ROOT/"runtime/graphics/graphics.ld"
    sources = ([ROOT/"tests/rv32/graphics_gate_stubs.c"] if gate_fixture else
               [ROOT/"runtime/graphics/graphics.c", ROOT/"runtime/graphics/native.c",
                ROOT/"runtime/portable/geometry.c"])
    if scene_session:
        sources += [ROOT/"runtime/graphics/scene_session.c", ROOT/"runtime/portable/scene.c",
                    ROOT/"runtime/portable/vector.c", ROOT/"runtime/graphics/native_text.c"]
    if rect_copy:
        sources += [ROOT/"runtime/portable/rect_copy_commands.c"]
    if raster_commands:
        sources += [ROOT/"runtime/portable/raster_commands.c", ROOT/"runtime/portable/rle.c"]
    if input_observer:
        sources += [ROOT/"runtime/graphics/input.c"]
    if flash_reader:
        sources += [ROOT/"runtime/graphics/flash_read.c"]
    if storage_diagnostics:
        sources += [ROOT/"runtime/graphics/storage_diag.c", ROOT/"runtime/graphics/storage_diag_native.c"]
    if flash_canary:
        sources += [ROOT/"runtime/graphics/flash_canary.c", ROOT/"runtime/graphics/flash_canary_native.c",
                    ROOT/"runtime/graphics/flash_canary_entry.S", ROOT/"runtime/graphics/flash_store_native.c"]
    for path in [entry, linker, *sources]:
        if not path.is_file():
            raise ValueError(f"Required source is missing: {path}")
    # Freeze all inputs, including headers, and detect concurrent source drift.
    inputs = [Path(__file__).resolve(), entry, linker, *sources, *sorted((ROOT/"runtime/graphics").glob("*.h")),
              *sorted((ROOT/"runtime/portable").glob("*.h")),
              *sorted((ROOT/"runtime/graphics").glob("*.inc")),
              *sorted((ROOT/"runtime/portable").glob("*.inc"))]
    hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in inputs}
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    flags = [*FLAGS, "-I"+str(ROOT/"runtime/graphics"), "-I"+str(ROOT/"runtime/portable")]
    if scene_session:
        flags += ["-DMM_GRAPHICS_SCENE=1", "-DMM_NATIVE_TEXT_FIRMWARE=1"]
    if rect_copy:
        flags += ["-DMM_RECT_COPY=1"]
    if raster_commands:
        flags += ["-DMM_RASTER_COMMANDS=1"]
    if input_observer:
        flags += ["-DMM_GRAPHICS_INPUT=1"]
    if flash_reader:
        flags += ["-DMM_GRAPHICS_FLASH_READ=1"]
    if external_tail_reader:
        flags += ["-DMM_EXTERNAL_TAIL_READ=1"]
    if storage_diagnostics:
        flags += ["-DMM_STORAGE_DIAGNOSTICS=1"]
    if full_store_reader:
        flags += ["-DMM_FULL_STORE_READ=1"]
    if flash_canary:
        flags += ["-DMM_FLASH_CANARY=1"]
    objects = []
    for source in [entry, *sources]:
        obj = out/(source.stem+".o")
        portable_flags = ["-Wno-unused-function"] if source.parent == ROOT/"runtime/portable" else []
        run("gcc", *flags, *portable_flags, "-c", source, "-o", obj)
        objects.append(obj)
    elf = out/"graphics.elf"
    retain = ["-Wl,--undefined="+name for name in SCENE_ENTRIES] if scene_session else []
    if input_observer:
        retain += ["-Wl,--undefined="+name for name in INPUT_ENTRIES]
    if flash_reader:
        retain += ["-Wl,--undefined=glassly_flash_read_command", "-Wl,--undefined=glassly_flash_read_native"]
    run("gcc", *flags, "-Wl,--no-relax,--gc-sections,--build-id=none,--fatal-warnings",
        *retain, "-Wl,-Map="+str(out/"graphics.map"), "-T", linker, *objects, "-o", elf)
    if run("nm", "-u", elf).strip():
        raise ValueError("Graphics ELF has undefined symbols")
    elf_loads = inspect_elf(elf.read_bytes())
    for tool, arguments, name in [
        ("objdump", ["-d", elf], "graphics.asm"),
        ("readelf", ["-h", "-S", "-l", "-r", elf], "graphics.readelf.txt"),
        ("nm", ["-n", elf], "graphics.symbols.txt"),
        ("size", ["-A", elf], "graphics.size.txt")]:
        (out/name).write_bytes(run(tool, *arguments))
    symbols = {}
    for row in (out/"graphics.symbols.txt").read_text().splitlines():
        fields = row.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    if symbols.get("service_entry") != 0x0439bea0 or symbols.get("display_gate") != 0x0439bee0:
        raise ValueError("Linked gates do not match pinned entry addresses")
    for name in ("glassly_graphics_probe", "glassly_graphics_command", "glassly_graphics_display"):
        if name not in symbols:
            raise ValueError(f"Required C entry missing: {name}")
    if scene_session and any(name not in symbols for name in SCENE_ENTRIES):
        raise ValueError("A required retained scene-session entry is missing")
    if input_observer and any(name not in symbols for name in INPUT_ENTRIES):
        raise ValueError("A required input-observer entry is missing")
    if flash_reader and any(name not in symbols for name in ("glassly_flash_read_command", "glassly_flash_read_native")):
        raise ValueError("A required flash-reader entry is missing")
    run("objcopy", "-O", "binary", elf, out/"graphics.bin")
    blob = (out/"graphics.bin").read_bytes()
    if not 80 <= len(blob) <= MAX_BLOB_BYTES or len(blob) % 16:
        raise ValueError("Graphics blob violates 16-alignment / 65536-byte bound")
    if blob[0x40:0x44] != bytes.fromhex("032504f9"):
        raise ValueError("Display gate does not first replay displaced worker load")
    usage = [line for path in sorted(out.glob("*.su")) for line in path.read_text().splitlines()]
    check_stack_usage(usage)
    if any(sha((ROOT/path).read_bytes()) != digest for path, digest in hashes.items()):
        raise ValueError("Build input changed during compilation")
    report = {"format": "memomind-graphics-build-v1", "gate_fixture_only": gate_fixture,
              "scene_session": scene_session, "retained_scene_entries": list(SCENE_ENTRIES) if scene_session else [],
              "input_observer": input_observer, "retained_input_entries": list(INPUT_ENTRIES) if input_observer else [],
              "flash_reader": flash_reader,
              "external_tail_reader": external_tail_reader,
              "storage_diagnostics": storage_diagnostics,
              "full_store_reader": full_store_reader,
              "flash_canary": flash_canary,
              "raster_commands": raster_commands,
              "rect_copy": rect_copy,
              "flash_reader_native": "0x04329ad8" if flash_reader else None,
              "observer_gate_stack_bytes": 144 if input_observer else 0,
              "max_blob_bytes": MAX_BLOB_BYTES,
              "portable_extra_flags": ["-Wno-unused-function"],
              "compiler": run("gcc", "--version").decode().splitlines()[0], "flags": flags,
              "source_sha256": hashes, "blob_bytes": len(blob), "blob_sha256": sha(blob),
              "elf_sha256": sha(elf.read_bytes()), "elf_machine": "EM_RISCV/ELF32/little-endian",
              "elf_load_segments": elf_loads,
              "symbols": symbols, "entry_address": "0x0439bea0", "display_gate_address": "0x0439bee0",
              "undefined_symbols": [], "nonempty_writable_sections": [], "relocation_records": [],
              "stack_usage": usage, "stack_usage_limit_claimed": False,
              "max_static_function_frame_bytes": MAX_STATIC_FRAME,
              "stack_bound_scope": "Per-function frame only; not cumulative call-chain or task-stack safety",
              "device_execution": "not established by compilation"}
    (out/"build.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New build directory")
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--gate-fixture", action="store_true", help="Link only synthetic C entry stubs")
    profiles.add_argument("--scene-session", action="store_true", help="Enable retained scene adapter and core")
    parser.add_argument("--input-observer", action="store_true", help="Observe cooked input then preserve stock dispatch; requires --scene-session")
    parser.add_argument("--flash-reader", action="store_true", help="Fixed allowlisted read-only flash acquisition; requires scene+input")
    parser.add_argument("--external-tail-reader", action="store_true", help="Also read device1 0x700000..0x800000; requires flash-reader, performs no reservation or writes")
    parser.add_argument("--storage-diagnostics", action="store_true", help="Fixed passive storage preflight; requires external-tail-reader")
    parser.add_argument("--full-store-reader", action="store_true", help="Read complete device1 0x500000..0x800000; requires storage diagnostics, no writes")
    parser.add_argument("--flash-canary", action="store_true", help="One-shot fixed-sector normal worker; requires full-store reader and separately constructed registry carve")
    parser.add_argument("--raster-commands", action="store_true", help="Add mode3/6 RLE on one display, first-left bbox; requires scene-session")
    parser.add_argument("--rect-copy", action="store_true", help="Add mode9 overlap-safe copy, first-left rect pair; requires raster-commands")
    args = parser.parse_args()
    try:
        print(json.dumps(compile_graphics(args.output, gate_fixture=args.gate_fixture,
                                         scene_session=args.scene_session, input_observer=args.input_observer, flash_reader=args.flash_reader, external_tail_reader=args.external_tail_reader, storage_diagnostics=args.storage_diagnostics, full_store_reader=args.full_store_reader, flash_canary=args.flash_canary, raster_commands=args.raster_commands, rect_copy=args.rect_copy), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            parser.exit(2, exc.stderr.decode()+str(exc)+"\n")
        parser.exit(2, str(exc)+"\n")


if __name__ == "__main__":
    main()
