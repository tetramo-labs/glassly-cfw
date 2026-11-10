#!/usr/bin/env python3
"""Host tests of the NIMO runtime adapter: the real glassly.c, display.c,
scene_session.c and portable scene core against host stand-ins for the stock
functions, under ASan/UBSan. Also replays the scripts/scene_packets.py demos.
Offline only; never touches a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
NIMO = ROOT / "runtime/nimo"
PORTABLE = ROOT / "runtime/portable"
sys.path.insert(0, str(ROOT / "scripts"))
import scene_packets  # noqa: E402

DEFINES = ["-DNIMO_HOST", "-DMM_SCENE_STEREO_EYES", "-DMM_SCENE_FIXED_EYE", "-DMM_RASTER_COMMANDS",
           "-DMM_COMMAND_BUNDLES", "-DMM_RECT_COPY", "-DCFW_CACHE_OBJECTS=128u", "-DCFW_CACHE_ASSETS=128u",
           "-DCFW_TEXTURE_CACHE_SIZE=65536u"]
SOURCES = [NIMO / "tests/test_session.c", NIMO / "tests/host_stock.c", NIMO / "glassly.c", NIMO / "display.c",
           NIMO / "scene_session.c"] + [PORTABLE / f"{n}.c" for n in
                                        ("scene", "geometry", "vector", "rle", "raster_commands", "rect_copy_commands")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--revision", type=int, default=5)
    parser.add_argument("--cc", default="clang")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"format": "nimo-session-host-tests-v1", "passed": False, "hardware_tested": False, "commands": [],
              "scope": "Actual runtime C and portable scene core; stock functions are host stand-ins"}

    def run(name, command):
        result = subprocess.run([str(c) for c in command], capture_output=True, text=True)
        (out / f"{name}.stdout").write_text(result.stdout)
        (out / f"{name}.stderr").write_text(result.stderr)
        report["commands"].append({"name": name, "argv": [str(c) for c in command], "returncode": result.returncode})
        if result.returncode != 0:
            raise RuntimeError(f"{name} failed; see {name}.stderr")
        return result.stdout

    try:
        flags = ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                 "-fsanitize=address,undefined", "-fno-sanitize-recover=all", *DEFINES,
                 f"-DGLASSLY_CFW_REVISION={args.revision}", "-I" + str(NIMO), "-I" + str(PORTABLE)]
        binary = out / "test_session"
        run("build", [args.cc, *flags, *SOURCES, "-o", binary])
        stdout = run("session", [binary])
        lines = {line.split(" ", 1)[0]: line.split(" ", 1)[1] for line in stdout.splitlines() if " " in line}
        identity = json.loads(lines["IDENTITY"])
        status = json.loads(lines["STATUS"])
        expected = {"version": f"GLASSLYCFW/{args.revision}", "revision": args.revision, "platform": "nimo",
                    "max_message": 0x3000 - 4, "owned": 0}
        if any(identity.get(k) != v for k, v in expected.items()) or identity["canvas"] != \
                {"width": 540, "height": 280, "stride": 270, "format": "gray4"}:
            raise RuntimeError(f"identity JSON differs: {identity}")
        if len(lines["IDENTITY"]) + 1 >= 560 or len(lines["STATUS"]) + 1 >= 560:
            raise RuntimeError("a JSON reply reaches the 560-byte reply buffer")
        crumbs = json.loads(lines["BREADCRUMBS"])
        if crumbs["boot"] != 2 or crumbs["last_crash"]["stage"] != "present" or crumbs["last_crash"]["mode"] != 36:
            raise RuntimeError(f"breadcrumbs after a reset mid-present: {crumbs}")
        size, crc = lines["CHECKSUM"].split()
        data = bytes((i * 7 + 3) & 0xFF for i in range(int(size)))
        if int(crc, 16) != zlib.crc32(data):
            raise RuntimeError("checksum reply differs from zlib.crc32")
        report.update(identity=identity, status=status, checksum={"bytes": int(size), "crc32": crc},
                      breadcrumbs={"boot": crumbs["boot"], "last_crash": crumbs["last_crash"]},
                      result=[l for l in stdout.splitlines()
                              if not l.startswith(("IDENTITY", "STATUS", "CHECKSUM", "BREADCRUMBS"))])
        scenes = out / "scenes"
        scenes.mkdir()
        demos = {"demo-geometry.bin": scene_packets.demo(), **scene_packets.retained()}
        for name, packet in demos.items():
            (scenes / name).write_bytes(packet)
        report["scenes"] = {n: hashlib.sha256(p).hexdigest() for n, p in demos.items()}
        replay = run("scenes", [binary, "--scenes", scenes]).splitlines()
        report["scene_result"] = [l for l in replay if not l.startswith("REPLY ")]
        # The hardware steps expect exactly what the host replay answered, on both arms.
        replies = {}
        for line in replay:
            if line.startswith("REPLY "):
                _, arm, name, data = line.split()
                replies.setdefault(name, set()).add(data)
        steps = json.loads((ROOT / f"tests/hardware/steps-{args.revision}.json").read_text())["steps"]
        checked = []
        for step in steps:
            name = Path(step.get("payload_file", "")).name
            # The touch cues are plain mode-36 frames; the RV32 emulator replays them.
            if step["key"] == "20" and name in demos:
                answers = replies.get(name, set())
                exact, prefix = step.get("expect_reply_hex"), step.get("expect_reply_prefix_hex", "")
                answer = next(iter(answers)) if len(answers) == 1 else None
                if answer is None or (exact is not None and answer != exact) or not answer.startswith(prefix):
                    raise RuntimeError(f"step {step['step']}: host replies {answers} differ from the expected reply")
                checked.append(step["step"])
        report["hardware_steps_checked"] = checked
        report["passed"] = True
    except (OSError, RuntimeError, KeyError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("commands", "identity", "status")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
