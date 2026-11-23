#!/usr/bin/env python3
"""Build a NIMO custom image from a stock OTA and a patch manifest.

Each edit replaces a NUL-terminated string inside one component body with a
string of at most the same byte length (NUL padded). The original bytes and
their terminator are checked before anything changes, the container is rebuilt
with nimo_ota.repack, and the result is unpacked again to prove that only the
edited bytes differ. Never contacts a device.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nimo_ota  # noqa: E402


def apply_edits(body, edits):
    body = bytearray(body)
    for edit in edits:
        offset = int(edit["offset"], 0)
        old = edit["old"].encode()
        new = edit["new"].encode()
        nimo_ota.require(len(new) <= len(old), f"{edit['new']!r} is longer than {edit['old']!r}")
        nimo_ota.require(body[offset:offset + len(old) + 1] == old + b"\0",
                         f"{edit['old']!r} is not a NUL-terminated string at {edit['offset']}")
        body[offset:offset + len(old)] = new + b"\0" * (len(old) - len(new))
    return bytes(body)


def build(source, manifest):
    nimo_ota.require(nimo_ota.sha(source) == manifest["source"]["sha256"], "Source image hash differs from manifest")
    _, streams = nimo_ota.unpack_ota(source)
    rows = [s["info"]["index"] for s in streams if s["info"].get("partition_type") == manifest["partition_type"]]
    nimo_ota.require(len(rows) == 1, "Manifest partition type is not one unique component")
    component = rows[0]
    stock_body = streams[component]["raw"][32:]
    body = apply_edits(stock_body, manifest["edits"])
    image = nimo_ota.repack(source, {component: body})

    report, rebuilt = nimo_ota.unpack_ota(image)
    for index, stream in enumerate(rebuilt):
        if index != component:
            nimo_ota.require(stream["raw"] == streams[index]["raw"], f"Stream {index} changed")
    changed = [i for i, (a, b) in enumerate(zip(stock_body, rebuilt[component]["raw"][32:])) if a != b]
    allowed = set()
    for edit in manifest["edits"]:
        offset = int(edit["offset"], 0)
        allowed.update(range(offset, offset + len(edit["old"].encode())))
    nimo_ota.require(set(changed) <= allowed, "Bytes outside the edits changed")

    staging = [p for p in report["partitions"] if p["type"] == 4]
    nimo_ota.require(len(staging) == 1 and len(image) <= staging[0]["allocation_size"],
                     "Image does not fit the staging partition")
    verification = {
        "name": manifest["name"],
        "source_sha256": manifest["source"]["sha256"],
        "output_sha256": nimo_ota.sha(image),
        "output_size": len(image),
        "partition_type": manifest["partition_type"],
        "row": component,
        "changed_body_bytes": len(changed),
        "packed_size_stock": streams[component]["info"]["packed_size"],
        "packed_size_patched": rebuilt[component]["info"]["packed_size"],
        "staging_allocation": staging[0]["allocation_size"],
        "other_streams_identical": True,
        "checksums": report["checksums"],
    }
    return image, verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source", type=Path, help="Stock OTA image named in the manifest")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    try:
        image, verification = build(args.source.read_bytes(), manifest)
    except ValueError as error:
        parser.exit(1, f"error: {error}\n")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / manifest["output"]
    if output.exists() and output.read_bytes() != image:
        parser.exit(1, f"error: {output} exists with different content\n")
    output.write_bytes(image)
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
