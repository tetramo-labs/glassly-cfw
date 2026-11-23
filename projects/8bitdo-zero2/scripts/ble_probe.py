"""Build/run a bounded macOS BLE diagnostic and preserve local evidence.

scan logs Zero 2 name candidates without connecting. inspect/subscribe require
an observed CoreBluetooth UUID. subscribe enables notifications only on FF10/FF13;
it does not write vendor characteristic values. cycle additionally disables and
reenables that subscription, then disconnects after a bounded hold. keepalive
also writes one zero byte to FF13 after subscription and every 20 seconds after
acknowledgement, exercising the audited stock idle/watchdog reset handler.
echo checks four one-byte notifications. buttons subscribes, writes A1 to start
v4 button snapshots, then writes A0 before intentional disconnect.
No firmware is modified.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['scan', 'inspect', 'subscribe', 'cycle', 'keepalive', 'echo', 'buttons'])
    parser.add_argument('--identifier', type=uuid.UUID)
    parser.add_argument('--seconds', type=int, default=60)
    args = parser.parse_args()
    if sys.platform != 'darwin' or not 5 <= args.seconds <= 300:
        parser.error('Requires macOS and --seconds between 5 and 300')
    if (args.mode == 'scan') != (args.identifier is None):
        parser.error('Connection modes require --identifier; scan does not accept it')
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    executable = build / 'probe_zero2'
    subprocess.run(['swiftc', '-warnings-as-errors', str(ROOT/'tools/probe_zero2.swift'),
                    '-framework', 'CoreBluetooth', '-o', str(executable)], check=True)
    output = build / 'hardware' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-ble-' + args.mode)
    output.mkdir(parents=True)
    sources = ['scripts/ble_probe.py', 'tools/probe_zero2.swift']
    for source in sources:
        (output / Path(source).name).write_bytes((ROOT / source).read_bytes())
    command = [str(executable), args.mode, str(args.identifier) if args.identifier else '-', str(args.seconds)]
    plan = {'mode': args.mode, 'identifier': str(args.identifier) if args.identifier else None,
            'seconds': args.seconds, 'source_sha256': {p: digest(ROOT/p) for p in sources},
            'executable_sha256': digest(executable), 'command': command,
            'swift_version': subprocess.check_output(['swiftc', '--version'], text=True).strip(),
            'hardware_observation': True,
            'writes': ('FF13 CCC plus A1 start and A0 stop for v4 button streaming' if args.mode == 'buttons'
                       else 'FF13 CCC plus four sequential one-byte FF13 echo requests: 31 a5 00 ff' if args.mode == 'echo'
                       else 'FF13 CCC plus one zero byte on FF13 every 20 seconds after acknowledgement' if args.mode == 'keepalive'
                       else 'FF13 CCC subscription only' if args.mode in ('subscribe', 'cycle') else 'none')}
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(f'Local BLE evidence: {output}', flush=True)
    code = 1
    try:
        with (output / 'events.jsonl').open('x') as log, (output / 'stderr.log').open('x') as errors:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True)
            try:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
                code = process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
    finally:
        result = {'exit_code': code, 'files': {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    raise SystemExit(code)


if __name__ == '__main__':
    main()
