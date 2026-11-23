#!/usr/bin/env python3
"""Offline parser/repacker for the observed MemoMind ME/WuQi OTA layout.

Derived from stock H001Y 1.0.3.127. This validates container integrity, not
device acceptance, boot safety, cryptographic authorization or recovery.
Repacking accepts only same-length component bodies and preserves every
uninterpreted field. It never contacts a device.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import zlib

OUTER_SIZE = 18
STREAM_START = 0x96
TABLE_START = 0x32
HEADER_CRC = 0x92
COMPONENT_COUNT = 6


def crc(data):
    return zlib.crc32(data) & 0xffffffff


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unpack_ota(data):
    require(len(data) >= STREAM_START + 4, "Container too short")
    require(data[:2] == b"ME" and data[2:6] == bytes.fromhex("02011001"),
            "Unsupported ME envelope profile")
    require(struct.unpack_from(">I", data, 6)[0] == len(data) - OUTER_SIZE,
            "ME payload length mismatch")
    require(struct.unpack_from(">I", data, 14)[0] == crc(data[OUTER_SIZE:]),
            "ME payload CRC32 mismatch")
    require(struct.unpack_from("<I", data, 18)[0] == 0xabcd6543,
            "Unsupported inner magic")
    require(struct.unpack_from("<I", data, HEADER_CRC)[0] == crc(data[0x22:HEADER_CRC]),
            "Compression table CRC32 mismatch")
    require(struct.unpack_from("<I", data, len(data)-4)[0] == crc(data[STREAM_START:-4]),
            "Compressed stream CRC32 mismatch")
    meta_size, meta_packed = struct.unpack_from("<II", data, 0x22)
    require(meta_size == 344, "Unsupported partition metadata size")
    entries = [(meta_size, meta_packed, None, None)]
    entries += [struct.unpack_from("<IIII", data, TABLE_START + i * 16)
                for i in range(COMPONENT_COUNT)]
    streams = []
    offset = STREAM_START
    for index, (size, packed_size, start, end) in enumerate(entries):
        require(packed_size >= 13 and offset + packed_size <= len(data)-4,
                f"Stream {index} exceeds container bounds")
        if index:
            require(start < end and 32 <= size <= end-start,
                    f"Component {index} exceeds declared flash range")
        packed = data[offset:offset+packed_size]
        require(packed[:5] == bytes.fromhex("5d00800000"),
                f"Stream {index} uses an unsupported LZMA profile")
        require(struct.unpack_from("<Q", packed, 5)[0] == size,
                f"Stream {index} LZMA length differs from table")
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        raw = decoder.decompress(packed, max_length=size+1)
        require(len(raw) == size and decoder.eof and not decoder.unused_data,
                f"Stream {index} decoded length or end boundary mismatch")
        info = {"index": index, "offset": offset, "packed_size": packed_size,
                "unpacked_size": size, "packed_sha256": sha(packed),
                "unpacked_sha256": sha(raw), "flash_start": start, "flash_end": end}
        if index:
            words = struct.unpack_from("<8I", raw)
            require(words[0] == 0xa4e49a17 and words[1] == len(raw)-32,
                    f"Component {index} image header/length invalid")
            require(words[4] == crc(raw[32:]), f"Component {index} body CRC32 mismatch")
            info.update(image_header_words=list(words), body_sha256=sha(raw[32:]),
                        body_crc32=words[4], load_address_candidate=words[3],
                        auxiliary_address_unknown=words[6])
        streams.append({"info": info, "raw": raw, "packed": packed})
        offset += packed_size
    require(offset == len(data)-4, "Unaccounted bytes before trailer")
    metadata = streams[0]["raw"]
    header_words = struct.unpack_from("<6I", metadata)
    require(header_words[1] == 16, "Unsupported partition count")
    partitions = []
    for index in range(header_words[1]):
        kind, flash, load, body_size, allocation = struct.unpack_from("<5I", metadata, 24+20*index)
        partitions.append({"index": index, "type": kind, "flash_start": flash,
                           "load_address": load, "body_size": body_size,
                           "allocation_size": allocation})
    for stream in streams[1:]:
        info = stream["info"]
        matches = [p for p in partitions if p["flash_start"] == info["flash_start"]]
        require(len(matches) == 1, "Component has no unique partition")
        partition = matches[0]
        require(partition["flash_start"] + partition["allocation_size"] == info["flash_end"]
                and partition["body_size"] == info["unpacked_size"]-32
                and partition["load_address"] == info["load_address_candidate"],
                f"Component {info['index']} disagrees with partition metadata")
        info["partition_index"] = partition["index"]
        info["partition_type"] = partition["type"]
    report = {"source_sha256": sha(data), "source_size": len(data),
              "profile": "observed-MemoMind-ME-WuQi-six-component",
              "inner_version_word": struct.unpack_from("<I", data, 22)[0],
              "metadata_header_words": list(header_words), "partitions": partitions,
              "streams": [s["info"] for s in streams],
              "checksums": {"outer_payload_crc32": "verified",
                            "compression_table_crc32": "verified",
                            "packed_streams_crc32": "verified",
                            "component_body_crc32": "verified-all-six"},
              "unaccounted_bytes": 0,
              "limitations": ["Uninterpreted header words are retained, not assigned invented semantics.",
                              "CRC validity does not prove modified firmware is accepted or safe to boot.",
                              "No standalone signature block is identified; enforcement remains unknown."]}
    return report, streams


def repack(data, replacements):
    report, streams = unpack_ota(data)
    for index, body in replacements.items():
        require(1 <= index <= COMPONENT_COUNT, "Only component indices 1 through 6 may be replaced")
        stream = streams[index]
        old = stream["raw"]
        require(len(body) == len(old)-32, "Only same-length body replacement is supported")
        if body == old[32:]:
            continue
        raw = bytearray(old[:32]) + body
        struct.pack_into("<I", raw, 16, crc(body))
        packed = bytearray(lzma.compress(bytes(raw), format=lzma.FORMAT_ALONE,
                          filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 32768,
                                    "lc": 3, "lp": 0, "pb": 2}]))
        # Python encodes unknown size; the observed vendor format stores it.
        struct.pack_into("<Q", packed, 5, len(raw))
        stream.update(raw=bytes(raw), packed=bytes(packed))
    header = bytearray(data[:STREAM_START])
    for index, stream in enumerate(streams[1:]):
        struct.pack_into("<I", header, TABLE_START + index*16 + 4, len(stream["packed"]))
    struct.pack_into("<I", header, HEADER_CRC, crc(header[0x22:HEADER_CRC]))
    packed = b"".join(s["packed"] for s in streams)
    result = header + packed + struct.pack("<I", crc(packed))
    struct.pack_into(">I", result, 6, len(result)-OUTER_SIZE)
    struct.pack_into(">I", result, 14, crc(result[OUTER_SIZE:]))
    unpack_ota(result)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    inspect = subs.add_parser("inspect")
    inspect.add_argument("source", type=Path)
    extract = subs.add_parser("extract")
    extract.add_argument("source", type=Path)
    extract.add_argument("output", type=Path, help="New directory")
    build = subs.add_parser("repack")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path, help="New output file; never flashes")
    build.add_argument("--expected-sha256", required=True)
    build.add_argument("--body", action="append", default=[], metavar="INDEX=FILE")
    args = parser.parse_args()
    try:
        data = args.source.read_bytes()
        report, streams = unpack_ota(data)
        if args.command == "extract":
            args.output.mkdir(parents=True, exist_ok=False)
            (args.output / "container-header.bin").write_bytes(data[:STREAM_START])
            for stream in streams:
                index = stream["info"]["index"]
                (args.output / f"segment-{index}.bin").write_bytes(stream["raw"])
                (args.output / f"segment-{index}.lzma").write_bytes(stream["packed"])
                if index:
                    (args.output / f"segment-{index}.body.bin").write_bytes(stream["raw"][32:])
            (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        elif args.command == "repack":
            require(sha(data) == args.expected_sha256, "Source hash differs from expected exact base")
            replacements = {}
            for spec in args.body:
                index, path = spec.split("=", 1)
                index = int(index)
                require(index not in replacements, "Duplicate component replacement")
                replacements[index] = Path(path).read_bytes()
            result = repack(data, replacements)
            with args.output.open("xb") as stream:
                stream.write(result)
            report, _ = unpack_ota(result)
            report["offline_only"] = True
            report["byte_identical_to_source"] = result == data
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, lzma.LZMAError, struct.error) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
