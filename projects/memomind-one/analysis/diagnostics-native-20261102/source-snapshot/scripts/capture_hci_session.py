#!/usr/bin/env python3
"""Collect full Android HCI logs and logcat during a research session.

Does not change Bluetooth configuration. Recovers a rotated log's tail only
when its archived bytes exactly extend the prior snapshot; otherwise records a
possible gap. Records alone never establish losslessness. Ctrl-C stops cleanly.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time


def recover_rotated_tail(previous, target, archived):
    """Append only a verified extension of the owned previous segment.

    Android may rotate again before .last is read. A mismatching archive must
    never be spliced into the old segment, even if its file header matches.
    This byte-prefix proof does not validate records or establish continuity.
    """
    if (len(previous)<16 or previous[:8]!=b'btsnoop\0'
            or not archived.startswith(previous)):
        raise ValueError('Rotated archive does not extend the prior snapshot')
    if target.read_bytes()!=previous:
        raise ValueError('Owned segment differs from its prior snapshot')
    tail=archived[len(previous):]
    with target.open('ab') as out:
        out.write(tail)
    return len(tail)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--interval', type=float, default=3)
    args = p.parse_args()
    if args.interval <= 0:
        p.error('interval must be positive')
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    adb = ['adb', '-s', args.serial]

    def root(command):
        result = subprocess.run(adb + ['shell', '-T', 'su', '-c', command],
                                capture_output=True, timeout=25, check=True)
        return result.stdout

    if root('getprop persist.bluetooth.btsnooplogmode').strip() != b'full':
        raise RuntimeError('Full HCI logging must already be enabled')
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    events = (args.output / 'capture-events.jsonl').open('x')
    log = (args.output / 'logcat.txt').open('xb')
    process = subprocess.Popen(adb + ['logcat', '-v', 'epoch'], stdout=log,
                               stderr=subprocess.STDOUT)
    previous = b''
    segment = 0
    target = None

    def event(kind, **fields):
        events.write(json.dumps({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'kind': kind, **fields}) + '\n')
        events.flush()

    def snapshot():
        nonlocal previous, segment, target
        data = root('cat /data/misc/bluetooth/logs/btsnoop_hci.log')
        if not data.startswith(b'btsnoop\x00'):
            raise RuntimeError('HCI snapshot lacks btsnoop header')
        if target is None or not data.startswith(previous):
            if target is not None:
                try:
                    archived=root('cat /data/misc/bluetooth/logs/btsnoop_hci.log.last')
                    recovered=recover_rotated_tail(previous,target,archived)
                    event('rotation_tail_recovered',file=target.name,bytes=recovered,
                          archived_bytes=len(archived),prefix_verified=True)
                except (OSError,ValueError,subprocess.SubprocessError) as exc:
                    event('rotation_possible_gap',file=target.name,message=str(exc),
                          previous_bytes=len(previous),continuity_proven=False)
            segment += 1
            target = args.output / f'hci-{segment:03d}.btsnoop'
            target.touch(exist_ok=False)
            previous = b''
            event('segment_started', file=target.name)
        if len(data) > len(previous):
            with target.open('ab') as out:
                out.write(data[len(previous):])
            event('snapshot', file=target.name, bytes=len(data))
        previous = data

    try:
        event('started', serial=args.serial, process_id=process.pid)
        snapshot()
        print(f'Capture active: {args.output.resolve()}', flush=True)
        while running:
            if process.poll() is not None:
                raise RuntimeError('Logcat collector exited')
            time.sleep(args.interval)
            snapshot()
        snapshot()
        event('finished')
    except Exception as exc:
        event('error', message=str(exc))
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        events.close()
        files = []
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                files.append({'file': path.name, 'bytes': path.stat().st_size,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        (args.output / 'capture-manifest.json').write_text(json.dumps(files, indent=2) + '\n')


if __name__ == '__main__':
    main()
