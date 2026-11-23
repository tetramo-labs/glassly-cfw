#!/usr/bin/env python3
"""Offline parser/repacker for the NIMO (BitFantasy) WuQi OTA container.

The layout is the WuQi ADK update container also used by the MemoMind One
(``glassly-memomind-one-cfw/scripts/memomind_ota.py``): an 18-byte outer
envelope, a 0xabcd6543 inner header with a stream table, one LZMA-alone
stream per table row, and a trailing CRC32. One row carries the partition
metadata and is marked by the flash range (2, 0); the 0.1.x images put it
first, the 1.1.5.1 image fourth. NIMO images differ from the MemoMind ones in
the outer magic (two zero bytes rather than ``ME``) and in the component count
(four or six), so counts and order are derived from the bytes, not pinned.

This validates container integrity only. It says nothing about device
acceptance, boot safety, signatures or recovery, and it never contacts a
device. Repacking accepts same-length component bodies and preserves every
uninterpreted field.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import zlib

OUTER_SIZE = 18
INNER_MAGIC = 0xabcd6543
IMAGE_MAGIC = 0xa4e49a17
ROWS_START = 0x22
META_RANGE = (2, 0)
LZMA_PROPS = bytes.fromhex("5d00800000")
MAX_COMPONENTS = 16


def crc(data):
    return zlib.crc32(data) & 0xffffffff


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pack_stream(raw):
    packed = bytearray(lzma.compress(raw, format=lzma.FORMAT_ALONE,
                                     filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 32768,
                                               "lc": 3, "lp": 0, "pb": 2}]))
    # Python encodes an unknown size; the vendor container stores it.
    struct.pack_into("<Q", packed, 5, len(raw))
    return bytes(packed)


def locate_table(data):
    """Return (row_count, table_crc_offset, stream_start).

    The first row's LZMA stream follows the table CRC and declares that row's
    size, so the row count is the unique count whose table CRC verifies and
    whose following bytes are that stream's header.
    """
    first_size = struct.unpack_from("<I", data, ROWS_START)[0]
    candidates = []
    for rows in range(2, MAX_COMPONENTS + 2):
        crc_offset = ROWS_START + 16 * rows
        start = crc_offset + 4
        if start + 13 > len(data):
            break
        if struct.unpack_from("<I", data, crc_offset)[0] != crc(data[ROWS_START:crc_offset]):
            continue
        if data[start:start + 5] != LZMA_PROPS or struct.unpack_from("<Q", data, start + 5)[0] != first_size:
            continue
        candidates.append((rows, crc_offset, start))
    require(len(candidates) == 1, "Component table size is ambiguous or unverifiable")
    return candidates[0]


def unpack_ota(data):
    require(len(data) >= ROWS_START + 32 + 4 + 13 + 4, "Container too short")
    require(data[2:6] == bytes.fromhex("02011001"), "Unsupported envelope profile")
    require(struct.unpack_from(">I", data, 6)[0] == len(data) - OUTER_SIZE, "Envelope payload length mismatch")
    require(struct.unpack_from(">I", data, 14)[0] == crc(data[OUTER_SIZE:]), "Envelope payload CRC32 mismatch")
    require(struct.unpack_from("<I", data, 18)[0] == INNER_MAGIC, "Unsupported inner magic")
    rows, header_crc, stream_start = locate_table(data)
    count = rows - 1
    require(struct.unpack_from("<I", data, len(data) - 4)[0] == crc(data[stream_start:-4]),
            "Compressed stream CRC32 mismatch")
    entries = [struct.unpack_from("<IIII", data, ROWS_START + i * 16) for i in range(rows)]
    meta_rows = [i for i, entry in enumerate(entries) if entry[2:] == META_RANGE]
    require(len(meta_rows) == 1, "No unique partition-metadata row")
    meta_row = meta_rows[0]
    streams = []
    offset = stream_start
    for index, (size, packed_size, start, end) in enumerate(entries):
        require(packed_size >= 13 and offset + packed_size <= len(data) - 4,
                f"Stream {index} exceeds container bounds")
        if index != meta_row:
            require(start < end and 32 <= size <= end - start,
                    f"Component {index} exceeds declared flash range")
        packed = data[offset:offset + packed_size]
        require(packed[:5] == LZMA_PROPS, f"Stream {index} uses an unsupported LZMA profile")
        require(struct.unpack_from("<Q", packed, 5)[0] == size, f"Stream {index} LZMA length differs from table")
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        raw = decoder.decompress(packed, max_length=size + 1)
        require(len(raw) == size and decoder.eof and not decoder.unused_data,
                f"Stream {index} decoded length or end boundary mismatch")
        info = {"index": index, "offset": offset, "packed_size": packed_size, "unpacked_size": size,
                "packed_sha256": sha(packed), "unpacked_sha256": sha(raw)}
        if index == meta_row:
            info["metadata"] = True
        else:
            info.update(flash_start=start, flash_end=end)
            words = struct.unpack_from("<8I", raw)
            require(words[0] == IMAGE_MAGIC and words[1] == len(raw) - 32,
                    f"Component {index} image header/length invalid")
            require(words[4] == crc(raw[32:]), f"Component {index} body CRC32 mismatch")
            info.update(image_header_words=list(words), body_sha256=sha(raw[32:]), body_crc32=words[4],
                        load_address_candidate=words[3], auxiliary_address_unknown=words[6])
        streams.append({"info": info, "raw": raw, "packed": packed})
        offset += packed_size
    require(offset == len(data) - 4, "Unaccounted bytes before trailer")
    metadata = streams[meta_row]["raw"]
    header_words = struct.unpack_from("<6I", metadata)
    partition_count = header_words[1]
    require(24 + 20 * partition_count <= len(metadata), "Partition table exceeds metadata stream")
    partitions = []
    for index in range(partition_count):
        kind, flash, load, body_size, allocation = struct.unpack_from("<5I", metadata, 24 + 20 * index)
        partitions.append({"index": index, "type": kind, "flash_start": flash, "load_address": load,
                           "body_size": body_size, "allocation_size": allocation})
    for stream in streams:
        info = stream["info"]
        if info.get("metadata"):
            continue
        matches = [p for p in partitions if p["flash_start"] == info["flash_start"]]
        require(len(matches) == 1, f"Component {info['index']} has no unique partition")
        partition = matches[0]
        require(partition["flash_start"] + partition["allocation_size"] == info["flash_end"]
                and partition["body_size"] == info["unpacked_size"] - 32
                and partition["load_address"] == info["load_address_candidate"],
                f"Component {info['index']} disagrees with partition metadata")
        info["partition_index"] = partition["index"]
        info["partition_type"] = partition["type"]
    report = {"source_sha256": sha(data), "source_size": len(data),
              "profile": "WuQi-ADK-update-container",
              "outer_magic": data[:2].hex(),
              "inner_header_words": [hex(w) for w in struct.unpack_from("<4I", data, 22)],
              "component_count": count, "metadata_row": meta_row,
              "table_crc_offset": header_crc, "stream_start": stream_start,
              "metadata_header_words": list(header_words), "partitions": partitions,
              "streams": [s["info"] for s in streams],
              "checksums": {"outer_payload_crc32": "verified", "compression_table_crc32": "verified",
                            "packed_streams_crc32": "verified",
                            "component_body_crc32": f"verified-all-{count}"},
              "unaccounted_bytes": 0,
              "limitations": ["Uninterpreted header words are retained, not assigned invented semantics.",
                              "CRC validity does not prove modified firmware is accepted or safe to boot.",
                              "No standalone signature block is identified; enforcement remains unknown."]}
    return report, streams


def rebuild(data, streams, stream_start, header_crc):
    """Reassemble a container from (possibly replaced) streams, refreshing every checksum."""
    header = bytearray(data[:stream_start])
    for index, stream in enumerate(streams):
        struct.pack_into("<II", header, ROWS_START + index * 16, len(stream["raw"]), len(stream["packed"]))
    struct.pack_into("<I", header, header_crc, crc(header[ROWS_START:header_crc]))
    packed = b"".join(s["packed"] for s in streams)
    result = header + packed + struct.pack("<I", crc(packed))
    struct.pack_into(">I", result, 6, len(result) - OUTER_SIZE)
    struct.pack_into(">I", result, 14, crc(result[OUTER_SIZE:]))
    return bytes(result)


def repack(data, replacements):
    report, streams = unpack_ota(data)
    for index, body in replacements.items():
        require(0 <= index < len(streams) and index != report["metadata_row"],
                "Replacement index is not a component row")
        stream = streams[index]
        old = stream["raw"]
        require(len(body) == len(old) - 32, "Only same-length body replacement is supported")
        if body == old[32:]:
            continue
        raw = bytearray(old[:32]) + body
        struct.pack_into("<I", raw, 16, crc(body))
        stream.update(raw=bytes(raw), packed=pack_stream(bytes(raw)))
    result = rebuild(data, streams, report["stream_start"], report["table_crc_offset"])
    unpack_ota(result)
    return result


def replace_body(data, index, body):
    """Replace one component body with one of any length that fits its flash
    allocation. Updates the image header (length, CRC), the partition row's body
    size in the metadata stream, and every container length and checksum."""
    report, streams = unpack_ota(data)
    meta_row = report["metadata_row"]
    require(0 <= index < len(streams) and index != meta_row, "Replacement index is not a component row")
    stream = streams[index]
    info = stream["info"]
    require(32 + len(body) <= info["flash_end"] - info["flash_start"], "Body exceeds the partition allocation")
    raw = bytearray(stream["raw"][:32]) + body
    struct.pack_into("<I", raw, 4, len(body))
    struct.pack_into("<I", raw, 16, crc(body))
    stream.update(raw=bytes(raw), packed=pack_stream(bytes(raw)))
    meta = bytearray(streams[meta_row]["raw"])
    struct.pack_into("<I", meta, 24 + 20 * info["partition_index"] + 12, len(body))
    if bytes(meta) != streams[meta_row]["raw"]:
        streams[meta_row].update(raw=bytes(meta), packed=pack_stream(bytes(meta)))
    result = rebuild(data, streams, report["stream_start"], report["table_crc_offset"])
    rebuilt, _ = unpack_ota(result)
    staging = [p for p in rebuilt["partitions"] if p["type"] == 4]
    if staging:  # vendor images stage the whole OTA in partition type 4
        require(len(staging) == 1 and (len(result) - OUTER_SIZE + 4095) // 4096 * 4096 <= staging[0]["allocation_size"],
                "Image exceeds the staging partition")
    return result


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
            (args.output / "container-header.bin").write_bytes(data[:report["stream_start"]])
            for stream in streams:
                index = stream["info"]["index"]
                (args.output / f"segment-{index}.bin").write_bytes(stream["raw"])
                (args.output / f"segment-{index}.lzma").write_bytes(stream["packed"])
                if index != report["metadata_row"]:
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
