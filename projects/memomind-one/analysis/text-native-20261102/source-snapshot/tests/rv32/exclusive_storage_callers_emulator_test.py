#!/usr/bin/env python3
"""Pinned RV32 callers executing production exclusive-store refusal gates.

Native five mount callers, teardown, busy test, memcpy/memset, reset wrappers and
selected full worker dispatch run unchanged. Only heap free, task queue receive,
ticks, display completion enqueue and delay are explicit mocks. No hardware.
Requires Unicorn 2.1.4 and assertions; output must be a new analysis directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_memomind_exclusive_storage as constructor

APP = ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
APP_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
BASE, GP, RET = 0x041eb020, 0x02011688, 0x05000000
SCRATCH, STACK, SP = 0x03000000, 0x03010000, 0x0301fff0
DESC, OUTPUT, BUSY, JOB = SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000, SCRATCH + 0x4000
CTX, VALID, TRANSIENT, QUEUE = 0x02011e48, 0x02011e50, 0x0201613c, 0x02011e6c
OLD_CTX, OLD_TRANSIENT, QUEUE_TOKEN = 0x06002000, 0x06004000, 0x06006000
MOUNT, RESET, WORKER = 0x042a43c8, 0x0423e8b4, 0x042a90ba
# Exact pinned function ranges; actual instructions are from APP, not mock code.
NATIVE = [(0x02000000, 0x02000182), (0x0429bd4c, 0x0429bd66),
          (0x042a3df2, 0x042a3e20), (0x042a439e, 0x042a43c8),
          (0x042a4598, 0x042a4628), (0x042a4628, 0x042a469c),
          (0x042a4994, 0x042a49e2), (0x042a49e2, 0x042a4a2c),
          (0x042a4a2c, 0x042a4a6e), (0x0423eb42, 0x0423eb62),
          (WORKER, 0x042a9656)]
FORBIDDEN = {0x04329ad8, 0x04329b1e, 0x04329a14, 0x043299aa, 0x04329b90,
             0x04235032, 0x04234b5c, 0x04234ac8, 0x0434e6da, 0x0433c320,
             0x02009904, 0x020099a0, 0x041fd196, 0x04324bea,
             0x042a17f2, 0x042a1802, 0x042a1812, 0x042a1b74, 0x042a1976,
             0x042a24a4, 0x042a2542, 0x042a244a, 0x042a245c, 0x042a3d84}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def signed(value):
    return value if value < 0x80000000 else value - 0x100000000


def contains(ranges, address, size):
    return any(start <= address and address + size <= end for start, end in ranges)


def execute(u, r, body, *, name, entry, arguments, expected, expected_gates,
            busy=0, busy_pointer=False, old_context=False, abi=0x100,
            worker_command=None, enqueue_failures=0):
    m = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
    m.mem_map(0x041eb000, 0x200000, u.UC_PROT_READ | u.UC_PROT_EXEC)
    m.mem_write(BASE, body)
    m.mem_map(0x02000000, 0x60000)
    # Startup-derived initialized SRAM; BSS is zero. No synthetic ELF or code.
    m.mem_write(0x02000000, body[0x64:0x64 + 0xf8b4])
    offset = 0x04399fc8 - BASE
    m.mem_write(0x0200f8b8, body[offset:offset + 0x1e78])
    m.mem_map(SCRATCH, 0x20000)
    m.mem_write(SCRATCH, b'\xa5' * 0x10000)
    m.mem_map(RET, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
    # Unicorn decodes the block before its hook; supply a valid RET sentinel.
    # The hook stops before executing it; this is not fabricated target code.
    m.mem_write(RET, bytes.fromhex('67800000'))
    put32 = lambda address, value: m.mem_write(address, struct.pack('<I', value & 0xffffffff))
    get32 = lambda address: struct.unpack('<I', m.mem_read(address, 4))[0]
    m.mem_write(DESC, bytes(0x6c))
    put32(DESC + 0x68, abi)
    m.mem_write(BUSY, bytes(0x100))
    m.mem_write(BUSY + 0xa5, bytes([busy]))
    put32(0x02011e28, BUSY if busy_pointer or busy else 0)
    put32(CTX, OLD_CTX if old_context else 0)
    put32(TRANSIENT, OLD_TRANSIENT if old_context else 0)
    m.mem_write(VALID, b'\x01' if old_context else b'\x00')
    put32(QUEUE, QUEUE_TOKEN)
    if worker_command is not None:
        m.mem_write(JOB, bytes(0x100))
        m.mem_write(JOB, struct.pack('<H', worker_command))
        m.mem_write(JOB + 2, b'\x5a')
        put32(JOB + 4, 0xcccccccc)
        put32(JOB + 12, 0x6c)
        m.mem_write(JOB + 0x29, bytes(m.mem_read(DESC, 0x6c)))
    ram_before = bytes(m.mem_read(0x02000000, 0x60000))
    data_before = bytes(m.mem_read(SCRATCH, 0x10000))
    reg = lambda i: getattr(r, 'UC_RISCV_REG_X' + str(i))
    preserved = {i: 0xabc00000 + i for i in (8, 9, *range(18, 28))}
    for i, value in {**preserved, 1: RET, 2: SP, 3: GP, 4: 0x12345678,
                     **{10 + j: value for j, value in enumerate(arguments)}}.items():
        m.reg_write(reg(i), value)
    state = dict(done=False, steps=0, min_sp=SP, gates=[], frees=[], mocks=[],
                 receives=0, ticks=0, enqueues=0, delays=[], completions=[])
    installer = entry == 0x042a4598 or worker_command == 0xa8
    global_writes = [(CTX, CTX + 4), (VALID, VALID + 1), (TRANSIENT, TRANSIENT + 24)] if installer else []
    job_writes = [] if worker_command is None else [(JOB + 4, JOB + 8), (JOB + 24, JOB + 32)]
    if worker_command == 0xb0:
        job_writes += [(JOB + 0x29, JOB + 0x29 + 24)]
    read_ranges = [(STACK, SCRATCH + 0x20000), (DESC, DESC + 0x6c),
                   (BUSY, BUSY + 0x100), (OUTPUT, OUTPUT + 32),
                   (0x02011e28, 0x02011e2c), (CTX, CTX + 4),
                   (TRANSIENT, TRANSIENT + 24), (QUEUE, QUEUE + 4)]
    if worker_command is not None:
        read_ranges += [(JOB, JOB + 0x100)]
    write_ranges = [(STACK, SCRATCH + 0x20000)] + global_writes + job_writes
    gate_addresses = {row[0] for row in constructor.GATES}
    allowed = NATIVE + [(address, address + 4) for address in gate_addresses]

    def return_mock(value=0):
        m.reg_write(reg(10), value & 0xffffffff)
        m.reg_write(r.UC_RISCV_REG_PC, m.reg_read(reg(1)))

    def instruction(mu, address, size, _):
        state['steps'] += 1
        state['min_sp'] = min(state['min_sp'], mu.reg_read(reg(2)))
        if address == RET:
            assert worker_command is None, 'worker unexpectedly returned'
            state['done'] = True
            mu.emu_stop()
            return
        assert address not in FORBIDDEN, ('forbidden store/flash/KV/allocation/assert', hex(address))
        if address in gate_addresses:
            state['gates'].append(dict(entry=hex(address), arguments=[mu.reg_read(reg(10 + j)) for j in range(4)]))
        if address == 0x0434e6ee:
            assert installer, 'unexpected heap free'
            pointer = mu.reg_read(reg(10))
            expected_free = ([OLD_TRANSIENT, OLD_CTX] if old_context else [0, 0])
            assert len(state['frees']) < 2 and pointer == expected_free[len(state['frees'])]
            state['frees'].append(pointer)
            state['mocks'].append('heap_free')
            return_mock()
            return
        if worker_command is not None and address in (0x0200ef04, 0x0200f6e8, 0x0425add2, 0x0200f758):
            if address == 0x0200ef04:
                assert mu.reg_read(reg(10)) == QUEUE_TOKEN
                state['receives'] += 1
                if state['receives'] == 2:
                    assert state['completions'] == [JOB], 'worker looped without accepted completion'
                    state['done'] = True
                    mu.emu_stop()
                    return
                destination = mu.reg_read(reg(11))
                assert contains([(STACK, SCRATCH + 0x20000)], destination, 4)
                put32(destination, JOB)
                state['mocks'].append('queue_receive_owned_job')
                return_mock(1)
            elif address == 0x0200f6e8:
                state['ticks'] += 1
                state['mocks'].append('tick')
                return_mock(100 + state['ticks'])
            elif address == 0x0200f758:
                delay = mu.reg_read(reg(10))
                assert delay == 10
                state['delays'].append(delay)
                state['mocks'].append('task_delay')
                return_mock()
            else:
                assert [mu.reg_read(reg(10 + j)) for j in (0, 1, 3)] == [0x16, 4, 4]
                source = mu.reg_read(reg(12))
                assert contains([(STACK, SCRATCH + 0x20000)], source, 4) and get32(source) == JOB
                state['enqueues'] += 1
                state['mocks'].append('display_enqueue_copy_pointer')
                if state['enqueues'] <= enqueue_failures:
                    return_mock(1)
                else:
                    state['completions'].append(JOB)
                    return_mock(0)
            return
        assert contains(allowed, address, size), ('unexpected native execution', hex(address), size)

    def read(mu, access, address, size, value, _):
        assert contains(read_ranges, address, size), ('unexpected/null/store data read', hex(address), size)

    def write(mu, access, address, size, value, _):
        assert contains(write_ranges, address, size), ('unexpected data write', hex(address), size)

    m.hook_add(u.UC_HOOK_CODE, instruction)
    m.hook_add(u.UC_HOOK_MEM_READ, read)
    m.hook_add(u.UC_HOOK_MEM_WRITE, write)
    m.emu_start(entry, 0, count=20000)
    assert state['done'], 'instruction budget exhausted'
    assert [int(g['entry'], 16) for g in state['gates']] == expected_gates
    assert m.reg_read(reg(3)) == GP and m.reg_read(reg(4)) == 0x12345678
    if worker_command is None:
        assert signed(m.reg_read(reg(10))) == expected
        assert m.reg_read(reg(2)) == SP
        for i, value in preserved.items():
            assert m.reg_read(reg(i)) == value, ('callee-saved register', i)
    else:
        assert signed(get32(JOB + 4)) == expected
        assert state['ticks'] == 2 and state['enqueues'] == enqueue_failures + 1
        assert state['delays'] == [10] * enqueue_failures and state['receives'] == 2
        assert get32(JOB + 24) == 101 and get32(JOB + 28) == 102
        if worker_command == 0xb0:
            assert bytes(m.mem_read(JOB + 0x29, 24)) == bytes(24)
    # Snapshot differences also catch writes performed by Python mock APIs.
    for start, before, permitted in [(0x02000000, ram_before, global_writes), (SCRATCH, data_before, job_writes)]:
        after = bytes(m.mem_read(start, len(before)))
        for index, (old, new) in enumerate(zip(before, after)):
            if old != new:
                assert contains(permitted, start + index, 1), ('unexpected final memory difference', hex(start + index))
    if installer and expected_gates:
        assert state['frees'] == ([OLD_TRANSIENT, OLD_CTX] if old_context else [0, 0])
        assert get32(CTX) == 0 and bytes(m.mem_read(TRANSIENT, 24)) == bytes(24)
        assert bytes(m.mem_read(VALID, 1)) == b'\x00'
    else:
        assert not state['frees']
    if entry in (0x0423eb42, 0x0423eb52):
        assert state['gates'][0]['arguments'][0] == (entry == 0x0423eb52)
    return dict(name=name, entry=hex(entry), expected_return_or_job_status=expected,
                passed=True, gate_calls=state['gates'], heap_frees=state['frees'],
                mocks=state['mocks'], native_instructions=state['steps'],
                max_observed_stack_bytes=SP - state['min_sp'], flash_calls=0, kv_calls=0,
                allocations=0, enqueue_attempts=state['enqueues'], delays=state['delays'],
                completed_worker_jobs=len(state['completions']),
                callee_saved_and_stack_checked=worker_command is None)


def cases():
    rows = []
    def add(name, entry, arguments, expected, gates=None, **kw):
        rows.append(dict(name=name, entry=entry, arguments=arguments, expected=expected,
                         expected_gates=[MOUNT] if gates is None else gates, **kw))
    add('install refused after real null-context teardown', 0x042a4598, [DESC, 0, 0, OUTPUT], -5)
    add('install tears down synthetic old allocations then refuses', 0x042a4598, [DESC, 0, 0, OUTPUT], -5, old_context=True)
    add('install native busy guard', 0x042a4598, [DESC, 0, 0, OUTPUT], -3, [], busy=1)
    add('install nonbusy existing runtime pointer', 0x042a4598, [DESC, 0, 0, OUTPUT], -5, busy_pointer=True)
    add('install invalid ABI', 0x042a4598, [DESC, 0, 0, OUTPUT], -8, [], abi=0)
    add('install null descriptor', 0x042a4598, [0, 0, 0, OUTPUT], -8, [])
    add('install null output', 0x042a4598, [DESC, 0, 0, 0], -8, [])
    add('query refused output unchanged', 0x042a4628, [DESC, OUTPUT], -5)
    add('query existing store context guard', 0x042a4628, [DESC, OUTPUT], -3, [], old_context=True)
    add('query invalid ABI', 0x042a4628, [DESC, OUTPUT], -8, [], abi=0)
    add('query null descriptor', 0x042a4628, [0, OUTPUT], -1, [])
    add('query null output', 0x042a4628, [DESC, 0], -1, [])
    add('select refused before touching name', 0x042a4994, [0x06008000], -5)
    add('select null name still refuses mount', 0x042a4994, [0], -5)
    for entry, name, arguments in [(0x042a49e2, 'remove', [0x06008000, 0xffffffff]),
                                    (0x042a4a2c, 'clear', [0x06008000])]:
        add(name + ' refused before touching argument', entry, arguments, -5)
        add(name + ' native busy guard', entry, arguments, -3, [], busy=1)
        add(name + ' nonbusy runtime pointer', entry, arguments, -5, busy_pointer=True)
    add('ordinary reset wrapper forwards failure', 0x0423eb42, [0xffffffff], -1, [RESET])
    add('forced reset wrapper forwards failure', 0x0423eb52, [0], -1, [RESET])
    for command, name, gates in [(0xfffc, 'reset', [RESET]), (0xa8, 'install', [MOUNT]), (0xb0, 'query', [MOUNT])]:
        for failures in (0, 2):
            add(f'worker {name}, enqueue failures {failures}', WORKER, [0], -5, gates,
                worker_command=command, enqueue_failures=failures)
    assert len(rows) == 28
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if ROOT / 'analysis' not in out.parents or ROOT / 'analysis/ghidra' in out.parents:
        parser.error('Output must be a new directory under analysis, outside frozen ghidra evidence')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(format='memomind-exclusive-store-native-callers-v1', all_passed=False,
                  device_actions=0, cases=[], provenance={},
                  limitations=['Actual pinned callers and production gates, not whole boot or hardware execution.',
                               'Heap frees, queue receive, ticks, completion enqueue and delay are explicit mocks.',
                               'Worker stops on next receive after completion; downstream display/GM reply is not executed.',
                               'Synthetic old-context teardown does not prove safe cancellation of a running plugin.',
                               'No real mutex contention, native allocator, power loss, other raw owners or full boot coverage.',
                               'Read/program/erase/badmap gates are applied but unreachable from refused mounts; direct gates have a separate test.',
                               'Observed native stack is not a worst-case task/interrupt stack budget.'])
    status = 1
    try:
        if not __debug__:
            raise RuntimeError('Assertions must be enabled')
        import unicorn as u
        from unicorn import riscv_const as r
        assert u.__version__ == '2.1.4'
        original = APP.read_bytes()
        assert sha(original) == APP_SHA
        body, edits = constructor.apply_owner_gates(original)
        assert len(edits) == 6 and sum(len(bytes.fromhex(e['before'])) for e in edits) == 26
        report.update(unicorn=u.__version__, gated_body_sha256=sha(body), production_gate_edits=edits,
                      startup_mapping=dict(sram_code_source='041eb084', sram_code_destination='02000000',
                                           data_source='04399fc8', data_destination='0200f8b8', gp=hex(GP)))
        for path in (Path(__file__), Path(constructor.__file__), APP,
                     ROOT / 'analysis/exclusive-store-review-20261101/report.md'):
            report['provenance'][str(path.relative_to(ROOT))] = sha(path.read_bytes())
        for spec in cases():
            report['active_case'] = spec['name']
            report['cases'].append(execute(u, r, body, **spec))
        report.pop('active_case')
        report.update(all_passed=True, case_count=len(report['cases']),
                      max_observed_stack_bytes=max(c['max_observed_stack_bytes'] for c in report['cases']))
        status = 0
    except Exception as exc:
        report.update(error=str(exc), traceback=traceback.format_exc())
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(all_passed=report['all_passed'], cases=len(report['cases']), output=str(out))))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
