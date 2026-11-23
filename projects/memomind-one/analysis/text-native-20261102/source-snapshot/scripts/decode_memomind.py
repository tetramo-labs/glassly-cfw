#!/usr/bin/env python3
"""Decode observed MemoMind RFCOMM envelopes and verify OTA bytes offline.

No device access or flashing. Requires TShark for HCI/L2CAP/RFCOMM reassembly.
The 70076e envelope and CRC32 are validated against the captured stock OTA.
Normal fa00 frame fragmentation is inventoried but not guessed across writes.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import zlib

MAGIC = bytes.fromhex("70076e")


def encode_ota(command, sequence, parameters=b"", flags=0xC0):
    payload = bytes([sequence]) + parameters
    if len(payload) > 65535:
        raise ValueError("Payload exceeds wire length field")
    return MAGIC + bytes([flags, command]) + len(payload).to_bytes(2, "big") + payload + b"\x33"


def encode_chunk(sequence, offset, data):
    if not 0 <= offset <= 0xffffffff or len(data) > 630:
        raise ValueError("Offset or chunk length outside observed format")
    return encode_ota(0xE5, sequence, offset.to_bytes(4, "big") + data +
                      zlib.crc32(data).to_bytes(4, "big"))


def encode_control(sequence, service, command, payload=b""):
    """Encode one observed fa00 frame; larger fragmented messages unsupported."""
    length = len(payload) + 9
    if length > 512:
        raise ValueError("Control fragmentation has not been implemented")
    body = b"\xfa\x00" + length.to_bytes(2, "big") + bytes([sequence, service, command]) + payload
    return body + (sum(body) & 0xffff).to_bytes(2, "big")


class OtaStream:
    """Parse application frames independently of RFCOMM write boundaries."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 7:
            if self.buffer[:3] != MAGIC:
                raise ValueError("Unrecognized prefix in OTA stream; refusing resynchronization")
            length = int.from_bytes(self.buffer[5:7], "big")
            total = length + 8
            if len(self.buffer) < total:
                break
            frame = bytes(self.buffer[:total])
            if frame[-1] != 0x33:
                raise ValueError("Invalid OTA frame footer")
            del self.buffer[:total]
            frames.append(frame)
        return frames


def ranges(mask, wanted):
    result = []
    start = None
    for i, value in enumerate(mask):
        if bool(value) == wanted and start is None:
            start = i
        elif bool(value) != wanted and start is not None:
            result.append([start, i])
            start = None
    if start is not None:
        result.append([start, len(mask)])
    return result


def decode(capture, firmware, output, start_epoch=None):
    display_filter = "btrfcomm && data.data"
    if start_epoch is not None:
        start_epoch = float(start_epoch)
        if not math.isfinite(start_epoch):
            raise ValueError("start_epoch must be a finite Unix timestamp")
        display_filter += f" && frame.time_epoch >= {start_epoch:.9f}"
    # Use a display filter only: earlier packets remain available to TShark's
    # HCI/L2CAP/RFCOMM dissection, including channel setup and fragmentation.
    output.mkdir(parents=True, exist_ok=False)
    fields = ["frame.number", "frame.time_epoch", "hci_h4.direction", "bthci_acl.chandle",
              "btrfcomm.channel", "data.data"]
    command = ["tshark", "-r", str(capture), "-Y", display_filter, "-T", "fields"]
    for name in fields:
        command += ["-e", name]
    extracted = subprocess.run(command, capture_output=True, check=True)
    (output / "rfcomm.tsv").write_bytes(extracted.stdout)
    (output / "tshark.stderr").write_bytes(extracted.stderr)
    stock = firmware.read_bytes()
    recovered = bytearray(len(stock))
    coverage = bytearray(len(stock))
    parsers = {}
    packet_counts = Counter()
    commands = Counter()
    errors = []
    chunks = []
    requests = []
    normal = []
    packets = []
    for line in extracted.stdout.decode().splitlines():
        number, timestamp, direction, handle, channel, raw = line.split("\t")
        if "," in raw:
            errors.append({"frame": number, "error": "Multiple data fields require explicit dissection"})
            continue
        data = bytes.fromhex(raw)
        key = (handle, channel, direction)
        packet_counts[f"channel{channel}/direction{direction}"] += 1
        source = {"frame": int(number), "timestamp": timestamp,
                  "direction": int(direction, 0), "handle": handle, "channel": int(channel)}
        if data.startswith(b"\xfa"):
            declared = int.from_bytes(data[1:4], "big")
            checksum = len(data) >= 9 and sum(data[:-2]) & 0xffff == int.from_bytes(data[-2:], "big")
            normal.append({**source, "sequence": data[4], "service": data[5], "command": data[6],
                           "declared_length": declared, "observed_length": len(data),
                           "checksum_ok": checksum, "payload_hex": data[7:-2].hex(),
                           "fragmented": declared != len(data)})
            if not checksum:
                errors.append({**source, "error": "Normal frame checksum mismatch"})
            continue
        if key not in parsers:
            if not data.startswith(MAGIC):
                continue
            parsers[key] = OtaStream()
        try:
            framed = parsers[key].feed(data)
        except ValueError as exc:
            errors.append({**source, "error": str(exc)})
            continue
        for frame in framed:
            flags, cmd = frame[3:5]
            payload = frame[7:-1]
            commands[f"0x{cmd:02x}/direction{source['direction']}"] += 1
            row = {**source, "flags": flags, "command": cmd, "payload_length": len(payload)}
            if cmd == 0xE5 and source["direction"] == 0:
                if len(payload) < 9:
                    errors.append({**source, "error": "Short OTA data payload"})
                    continue
                seq = payload[0]
                offset = int.from_bytes(payload[1:5], "big")
                body, checksum = payload[5:-4], int.from_bytes(payload[-4:], "big")
                crc_ok = zlib.crc32(body) == checksum
                end = offset + len(body)
                match = end <= len(stock) and stock[offset:end] == body
                chunk = {**row, "sequence": seq, "offset": offset, "length": len(body),
                         "crc32": f"{checksum:08x}", "crc32_ok": crc_ok, "matches_stock": match,
                         "wire_roundtrip_ok": frame == encode_chunk(seq, offset, body),
                         "sha256": hashlib.sha256(body).hexdigest()}
                chunks.append(chunk)
                if not crc_ok or not match or end > len(stock):
                    errors.append({**source, "error": "OTA chunk CRC/stock/range mismatch", "offset": offset})
                elif any(coverage[offset:end]) and recovered[offset:end] != body:
                    errors.append({**source, "error": "Conflicting overlapping OTA chunks", "offset": offset})
                else:
                    recovered[offset:end] = body
                    coverage[offset:end] = b"\x01" * len(body)
            else:
                row["payload_hex"] = payload.hex()
            if source["direction"] == 1 and cmd in (0xE3, 0xE5) and len(payload) >= 9:
                requested = {**source, "command": cmd, "transport_status": payload[0],
                             "sequence": payload[1], "result": payload[2],
                             "offset": int.from_bytes(payload[3:7], "big"),
                             "block_size": int.from_bytes(payload[7:9], "big"),
                             "extra_hex": payload[9:].hex()}
                requests.append(requested)
            packets.append(row)
    for key, parser in parsers.items():
        if parser.buffer:
            errors.append({"stream": key, "error": "Incomplete final OTA frame", "bytes": len(parser.buffer)})
    requested_mask = bytearray(len(stock))
    for request in requests:
        start, length = request["offset"], request["block_size"]
        if request["transport_status"] or request["result"] or not length:
            continue
        end = min(start + length, len(stock))
        if start >= len(stock):
            errors.append({"error": "Requested offset outside stock image", **request})
        else:
            requested_mask[start:end] = b"\x01" * (end - start)
    missing_requested = bytearray(r and not c for r, c in zip(requested_mask, coverage))
    block_checks = []
    for index, request in enumerate(requests):
        if not request["block_size"]:
            continue
        following = requests[index + 1] if index + 1 < len(requests) else None
        selected = [c for c in chunks if c["frame"] > request["frame"] and
                    (following is None or c["frame"] < following["frame"])]
        cursor = request["offset"]
        contiguous = True
        for chunk in selected:
            contiguous = contiguous and chunk["offset"] == cursor
            cursor = chunk["offset"] + chunk["length"]
        end = min(request["offset"] + request["block_size"], len(stock))
        complete = bool(selected and following and contiguous and cursor == end and
                        following["sequence"] == selected[-1]["sequence"] and
                        not following["result"] and not following["transport_status"])
        block_checks.append({"request_frame": request["frame"],
                             "ack_frame": following["frame"] if following else None,
                             "offset": request["offset"], "end_exclusive": end,
                             "chunks": len(selected), "complete_before_ack": complete})
    covered_ranges = ranges(coverage, True)
    recovered_ranges = []
    for start, end in covered_ranges:
        name = f"range-{start:08x}-{end:08x}.bin"
        data = bytes(recovered[start:end])
        (output / name).write_bytes(data)
        recovered_ranges.append({"start": start, "end_exclusive": end, "path": name,
                                 "sha256": hashlib.sha256(data).hexdigest(),
                                 "matches_stock": data == stock[start:end]})
    summary = {"capture": str(capture.resolve()),
               "selection": {"start_epoch": start_epoch, "display_filter": display_filter,
                             "dissection_context": "Entire capture; display filtering only"},
               "comparison_image_semantics": "Legacy *_stock and matches_stock keys compare against the supplied firmware path/hash, including modified images.",
               "capture_sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
               "firmware": str(firmware.resolve()), "firmware_size": len(stock),
               "firmware_sha256": hashlib.sha256(stock).hexdigest(),
               "rfcomm_packets": dict(packet_counts), "ota_commands": dict(commands),
               "ota_chunks": len(chunks), "all_chunk_crc32_valid": bool(chunks) and all(c["crc32_ok"] for c in chunks),
               "all_chunks_match_stock": bool(chunks) and all(c["matches_stock"] for c in chunks),
               "all_chunks_roundtrip": bool(chunks) and all(c["wire_roundtrip_ok"] for c in chunks),
               "requested_blocks": len(block_checks),
               "all_requested_blocks_complete_before_ack": bool(block_checks) and all(b["complete_before_ack"] for b in block_checks),
               "covered_bytes": sum(coverage), "covered_ranges": recovered_ranges,
               "not_transferred_by_e5": ranges(coverage, False),
               "missing_requested_ranges": ranges(missing_requested, True),
               "terminal_request_observed": bool(requests and requests[-1]["block_size"] == 0 and requests[-1]["offset"] == 0),
               "errors": errors,
               "limitations": ["Requested blocks at end of file are clipped to file size for coverage comparison.",
                 "Connection handles may be reused; this trace should cover one selected device/session.",
                 "Normal fa00 fragments remain individually inventoried; logical TLV reassembly is not implemented.",
                 "Matching captured bytes does not establish signature bypass, recovery, or acceptance of modified firmware."]}
    for name, value in [("summary", summary), ("chunks", chunks), ("requests", requests),
                        ("ota-frames", packets), ("normal-frames", normal), ("block-checks", block_checks)]:
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path)
    p.add_argument("firmware", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--start-epoch", type=float, help="Select records at/after Unix seconds; retain full capture dissection context")
    a = p.parse_args()
    result = decode(a.capture, a.firmware, a.output, start_epoch=a.start_epoch)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] or result["missing_requested_ranges"] or
                     not result["all_requested_blocks_complete_before_ack"] or
                     not result["terminal_request_observed"] else 0)
