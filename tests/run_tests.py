#!/usr/bin/env python3
"""Run the offline MemoMind regression suites and retain scoped evidence.

Exit 0 means all required offline suites passed, not complete G2/device parity.
Exit 1 means a required suite failed or could not run. --require-complete also
exits 2 when the G2 port inventory remains incomplete. Never operates a device.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def source_snapshot():
    paths = set()
    for base in ('scripts', 'runtime', 'tests'):
        for path in (ROOT / base).rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.c', '.h', '.inc', '.S', '.ld', '.json'):
                rel = path.relative_to(ROOT)
                if not {'build', '__pycache__', 'upstream'}.intersection(rel.parts):
                    paths.add(path)
    for base in ('swift/MemoMindKit/Sources', 'swift/MemoMindKit/Tests'):
        for path in (ROOT / base).rglob('*'):
            if path.is_file() and path.suffix in ('.swift', '.plist'):
                paths.add(path)
    paths.add(ROOT / 'swift/MemoMindKit/Package.swift')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def rebuilt_command(command):
    if len(command) > 1 and command[1].startswith('tests/rv32/') and '--build' in command:
        build = Path(command[command.index('--build') + 1])
        if (build / 'graphics.bin').is_file():
            return [command[0], 'tests/rv32/run_rebuilt.py', *command[1:]]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--include-keyboard-reference', action='store_true',
                        help='Run optional historical keyboard checks; failures do not block required parity')
    parser.add_argument('--include-volume-gate-reference', action='store_true', help='Run optional volume-gate reference')
    parser.add_argument('--rv32-python', type=Path,
                        default=ROOT / '.tools/rv32-tests-venv/bin/python')
    parser.add_argument('--demos-dependencies', type=Path,
                        default=Path.home() / 'dev/g2flash/demos/node_modules')
    parser.add_argument('--g2-media', type=Path, default=Path.home() / 'dev/g2flash/demos')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    python = sys.executable
    commands = [
        ('rebuilt_fixtures', 'Fresh-build fixture binding preserves historical pins and rejects source/blob drift',
         [python, 'tests/rv32/test_rebuilt.py']),
        ('inventory', 'Exact original assertion mappings and coverage inventory are current; read-only check',
         [python, 'tests/g2_compat/inventory.py', '--check']),
        ('inventory_scope', 'Hardware exclusions preserve compass/raw IMU/button/ALS requirements; mixed settings and optional-failure isolation',
         [python, 'tests/g2_compat/test_scope.py']),
        ('firmware_transport', 'MemoMind image construction, framing, replay and validation; offline',
         [python, 'tests/run_python_tests.py', '--report', str(out / 'firmware_transport.json')]),
        ('native_swift', 'Native Mac CLI build plus Swift protocol, exact capture replay, image validation and failure tests; no radio operations',
         ['swift', 'test', '--package-path', 'swift/MemoMindKit']),
        ('g2_compat', 'Ported pure algorithms and separately labeled unchanged G2 reference suites',
         [python, 'tests/g2_compat/run_tests.py', '--output', str(out / 'g2_compat'),
          '--demos-dependencies', str(args.demos_dependencies), '--g2-media', str(args.g2_media)]),
        ('geometry', 'MemoMind GRAY4 geometry/RLE compared to pinned G2; RV32 compile checks',
         [python, 'runtime/portable/tests/run_tests.py', '--output', str(out / 'geometry')]),
        ('scene', 'Production portable scene/cache/assets with original shape/vector assertions and media replays',
         [python, 'runtime/portable/tests/run_scene_tests.py', '--output', str(out / 'scene'),
          '--fixtures-from', str(out / 'g2_compat')]),
        ('notifications', 'Portable notification relay with all original scenarios; G2 hook shim is test-only, native adapter pending',
         [python, 'runtime/portable/tests/run_notification_tests.py', '--output', str(out / 'notifications')]),
        ('keyboard', 'Portable keyboard state machine with all original host scenarios; native HOGP and ARM hook coverage remain separate',
         [python, 'runtime/portable/tests/run_keyboard_tests.py', '--output', str(out / 'keyboard')]),
        ('record_transport', 'Portable record parser with all original scenarios and production pinned inflater; hardware excluded',
         [python, 'runtime/portable/tests/run_transport_tests.py', '--output', str(out / 'record-transport')]),
        ('record_session_host', 'Native record carrier allocation failures and deferred destruction with ASan/UBSan',
         [python, 'runtime/graphics/tests/run_record_transport_tests.py', '--output', str(out / 'record-session-host')]),
        ('record_inflater_rv32', 'Actual RV32 production inflater dictionary, bounds, failure and ownership checks',
         [str(args.rv32_python.absolute()), 'tests/rv32/inflater_runtime_emulator_test.py', '--output', str(out / 'record-inflater-rv32')]),
        ('record_build', 'Full native record runtime with existing display, storage and notification features',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'record-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader',
          '--storage-diagnostics', '--full-store-reader', '--flash-canary', '--raster-commands',
          '--rect-copy', '--command-bundles', '--text-commands', '--diagnostic-commands',
          '--reset-undo-trim', '--minimal-launcher', '--flash-scene', '--wake-control',
          '--notification-relay', '--record-transport', '--microphone-control', '--sensor-capture', '--cfw-revision', '8', '--rx-profile', 'app-rx-96k-v1']),
        ('microphone_host', 'Leased native Opus lifecycle, cancellation and cleanup failures under sanitizers',
         [python, 'runtime/graphics/tests/run_microphone_tests.py', '--output', str(out / 'microphone-host')]),
        ('microphone_native_abi', 'Actual stock recording task, open, stop, reset, cooldown and format ABI; hardware mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/microphone_native_abi_test.py', '--report', str(out / 'microphone-native-abi.json')]),
        ('sensor_native_abi', 'Actual ALS read/power/settings and IMU acquisition/decoding/ownership; bus, driver and RTOS mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/sensor_native_abi_test.py', '--report', str(out / 'sensor-native-abi.json')]),
        ('sensor_capture_host', 'Passive snapshot generation, expiry, cleanup and failure paths with ASan/UBSan',
         [python, 'runtime/graphics/tests/run_sensor_capture_tests.py', '--output', str(out / 'sensor-capture-host')]),
        ('sensor_capture_runtime', 'Linked passive sensor control and patched stock acquisition/decoder with mocked bus and RTOS',
         [str(args.rv32_python.absolute()), 'tests/rv32/sensor_capture_runtime_test.py',
          '--build', str(out / 'record-build'), '--report', str(out / 'sensor-capture-runtime.json')]),
        ('microphone_runtime', 'Linked microphone control and native SPP/iAP2 veneers; native audio APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/microphone_runtime_emulator_test.py',
          '--build', str(out / 'record-build'), '--report', str(out / 'microphone-runtime.json')]),
        ('record_gates', 'Actual full record-profile notification/wake service gates preserve register and stack contracts',
         [str(args.rv32_python.absolute()), 'tests/rv32/notification_gate_emulator_test.py',
          '--build', str(out / 'record-build'), '--report', str(out / 'record-gates.json')]),
        ('record_runtime', 'Actual native GM carrier through display queue, parser, inflater and scene; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/record_runtime_emulator_test.py',
          '--build', str(out / 'record-build'), '--report', str(out / 'record-runtime.json')]),
        ('upstream_policy', 'Portable extension/settings/heading/link policies; original battery scenario retained as optional hardware reference; native mappings pending',
         [python, 'runtime/portable/tests/run_upstream_tests.py', '--output', str(out / 'upstream-policy')]),
        ('native_text_host', 'Resource-backed native glyph adapter with injected font APIs and sanitizers',
         [python, 'runtime/graphics/tests/run_native_text_tests.py', '--output', str(out / 'native-text-host')]),
        ('scene_session_host', 'Scene memory/timer ownership and native graphics queue integration; firmware APIs mocked',
         [python, 'runtime/graphics/tests/run_scene_session_tests.py', '--output', str(out / 'scene-session-host'),
          '--fixtures-from', str(out / 'g2_compat')]),
        ('input_host', 'Passive input ownership, ring/ACK/lease and Python JSON contract; native APIs mocked',
         [python, 'runtime/graphics/tests/run_input_tests.py', '--output', str(out / 'input-host')]),
        ('rv32_build', 'Recompile checked-in probe sources with the pinned RISC-V toolchain',
         [python, 'scripts/compile_memomind_probe.py', str(out / 'probe-build')]),
        ('rv32_probe', 'Actual installed probe machine code, with explicitly mocked native functions',
         [str(args.rv32_python.absolute()), 'tests/rv32/probe_emulator_test.py',
          '--build', str(out / 'probe-build'), '--report', str(out / 'rv32_probe.json')]),
        ('graphics_host', 'Display-worker C ownership/lifecycle and full255 geometry requests; native mocks',
         [python, 'runtime/graphics/tests/run_tests.py', '--output', str(out / 'graphics-host')]),
        ('graphics_build', 'Recompile two-hook graphics runtime from current sources',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'graphics-build')]),
        ('graphics_gates', 'Actual RV32 gates and displaced worker callsite; mocked C boundaries',
         [str(args.rv32_python.absolute()), 'tests/rv32/graphics_gate_emulator_test.py',
          '--build', str(out / 'graphics-build'), '--report', str(out / 'graphics-gates.json')]),
        ('graphics_runtime', 'Actual RV32 C/native adapters and geometry; only external firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/graphics_runtime_emulator_test.py',
          '--build', str(out / 'graphics-build'), '--report', str(out / 'graphics-runtime.json')]),
        ('scene_build', 'Compile retained scene/session native adapter as a separate RV32 artifact',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'scene-build'), '--scene-session']),
        ('scene_gates', 'Actual scene build gates/callsite; C boundaries mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/graphics_gate_emulator_test.py',
          '--build', str(out / 'scene-build'), '--report', str(out / 'scene-gates.json')]),
        ('scene_runtime', 'Actual scene RV32 handlers, session and cache/vector C; external firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/scene_runtime_emulator_test.py',
          '--build', str(out / 'scene-build'), '--report', str(out / 'scene-runtime.json')]),
        ('input_build', 'Compile optional passive input observer with retained scene runtime',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'input-build'), '--scene-session', '--input-observer']),
        ('input_gates', 'Actual input-enabled RV32 gates preserve stock integer/FPR/fcsr state; C callbacks mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/input_gate_emulator_test.py',
          '--build', str(out / 'input-build'), '--report', str(out / 'input-gates.json')]),
        ('input_runtime', 'Actual input RV32 handlers/native wrappers and lifecycle; external firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/input_runtime_emulator_test.py',
          '--build', str(out / 'input-build'), '--report', str(out / 'input-runtime.json')]),
        ('flash_read_host', 'Bounded read-only flash ranges, request ownership and failures; native driver mocked',
         [python, 'runtime/graphics/tests/run_flash_read_tests.py', '--output', str(out / 'flash-read-host')]),
        ('flash_read_build', 'Compile optional allowlisted flash reader with scene and input runtime',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'flash-read-build'),
          '--scene-session', '--input-observer', '--flash-reader']),
        ('flash_read_gates', 'Actual flash-enabled RV32 service/display gates preserve stock behavior; C callbacks mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_read_gate_emulator_test.py',
          '--build', str(out / 'flash-read-build'), '--report', str(out / 'flash-read-gates.json')]),
        ('flash_read_runtime', 'Actual flash-reader RV32 handler and native veneer; external APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_read_runtime_emulator_test.py',
          '--build', str(out / 'flash-read-build'), '--report', str(out / 'flash-read-runtime.json')]),
        ('flash_read_contract', 'Production C and actual RV32 emitted replies accepted/rejected by Python client over GM framing',
         [python, 'tests/check_flash_contract.py', '--host-report', str(out / 'flash-read-host/report.json'),
          '--rv32-report', str(out / 'flash-read-runtime.json'), '--report', str(out / 'flash-read-contract.json')]),
        ('external_read_host', 'Read-only external-tail profile boundaries and ownership; native flash mocked',
         [python, 'runtime/graphics/tests/run_flash_read_tests.py', '--external-tail', '--output', str(out / 'external-read-host')]),
        ('external_read_build', 'Compile separate read-only external-tail acquisition profile',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'external-read-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader']),
        ('external_read_gates', 'Actual external-tail reader service/display gates; C bodies mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/external_read_gate_emulator_test.py',
          '--build', str(out / 'external-read-build'), '--report', str(out / 'external-read-gates.json')]),
        ('external_read_runtime', 'Actual external-tail reader handler and native wrapper; hardware mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/external_read_runtime_emulator_test.py',
          '--build', str(out / 'external-read-build'), '--report', str(out / 'external-read-runtime.json')]),
        ('external_read_contract', 'External-tail C/RV32 emitted replies checked by pinned Python profile and GM framing',
         [python, 'tests/check_flash_contract.py', '--host-report', str(out / 'external-read-host/report.json'),
          '--rv32-report', str(out / 'external-read-runtime.json'), '--report', str(out / 'external-read-contract.json')]),
        ('flash_store', '256KiB transactional flash-store core: exhaustive partial-I/O faults, bad sectors, rollback and RV32 audit',
         [python, 'runtime/portable/tests/run_flash_store_tests.py', '--output', str(out / 'flash-store')]),
        ('flash_store_native', 'Fixed native tail adapter: range/badmap/ownership, cache maintenance and readback; native APIs mocked',
         [python, 'runtime/graphics/tests/run_flash_store_native_tests.py', '--output', str(out / 'flash-store-native')]),
        ('scene_flash_store', 'Full256KiB scene backend: unchanged fixture differentials,65535-byte messages,rollback/read faults and RV32 audit',
         [python, 'runtime/portable/tests/run_scene_store_tests.py', '--fixtures-from', str(out / 'g2_compat'),
          '--output', str(out / 'scene-flash-store')]),
        ('external_reservation_native', 'Actual pinned native cache code with exact constructor edits; physical flash and KV mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/external_reservation_emulator_test.py',
          '--output', str(out / 'external-reservation-native')]),
        ('exclusive_storage_native', 'Six CUS8 entry gates from reconstructed candidate; unmapped RAM/MMIO, no hardware ownership claim',
         [str(args.rv32_python.absolute()), 'tests/rv32/exclusive_storage_emulator_test.py',
          '--output', str(out / 'exclusive-storage-native')]),
        ('exclusive_storage_callers', 'Actual native mount callers, reset wrappers and worker failure propagation; firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/exclusive_storage_callers_emulator_test.py',
          '--output', str(out / 'exclusive-storage-callers')]),
        ('heap_registry_native', 'Actual native BSS clear/pool/TLSF allocation/free with exact constructor registry carve; critical sections mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/heap_carve_emulator_test.py',
          '--output', str(out / 'heap-registry-native')]),
        ('dashboard_islands_native', 'Six retired card entries and actual nine-type dispatcher fallback; UI and record APIs mocked, no hardware',
         [str(args.rv32_python.absolute()), 'tests/rv32/dashboard_islands_emulator_test.py',
          '--output', str(out / 'dashboard-islands-native.json')]),
        ('dashboard_ram_native', 'Six production cold-boot UI gates, 230 native null-owner cases; only logging predicate mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/dashboard_ram_emulator_test.py',
          '--output', str(out / 'dashboard-ram-native')]),
        ('storage_diag_host', 'Fixed topology/badmap serializers: sanitizer bounds, corrupt records, source distinctions',
         [python, 'runtime/graphics/tests/run_storage_diag_tests.py', '--output', str(out / 'storage-diag-host')]),
        ('storage_diag_build', 'Compile fixed read-only storage preflight profile with existing scene/input/reader',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'storage-diag-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics']),
        ('storage_diag_gates', 'Actual diagnostic-profile service/display gates preserve stock dispatch; C bodies mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/storage_diag_gate_emulator_test.py',
          '--build', str(out / 'storage-diag-build'), '--report', str(out / 'storage-diag-gates.json')]),
        ('storage_diag_runtime', 'Actual fixed RAM loads, single-key native veneers and serializers; RAM/KV mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/storage_diag_runtime_emulator_test.py',
          '--build', str(out / 'storage-diag-build'), '--report', str(out / 'storage-diag-runtime.json')]),
        ('storage_diag_contract', 'Emitted C/RV32 diagnostics independently checked through fragmented GM and Python',
         [python, 'tests/check_storage_diag_contract.py', '--host-report', str(out / 'storage-diag-host/report.json'),
          '--rv32-report', str(out / 'storage-diag-runtime.json'), '--report', str(out / 'storage-diag-contract.json')]),
        ('storage_diag_scene', 'Existing scene actual-code scenarios rerun against diagnostic image; firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/storage_diag_existing_runtime_emulator_test.py', '--suite', 'scene',
          '--build', str(out / 'storage-diag-build'), '--report', str(out / 'storage-diag-scene.json')]),
        ('storage_diag_input', 'Existing input actual-code scenarios rerun against diagnostic image; firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/storage_diag_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'storage-diag-build'), '--report', str(out / 'storage-diag-input.json')]),
        ('badmap_native', 'Actual pinned KV getter/iterator/CRC/badmap loader with synthetic read-only KV and RTOS locks',
         [str(args.rv32_python.absolute()), 'tests/rv32/badmap_acquisition_emulator_test.py',
          '--output', str(out / 'badmap-native')]),
        ('full_store_read_host', 'Read-only full3MiB range boundaries and ownership; native flash mocked',
         [python, 'runtime/graphics/tests/run_flash_read_tests.py', '--full-store', '--output', str(out / 'full-store-host')]),
        ('full_store_read_build', 'Compile explicit full3MiB read-only profile with diagnostics, scene and input',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'full-store-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics', '--full-store-reader']),
        ('full_store_read_gates', 'Actual full-store reader service/display gates; C entry points mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/full_store_read_gate_emulator_test.py',
          '--build', str(out / 'full-store-build'), '--report', str(out / 'full-store-gates.json')]),
        ('full_store_read_runtime', 'Actual bounded full-store reader and diagnostic machine code; native flash/KV mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/full_store_read_runtime_emulator_test.py',
          '--build', str(out / 'full-store-build'), '--report', str(out / 'full-store-runtime.json')]),
        ('full_store_read_contract', 'Full-store emitted C/RV32 replies through strict GM/Python profile validation',
         [python, 'tests/check_full_store_read_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'full-store-runtime.json'), '--report', str(out / 'full-store-contract.json')]),
        ('full_store_scene', 'Existing scene actual-code scenarios on the full-store reader image; native mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/full_store_existing_runtime_emulator_test.py', '--suite', 'scene',
          '--build', str(out / 'full-store-build'), '--report', str(out / 'full-store-scene.json')]),
        ('full_store_input', 'Existing input actual-code scenarios on the full-store reader image; native mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/full_store_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'full-store-build'), '--report', str(out / 'full-store-input.json')]),
        ('raster_commands_host', 'Optional mode3/6 actual sender/decoder differential and native queue tests with ASan/UBSan',
         [python, 'runtime/graphics/tests/run_raster_commands_tests.py', '--output', str(out / 'raster-commands-host')]),
        ('raster_commands_build', 'Fresh optional mode3/6 RV32 runtime with scene/input/full reader/canary; legacy profiles unchanged',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'raster-commands-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands']),
        ('raster_commands_gates', 'Actual fresh raster runtime gates; original complete gate suite with mocked C boundaries',
         [str(args.rv32_python.absolute()), 'tests/rv32/raster_commands_gate_emulator_test.py',
          '--build', str(out / 'raster-commands-build'), '--report', str(out / 'raster-commands-gates.json')]),
        ('raster_commands_runtime', 'Actual raster C/native wrappers: frame/delta, animation takeover, aliases, ownership; firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/raster_commands_runtime_emulator_test.py',
          '--build', str(out / 'raster-commands-build'), '--fixtures-from', str(out / 'raster-commands-host'),
          '--report', str(out / 'raster-commands-runtime.json')]),
        ('flash_canary_host', 'Fixed canary worker ownership, failure boundaries and restore logic; native mocks',
         [python, 'runtime/graphics/tests/run_flash_canary_tests.py', '--output', str(out / 'flash-canary-host')]),
        ('flash_canary_build', 'Compile fixed-sector canary with full reader, diagnostics, scene and input',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'flash-canary-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary']),
        ('flash_canary_gates', 'Actual canary gates and stack alignment; C boundaries mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_canary_gate_emulator_test.py',
          '--build', str(out / 'flash-canary-build'), '--report', str(out / 'flash-canary-gates.json')]),
        ('flash_canary_runtime', 'Actual canary service/worker machine code; native scheduling, flash and KV mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_canary_runtime_emulator_test.py',
          '--build', str(out / 'flash-canary-build'), '--report', str(out / 'flash-canary-runtime.json')]),
        ('flash_canary_contract', 'Emitted canary replies checked through strict client parser',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'flash-canary-runtime.json'), '--report', str(out / 'flash-canary-contract.json')]),
        ('flash_canary_reader', 'Retained full reader and diagnostics against canary machine code; native mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_canary_reader_emulator_test.py',
          '--build', str(out / 'flash-canary-build'), '--report', str(out / 'flash-canary-reader.json')]),
        ('flash_canary_reader_contract', 'Reader and diagnostic emitted replies preserve exact full-store contract',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'flash-canary-reader.json'), '--report', str(out / 'flash-canary-reader-contract.json')]),
        ('flash_canary_scene', 'Existing scene machine-code scenarios on canary image; native mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_canary_existing_runtime_emulator_test.py', '--suite', 'scene',
          '--build', str(out / 'flash-canary-build'), '--report', str(out / 'flash-canary-scene.json')]),
        ('flash_canary_input', 'Existing input machine-code scenarios on canary image; native mocks',
         [str(args.rv32_python.absolute()), 'tests/rv32/flash_canary_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'flash-canary-build'), '--report', str(out / 'flash-canary-input.json')]),
        ('raster_commands_canary', 'Retained canary service/worker suite on fresh raster machine code; flash/task APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/raster_commands_existing_runtime_emulator_test.py', '--suite', 'canary',
          '--build', str(out / 'raster-commands-build'), '--report', str(out / 'raster-commands-canary.json')]),
        ('raster_commands_reader', 'Retained full reader/diagnostic suite on fresh raster machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/raster_commands_existing_runtime_emulator_test.py', '--suite', 'reader',
          '--build', str(out / 'raster-commands-build'), '--report', str(out / 'raster-commands-reader.json')]),
        ('raster_commands_input', 'Retained input observer/owner/lease suite on fresh raster machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/raster_commands_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'raster-commands-build'), '--report', str(out / 'raster-commands-input.json')]),
        ('raster_commands_canary_contract', 'Repinned raster build canary replies checked by production strict client parser',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'raster-commands-canary.json'), '--report', str(out / 'raster-commands-canary-contract.json')]),
        ('raster_commands_reader_contract', 'Repinned raster build reader/diagnostic replies checked by strict client parser',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'raster-commands-reader.json'), '--report', str(out / 'raster-commands-reader-contract.json')]),
        ('rect_copy_host', 'Mode9 overlap/nibble/bounds/alias differential against pinned G2 copy; sanitizer native mocks',
         [python, 'runtime/graphics/tests/run_rect_copy_tests.py', '--output', str(out / 'rect-copy-host')]),
        ('rect_copy_build', 'Compile mode9 with prior raster/input/full reader/canary features',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'rect-copy-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands', '--rect-copy']),
        ('rect_copy_gates', 'Actual rect-copy machine-code gates with mocked C boundaries',
         [str(args.rv32_python.absolute()), 'tests/rv32/rect_copy_existing_runtime_emulator_test.py', '--suite', 'gates',
          '--build', str(out / 'rect-copy-build'), '--report', str(out / 'rect-copy-gates.json')]),
        ('rect_copy_runtime', 'Actual mode9 RV32 C/native wrappers, pixel copies, aliases and ownership; external firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/rect_copy_runtime_emulator_test.py',
          '--build', str(out / 'rect-copy-build'), '--report', str(out / 'rect-copy-runtime.json')]),
        ('rect_copy_canary', 'Retained fixed canary service/worker on mode9 machine code; native flash/tasks mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/rect_copy_existing_runtime_emulator_test.py', '--suite', 'canary',
          '--build', str(out / 'rect-copy-build'), '--report', str(out / 'rect-copy-canary.json')]),
        ('rect_copy_reader', 'Retained full reader/diagnostic service on mode9 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/rect_copy_existing_runtime_emulator_test.py', '--suite', 'reader',
          '--build', str(out / 'rect-copy-build'), '--report', str(out / 'rect-copy-reader.json')]),
        ('rect_copy_input', 'Retained input observer/lease service on mode9 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/rect_copy_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'rect-copy-build'), '--report', str(out / 'rect-copy-input.json')]),
        ('rect_copy_canary_contract', 'Mode9 build canary replies checked by strict production parser',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'rect-copy-canary.json'), '--report', str(out / 'rect-copy-canary-contract.json')]),
        ('rect_copy_reader_contract', 'Mode9 build reader/diagnostic replies checked by strict production parser',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'rect-copy-reader.json'), '--report', str(out / 'rect-copy-reader-contract.json')]),
        ('command_bundle_host', 'Mode8 pinned dispatch, single-present, partial effects and bounded settled collection with sanitizers',
         [python, 'runtime/graphics/tests/run_command_bundle_tests.py', '--output', str(out / 'command-bundle-host')]),
        ('command_bundle_build', 'Compile mode8 with raster/copy/input/full reader/canary and unchanged64KiB extension bound',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'command-bundle-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands', '--rect-copy', '--command-bundles']),
        ('command_bundle_runtime', 'Actual mode8 RV32 execution, cache/assets, ordered notifications, failures and ownership; firmware APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_runtime_emulator_test.py',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-runtime.json')]),
        ('command_bundle_gates', 'Retained register/stack gates on mode8 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_existing_runtime_emulator_test.py', '--suite', 'gates',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-gates.json')]),
        ('command_bundle_canary', 'Retained fixed canary service and worker on mode8 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_existing_runtime_emulator_test.py', '--suite', 'canary',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-canary.json')]),
        ('command_bundle_reader', 'Retained full reader and diagnostics on mode8 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_existing_runtime_emulator_test.py', '--suite', 'reader',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-reader.json')]),
        ('command_bundle_input', 'Retained passive input observer and lease on mode8 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-input.json')]),
        ('command_bundle_scene', 'Retained retained scene and immediate drawing on mode8 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/command_bundle_existing_runtime_emulator_test.py', '--suite', 'scene',
          '--build', str(out / 'command-bundle-build'), '--report', str(out / 'command-bundle-scene.json')]),
        ('command_bundle_canary_contract', 'Mode8 build canary replies checked by strict production parser',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'command-bundle-canary.json'), '--report', str(out / 'command-bundle-canary-contract.json')]),
        ('command_bundle_reader_contract', 'Mode8 build reader replies checked by strict production parser',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'command-bundle-reader.json'), '--report', str(out / 'command-bundle-reader-contract.json')]),
        ('text_command_host', 'Mode15 255-byte text, signed placement, controls/options, native resource preflight and G2 reference cases with sanitizers',
         [python, 'runtime/graphics/tests/run_text_command_tests.py', '--output', str(out / 'text-command-host')]),
        ('text_command_build', 'Compile mode15 with raster/copy/input/full reader/canary and unchanged64KiB extension bound',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'text-command-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands', '--rect-copy', '--command-bundles', '--text-commands']),
        ('text_command_runtime', 'Actual mode15 RV32 dispatch and resource-font paths; native calls mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_runtime_emulator_test.py',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-runtime.json')]),
        ('text_command_gates', 'Retained register/stack gates on mode15 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'gates',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-gates.json')]),
        ('text_command_canary', 'Retained fixed canary service and worker on mode15 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'canary',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-canary.json')]),
        ('text_command_reader', 'Retained full reader and diagnostics on mode15 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'reader',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-reader.json')]),
        ('text_command_input', 'Retained passive input observer and lease on mode15 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'input',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-input.json')]),
        ('text_command_scene', 'Retained retained scene and immediate drawing on mode15 machine code; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'scene',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-scene.json')]),
        ('text_command_canary_contract', 'Mode15 build canary replies checked by strict production parser',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'text-command-canary.json'), '--report', str(out / 'text-command-canary-contract.json')]),
        ('text_command_reader_contract', 'Mode15 build reader replies checked by strict production parser',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'text-command-reader.json'), '--report', str(out / 'text-command-reader-contract.json')]),
        ('text_command_bundle', 'Retained bundle suite on text machine code, including unchanged notifications and final cache semantics',
         [str(args.rv32_python.absolute()), 'tests/rv32/text_command_existing_runtime_emulator_test.py', '--suite', 'bundle',
          '--build', str(out / 'text-command-build'), '--report', str(out / 'text-command-bundle.json')]),
    ]
    commands += [
        ('diagnostic_command_host', 'Original G2 frame tracking and mode7 controls; native metadata/overlay ownership under sanitizers',
         [python, 'runtime/graphics/tests/run_diagnostic_command_tests.py', '--output', str(out / 'diagnostic-command-host')]),
        ('diagnostic_command_build', 'Compile diagnostics/cleanup with profile-specific size optimization and unchanged64KiB/512-byte guards',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'diagnostic-command-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands', '--rect-copy', '--command-bundles', '--text-commands', '--diagnostic-commands']),
        ('diagnostic_command_runtime', 'Actual mode7/11 RV32 dispatch, framebuffer isolation and overlay/session lifetime; native APIs mocked',
         [str(args.rv32_python.absolute()), 'tests/rv32/diagnostic_command_runtime_emulator_test.py',
          '--build', str(out / 'diagnostic-command-build'), '--report', str(out / 'diagnostic-command-runtime.json')]),
    ]
    for suite in ('gates', 'canary', 'reader', 'input', 'scene', 'bundle', 'text'):
        commands.append((
            'diagnostic_command_' + suite,
            'Retained ' + suite + ' checks on optimized diagnostics machine code; explicit metadata lifetime adaptations and native mocks',
            [str(args.rv32_python.absolute()), 'tests/rv32/diagnostic_command_existing_runtime_emulator_test.py',
             '--suite', suite, '--build', str(out / 'diagnostic-command-build'),
             '--report', str(out / ('diagnostic-command-' + suite + '.json'))]))
    commands += [
        ('diagnostic_command_canary_contract', 'Diagnostic build canary replies checked by strict production parser; no hardware writes',
         [python, 'tests/check_flash_canary_contract.py', '--host-report', str(out / 'flash-canary-host/report.json'),
          '--rv32-report', str(out / 'diagnostic-command-canary.json'), '--report', str(out / 'diagnostic-command-canary-contract.json')]),
        ('diagnostic_command_reader_contract', 'Diagnostic build flash-reader replies checked by strict production parser',
         [python, 'tests/check_flash_canary_reader_contract.py', '--host-report', str(out / 'full-store-host/report.json'),
          '--rv32-report', str(out / 'diagnostic-command-reader.json'), '--report', str(out / 'diagnostic-command-reader-contract.json')]),
    ]
    commands += [
        ('reset_undo_trim_host', 'Opt-in RESET scratch ownership, rollback failures and bundle retention under sanitizers',
         [python, 'runtime/graphics/tests/run_reset_undo_trim_tests.py', '--output', str(out / 'reset-undo-trim-host'),
          '--fixtures-from', str(out / 'g2_compat')]),
        ('reset_undo_trim_build', 'Compile native RESET undo policy within the existing64KiB allocation',
         [python, 'scripts/compile_memomind_graphics.py', str(out / 'reset-undo-trim-build'),
          '--scene-session', '--input-observer', '--flash-reader', '--external-tail-reader', '--storage-diagnostics',
          '--full-store-reader', '--flash-canary', '--raster-commands', '--rect-copy', '--command-bundles',
          '--text-commands', '--diagnostic-commands', '--reset-undo-trim']),
        ('reset_undo_trim_runtime', 'Actual RV32 allocation accounting, reacquisition failure, pixels and bundle ordering',
         [str(args.rv32_python.absolute()), 'tests/rv32/reset_undo_trim_runtime_emulator_test.py',
          '--build', str(out / 'reset-undo-trim-build'), '--report', str(out / 'reset-undo-trim-runtime.json')]),
    ]
    for suite in ('diagnostics', 'gates', 'canary', 'reader', 'input', 'scene', 'bundle', 'text'):
        commands.append((
            'reset_undo_trim_' + suite, 'Retained ' + suite + ' checks on RESET-trim machine code; native APIs mocked',
            [str(args.rv32_python.absolute()), 'tests/rv32/reset_undo_trim_existing_runtime_emulator_test.py',
             '--suite', suite, '--build', str(out / 'reset-undo-trim-build'),
             '--report', str(out / ('reset-undo-trim-' + suite + '.json'))]))
    commands.append(('minimal_owner_flash', 'Minimal launcher lifecycle, native COW worker and full raw-message capacities',
                     [python, 'runtime/graphics/tests/run_minimal_owner_flash_tests.py', '--output', str(out/'minimal-owner-flash'),
                      '--rv32-python', str(args.rv32_python.absolute())]))
    commands.append(('minimal_owner_flash_commands', 'Retained drawing, text, animation and diagnostic cleanup on flash scene',
                     [str(args.rv32_python.absolute()), 'tests/rv32/minimal_owner_flash_commands_test.py',
                      '--build', str(out/'minimal-owner-flash/build'), '--report', str(out/'minimal-owner-flash/retained-commands.json')]))
    if not args.include_keyboard_reference:
        commands = [entry for entry in commands if entry[0] != 'keyboard']
    else:
        for name, scope, command in commands:
            if name == 'g2_compat':command.append('--include-keyboard-reference')
    if args.include_volume_gate_reference:
        for name, scope, command in commands:
            if name == 'g2_compat':command.append('--include-volume-gate-reference')
    started = datetime.now(timezone.utc).isoformat()
    # Record sources independently of pass/fail. Raw firmware/build identities
    # are verified by the respective suites and their reports.
    source_hashes = source_snapshot()
    (out / 'source-sha256.json').write_text(json.dumps(source_hashes, indent=2) + '\n')
    results = []
    for name, scope, command in commands:
        command = rebuilt_command(command)
        print(f'Running {name}: {scope}', flush=True)
        begin = time.monotonic()
        row = {'name': name, 'scope': scope, 'command': command, 'parity_required': name != 'keyboard'}
        try:
            with (out / (name + '.stdout')).open('wb') as stdout, \
                 (out / (name + '.stderr')).open('wb') as stderr:
                process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                         timeout=600)
            row.update(returncode=process.returncode,
                       result='passed' if process.returncode == 0 else 'failed')
        except (OSError, subprocess.TimeoutExpired) as exc:
            row.update(result='could-not-run', error=str(exc))
        row['seconds'] = round(time.monotonic() - begin, 3)
        results.append(row)
        print(f'{name}: {row["result"]}', flush=True)
    inventory = json.loads((ROOT / 'tests/g2_compat/inventory.json').read_text())
    final_hashes = source_snapshot()
    changed = sorted(name for name in source_hashes.keys() | final_hashes.keys()
                     if source_hashes.get(name) != final_hashes.get(name))
    (out / 'source-sha256-final.json').write_text(json.dumps(final_hashes, indent=2) + '\n')
    incomplete = [r['upstream_file'] for r in inventory['rows'] if r.get('parity_required', True) and r['status'] != 'ported']
    # Keep each in-scope original orchestrator stage tied to a required local stage.
    # A renamed/deleted runner must not silently drop mapped upstream coverage.
    mapped = {stage for row in inventory['rows']
              for stages in row.get('aggregate_stage_mapping', {}).values() for stage in stages}
    mapped.update(stage for boundary in inventory.get('native_command_regressions', [])
                  for stage in boundary['aggregate_stages'])
    missing_stages = sorted(mapped - {row['name'] for row in results})
    # Every mixed suite remains incomplete even if some individual assertions
    # already execute the MemoMind implementation.
    complete = bool(inventory['full_memo_suite_port_complete']) and not incomplete
    passed = all(r['result'] == 'passed' for r in results if r['parity_required']) and not changed and not missing_stages
    report = {
        'format': 'memomind-offline-regression-v1', 'started_utc': started,
        'finished_utc': datetime.now(timezone.utc).isoformat(),
        'results': results, 'keyboard_reference_requested': args.include_keyboard_reference,
        'parity_scope': inventory['parity_scope'],
        'required_host_core_scenario_inventory': inventory['required_host_core_scenarios'],
        'all_required_offline_suites_passed': passed,
        'sources_changed_during_run': changed,
        'missing_upstream_mapped_stages': missing_stages,
        'memo_full_suite_port_complete': complete,
        'remaining_upstream_suite_files': incomplete,
        'upstream_commit': inventory['upstream_commit'],
        'host_core_scenario_inventory': inventory['host_core_scenarios'],
        'hardware_tested': False, 'device_actions': 0,
        'limitations': ['Reference G2 passes are not MemoMind implementation passes.',
                        'Offline passes do not establish on-device rendering or full CFW parity.'],
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Evidence: {out / "report.json"}')
    return 1 if not passed else (2 if args.require_complete and not complete else 0)


if __name__ == '__main__':
    raise SystemExit(main())
