#!/usr/bin/env python3
"""Query the optional input observer, or explicitly subscribe and save raw events.

Default is passive status. --seconds opts into a temporary input subscription.
Events are cooked stock IDs; their physical source is not inferred. A successful
recorded poll is fsynced before ACK advances. A failed request is never retried;
the native30-second lease cleans up an abandoned subscription. Coverage ends at
the final poll; events arriving between that poll and STOP may be discarded.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from memomind_input import InputClient
from memomind_transport import RfcommBridge
from probe_memomind import probe


def capture(client, seconds, interval, save):
    """save(row) must durably persist before returning; failures stop immediately."""
    if type(seconds) not in (int, float) or not 0 < seconds <= 3600:
        raise ValueError('seconds must be positive and at most3600')
    if type(interval) not in (int, float) or not 0.1 <= interval <= 5:
        raise ValueError('interval must be0.1..5 seconds')
    subscribed = client.subscribe()
    save({'kind': 'subscribe', 'reply': subscribed})
    deadline = time.monotonic() + seconds
    count = drops = 0
    while True:
        result = client.poll()
        save({'kind': 'poll', 'reply': result})
        if result['records']:
            client.acknowledge(result['records'][-1]['sequence'])
            count += len(result['records'])
        drops = result['drops']
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Drain queued pages promptly; avoid sleeping while a full page remains.
        if len(result['records']) < 8:
            time.sleep(min(interval, remaining))
    stopped = client.stop()
    save({'kind': 'stop', 'reply': stopped})
    return {'recorded_events': count, 'reported_drops': drops,
            'last_recorded_sequence': client.delivered,
            'coverage_ends_at_last_poll': True, 'physical_source_identified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=38741)
    parser.add_argument('--trace', type=Path, required=True, help='New JSONL file; exclusive creation')
    parser.add_argument('--seconds', type=float, default=0, help='Explicit subscription duration; default0 queries only')
    parser.add_argument('--interval', type=float, default=0.25)
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 3600 or not 0.1 <= args.interval <= 5 or not 0 < args.timeout <= 60:
        parser.error('Require seconds0..3600, interval0.1..5, timeout>0..60')
    with args.trace.open('x') as output:
        def save(row):
            output.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **row}) + '\n')
            output.flush()
            os.fsync(output.fileno())
        with RfcommBridge(args.host, args.port, timeout=args.timeout,
                          trace=lambda row: save({'kind': 'wire', 'data': row})) as transport:
            initial = probe(transport, args.address, legacy_repeat_fa=True)
            save({'kind': 'stock-baseline', 'result': initial})
            client = InputClient(transport, timeout=args.timeout)
            status = client.status()
            save({'kind': 'status', 'reply': status})
            result = capture(client, args.seconds, args.interval, save) if args.seconds else status
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
