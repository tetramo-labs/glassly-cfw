#!/usr/bin/env python3
"""Construct/reproduce a fixed two-hook graphics runtime OTA, offline only.

This separate profile does not alter the installed probe construction profile.
It proves container changes, not executable correctness or hardware readiness.
No offsets, hook bytes, entry addresses or ABI choices are accepted from callers.
"""
import argparse
import json
from pathlib import Path
import struct

from append_memomind_app import append_app
from build_memomind_runtime import address_pair
from memomind_rx_profile import DEFAULT_RX_PROFILE, rx_limit, mark_manifest, add_rx_argument
from memomind_ota import repack, sha, unpack_ota, require

SOURCE_SHA = "941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876"
FORMAT = "memomind-graphics-runtime-v1"
BODY_BASE, ENTRY, DISPLAY_GATE = 0x041eb020, 0x0439bea0, 0x0439bee0
INITIALIZER, DISPLAY_CALL, CONTINUATION = 0x042e82e0, 0x0425c00a, 0x0425c012
STOCK_HANDLER, STOCK_DISPLAY = 0x042e4680, 0x0425b38a
INIT_BEFORE, INIT_AFTER_STORE = bytes.fromhex("b7472e0493870768"), bytes.fromhex("bcd8")
DISPLACED_LOAD = bytes.fromhex("032504f9")
DISPLAY_BEFORE = bytes.fromhex("032504f9eff0cfb7")
STAGING_CAPACITY, APP_ALLOCATION = 0x25e000, 0x200000
MAX_BLOB_BYTES = 65536


def pc_relative_call(callsite, target):
    """Encode AUIPC ra,hi20; JALR ra,ra,lo12 with an eight-byte return PC."""
    require(type(callsite) is int and type(target) is int and
            0 <= callsite <= 0xfffffff7 and 0 <= target <= 0xffffffff and
            callsite % 2 == 0 and target % 2 == 0, "Call addresses must be RV32 halfword aligned")
    delta = target - callsite
    require(-(1 << 31) <= delta < (1 << 31), "Call displacement outside signed RV32 range")
    high = (delta + 0x800) >> 12
    low = delta - (high << 12)
    require(-2048 <= low <= 2047, "Invalid signed call low immediate")
    auipc = ((high & 0xfffff) << 12) | (1 << 7) | 0x17
    jalr = ((low & 0xfff) << 20) | (1 << 15) | (1 << 7) | 0x67
    return struct.pack("<II", auipc, jalr)


def _guard_nonoverlap(body_size, ranges):
    ordered = sorted(ranges)
    require(all(0 <= lo < hi <= body_size for lo, hi in ordered), "Hook exceeds original body")
    require(all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:])), "Hook ranges overlap")


def _guard_witnesses(body):
    init_offset, display_offset = INITIALIZER-BODY_BASE, DISPLAY_CALL-BODY_BASE
    _guard_nonoverlap(len(body), [(init_offset, init_offset+8), (display_offset, display_offset+8)])
    require(body[init_offset:init_offset+10] == INIT_BEFORE+INIT_AFTER_STORE,
            "Callback initializer/store byte witness differs")
    require(body[display_offset:display_offset+12] == DISPLAY_BEFORE+DISPLACED_LOAD,
            "Display callsite/continuation byte witness differs")


def _guard_final_bounds(file_size, app_raw_size):
    payload_size = file_size-18
    require(payload_size >= 0 and payload_size <= STAGING_CAPACITY and
            ((payload_size+4095) & ~4095) <= STAGING_CAPACITY,
            "Final recompression exceeds staging capacity")
    require(32 <= app_raw_size <= APP_ALLOCATION, "Final application exceeds existing allocation")


def construct_graphics(source, blob, *, rx_profile=DEFAULT_RX_PROFILE):
    limit = rx_limit(rx_profile)
    require(sha(source) == SOURCE_SHA, "Graphics requires exact visually verified text-patch source")
    require(isinstance(blob, bytes) and 16 <= len(blob) <= limit and len(blob) % 16 == 0,
            f"Graphics blob requires 16-aligned length, 16..{limit} bytes")
    require(len(blob) >= DISPLAY_GATE-ENTRY+len(DISPLACED_LOAD), "Display gate lies outside blob")
    require(blob[DISPLAY_GATE-ENTRY:DISPLAY_GATE-ENTRY+4] == DISPLACED_LOAD,
            "Display gate must begin by replaying lw a0,-0x70(s0)")
    original, old_streams = unpack_ota(source)
    original_body = old_streams[3]["raw"][32:]
    _guard_witnesses(original_body)
    require(address_pair(STOCK_HANDLER) == INIT_BEFORE, "Original initializer encoding differs")
    grown, append_audit = append_app(source, blob, expected_source_sha256=SOURCE_SHA, alignment=16)
    require(append_audit["mapping"]["payload_xip_start"] == ENTRY, "Append link address differs")
    _, streams = unpack_ota(grown)
    body = bytearray(streams[3]["raw"][32:])
    hooks = [
        {"name": "service15_callback_initializer", "address": INITIALIZER,
         "body_offset": INITIALIZER-BODY_BASE, "before": INIT_BEFORE.hex(),
         "after": address_pair(ENTRY).hex(), "target": ENTRY,
         "instruction_abi": "LUI a5; ADDI a5,a5; following c.sw a5,0x70(s1) preserved",
         "following_witness": INIT_AFTER_STORE.hex()},
        {"name": "display_worker_dispatch_call", "address": DISPLAY_CALL,
         "body_offset": DISPLAY_CALL-BODY_BASE, "before": DISPLAY_BEFORE.hex(),
         "after": pc_relative_call(DISPLAY_CALL, DISPLAY_GATE).hex(), "target": DISPLAY_GATE,
         "return_address": CONTINUATION,
         "instruction_abi": "AUIPC ra; JALR ra,ra; gate first replays lw a0,-0x70(s0)",
         "following_witness": DISPLACED_LOAD.hex()},
    ]
    for hook in hooks:
        off = hook["body_offset"]
        body[off:off+8] = bytes.fromhex(hook["after"])
    output = repack(grown, {3: bytes(body)})
    _guard_final_bounds(len(output), len(body)+32)
    rebuilt, final_streams = unpack_ota(output)
    require(final_streams[3]["raw"][32:] == body, "Reconstructed body differs")
    expected_prefix = bytearray(original_body)
    for hook in hooks:
        off = hook["body_offset"]
        expected_prefix[off:off+8] = bytes.fromhex(hook["after"])
        witness = bytes.fromhex(hook["following_witness"])
        require(body[off+8:off+8+len(witness)] == witness, "Following instruction witness changed")
    require(body[:len(original_body)] == expected_prefix, "Unexpected original-prefix modification")
    require(body[len(original_body):] == bytes(8)+blob, "Unexpected append padding/payload")
    for i in (0, 1, 2, 4, 5, 6):
        require(final_streams[i]["raw"] == streams[i]["raw"] and
                final_streams[i]["packed"] == streams[i]["packed"], "Hook changed another stream")
    unchanged = []
    for i in (1, 2, 4, 5, 6):
        require(final_streams[i]["packed"] == old_streams[i]["packed"] and
                final_streams[i]["raw"] == old_streams[i]["raw"], "Unrelated source component changed")
        unchanged.append({"index": i, "raw_and_packed_identical": True,
                          "raw_sha256": sha(old_streams[i]["raw"]),
                          "packed_sha256": sha(old_streams[i]["packed"])})
    manifest = {"format": FORMAT, "source_sha256": SOURCE_SHA, "output_sha256": sha(output),
                "blob_sha256": sha(blob), "blob_bytes": len(blob), "entry_address": ENTRY,
                "display_gate_address": DISPLAY_GATE, "hooks": hooks,
                "abi": {"isa": "RV32IMAFC", "calling_convention": "ilp32f",
                        "service_handler": "void(uint32_t command,void *request,const uint8_t *sequence,void **response)",
                        "display_gate": "worker s0 frame; replay load first; borrowed envelope in a0; preserve stack/callee-saved",
                        "ordinary_display_tail_target": STOCK_DISPLAY,
                        "display_return_address": CONTINUATION,
                        "envelope_owner": "stock worker frees after return; gate must not free or retain"}}
    prefix_diff = [i for i in range(len(original_body)) if original_body[i] != body[i]]
    proof = {"manifest": manifest, "offline_only": True, "append_audit_before_hooks": append_audit,
             "output_bytes": len(output), "output_body_sha256": sha(bytes(body)),
             "original_prefix_changed_byte_offsets": prefix_diff,
             "only_two_pinned_prefix_hook_ranges_changed": True,
             "initializer_store_and_display_continuation_preserved": True,
             "unchanged_streams": unchanged, "metadata_identical_to_append_stage": True,
             "final_bounds": {"staging_capacity": STAGING_CAPACITY, "payload_bytes": len(output)-18,
                              "rounded_payload_bytes": (len(output)-18+4095) & ~4095,
                              "staging_headroom": STAGING_CAPACITY-(len(output)-18),
                              "app_allocation": APP_ALLOCATION, "app_raw_bytes": len(body)+32,
                              "app_headroom": APP_ALLOCATION-len(body)-32},
             "checksums": rebuilt["checksums"],
             "limitations": ["Construction does not establish executable correctness or hardware readiness.",
                             "Blob hash and first displaced load do not prove all runtime ABI obligations.",
                             "Display queue ownership, lifecycle, rendering and execution require separate tests."]}
    mark_manifest(manifest, rx_profile)
    return output, manifest, proof


def verify_graphics(source, blob, manifest, *, rx_profile=DEFAULT_RX_PROFILE):
    output, expected, proof = construct_graphics(source, blob, rx_profile=rx_profile)
    require(type(manifest) is dict and manifest == expected and
            json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            "Graphics manifest differs from exact reproduced two-hook profile")
    return output, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("blob", type=Path)
    parser.add_argument("output_directory", type=Path, nargs="?", help="New directory; omitted previews manifest")
    parser.add_argument("--manifest", type=Path, help="Require exact reconstruction of this manifest")
    add_rx_argument(parser)
    args = parser.parse_args()
    try:
        source, blob = args.source.read_bytes(), args.blob.read_bytes()
        if args.manifest:
            output, proof = verify_graphics(source, blob, json.loads(args.manifest.read_text()), rx_profile=args.rx_profile)
            manifest = proof["manifest"]
        else:
            output, manifest, proof = construct_graphics(source, blob, rx_profile=args.rx_profile)
        if args.output_directory:
            args.output_directory.mkdir(parents=True, exist_ok=False)
            (args.output_directory/"firmware.bin").write_bytes(output)
            (args.output_directory/"runtime.bin").write_bytes(blob)
            (args.output_directory/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            (args.output_directory/"verification.json").write_text(json.dumps(proof, indent=2)+"\n")
        print(json.dumps(manifest, indent=2))
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
