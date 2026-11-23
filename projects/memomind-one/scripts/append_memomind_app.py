#!/usr/bin/env python3
"""Append bytes to the existing MemoMind application partition, offline only.

Accepts the exact captured stock or visually verified text-patch OTA. It does
not link ELF files, change an entry point, relocate partitions, patch hooks,
allocate RAM, contact a device, or establish that appended code will execute.
"""
import argparse
import json
import lzma
from pathlib import Path
import struct

from memomind_ota import (HEADER_CRC, OUTER_SIZE, STREAM_START, TABLE_START,
                         crc, require, sha, unpack_ota)

APP_INDEX = 3
ALLOWED_SOURCES = {
    "08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712": "stock-1.0.3.127",
    "941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876": "verified-text-1.0.3.127",
}


def pack_stream(raw):
    packed = bytearray(lzma.compress(raw, format=lzma.FORMAT_ALONE,
                                   filters=[{"id": lzma.FILTER_LZMA1,
                                             "dict_size": 32768, "lc": 3,
                                             "lp": 0, "pb": 2}]))
    struct.pack_into("<Q", packed, 5, len(raw))
    return bytes(packed)


def append_app(source, payload, *, expected_source_sha256, alignment=4,
               expected_output_sha256=None):
    """Return (OTA bytes, audit). Empty payload is an exact no-op, without padding.

    Alignment applies to the payload's derived XIP address, not its offset in
    the compressed OTA. Zero padding precedes the payload when required.
    """
    source_hash = sha(source)
    require(source_hash == expected_source_sha256, "Source SHA-256 mismatch")
    require(source_hash in ALLOWED_SOURCES, "Source is not a pinned stock or verified text OTA")
    require(type(alignment) is int and 1 <= alignment <= 4096 and
            alignment & (alignment - 1) == 0, "Alignment must be a power of two from 1 to 4096")
    require(isinstance(payload, bytes), "Payload must be bytes")
    original, streams = unpack_ota(source)
    info = streams[APP_INDEX]["info"]
    app = streams[APP_INDEX]["raw"]
    body = app[32:]
    load = info["load_address_candidate"]
    allocation = info["flash_end"] - info["flash_start"]
    require(info["partition_type"] == 0x20 and info["partition_index"] == 2 and
            info["flash_start"] == 0x1eb000 and info["flash_end"] == 0x3eb000 and
            load == 0x041eb020 and allocation == 0x200000,
            "Unexpected application partition mapping")
    staging = [p for p in original["partitions"] if p["type"] == 4]
    require(len(staging) == 1 and staging[0]["flash_start"] == 0x481000 and
            staging[0]["allocation_size"] == 0x25e000, "Unexpected staging allocation")
    capacity = staging[0]["allocation_size"]
    padding_size = (-(load + len(body))) % alignment if payload else 0
    payload_offset = len(body) + padding_size
    new_body_size = payload_offset + len(payload)
    require(new_body_size + 32 <= allocation, "Append exceeds existing application allocation")

    if payload:
        new_body = body + bytes(padding_size) + payload
        new_app = bytearray(app[:32]) + new_body
        struct.pack_into("<I", new_app, 4, new_body_size)
        struct.pack_into("<I", new_app, 16, crc(new_body))
        new_meta = bytearray(streams[0]["raw"])
        metadata_size_offset = 24 + 20 * info["partition_index"] + 12
        struct.pack_into("<I", new_meta, metadata_size_offset, new_body_size)
        packed_streams = [s["packed"] for s in streams]
        packed_streams[0] = pack_stream(bytes(new_meta))
        packed_streams[APP_INDEX] = pack_stream(bytes(new_app))
        header = bytearray(source[:STREAM_START])
        # Metadata raw size stays 344; its packed size can change.
        struct.pack_into("<I", header, 0x26, len(packed_streams[0]))
        app_row = TABLE_START + (APP_INDEX - 1) * 16
        struct.pack_into("<II", header, app_row, len(new_app), len(packed_streams[APP_INDEX]))
        struct.pack_into("<I", header, HEADER_CRC, crc(header[0x22:HEADER_CRC]))
        packed = b"".join(packed_streams)
        result = header + packed + struct.pack("<I", crc(packed))
        struct.pack_into(">I", result, 6, len(result) - OUTER_SIZE)
        struct.pack_into(">I", result, 14, crc(result[OUTER_SIZE:]))
        output = bytes(result)
    else:
        output = source

    staged_bytes = len(output) - OUTER_SIZE
    rounded_staged_bytes = (staged_bytes + 4095) & ~4095
    require(staged_bytes <= capacity and rounded_staged_bytes <= capacity,
            "Recompressed OTA exceeds existing staging allocation")
    if expected_output_sha256 is not None:
        require(sha(output) == expected_output_sha256, "Output SHA-256 mismatch")
    rebuilt, updated = unpack_ota(output)
    new_body = updated[APP_INDEX]["raw"][32:]
    require(new_body[:len(body)] == body, "Original application body prefix changed")
    require(new_body[len(body):payload_offset] == bytes(padding_size) and
            new_body[payload_offset:] == payload, "Unexpected appended bytes")
    require(app[:4] == updated[APP_INDEX]["raw"][:4] and
            app[8:16] == updated[APP_INDEX]["raw"][8:16] and
            app[20:32] == updated[APP_INDEX]["raw"][20:32],
            "Unexpected application header changes")
    metadata_size_offset = 24 + 20 * info["partition_index"] + 12
    old_meta, new_meta = streams[0]["raw"], updated[0]["raw"]
    require(old_meta[:metadata_size_offset] == new_meta[:metadata_size_offset] and
            old_meta[metadata_size_offset+4:] == new_meta[metadata_size_offset+4:],
            "Unexpected partition metadata changes")
    unchanged = []
    for index in (1, 2, 4, 5, 6):
        old, new = streams[index], updated[index]
        require(old["raw"] == new["raw"] and old["packed"] == new["packed"],
                f"Untouched stream {index} changed")
        unchanged.append({"index": index, "raw_byte_identical": True,
                          "packed_byte_identical": True,
                          "raw_sha256": sha(old["raw"]),
                          "packed_sha256": sha(old["packed"])})
    # The only changed envelope/table fields may be lengths and their checksums.
    allowed_header = (set(range(6, 10)) | set(range(14, 18)) | set(range(0x26, 0x2a)) |
                      set(range(0x52, 0x5a)) | set(range(HEADER_CRC, HEADER_CRC+4)))
    header_changes = [i for i in range(STREAM_START) if source[i] != output[i]]
    require(set(header_changes) <= allowed_header, "Unexpected container header changes")
    audit = {
        "format": "memomind-app-append-audit-v1", "offline_only": True,
        "source_profile": ALLOWED_SOURCES[source_hash], "source_sha256": source_hash,
        "output_sha256": sha(output), "source_bytes": len(source), "output_bytes": len(output),
        "byte_identical_noop": output == source, "component": APP_INDEX,
        "original_body_sha256": sha(body), "output_body_sha256": sha(new_body),
        "original_body_size": len(body), "output_body_size": len(new_body),
        "prefix_unchanged": True, "prefix_length": len(body), "prefix_sha256": sha(body),
        "append": {"body_start": len(body), "body_end_exclusive": len(new_body),
                   "sha256_including_padding": sha(new_body[len(body):]),
                   "payload_body_start": payload_offset,
                   "payload_body_end_exclusive": payload_offset + len(payload),
                   "payload_bytes": len(payload), "payload_sha256": sha(payload),
                   "alignment": alignment, "padding_bytes": padding_size, "padding_value": 0},
        "mapping": {"basis": "component header and partition metadata; no ELF load map inferred",
                    "body_xip_base": load, "flash_partition_start": info["flash_start"],
                    "flash_partition_end_exclusive": info["flash_end"],
                    "body_flash_start": info["flash_start"] + 32,
                    "payload_flash_start": info["flash_start"] + 32 + payload_offset,
                    "payload_flash_end_exclusive": info["flash_start"] + 32 + len(new_body),
                    "payload_xip_start": load + payload_offset,
                    "payload_xip_end_exclusive": load + len(new_body),
                    "flash_layout_unchanged": True, "elf_load_map_established": False},
        "bounds": {"app_allocation": allocation, "app_raw_bytes": len(new_body)+32,
                   "app_free_bytes": allocation-len(new_body)-32,
                   "staging_capacity": capacity, "staged_payload_bytes": staged_bytes,
                   "staged_payload_rounded_4096": rounded_staged_bytes,
                   "staging_free_bytes": capacity-staged_bytes,
                   "staging_capacity_basis": "pinned metadata type4 allocation; native043415b4/e2 bound",
                   "all_bounds_pass": True},
        "metadata_body_size_field_offset": metadata_size_offset,
        "metadata_only_matching_body_size_may_change": True,
        "container_header_changed_offsets": header_changes,
        "app_header_only_length_and_crc_may_change": True,
        "unchanged_streams": unchanged,
        "stream_sizes": [{"index": i, "old_raw": len(streams[i]["raw"]),
                          "new_raw": len(updated[i]["raw"]),
                          "old_packed": len(streams[i]["packed"]),
                          "new_packed": len(updated[i]["packed"])} for i in range(7)],
        "checksums": rebuilt["checksums"],
        "limitations": ["Appending does not redirect execution or establish code correctness.",
                        "No ELF link addresses, RAM allocation or startup copy changes are inferred.",
                        "Existing text patch boot success does not prove acceptance of a grown image.",
                        "Bootloader decompression/activation behavior and recovery remain unverified."]}
    return output, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("payload", type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-output-sha256")
    parser.add_argument("--alignment", type=int, default=4)
    parser.add_argument("--output", type=Path, help="New OTA file; requires expected output hash")
    parser.add_argument("--audit", type=Path, help="New JSON audit file")
    args = parser.parse_args()
    try:
        require(not args.output or args.expected_output_sha256 is not None,
                "Writing an OTA requires --expected-output-sha256; preview first without --output")
        output, audit = append_app(args.source.read_bytes(), args.payload.read_bytes(),
                                  expected_source_sha256=args.expected_source_sha256,
                                  alignment=args.alignment,
                                  expected_output_sha256=args.expected_output_sha256)
        for path in (args.output, args.audit):
            require(path is None or not path.exists(), "Output path already exists")
        require(args.output is None or args.audit is None or args.output.resolve() != args.audit.resolve(),
                "OTA and audit paths must differ")
        if args.output:
            with args.output.open("xb") as handle:
                handle.write(output)
        if args.audit:
            with args.audit.open("x") as handle:
                handle.write(json.dumps(audit, indent=2) + "\n")
        print(json.dumps(audit, indent=2))
    except (OSError, ValueError, lzma.LZMAError, struct.error) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
