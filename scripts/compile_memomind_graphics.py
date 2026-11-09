#!/usr/bin/env python3
"""Compile fixed RV32 graphics gates and C runtime; retain complete build evidence.

No OTA construction or device access. --gate-fixture uses clearly labeled
link-only C entry stubs for instruction/ABI testing before the runtime is ready.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from memomind_rx_profile import DEFAULT_RX_PROFILE, rx_limit, linker_name, add_rx_argument

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


def inspect_elf(data, *, rx_profile=DEFAULT_RX_PROFILE):
    limit = rx_limit(rx_profile)
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
                    not 0x0439bea0 <= virtual < virtual+memsz <= 0x0439bea0+limit or
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


def compile_graphics(output, *, gate_fixture=False, scene_session=False, input_observer=False, flash_reader=False, external_tail_reader=False, storage_diagnostics=False, full_store_reader=False, flash_canary=False, raster_commands=False, rect_copy=False, command_bundles=False, text_commands=False, diagnostic_commands=False, reset_undo_trim=False, minimal_launcher=False, flash_scene=False, wake_control=False, notification_relay=False, record_transport=False, microphone_control=False, sensor_capture=False, raw_present=False, ble_probe=False, lean_diagnostics=False, lean_capabilities=False, relax=False, cfw_revision=None, rx_profile=DEFAULT_RX_PROFILE):
    limit = rx_limit(rx_profile)
    if cfw_revision is None: cfw_revision = 2 if notification_relay else 1
    if type(cfw_revision) is not int or not 1 <= cfw_revision <= 65535:
        raise ValueError("CFW revision must be an integer in 1..65535")
    if record_transport and (not flash_scene or not diagnostic_commands):
        raise ValueError("Record transport requires flash scene and diagnostic commands")
    if microphone_control and (not wake_control or cfw_revision < 7):
        raise ValueError("Microphone control requires the wake profile and CFW revision >=7")
    if sensor_capture and (not microphone_control or cfw_revision < 10):
        raise ValueError("Sensor capture requires microphone profile and CFW revision >=10")
    if notification_relay and cfw_revision < 2:
        raise ValueError("Notification candidate requires CFW revision >=2")
    if notification_relay and not wake_control:
        raise ValueError("Notification relay requires wake control")
    if reset_undo_trim and not scene_session:
        raise ValueError("RESET undo trimming requires scene-session")
    if diagnostic_commands and not text_commands:
        raise ValueError("Diagnostic commands require the text-commands profile")
    if text_commands and not command_bundles:
        raise ValueError("Text commands require the command-bundles profile")
    if command_bundles and not rect_copy:
        raise ValueError("Command bundles require the rect-copy profile")
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
    if wake_control and not (flash_scene and input_observer):
        raise ValueError("Wake control requires flash scene and input observer")
    if flash_scene and not (minimal_launcher and flash_canary):
        raise ValueError("Flash scene requires minimal launcher and reserved flash-canary profile")
    if minimal_launcher and not diagnostic_commands:
        raise ValueError("Minimal launcher requires full diagnostic scene profile")
    entry, linker = ROOT/"runtime/graphics/entry.S", ROOT/"runtime/graphics"/linker_name(rx_profile)
    sources = ([ROOT/"tests/rv32/graphics_gate_stubs.c"] if gate_fixture else
               [ROOT/"runtime/graphics/graphics.c", ROOT/"runtime/graphics/native.c",
                ROOT/"runtime/portable/geometry.c"])
    if scene_session:
        sources += [ROOT/"runtime/graphics/scene_session.c", ROOT/"runtime/portable/scene.c",
                    ROOT/"runtime/portable/vector.c", ROOT/"runtime/graphics/native_text.c"]
    if flash_scene:
        sources += [ROOT/"runtime/graphics/freestanding.c", ROOT/"runtime/graphics/flash_broker.c", ROOT/"runtime/graphics/large_message.c",
                    ROOT/"runtime/portable/flash_store.c", ROOT/"runtime/portable/scene_store.c", ROOT/"runtime/portable/scene_flash_store.c"]
    if notification_relay:
        sources += [ROOT/"runtime/graphics/notification_native.c", ROOT/"runtime/graphics/notification_entry.S",
                    ROOT/"runtime/portable/notifications.c", ROOT/"runtime/portable/ancs_ingress.c"]
    if microphone_control:
        sources += [ROOT/"runtime/graphics/microphone_native.c", ROOT/"runtime/graphics/microphone_entry.S"]
    if sensor_capture:
        sources += [ROOT/"runtime/graphics/sensor_capture.c", ROOT/"runtime/graphics/sensor_entry.S"]
    if ble_probe:
        sources += [ROOT/"runtime/graphics/ble_probe.c"]
    if wake_control:
        sources += [ROOT/"runtime/graphics/wake_control.c", ROOT/"runtime/portable/wake.c"]
    if minimal_launcher:
        sources += [ROOT/"runtime/graphics/minimal_launcher.c", ROOT/"runtime/graphics/minimal_launcher_entry.S"]
    if diagnostic_commands:
        sources += [ROOT/"runtime/graphics/diagnostics.c"]
    if rect_copy:
        sources += [ROOT/"runtime/portable/rect_copy_commands.c"]
    if raster_commands:
        sources += [ROOT/"runtime/portable/raster_commands.c", ROOT/"runtime/portable/rle.c"]
    if input_observer:
        sources += [ROOT/"runtime/graphics/input.c"]
    if flash_reader:
        sources += [ROOT/"runtime/graphics/flash_read.c"]
    if storage_diagnostics:
        # The native veneers back the flash broker; the 0x7B topology/badmap ops are dev-only.
        sources += [ROOT/"runtime/graphics/storage_diag_native.c"]
        if not lean_diagnostics:
            sources += [ROOT/"runtime/graphics/storage_diag.c"]
    if flash_canary:
        sources += [ROOT/"runtime/graphics/flash_canary.c", ROOT/"runtime/graphics/flash_canary_native.c",
                    ROOT/"runtime/graphics/flash_canary_entry.S", ROOT/"runtime/graphics/flash_store_native.c"]
    if record_transport:
        vendor=ROOT/"runtime/vendor/zlib"
        manifest=json.loads((vendor/"UPSTREAM.json").read_text())
        for name,digest in manifest["files"].items():
            if sha((vendor/name).read_bytes())!=digest:raise ValueError("Inflater source drift: "+name)
        sources += [ROOT/"runtime/graphics/record_session.c", ROOT/"runtime/portable/transport.c", ROOT/"runtime/portable/inflater.c"]
        sources += [vendor/name for name in ("inflate.c","inffast.c","inftrees.c","adler32.c","zutil.c")]
    for path in [entry, linker, *sources]:
        if not path.is_file():
            raise ValueError(f"Required source is missing: {path}")
    # Freeze all inputs, including headers, and detect concurrent source drift.
    inputs = [Path(__file__).resolve(), ROOT/"scripts/memomind_rx_profile.py", entry, linker, *sources, *sorted((ROOT/"runtime/graphics").glob("*.h")),
              *sorted((ROOT/"runtime/portable").glob("*.h")),
              *sorted((ROOT/"runtime/graphics").glob("*.inc")),
              *sorted((ROOT/"runtime/portable").glob("*.inc"))]
    hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in inputs}
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    if record_transport:
        for path in sorted((ROOT/"runtime/vendor/zlib").iterdir()):
            if path.is_file():hashes[str(path.relative_to(ROOT))]=sha(path.read_bytes())
    flags = [*(f for f in FLAGS if not (relax and f == "-mno-relax")), "-DMM_CFW_REVISION="+str(cfw_revision), "-I"+str(ROOT/"runtime/graphics"), "-I"+str(ROOT/"runtime/portable")]
    if record_transport:
        flags += ["-DMM_RECORD_TRANSPORT=1", "-DZ_SOLO", "-DNO_GZIP", "-I"+str(ROOT/"runtime/vendor/zlib")]
    if scene_session:
        flags += ["-DMM_GRAPHICS_SCENE=1", "-DMM_NATIVE_TEXT_FIRMWARE=1"]
    if flash_scene:
        flags += ["-DMM_FLASH_SCENE=1", "-DMM_SCENE_EXTERNAL_STORE=1"]
    if notification_relay:
        flags += ["-DMM_NOTIFICATION_RELAY=1"]
    if microphone_control:
        flags += ["-DMM_MICROPHONE_CONTROL=1"]
    if sensor_capture:
        flags += ["-DMM_SENSOR_CAPTURE=1"]
    if ble_probe:
        if not wake_control:
            raise ValueError("The BLE probe routes through the wake service gate")
        flags += ["-DMM_BLE_PROBE=1"]
    if raw_present:
        if not scene_session or not flash_scene:
            raise ValueError("Raw presents require the scene session and flash scene")
        # Per-eye panels: eye-tagged objects render and present once per eye.
        flags += ["-DMM_RAW_PRESENT=1", "-DMM_SCENE_STEREO_EYES=1"]
    if wake_control:
        flags += ["-DMM_WAKE_CONTROL=1"]
    if minimal_launcher:
        flags += ["-DMM_MINIMAL_LAUNCHER=1"]
    if reset_undo_trim:
        flags += ["-DMM_SCENE_RESET_UNDO_TRIM=1"]
    if diagnostic_commands:
        flags += ["-DMM_DIAGNOSTIC_COMMANDS=1"]
    if text_commands:
        flags += ["-DMM_TEXT_COMMANDS=1"]
    if command_bundles:
        flags += ["-DMM_COMMAND_BUNDLES=1"]
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
        if not lean_diagnostics:
            flags += ["-DMM_STORAGE_DIAG_OPS=1"]
    if lean_capabilities:
        flags += ["-DMM_LEAN_CAPABILITIES=1"]
    if full_store_reader:
        flags += ["-DMM_FULL_STORE_READ=1"]
    if flash_canary:
        flags += ["-DMM_FLASH_CANARY=1"]
    objects = []
    for source in [entry, *sources]:
        obj = out/(source.stem+".o")
        portable_flags = ["-Wno-unused-function"] if source.parent == ROOT/"runtime/portable" else []
        diagnostic_flags = (["-Oz"] if source.name == "diagnostics.c" else
                            ["-Os"] if diagnostic_commands and source == ROOT/"runtime/graphics/graphics.c" else [])
        trim_flags = ["-Os"] if (reset_undo_trim or diagnostic_commands) and source == ROOT/"runtime/portable/scene.c" else []
        record_flags = ["-Os"] if record_transport and (source.name in ("record_session.c","transport.c","inflater.c") or source.parent.name=="zlib") else []
        microphone_flags = (["-Oz"] if source.name == "microphone_native.c" else
                            ["-Os"] if microphone_control and source.name in ("geometry.c", "vector.c") else [])
        sensor_flags = ["-Os"] if sensor_capture and source.suffix==".c" and source.parent.name=="graphics" else []
        run("gcc", *flags, *portable_flags, *diagnostic_flags, *trim_flags, *record_flags, *microphone_flags, *sensor_flags, "-c", source, "-o", obj)
        objects.append(obj)
    elf = out/"graphics.elf"
    retain = ["-Wl,--undefined="+name for name in SCENE_ENTRIES] if scene_session else []
    if minimal_launcher:
        retain += ["-Wl,--undefined=glassly_launcher_"+n+"_entry" for n in ("init","destroy","tick","event","message","home","suspend")]
    if input_observer:
        retain += ["-Wl,--undefined="+name for name in INPUT_ENTRIES]
    if flash_reader:
        retain += ["-Wl,--undefined=glassly_flash_read_command", "-Wl,--undefined=glassly_flash_read_native"]
    if microphone_control:
        retain += ["-Wl,--undefined=glassly_microphone_"+name+"_entry" for name in ("task","spp","iap2","link")]
    if sensor_capture:
        retain += ["-Wl,--undefined=glassly_sensor_"+name+"_entry" for name in ("imu","als")]
    if notification_relay:
        retain += ["-Wl,--undefined=glassly_notification_entry"]
    if ble_probe:
        retain += ["-Wl,--undefined=glassly_ble_boot_entry"]
    run("gcc", *flags, "-Wl,--" + ("relax" if relax else "no-relax") + ",--gc-sections,--build-id=none,--fatal-warnings",
        *retain, "-Wl,-Map="+str(out/"graphics.map"), "-T", linker, *objects, "-o", elf)
    if run("nm", "-u", elf).strip():
        raise ValueError("Graphics ELF has undefined symbols")
    elf_loads = inspect_elf(elf.read_bytes(), rx_profile=rx_profile)
    for tool, arguments, name in [
        ("objdump", ["-d", elf], "graphics.asm"),
        ("readelf", ["-h", "-S", "-l", "-r", elf], "graphics.readelf.txt"),
        ("nm", ["-n", elf], "graphics.symbols.txt"),
        ("size", ["-A", elf], "graphics.size.txt")]:
        (out/name).write_bytes(run(tool, *arguments))
    if relax and re.search(r"\bgp\b", (out/"graphics.asm").read_text()):
        raise ValueError("Relaxed link addresses data through gp, which belongs to the stock firmware")
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
    if not 80 <= len(blob) <= limit or len(blob) % 16:
        raise ValueError(f"Graphics blob violates 16-alignment / {limit}-byte bound")
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
              "raw_present": raw_present,
              "ble_probe": ble_probe,
              "lean_diagnostics": lean_diagnostics,
              "lean_capabilities": lean_capabilities,
              "command_bundles": command_bundles,
              "text_commands": text_commands,
              "diagnostic_commands": diagnostic_commands,
              "reset_undo_trim": reset_undo_trim,
              "minimal_launcher": minimal_launcher,
              "flash_scene": flash_scene, "wake_control": wake_control, "notification_relay": notification_relay, "record_transport": record_transport, "microphone_control": microphone_control, "sensor_capture": sensor_capture, "cfw_revision": cfw_revision,
              "sensor_size_flags": "graphics C sources -Os" if sensor_capture else None,
              "scene_extra_flags": ["-Os"] if reset_undo_trim or diagnostic_commands else [],
              "microphone_size_flags": {"microphone_native.c": "-Oz", "geometry.c": "-Os", "vector.c": "-Os"} if microphone_control else {},
              "diagnostics_extra_flags": ["-Oz"] if diagnostic_commands else [],
              "graphics_extra_flags": ["-Os"] if diagnostic_commands else [],
              "linker_relaxation": relax,
              "flash_reader_native": "0x04329ad8" if flash_reader else None,
              "observer_gate_stack_bytes": 144 if input_observer else 0,
              "max_blob_bytes": limit,
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
    if rx_profile != DEFAULT_RX_PROFILE:
        report["rx_profile"] = rx_profile
    (out/"build.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cfw-revision", type=int, help="Numeric GLASSLYCFW revision; increment before every flash")
    parser.add_argument("--notification-relay", action="store_true")
    parser.add_argument("--microphone-control", action="store_true")
    parser.add_argument("--sensor-capture", action="store_true")
    parser.add_argument("--lean-diagnostics", action="store_true", help="Leave out the 0x7B storage topology/badmap ops (dev-only)")
    parser.add_argument("--lean-capabilities", action="store_true", help="Leave out capability keys no client reads")
    parser.add_argument("--ble-probe", action="store_true", help="Add command 0x74: register a Glassly GATT service after boot, enable advertising, count and echo writes")
    parser.add_argument("--raw-present", action="store_true", help="Present changed boxes straight into the panel slices, bypassing the LVGL redraw; requires scene-session and flash-scene")
    parser.add_argument("--relax", action="store_true", help="Let the linker shorten calls and jumps inside the blob; no gp-relative data (revision 12: the partial renderer needs the 5.6 KB)")
    parser.add_argument("--record-transport", action="store_true")
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
    parser.add_argument("--diagnostic-commands", action="store_true", help="Add native diagnostics and implemented-session cleanup; requires text-commands")
    parser.add_argument("--text-commands", action="store_true", help="Add mode15 native resource text; requires command-bundles")
    parser.add_argument("--command-bundles", action="store_true", help="Add mode8 sequential subdispatch/single present; requires rect-copy")
    parser.add_argument("--reset-undo-trim", action="store_true", help="Native standalone RESET scratch release and mandatory mutation rollback; requires scene-session")
    parser.add_argument("--minimal-launcher", action="store_true", help="Cold-boot dashboard lifecycle replacement; requires separately constructed callback and external-entry gates")
    parser.add_argument("--flash-scene", action="store_true", help="Flash COW assets via native worker and bounded large-message assembly; requires minimal launcher")
    parser.add_argument("--wake-control", action="store_true", help="Independent wake/frame leases and single-button events; requires flash scene")
    add_rx_argument(parser)
    args = parser.parse_args()
    try:
        print(json.dumps(compile_graphics(args.output, gate_fixture=args.gate_fixture,
                                         scene_session=args.scene_session, input_observer=args.input_observer, flash_reader=args.flash_reader, external_tail_reader=args.external_tail_reader, storage_diagnostics=args.storage_diagnostics, full_store_reader=args.full_store_reader, flash_canary=args.flash_canary, raster_commands=args.raster_commands, rect_copy=args.rect_copy, command_bundles=args.command_bundles, text_commands=args.text_commands, diagnostic_commands=args.diagnostic_commands, reset_undo_trim=args.reset_undo_trim, minimal_launcher=args.minimal_launcher, flash_scene=args.flash_scene, wake_control=args.wake_control, notification_relay=args.notification_relay, record_transport=args.record_transport, microphone_control=args.microphone_control, sensor_capture=args.sensor_capture, raw_present=args.raw_present, ble_probe=args.ble_probe, lean_diagnostics=args.lean_diagnostics, lean_capabilities=args.lean_capabilities, relax=args.relax, cfw_revision=args.cfw_revision, rx_profile=args.rx_profile), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            parser.exit(2, exc.stderr.decode()+str(exc)+"\n")
        parser.exit(2, str(exc)+"\n")


if __name__ == "__main__":
    main()
