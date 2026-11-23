#!/usr/bin/env python3
"""Execute actual stock card dispatcher through six production refusal gates.

The original RV32 dispatcher and startup memcpy/memset code execute. Record
iterator, clock/settings/log queries and UI fallback are explicit mocks. This
tests caller/ABI/borrowed-data boundaries, not LVGL fallback rendering or hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import build_memomind_dashboard_reclaim as c
import unicorn as u
from unicorn import riscv_const as r

BASE, RET, GP = c.BODY_BASE, 0x05000000, 0x02011688
SCRATCH, SP = 0x03000000, 0x0301fff0
APP_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
TYPES = {2: 0x042711a4, 4: 0x04270f98, 5: 0x04270dd2, 6: 0x04270dd2,
         7: 0x04270c82, 8: 0x04270c82, 9: 0x04270ace, 10: 0x042708e2, 11: 0x042708e2}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def execute(body, edits, entry, arguments, count=1, direct=False):
    m = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
    m.mem_map(0x041eb000, 0x200000, u.UC_PROT_READ | u.UC_PROT_EXEC)
    m.mem_write(BASE, body)
    m.mem_map(0x02000000, 0x60000)
    m.mem_write(0x02000000, body[0x64:0x64+0xf8b4])
    off = 0x04399fc8-BASE
    m.mem_write(0x0200f8b8, body[off:off+0x1e78])
    m.mem_map(SCRATCH, 0x20000)
    # Immutable borrowed item records, with non-null raw payload pointers.
    for i in range(8):
        m.mem_write(SCRATCH+i*32, struct.pack('<8I', i, 0, SCRATCH+0x1000+i*16, 16, 0, 0, 0, 0))
    data_before = bytes(m.mem_read(SCRATCH, 0x10000))
    ram_before = bytes(m.mem_read(0x02000000, 0x60000))
    m.mem_map(RET, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
    m.mem_write(RET, bytes.fromhex('67800000'))
    reg = lambda i: getattr(r, 'UC_RISCV_REG_X'+str(i))
    preserved = {i: 0xaabb0000+i for i in (8, 9, *range(18, 28))}
    initial = {**preserved, 1: RET, 2: SP, 3: GP, 4: 0x12345678,
               **{10+i: arg for i, arg in enumerate(arguments)}}
    for i, value in initial.items(): m.reg_write(reg(i), value & 0xffffffff)
    registers_before = {i: m.reg_read(reg(i)) for i in range(1, 32)}
    state = dict(done=False, steps=0, gates=[], fallbacks=[], iterator=0, mocks=[])
    gate_entries = {row['entry'] for row in edits}
    mock_names = {0x0422b05a: 'setting', 0x02003d5e: 'logging_enabled',
                  0x04270758: 'dashboard_context', 0x0434f16a: 'clock',
                  0x042a7aa2: 'time_changed', 0x042a7b3a: 'iterator_reset',
                  0x042a7b26: 'iterator_next', 0x042a792e: 'record_count',
                  0x04266b06: 'UI_fallback'}

    def hook(mu, address, size, _):
        state['steps'] += 1
        if address == RET:
            state['done'] = True; mu.emu_stop(); return
        for row in edits:
            assert not row['rx_start'] <= address < row['rx_end'], ('retired tail executed', hex(address))
        if address in gate_entries: state['gates'].append(address)
        if address in mock_names:
            assert not direct, ('direct gate called dependency', hex(address))
            state['mocks'].append(mock_names[address])
            result = 0
            if address == 0x0422b05a: result = 1
            elif address == 0x042a792e: result = count
            elif address == 0x042a7b3a: state['iterator'] = 0
            elif address == 0x042a7b26:
                result = SCRATCH+state['iterator']*32
                state['iterator'] += 1
                assert state['iterator'] <= 7
            elif address == 0x04266b06: state['fallbacks'].append(mu.reg_read(reg(10)))
            mu.reg_write(reg(10), result)
            mu.reg_write(r.UC_RISCV_REG_PC, mu.reg_read(reg(1)))
            return
        assert (0x04271fb2 <= address < 0x042722fa or
                0x020000da <= address < 0x02000182 or
                any(row['entry'] <= address < row['entry']+4 for row in edits)), ('unexpected execution', hex(address))

    def write_hook(mu, access, address, size, value, _):
        assert not direct, ('direct gate wrote memory', hex(address))
        assert SP-64 <= address and address+size <= SP, ('write escaped caller stack', hex(address))

    m.hook_add(u.UC_HOOK_CODE, hook)
    m.hook_add(u.UC_HOOK_MEM_WRITE, write_hook)
    if direct:
        def read_hook(mu, access, address, size, value, _):
            raise AssertionError(('direct gate read data memory', hex(address)))
        m.hook_add(u.UC_HOOK_MEM_READ, read_hook)
    m.emu_start(entry, RET+4, count=10000)
    assert state['done'], 'did not return'
    assert m.reg_read(reg(2)) == SP
    for i, value in {**preserved, 3: GP, 4: initial[4]}.items():
        assert m.reg_read(reg(i)) == value, ('ABI clobber', i)
    assert bytes(m.mem_read(SCRATCH, 0x10000)) == data_before, 'borrowed input changed'
    assert bytes(m.mem_read(0x02000000, 0x60000)) == ram_before, 'firmware global changed'
    if direct:
        assert m.reg_read(reg(10)) == 0xffffffff and state['gates'] == [entry]
        assert not state['fallbacks'] and not state['mocks']
        for i, value in registers_before.items():
            if i != 10: assert m.reg_read(reg(i)) == value, ('gate register clobber', i)
    else:
        assert state['gates'] == [TYPES[arguments[0]]]
        assert state['fallbacks'] == [arguments[0]]
    return dict(entry=hex(entry), arguments=arguments, count=count, direct=direct, **state)


def main():
    assert __debug__, 'Assertions are required'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original = (ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
    assert sha(original) == APP_SHA
    body, edits = c.apply_renderer_islands(original)
    cases = []
    for row in edits:
        for arg in (0, 0xffffffff, SCRATCH):
            cases.append(execute(body, edits, row['entry'], [arg, 0xffffffff], direct=True))
    for card_type in TYPES:
        for count in (1, 3, 7):
            for event in (0, 0x44):
                cases.append(execute(body, edits, 0x04271fb2, [card_type, event], count=count))
    report = dict(passed=True, offline_only=True, cases=len(cases), direct_gate_cases=18,
                  actual_dispatcher_cases=54, unicorn=u.__version__, source_sha256=APP_SHA,
                  edited_body_sha256=sha(body), rx_capacity=2746, results=cases,
                  limitations=['UI fallback, iterator, clock, logging and settings APIs are mocked.',
                               'No hardware, real LVGL rendering, global indirect reachability or payload execution proof.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out: out.write(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, indent=2))


if __name__ == '__main__':
    main()
