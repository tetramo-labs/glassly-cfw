#!/usr/bin/env python3
"""Apply explicit, hash-pinned component-body edits to an OTA, offline only.

This constructs a container; it does not establish executable correctness,
device acceptance, boot authentication, or recovery. No transport is imported.
"""
import argparse
import json
from pathlib import Path
import re

from memomind_ota import repack, require, sha, unpack_ota


def digest(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            f"{label} must be a lowercase SHA-256")
    return value


def exact_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys),
            f"{label} must contain exactly: {', '.join(keys)}")


def hex_bytes(value, label):
    require(isinstance(value, str) and len(value) > 0 and
            re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value),
            f"{label} must be nonempty, contiguous hexadecimal bytes")
    return bytes.fromhex(value)


def apply_patch(source, manifest):
    exact_keys(manifest, ("format", "source_sha256", "output_sha256", "edits"), "Manifest")
    require(manifest["format"] == "memomind-body-patch-v1", "Unsupported patch format")
    expected_source = digest(manifest["source_sha256"], "source_sha256")
    expected_output = digest(manifest["output_sha256"], "output_sha256")
    require(sha(source) == expected_source, "Source differs from exact pinned OTA")
    original, streams = unpack_ota(source)
    edits = manifest["edits"]
    require(isinstance(edits, list) and len(edits) > 0, "At least one explicit edit is required")
    bodies, ranges, changes = {}, {}, []
    for ordinal, edit in enumerate(edits):
        exact_keys(edit, ("component", "body_sha256", "offset", "before", "after", "reason"),
                   f"Edit {ordinal}")
        component, offset = edit["component"], edit["offset"]
        require(type(component) is int and 1 <= component <= 6, "Component must be 1 through 6")
        require(type(offset) is int and offset >= 0, "Offset must be a nonnegative integer")
        require(isinstance(edit["reason"], str) and edit["reason"].strip(), "Edit reason is required")
        body = streams[component]["raw"][32:]
        require(sha(body) == digest(edit["body_sha256"], "body_sha256"),
                f"Component {component} differs from pinned original body")
        before = hex_bytes(edit["before"], "before")
        after = hex_bytes(edit["after"], "after")
        require(len(before) == len(after), "Only same-length edits are supported")
        require(before != after, "An edit must change bytes")
        end = offset + len(before)
        require(end <= len(body), "Edit exceeds component body")
        require(body[offset:end] == before, "Expected original bytes do not match")
        intervals = ranges.setdefault(component, [])
        require(all(end <= lo or offset >= hi for lo, hi in intervals), "Overlapping edits")
        intervals.append((offset, end))
        bodies.setdefault(component, bytearray(body))[offset:end] = after
        changes.append({"component": component, "body_offset": offset, "length": len(before),
                        "before": before.hex(), "after": after.hex(), "reason": edit["reason"]})
    output = repack(source, {i: bytes(body) for i, body in bodies.items()})
    require(sha(output) == expected_output, "Rebuilt output differs from pinned output SHA-256")
    rebuilt, rebuilt_streams = unpack_ota(output)
    # Independently account for every decompressed byte, including untouched images.
    for i in range(7):
        expected = bytes(bodies[i]) if i in bodies else streams[i]["raw"][32:]
        require(rebuilt_streams[i]["raw"][32:] == expected, "Unexpected reconstructed body change")
        if i not in bodies:
            require(rebuilt_streams[i]["raw"] == streams[i]["raw"] and
                    rebuilt_streams[i]["packed"] == streams[i]["packed"],
                    "Untouched stream was changed")
    return output, {"offline_only": True, "source_sha256": expected_source,
                    "output_sha256": expected_output, "source_bytes": len(source),
                    "output_bytes": len(output), "changes": changes,
                    "original_checksums": original["checksums"],
                    "rebuilt_checksums": rebuilt["checksums"],
                    "device_acceptance": "untested", "boot_safety": "unestablished"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="New OTA file; omitted means verify only")
    args = parser.parse_args()
    try:
        output, report = apply_patch(args.source.read_bytes(), json.loads(args.manifest.read_text()))
        if args.output:
            with args.output.open("xb") as handle:
                handle.write(output)
            report["output_path"] = str(args.output)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
