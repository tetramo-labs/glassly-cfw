"""Verify selected unmodified stock Thumb routines in virtual memory only.

No hardware access, full boot, radio emulation, or firmware patching. The GPIO
registers are ordinary emulator RAM. Input-reader instructions are not stubbed.
Radio sleep/wake is disabled for the isolated IPC checks.
"""
import hashlib
import json
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_PROT_ALL, UC_PROT_READ, UC_PROT_EXEC, __version__
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

from firmware_image import ROOT, load_stock
from startup import reconstruct
from memory_layout import POOLS

BASE, RAM, STOP = 0x1018000, 0x20000, 0x1018100
# Observed input bank/bit -> stock mask bit. Physical button labels unresolved.
INPUTS = ((0, 1, 5), (0, 0, 4), (0, 9, 13), (0, 10, 12),
          (0, 5, 11), (1, 14, 9), (1, 10, 8), (1, 13, 7),
          (1, 12, 6), (1, 11, 0), (2, 4, 3), (2, 1, 10))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def call(uc, address, arg=0, limit=20000):
    uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    uc.reg_write(UC_ARM_REG_R0, arg)
    uc.emu_start(address | 1, STOP, count=limit)
    require(uc.reg_read(UC_ARM_REG_PC) == STOP, 'Routine did not return within instruction limit')
    require(uc.reg_read(UC_ARM_REG_SP) == 0x2ff00, 'Routine did not restore stack')
    return uc.reg_read(UC_ARM_REG_R0)


def gpio(uc, bits):
    levels = [0xffff] * 3
    expected = 0
    for i, (bank, pin, mask_bit) in enumerate(INPUTS):
        if bits & (1 << i):
            levels[bank] &= ~(1 << pin)
            expected |= 1 << mask_bit
    uc.mem_write(0xf873c, struct.pack('<3H', *levels))
    return expected


def verify_memory_pools(uc):
    arguments, written = [], set()
    lowest_sp = [0x2ff00]

    def observe(emu, address, size, _):
        lowest_sp[0] = min(lowest_sp[0], emu.reg_read(UC_ARM_REG_SP))
        if address == 0x1023c5c:
            arguments.append(tuple(emu.reg_read(r) for r in
                                   (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)))

    def writes(emu, access, address, size, value, _):
        written.update(range(address, address + size))

    code_hook = uc.hook_add(UC_HOOK_CODE, observe)
    write_hook = uc.hook_add(UC_HOOK_MEM_WRITE, writes)
    call(uc, 0x1023bb4)
    uc.hook_del(code_hook)
    uc.hook_del(write_hook)
    require(arguments == list(POOLS), 'Pool initializer arguments differ from audited layout')
    allowed = set(range(lowest_sp[0], 0x2ff00))
    for head, start, count, stride in POOLS:
        blocks = [start + i * stride for i in range(count)]
        expected_chain = list(reversed(blocks))
        cursor = int.from_bytes(uc.mem_read(head, 4), 'little')
        for expected in expected_chain:
            require(cursor == expected, 'Pool free-list block differs')
            cursor = int.from_bytes(uc.mem_read(cursor, 4), 'little')
        require(cursor == 0, 'Pool list did not terminate')
        for address in [head] + blocks:
            allowed.update(range(address, address + 4))
    require(written <= allowed, 'Pool initializer wrote outside heads, block links or stack')
    return {'pools': len(POOLS), 'blocks': sum(p[2] for p in POOLS),
            'all_arguments_and_free_lists_checked': True,
            'writes_limited_to_heads_block_links_and_stack': True,
            'observed_initializer_stack_bytes': 0x2ff00 - lowest_sp[0],
            'stubs': [], 'whole_firmware_stack_bound': False}


def verify_input_gates(uc):
    # Isolate the stock task's mode-5 branch. Only unrelated preamble calls
    # are stubbed; both capacity routines and all gate branches execute stock.
    stubs = {0x101c418: 0, 0x101f0bc: 1, 0x101a92c: 0,
             0x101fba0: 0, 0x101fc18: 0}
    stops = {0x101f718: 'gpio', 0x1020544: 'alternate_input'}
    reached = []

    def hook(emu, address, size, _):
        if address in stubs:
            emu.reg_write(UC_ARM_REG_R0, stubs[address])
            emu.reg_write(UC_ARM_REG_PC, emu.reg_read(UC_ARM_REG_LR))
        elif address in stops:
            reached.append(stops[address])
            emu.emu_stop()

    hooks = [uc.hook_add(UC_HOOK_CODE, hook, begin=a, end=a) for a in (*stubs, *stops)]
    cases = [(2, 799, 1997, 'early_return'), (2, 800, 1997, 'gpio'),
             (2, 800, 1998, 'alternate_input'), (2, 799, 1998, 'early_return'),
             (1, 799, 1997, 'gpio'), (1, 799, 1998, 'gpio')]
    results = []
    for state, available, used, expected in cases:
        uc.mem_write(0x20346, b'\x01')
        uc.mem_write(0x201b4, b'\x05')
        uc.mem_write(0x20182, bytes((state,)))
        uc.mem_write(0x20f90, struct.pack('<II', 2048, used))
        uc.mem_write(0x24000, struct.pack('<4H', 0x6000, 0x67ff, 0x6000, 0x6800 - available))
        reached.clear()
        uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.emu_start(0x101ca41, STOP, count=20000)
        if not reached:
            require(uc.reg_read(UC_ARM_REG_PC) == STOP, 'Input task did not reach expected boundary')
            require(uc.reg_read(UC_ARM_REG_SP) == 0x2ff00, 'Input task did not restore stack')
            require(uc.reg_read(UC_ARM_REG_R0) == 0, 'Input task early return was not zero')
        result = reached[0] if reached else 'early_return'
        require(result == expected, 'Input congestion gate differs')
        results.append(dict(state=state, ipc_available=available, software_ring_used=used, reached=result))
    for h in hooks:
        uc.hook_del(h)
    return {'mode': 5, 'software_ring_capacity': 2048, 'cases': results,
            'stubs': {f'0x{a:08x}': v for a, v in stubs.items()},
            'finding': 'In state 2, stock GPIO sampling is skipped by either IPC or software-ring congestion; other modes not exhaustively checked'}


def verify_timer(uc):
    # Install the actual run-loop vtable and execute its stock initializer.
    # Tick scale below is synthetic, not a measured wall-clock period.
    call(uc, 0x1024044, 0x1029158)
    uc.mem_write(0x2058d, b'\x0a')
    uc.mem_write(0x20640, struct.pack('<I', 100))
    call(uc, 0x10202a4)
    require(int.from_bytes(uc.mem_read(0x219e4, 4), 'little') == 0x101be15, 'Input callback registration differs')
    require(int.from_bytes(uc.mem_read(0x2063c, 4), 'little') == 0x219dc, 'Input timer not added to run loop')
    cases = 0
    for quantum in (1, 5, 10):
        uc.mem_write(0x2058d, bytes((quantum,)))
        for tick in (0, 100, 0xfffffffe, 0xffffffff):
            uc.mem_write(0x20640, struct.pack('<I', tick))
            for delay in (0, 9, 29):
                uc.reg_write(UC_ARM_REG_R1, delay)
                call(uc, 0x10240ac, 0x219dc)
                deadline = int.from_bytes(uc.mem_read(0x219e0, 4), 'little')
                require(deadline == (tick + 1 + delay // quantum) & 0xffffffff, 'Timer deadline differs')
                cases += 1
    return {'deadline_cases': cases, 'registration_executed': True,
            'timer_address': '0x000219dc', 'callback': '0x0101be15',
            'tick_counter': '0x00020640', 'scale_byte': '0x0002058d',
            'formula': 'deadline = tick + 1 + floor(delay_argument / scale), modulo 2^32',
            'scales_are_synthetic': True, 'wall_clock_and_sleep_behavior_verified': False}


def verify_ble_lifecycle(uc):
    """Exercise real software-ring dispatch and timer/list operations.

    Disable/enable IRQ wrappers and the power/indicator hook are isolated.
    Observe restart entry without executing its hardware reset operations.
    Radio generation of these events and CCC commit semantics are not tested.
    """
    side_effects, restarts = [], []
    stubs = (0x101f98c, 0x101f9a0, 0x101c874, 0x1023290)

    def stub(emu, address, size, _):
        if address == 0x101c874:
            side_effects.append(emu.reg_read(UC_ARM_REG_R0))
        if address == 0x1023290:
            restarts.append(address)
        emu.reg_write(UC_ARM_REG_PC, emu.reg_read(UC_ARM_REG_LR))

    hooks = [uc.hook_add(UC_HOOK_CODE, stub, begin=a, end=a) for a in stubs]

    def word(address):
        return int.from_bytes(uc.mem_read(address, 4), 'little')

    def event(opcode, payload=b''):
        packet = bytes((2, opcode, len(payload))) + payload
        uc.mem_write(0x25000, packet)
        uc.mem_write(0x20f8c, struct.pack('<5I', 0x25000, 256, len(packet), 0, len(packet)))
        uc.mem_write(0x20020, struct.pack('<I', 1))
        call(uc, 0x101986c)
        require(word(0x20f94) == 0 and word(0x20020) == 0, 'Event not fully consumed')

    call(uc, 0x1023f24)  # Actual run-loop initializer; vtable set by timer checks.
    uc.mem_write(0x21ebc, bytes(24))
    uc.mem_write(0x2058d, b'\x0a')
    uc.mem_write(0x20640, struct.pack('<I', 100))
    uc.mem_write(0x20648, struct.pack('<H', 0x2345))  # Synthetic returned handle.
    uc.mem_write(0x20182, b'\x55')
    event(2)
    require(bytes(uc.mem_read(0x20682, 1)) == b'\x02', 'Event 2 did not set BLE state')
    require(bytes(uc.mem_read(0x20182, 1)) == b'\x55', 'Dispatcher conflated BLE and HID state')
    require(word(0x21ec0) == 700 and word(0x21ec4) == 0x1023a91, 'Connect timer differs')
    require(word(0x2063c) == 0x21ebc, 'Connect timer not linked')
    event(8, struct.pack('<H', 0x2346))
    require(word(0x2063c) == 0x21ebc, 'Unrelated write cancelled stock timer')
    uc.mem_write(0x20198, struct.pack('<I', 0x12345678))
    event(8, struct.pack('<H', 0x2345))
    require(word(0x2063c) == 0 and uc.mem_read(0x21ed0, 1)[0] == 0, 'Matching write did not cancel timer')
    require(word(0x20198) == 0, 'Matching write did not clear idle counter')

    # Concrete payload used by the bounded host keepalive experiment. The
    # unmodified handler must consume the byte and reset both idle mechanisms.
    event(2)
    uc.mem_write(0x20198, struct.pack('<I', 0x12345678))
    event(8, struct.pack('<H', 0x2345) + b'\x00')
    require(word(0x2063c) == 0 and uc.mem_read(0x21ed0, 1)[0] == 0,
            'One-byte vendor write did not cancel watchdog')
    require(word(0x20198) == 0, 'One-byte vendor write did not clear idle counter')

    watchdog_cases = []
    for disconnected, mode, flags, expected in ((False, 0, 0, 1), (False, 3, 0, 0),
                                                (False, 0, 0x40, 0), (True, 0, 0, 0)):
        event(2)
        if disconnected:
            event(5)
            require(uc.mem_read(0x20682, 1)[0] == 3, 'Event 5 did not clear BLE state')
        uc.mem_write(0x20181, bytes((mode,)))
        uc.mem_write(0x201dc, bytes((flags,)))
        uc.mem_write(0x20640, struct.pack('<I', word(0x21ec0)))
        restarts.clear()
        call(uc, 0x1023e80)  # Actual run-loop iteration removes then fires timer.
        require(len(restarts) == expected, 'Watchdog guard behavior differs')
        watchdog_cases.append(dict(disconnected=disconnected, mode=mode, flags=flags,
                                   restart_entry_calls=len(restarts)))
    for hook in hooks:
        uc.hook_del(hook)
    return {'ble_state_address': '0x00020682', 'connected_value': 2, 'disconnected_value': 3,
            'event_opcodes': {'connect': 2, 'disconnect': 5, 'data': 8},
            'timer_address': '0x00021ebc', 'timer_delay_argument': 5999,
            'wrong_handle_preserves_timer': True, 'matching_handle_cancels_timer': True,
            'single_zero_byte_vendor_write_clears_idle_and_watchdog': True,
            'synthetic_handle': '0x2345', 'watchdog_cases': watchdog_cases,
            'stubs': [f'0x{a:08x}' for a in stubs],
            'radio_event_generation_verified': False, 'ccc_semantics_verified': False,
            'restart_executed': False, 'wall_time_verified': False}


def verify(data):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(BASE, 0x12000, UC_PROT_ALL)
    uc.mem_write(BASE, data)
    uc.mem_protect(BASE, 0x12000, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_map(RAM, 0x10000)
    uc.mem_write(RAM, b'\xa5' * 0x10000)
    uc.emu_start(BASE + 0x201, BASE + 0xcf48, count=500000)
    require(uc.reg_read(UC_ARM_REG_PC) == BASE + 0xcf48, 'Startup did not stop before application')
    records, regions, consumed = reconstruct(data)
    for address, expected in regions.items():
        require(bytes(uc.mem_read(address, len(expected))) == expected, 'Startup reconstruction differs from actual Thumb execution')
    # Outside scatter regions, only the emulated stack may have been written.
    require(bytes(uc.mem_read(0x22b18, 0x2fe00 - 0x22b18)) == b'\xa5' * (0x2fe00 - 0x22b18), 'Startup wrote outside declared regions')
    startup_hash = hashlib.sha256(uc.mem_read(RAM, 0x2b18)).hexdigest()
    memory_pools = verify_memory_pools(uc)

    uc.mem_map(0xf8000, 0x1000)  # Simulated GPIO only; never physical memory.
    for bits in range(1 << len(INPUTS)):
        expected = gpio(uc, bits)
        require(call(uc, 0x101f64c) == expected, f'GPIO mismatch for {bits:03x}')
    # All unused bank bits driven low must still yield an empty input mask.
    used = [0, 0, 0]
    for bank, pin, _ in INPUTS:
        used[bank] |= 1 << pin
    uc.mem_write(0xf873c, struct.pack('<3H', *used))
    require(call(uc, 0x101f64c) == 0, 'Unused pins affected button mask')

    # The stock predicate is movs r0,#1; bx lr. Earlier experiments forced it
    # to zero, exercising an unreachable resample branch. Check the real path.
    require(data[0x709c:0x70a0] == bytes.fromhex('01207047'), 'Input predicate changed')
    require(call(uc, 0x101f09c) == 1, 'Stock predicate did not return one')
    delay_calls = []

    def observe_delay(emu, address, size, _):
        delay_calls.append(address)
        emu.emu_stop()  # Unexpected path is a failure, never substituted behavior.

    hook = uc.hook_add(UC_HOOK_CODE, observe_delay, begin=0x101b238, end=0x101b238)
    uc.mem_write(0x20150, bytes.fromhex('a55aa55a'))
    for bits in range(1 << len(INPUTS)):
        expected = gpio(uc, bits)
        require(call(uc, 0x101f718) == expected, 'Input wrapper did not return raw mask')
        require(bytes(uc.mem_read(0x20150, 4)) == bytes.fromhex('a55aa55a'), 'Bypassed retained state changed')
    require(not delay_calls, 'Stock input unexpectedly used delay/resample')
    uc.hook_del(hook)

    uc.mem_map(0xc0000, 0x10000)  # Simulated radio shared memory; no radio executes.
    uc.mem_write(0x20034, struct.pack('<I', 0x24000))
    uc.mem_write(0x20038, b'\0')  # Explicitly exclude sleep/wake handshake.
    input_gates = verify_input_gates(uc)
    timer = verify_timer(uc)
    ble_lifecycle = verify_ble_lifecycle(uc)
    packet = bytes.fromhex('0e00 4703000200000000')  # Opaque bytes, no BLE semantics asserted.
    uc.mem_write(0x24200, packet)
    size, count, exact_fill = 32, 0, 0
    for read in range(size):
        for write in range(size):
            uc.mem_write(0x24000, struct.pack('<4H', 0x6000, 0x601f, 0x6000 + read, 0x6000 + write))
            uc.mem_write(0xc6000, b'\xa5' * size)
            uc.mem_write(0x24100, struct.pack('<BBHI', 0, 9, len(packet), 0x24200))
            available = (read - write) % size or size
            accepted = available >= len(packet) + 3
            result = call(uc, 0x10202c8, 0x24100)
            require(result == int(accepted), 'IPC return/capacity mismatch')
            expected = bytearray(b'\xa5' * size)
            cursor = write
            if accepted:
                for byte in bytes((1, 9, len(packet))) + packet:
                    expected[cursor] = byte
                    cursor = (cursor + 1) % size
            require(bytes(uc.mem_read(0xc6000, size)) == expected, 'IPC copy/wrap mismatch')
            require(int.from_bytes(uc.mem_read(0x24006, 2), 'little') == 0x6000 + cursor, 'IPC cursor mismatch')
            if available == len(packet) + 3:
                require(cursor == read and result == 1, 'Expected exact-fill ambiguity')
                require(call(uc, 0x101ed1c) == size, 'Equal cursors were not interpreted as empty')
                exact_fill += 1
            count += 1
    return {
        'kind': 'offline execution of stock Thumb in simulated memory; not hardware validation',
        'unicorn_version': __version__,
        'tool_sha256': {name: hashlib.sha256((ROOT / 'tools' / name).read_bytes()).hexdigest()
                        for name in ('emulate_stock.py', 'startup.py', 'memory_layout.py')},
        'section_sha256': hashlib.sha256(data).hexdigest(),
        'startup': {'records': records, 'compressed_bytes_consumed': consumed,
                    'initialized_and_zero_ram_sha256': startup_hash},
        'memory_pools': memory_pools,
        'gpio': {'combinations': 4096, 'ignored_pins_checked': True,
                 'mapping': [{'bank': b, 'pin_bit': p, 'mask_bit': m} for b, p, m in INPUTS],
                 'physical_labels': 'unresolved'},
        'input_wrapper': {'combinations': 4096, 'stubs': [],
                          'constant_predicate': '0x0101f09c returns one',
                          'delay_calls': len(delay_calls), 'retained_state_unchanged': True,
                          'finding': 'Stock wrapper returns raw GPIO mask; delay/resample branch is bypassed'},
        'input_task_gates': input_gates,
        'timer': timer,
        'ble_lifecycle': ble_lifecycle,
        'ipc': {'cursor_pairs': count, 'exact_fill_ambiguities': exact_fill,
                'sleep_wake_tested': False, 'radio_delivery_tested': False,
                'finding': 'Stock accepts exact fill, leaving read == write; custom producer must reserve a byte'},
    }


def main():
    _, _, payloads = load_stock()
    report = verify(payloads[1])
    output = ROOT / 'build/stock/emulation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('Passed stock startup, 4096 GPIO and 4096 raw-wrapper combinations, 6 task gates, 36 timer cases, and 1024 IPC cursor pairs.')
    print('Verified all 8 stock pools, 26 linked blocks, and initializer write boundaries.')
    print('Verified queued BLE lifecycle/write dispatch and four watchdog guard cases; reset entry is stubbed.')
    print('Exact-fill ring ambiguity confirmed; radio delivery and hardware remain untested.')
    print(output)


if __name__ == '__main__':
    main()
