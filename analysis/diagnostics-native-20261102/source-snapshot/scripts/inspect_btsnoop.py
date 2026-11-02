#!/usr/bin/env python3
"""Check an Android H4 btsnoop file without claiming whole-session coverage.

Format reference: AOSP system/gd/hal/snoop_logger.cc (network-order record
header and H4 type byte). AOSP writes zero to the drop field unconditionally;
zero is therefore not evidence that no packets were lost.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import struct

EPOCH_DELTA = 0x00DC_DDB3_0F2F_8000
TYPES = {1: "command", 2: "acl", 3: "sco", 4: "event", 5: "iso"}


def inspect(path):
    path = Path(path)
    counts = Counter()
    handles = Counter()
    digest = hashlib.sha256()
    issues = []
    first = last = None
    packets = truncated = drops = 0
    with path.open("rb") as stream:
        size = path.stat().st_size
        header = stream.read(16)
        digest.update(header)
        if len(header) != 16 or header[:8] != b"btsnoop\0":
            raise ValueError("Missing or incomplete btsnoop file header")
        version, datalink = struct.unpack(">II", header[8:])
        if (version, datalink) != (1, 1002):
            raise ValueError(f"Expected btsnoop v1 H4/1002; got {version}/{datalink}")
        while stream.tell() < size:
            offset = stream.tell()
            raw = stream.read(24)
            digest.update(raw)
            if len(raw) != 24:
                issues.append({"offset": offset, "error": "incomplete record header"})
                break
            original, captured, flags, lost, stamp = struct.unpack(">IIIIQ", raw)
            if captured > size - stream.tell():
                issues.append({"offset": offset, "error": "incomplete record payload",
                               "declared": captured, "available": size - stream.tell()})
                # Hash the entire file even when its final record is incomplete.
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                break
            prefix = stream.read(min(captured, 5))
            digest.update(prefix)
            remaining = captured - len(prefix)
            while remaining:
                chunk = stream.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("File changed during inspection; use a stable snapshot")
                digest.update(chunk)
                remaining -= len(chunk)
            packets += 1
            if captured > original or not captured:
                issues.append({"offset": offset, "error": "invalid captured/original lengths"})
            if captured < original:
                truncated += 1
            drops = max(drops, lost)
            if first is None:
                first = stamp
            if last is not None and stamp < last:
                issues.append({"offset": offset, "error": "timestamp moved backwards"})
            last = stamp
            packet_type = prefix[0] if prefix else 0
            counts[TYPES.get(packet_type, f"unknown_{packet_type}")] += 1
            if packet_type == 2 and len(prefix) >= 5:
                handle_flags, length = struct.unpack("<HH", prefix[1:5])
                handles[f"0x{handle_flags & 0x0fff:03x}"] += 1
                # original length includes the type byte plus four-byte ACL header.
                if original != length + 5:
                    issues.append({"offset": offset, "error": "ACL length disagrees with record"})
        if stream.tell() != size or path.stat().st_size != size:
            raise ValueError("File changed during inspection; use a stable snapshot")

    def timestamp(value):
        if value is None:
            return None
        try:
            return (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) +
                    dt.timedelta(microseconds=value - EPOCH_DELTA)).isoformat()
        except OverflowError:
            return f"out_of_range:{value}"

    return {"path": str(path.resolve()), "size": size, "sha256": digest.hexdigest(),
            "packets": packets, "packet_types": dict(counts), "acl_handles": dict(handles),
            "first_timestamp": timestamp(first), "last_timestamp": timestamp(last),
            "truncated_records": truncated, "maximum_reported_drop_count": drops,
            "issues": issues,
            "record_integrity_ok": packets > 0 and not issues and not truncated and not drops,
            "whole_session_coverage": "unproven",
            "limitations": ["AOSP writes zero drop counters; zero does not establish losslessness.",
                            "Valid records do not prove rotation continuity or coverage of the entire OTA.",
                            "App encryption and filtering are not detected by record validation."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.path)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["record_integrity_ok"] else 1)
