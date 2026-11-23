#!/usr/bin/env python3
"""Run synthetic font tests without linking or calling firmware addresses."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

RUNTIME = Path(__file__).resolve().parents[2]
SOURCES = [RUNTIME / "graphics/tests/test_native_text.c",
           RUNTIME / "graphics/native_text.c", RUNTIME / "portable/geometry.c"]


def run(directory):
    binary = directory / "test_native_text"
    command = [os.environ.get("CC", "cc"), "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
               *map(str, SOURCES), "-o", str(binary)]
    build = subprocess.run(command, capture_output=True, text=True)
    (directory / "build.stdout").write_text(build.stdout)
    (directory / "build.stderr").write_text(build.stderr)
    build.check_returncode()
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    (directory / "test.stdout").write_text(result.stdout)
    (directory / "test.stderr").write_text(result.stderr)
    report = {"passed": result.returncode == 0, "build_command": command,
              "result": result.stdout.strip(), "hardware_tested": False,
              "source_hashes": {str(p.relative_to(RUNTIME.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [*SOURCES, RUNTIME / "graphics/native_text.h"]}}
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(result.stdout, end="")
    result.check_returncode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Keep executable and evidence in a new directory")
    args = parser.parse_args()
    if args.output:
        out = args.output.resolve()
        out.mkdir(parents=True, exist_ok=False)
        run(out)
    else:
        with tempfile.TemporaryDirectory(prefix="memomind-native-text-") as directory:
            run(Path(directory))


if __name__ == "__main__":
    main()
