#!/usr/bin/env python3
"""Append a UTC timestamped user-action marker to a capture session."""
import argparse
import datetime as dt
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("session", type=Path)
parser.add_argument("action", help="e.g. tapped Pair, opened Firmware, started OTA")
args = parser.parse_args()
if not (args.session / "events.jsonl").is_file():
    parser.error("Not an existing capture session")
with (args.session / "actions.jsonl").open("a") as stream:
    stream.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(),
                             "action": args.action}) + "\n")
