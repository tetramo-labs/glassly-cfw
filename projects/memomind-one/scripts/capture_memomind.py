#!/usr/bin/env python3
"""Capture MemoMind artifacts and Bluetooth activity on a rooted Android phone.

Run only where ADB device/file access is permitted. Does not initiate an OTA.
Full HCI logging must be enabled in Developer options before starting; toggle
Bluetooth afterward, before pairing. A successful run is evidence collection,
not proof that the entire OTA was recovered.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shlex
import signal
import subprocess
import tarfile
import time

from inspect_btsnoop import inspect as inspect_btsnoop

PACKAGE = "com.memomind.ai.aphrodite"
APP = f"/data/user/0/{PACKAGE}"
ROOTS = [f"{APP}/cache", f"{APP}/files", f"{APP}/app_flutter",
         f"/sdcard/Android/data/{PACKAGE}", "/data/misc/bluetooth/logs"]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New capture directory; never overwrites an existing session")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--max-gib", type=float, default=10)
    args = parser.parse_args()
    if min(args.interval, args.minutes, args.max_gib) <= 0:
        parser.error("interval, minutes and max-gib must be positive")
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    out = args.output.resolve()
    (out / "objects").mkdir()
    (out / "apk").mkdir()
    adb = ["adb", "-s", args.serial]
    events = (out / "events.jsonl").open("a")
    stopping = False
    processes = []
    handles = []
    valid_hci_seen = False

    def event(kind, **data):
        events.write(json.dumps({"time": now(), "kind": kind, **data}) + "\n")
        events.flush()

    def run(argv, check=True):
        result = subprocess.run(adb + argv, capture_output=True, timeout=120)
        if check and result.returncode:
            raise RuntimeError(f"ADB failed: {result.stderr.decode(errors='replace')}")
        return result

    def root(command, check=True):
        # adb shell v2 (-T) carries binary stdout, separate stderr and exit status.
        # adb forwards this command argument; adding shell quotes here makes su
        # try to execute the entire command string as a single executable name.
        return run(["shell", "-T", "su", "-c", command], check)

    def save(name, result):
        (out / name).write_bytes(result.stdout)
        if result.stderr:
            (out / (name + ".stderr")).write_bytes(result.stderr)
        event("command_result", file=name, returncode=result.returncode)

    def stop(_sig, _frame):
        nonlocal stopping
        stopping = True

    def snapshot():
        nonlocal valid_hci_seen
        # Copy only relevant app storage, never shared_prefs or other apps' data.
        # Tar streams are inspected without extracting device-controlled paths.
        command = "tar -cf - " + " ".join(shlex.quote(p) for p in ROOTS)
        result = root(command, check=False)
        if result.stderr:
            event("snapshot_diagnostic", returncode=result.returncode,
                  stderr=result.stderr.decode(errors="replace"))
        count = 0
        try:
            with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    stream = archive.extractfile(member)
                    data = stream.read()
                    digest = hashlib.sha256(data).hexdigest()
                    target = out / "objects" / digest
                    if not target.exists():
                        target.write_bytes(data)
                        count += 1
                        if Path(member.name).name.startswith("btsnoop_hci.log"):
                            try:
                                health = inspect_btsnoop(target)
                            except ValueError as exc:
                                event("hci_invalid", sha256=digest, error=str(exc))
                            else:
                                event("hci_integrity", **health)
                                if health["record_integrity_ok"] and health["packet_types"].get("acl", 0):
                                    valid_hci_seen = True
                    event("file_observation", device_path=member.name,
                          size=len(data), mtime=member.mtime, sha256=digest)
        except tarfile.TarError as exc:
            event("snapshot_invalid", error=str(exc))
            raise RuntimeError("Snapshot stream invalid; capture coverage interrupted") from exc
        return count

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    event("session_start", serial=args.serial, package=PACKAGE,
          capture_roots=ROOTS, interval_seconds=args.interval)
    try:
        identity = root("id").stdout.decode()
        if "uid=0(" not in identity:
            raise RuntimeError("Root access unavailable")
        mode_result = root("getprop persist.bluetooth.btsnooplogmode")
        mode = mode_result.stdout.strip()
        save("hci-mode.txt", mode_result)
        if mode != b"full":
            raise RuntimeError("Enable FULL Bluetooth HCI snoop log in Android Developer options, "
                               "then toggle Bluetooth off/on before pairing and retry with a new output directory")
        save("package.txt", run(["shell", "dumpsys", "package", PACKAGE]))
        save("bluetooth-before.txt", run(["shell", "dumpsys", "bluetooth_manager"]))
        save("phone-time.txt", run(["shell", "date", "+%Y-%m-%dT%H:%M:%S%z"]))
        paths = run(["shell", "pm", "path", PACKAGE]).stdout.decode().splitlines()
        if not paths:
            raise RuntimeError("MemoMind APK not found")
        for line in paths:
            if not line.startswith("package:"):
                raise RuntimeError(f"Unexpected package path: {line!r}")
            path = line[len("package:"):].strip()
            run(["pull", path, str(out / "apk" / Path(path).name)])
        snapshot()
        if not valid_hci_seen:
            raise RuntimeError("No intact full-length HCI snapshot containing ACL packets found; "
                               "connect the glasses and verify logging before starting an OTA")
        pid = run(["shell", "pidof", PACKAGE], check=False).stdout.decode().strip().split()
        if pid:
            handle = (out / "app-logcat.txt").open("wb")
            handles.append(handle)
            processes.append(subprocess.Popen(adb + ["logcat", "-v", "epoch", "--pid", pid[0]],
                                               stdout=handle, stderr=subprocess.STDOUT))
            event("logcat_started", app_pid=pid[0], limitation="PID filter ends covering app after restart")
        else:
            event("logcat_unavailable", reason="App not running; app file logs still polled")
        print(f"Capture active: {out}\nPair/connect and exercise the app. Ctrl-C finishes collection.", flush=True)
        event("capture_ready", limitation="Observed intact ACL records; entire-session coverage, "
              "filtering and rotation continuity remain unproven")
        deadline = time.monotonic() + args.minutes * 60
        while not stopping and time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                event("logcat_ended")
                raise RuntimeError("Logcat collector exited")
            snapshot()
            total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
            if total > args.max_gib * 1024**3:
                event("storage_limit", bytes=total)
                break
            time.sleep(args.interval)
        snapshot()
        save("bluetooth-after.txt", run(["shell", "dumpsys", "bluetooth_manager"]))
        event("session_finished", ota_completeness="unverified")
    except Exception as exc:
        event("session_error", error=str(exc))
        raise
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for handle in handles:
            handle.close()
        events.close()
        manifest = []
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                hasher = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(chunk)
                manifest.append({"path": str(path.relative_to(out)),
                                 "size": path.stat().st_size, "sha256": hasher.hexdigest()})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
