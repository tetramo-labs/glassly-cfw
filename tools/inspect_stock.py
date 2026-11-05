"""Reproduce pinned v1.08 section and radio configuration evidence, offline."""
import argparse
import json
from pathlib import Path
import struct
import uuid

from firmware_image import ROOT, load_stock, sha256
from radio_config import parse_script, parse_attributes
from radio_disasm import decode_blob
from startup import reconstruct
from memory_layout import analyze as analyze_memory

ANCHORS = {
    "entry_trampoline": (0x0000, 4),
    "startup_stack_and_c_runtime": (0x0200, 20),
    "radio_configuration_load": (0x6ece, 10),
    "radio_configuration_pointer": (0x6ef8, 4),
    "radio_configuration_loader": (0xb3b8, 0x110),
    "report_router_entry": (0x71d4, 0x70),
    "report_router_connection_gate": (0x7240, 8),
    "ipc_capacity_checked_submit": (0x82c8, 0x2a),
    "ipc_copy_three_byte_header": (0x6b50, 0xe8),
    "ipc_copy_four_byte_header": (0x6c38, 0xe4),
    "hid_wrapper_ignores_submit_result": (0x1db8, 0x30),
    "runtime_scatter_loader": (0x364, 0x24),
    "runtime_data_decompressor": (0x3ca, 0x56),
    "runtime_scatter_table": (0x1182c, 0x20),
    "runtime_gatt_delete_add_service_add_characteristic": (0x2694, 0x1a),
    "command_complete_switch_table": (0x10e6, 0x13),
    "command_09_ack_sets_bit_6_on_zero_status": (0x1336, 0x16),
    "gpio_mask_reader": (0x764c, 0xca),
    "gpio_bank_read": (0x3b78, 0x1c),
    "input_wrapper_with_bypassed_resample_branch": (0x7718, 0x70),
    "input_predicate_always_returns_one": (0x709c, 4),
    "input_wrapper_call_before_report_router": (0x4bee, 0x14),
    "input_ipc_capacity_gate": (0x4b20, 0x20),
    "input_software_ring_gate": (0x4bdc, 0x16),
    "software_ring_headroom_check": (0x6f84, 0x1c),
    "input_timer_registration": (0x82a4, 0x24),
    "input_timer_callback_and_rearm": (0x3e14, 0x78),
    "run_loop_vtable": (0x11158, 0x28),
    "run_loop_timer_deadline": (0xbf7c, 0x20),
    "run_loop_tick_increment": (0xbf9c, 0x1c),
    "run_loop_delay_to_ticks": (0xbfb8, 0x14),
    "tick_scale_configuration": (0x4830, 0x44),
    "static_pool_registration": (0x273a, 4),
    "static_pool_initializer": (0xbbb4, 0xa8),
    "static_pool_list_construction": (0xbc5c, 0x62),
    "event_dispatcher_stack_frame": (0x186c, 6),
    "main_stack_frame": (0xcf48, 2),
    "startup_external_arm_rom_call": (0xd0a8, 0x18),
    "boot_version_marker_write": (0x8364, 0x10),
    "boot_mode_marker_writes": (0x83b0, 0x20),
    "application_event_switch_table": (0x188a, 0x19),
    "ble_connect_event_handler": (0x1ad2, 0x18),
    "ble_disconnect_event_handler": (0x1b2c, 0x14),
    "vendor_write_handle_filter_and_watchdog_cancel": (0x18e8, 0x36),
    "ble_watchdog_registration": (0xba5c, 0x34),
    "ble_watchdog_guard_and_rearm": (0xba90, 0x40),
    "ble_watchdog_cancel": (0xbad0, 0x18),
    "restart_path_called_by_watchdog": (0xb290, 0x1e),
    "restart_entry_trampoline": (0xb4, 0xe),
}

RADIO_RANGES = {
    "command_dispatch": (0x1bd, 0x1d0),
    "command_09_state_guard": (0x530, 0x534),
    "shared_authentication_guard_candidate": (0x534, 0x53d),
    "notification_property_check": (0x277, 0x28f),
    "delete_custom_attributes": (0x1f7, 0x1fd),
    "attribute_constructors_and_return_handle": (0x1fd, 0x23c),
    "att_write_patch": (0x512, 0x525),
    "write_callback_candidate": (0x1b0, 0x1b8),
}


def inspect():
    raw, sections, payloads = load_stock()
    data = payloads[1]
    base = sections[1]["addr"]
    script_offset = struct.unpack_from("<I", data, 0x6ef8)[0] - base
    records, script_size = parse_script(data, script_offset)
    tables = [r for r in records if r["address"] == 0xc4975]
    if len(tables) != 1:
        raise ValueError("Expected one radio attribute table")
    scatter, regions, consumed = reconstruct(data)
    ram = regions[0x20000]
    service, characteristic = ram[0x65a:0x66b], ram[0x66b:0x67f]
    microcode = records[0]['payload']
    instructions = decode_blob(microcode)
    report = {
        "status": "offline analysis; no bound firmware image",
        "stock_sha256": sha256(raw),
        "byte_exact_roundtrip": True,
        "sections": [dict(s, sha256=sha256(p)) for s, p in zip(sections, payloads)],
        "radio_script": {
            "offset": script_offset, "size": script_size,
            "sha256": sha256(data[script_offset:script_offset + script_size]),
            "records": [dict(offset=r["offset"], address=r["address"],
                             payload_offset=r["payload_offset"], size=len(r["payload"]),
                             sha256=sha256(r["payload"])) for r in records],
        },
        "radio_attribute_table": {
            "offset": tables[0]["payload_offset"], "size": len(tables[0]["payload"]),
            "attributes": parse_attributes(tables[0]["payload"]),
            "caveat": "Initial table only: ARM startup issues delete/add service commands; do not bind its handles as runtime handles",
        },
        "runtime_initialization": {
            "scatter_records": scatter,
            "compressed_bytes_consumed": consumed,
            "regions": [dict(address=addr, size=len(blob), sha256=sha256(blob))
                        for addr, blob in regions.items()],
            "caveat": "Only static initialization boundaries; RAM above these regions is not proven free",
        },
        "memory_constraints": analyze_memory(data),
        "runtime_gatt_command_arguments": {
            "service_address": 0x2065a, "service_payload_hex": service.hex(),
            "service_uuid": str(uuid.UUID(bytes=service[1:][::-1])),
            "characteristic_address": 0x2066b, "characteristic_payload_hex": characteristic.hex(),
            "characteristic_uuid": str(uuid.UUID(bytes=characteristic[2:18][::-1])),
            "properties": characteristic[0], "initial_value_hex": characteristic[19:].hex(),
            "returned_handle_storage": 0x20648,
            "caveat": "Arguments reconstructed from compressed startup data and traced call sites; live registration/handle assignment untested",
        },
        "radio_instruction_evidence": {
            "instruction_bytes": 4, "byte_order": "big",
            "address_unit": "radio instruction index; not ARM bytes",
            "complete_words": len(instructions), "trailing_bytes_hex": microcode[len(instructions)*4:].hex(),
            "memory_count_shift": 17,
            "caveat": "Partial decoder; cross-chip encoding reference adapted against stock constructor transfer sizes; unknown encodings retained",
            "ranges": {name: dict(start_pc=start, end_pc=end,
                                  section_offset=records[0]['payload_offset'] + start * 4,
                                  sha256=sha256(microcode[start*4:end*4]),
                                  external_targets=sorted({i['target'] for i in instructions[start:end]
                                      if i['target'] is not None and i['target'] >= len(instructions)}))
                       for name, (start, end) in RADIO_RANGES.items()},
            "command_09": {
                "dispatch_pc": 0x1c4, "entry_pc": 0x530, "state_address": 0x4652,
                "required_state_bit": 9, "external_continuation": 0x4eda,
                "external_failure_path": 0x501c, "external_guard": 0x7dc1,
                "notification_handle_candidate": 0x467b, "pending_length_candidate": 0x467a,
                "payload_prefix": "LE16 attribute handle supported by reference source; exact Zero 2 ROM parsing remains unavailable",
                "arm_completion_event": 6, "arm_ack_bit": 6,
                "bound": False,
            },
        },
        "anchors": {name: dict(offset=off, address=base + off, size=size,
                               sha256=sha256(data[off:off + size]))
                    for name, (off, size) in ANCHORS.items()},
        "unresolved": [
            "Hardware variant selection between package sections",
            "Radio command 0x09 ROM payload/acknowledgement semantics and CCC lifecycle",
            "Input polling hook before congestion gates, clock/sleep ownership and physical button mapping",
            "Independent GATT path before HID connection/readiness gates",
            "Reserved RAM, startup relocation, stack and executable payload placement",
            "Actual foreground/background/locked delivery on iPhone",
        ],
    }
    return report, payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/stock")
    args = parser.parse_args()
    report, payloads = inspect()
    args.output.mkdir(parents=True, exist_ok=True)
    for i, payload in enumerate(payloads):
        (args.output / f"section{i}.bin").write_bytes(payload)
    (args.output / "inspection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified both v1.08 sections and byte-exact roundtrip: {args.output}")
    print("No patched image generated; radio binding remains unresolved.")


if __name__ == "__main__":
    main()
