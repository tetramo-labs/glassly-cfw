"""Run offline checks and build unbound ARM Cortex-M0 input/stream objects."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    compiler = shutil.which("clang")
    if compiler is None:
        raise SystemExit("clang is required (Xcode Command Line Tools on macOS)")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    common = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Ifirmware"]
    run(common + ["-g", "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                  "firmware/button_stream.c", "tests/test_button_stream.c",
                  "-o", str(build / "test_button_stream")])
    run([str(build / "test_button_stream")])
    run(common + ["-g", "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                  "firmware/button_input.c", "firmware/button_stream.c", "tests/test_button_input.c",
                  "-o", str(build / "test_button_input")])
    run([str(build / "test_button_input")])
    if sys.platform == 'darwin':
        run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=address,undefined', 'tests/test_boot_reader.c',
             '-framework', 'IOKit', '-framework', 'CoreFoundation',
             '-o', str(build / 'test_boot_reader')])
        # Parser-only test includes the tool but never invokes its device code.
        subprocess.run([str(build / 'test_boot_reader')], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        print('Boot response CRC/address/length/status parser checks passed (no hardware access)')
        run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
             '-fsanitize=address,undefined', 'tests/test_flasher.c',
             '-framework', 'IOKit', '-framework', 'CoreFoundation',
             '-o', str(build / 'test_flasher')])
        run([str(build / 'test_flasher')])
        run(['swiftc', '-warnings-as-errors', 'tools/probe_zero2.swift',
             '-framework', 'CoreBluetooth', '-o', str(build / 'probe_zero2')])
        run([str(build / 'probe_zero2'), '--packet-selftest'])
        print('BLE diagnostic compiled; no Bluetooth access during checks')
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    target = build / "button_stream.arm.o"
    stack_frames = {}
    for component in ("button_stream", "button_input"):
        run(common + ["--target=arm-none-eabi", "-mcpu=cortex-m0", "-mthumb", "-Os",
                      "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fstack-usage", "-c",
                      f"firmware/{component}.c", "-o", str(build / f"{component}.arm.o")])
        for line in (build / f"{component}.arm.su").read_text().splitlines():
            location, size, kind = line.split('\t')
            if kind != 'static':
                raise SystemExit(f"Unbounded compiler stack estimate: {line}")
            stack_frames[location.rsplit(':', 1)[-1]] = int(size)
    version = subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
    report = {
        "artifact": target.name, "kind": "unbound relocatable object; not firmware",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "compiler": version, "target": "arm-none-eabi / Cortex-M0 / Thumb",
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                          for p in ("firmware/button_stream.c", "firmware/button_stream.h",
                                    "firmware/button_input.c", "firmware/button_input.h")},
        "protocol_version": 3, "packet_bytes": 8, "state_bytes": 80,
        "input": {"artifact": "button_input.arm.o", "state_bytes": 52,
                  "sha256": hashlib.sha256((build / "button_input.arm.o").read_bytes()).hexdigest(),
                  "debounce_ms": 8, "mask": "0x3ff9", "clock_and_poll_hook_bound": False},
        "total_component_state_bytes": 132,
        "compiler_stack_frame_bytes": stack_frames,
        "stack_caveat": "Per-function frames only; excludes caller argument area, send callback, stock callers, exceptions and nesting",
        "firmware_image_built": False, "hardware_accessed": False,
        "remaining": "Zero 2 radio/CCC/input binding and placement audit",
    }
    (build / "component.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Built build/button_{stream,input}.arm.o; these are not installable firmware images.")


if __name__ == "__main__":
    main()
