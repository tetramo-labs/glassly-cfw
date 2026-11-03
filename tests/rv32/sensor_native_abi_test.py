#!/usr/bin/env python3
"""Execute stock ALS reads and raw IMU reads; bus, mutex and driver calls are mocks."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
BASE, GP, SP, RET = 0x041eb020, 0x02011688, 0x0301fff0, 0x05000000
OUT, TABLE = 0x03000010, 0x03000100
STOCK_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
BODY = (ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
assert hashlib.sha256(BODY).hexdigest() == STOCK_SHA
MOCKS = {0x043421d2: 'bus_lock', 0x04342200: 'bus_unlock', 0x0200f758: 'sleep',
         0x0200a23a: 'enter', 0x0200a264: 'leave', 0x0200ec3a: 'mutex_lock',
         0x0200ecb2: 'mutex_unlock', 0x02000000: 'copy', 0x02003d5e: 'log_enabled',
         RET + 16: 'read', RET + 32: 'resume', RET + 48: 'suspend',
         0x0422a0c4: 'imu_force', 0x0422a06a: 'imu_resume', 0x042276d0: 'imu_signal',
         0x04229d46: 'imu_busy', 0x0422a1e0: 'imu_reset', 0x0434742e: 'imu_bus_read'}
RANGES = [(0x0422b67a, 0x0422b746), (0x04228900, 0x042289a2),
          (0x0422a18c, 0x0422a1b6), (0x04347344, 0x043473bc),
          (0x0422b5aa, 0x0422b67a), (0x042286a2, 0x0422877c),
          (0x042289a2, 0x042289c8), (0x04227cfc, 0x04227dd0),
          (0x04227e4c, 0x04227eca), (0x043475cc, 0x0434772c)]
SAMPLE = struct.pack('<7h', -32768, -1, 0, 1, 32767, -1234, 2345)


class Machine:
    def __init__(self):
        self.m = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        self.m.mem_map(BASE & ~4095, 0x200000)
        self.m.mem_write(BASE, BODY)
        self.m.mem_map(0x02000000, 0x60000)
        self.m.mem_map(0x03000000, 0x20000)
        self.m.mem_map(RET, 4096)
        for address in MOCKS:
            self.m.mem_write(address, bytes.fromhex('67800000'))
        self.calls = []
        self.critical = self.bus = self.mutex = 0
        self.raw = self.error = 0
        self.change_on_read = None
        self.shutdown_on_lock = False
        self.kind = 'als'
        self.power = False
        self.busy = 0
        self.registers = bytes(14)
        self.m.hook_add(u.UC_HOOK_CODE, self.hook)
        self.m.hook_add(u.UC_HOOK_MEM_WRITE, self.write)

    def get(self, index):
        return self.m.reg_read(getattr(r, f'UC_RISCV_REG_X{index}'))

    def put(self, index, value):
        self.m.reg_write(getattr(r, f'UC_RISCV_REG_X{index}'), value)

    def word(self, address, value):
        self.m.mem_write(address, struct.pack('<I', value))

    def half(self, address):
        return struct.unpack('<H', self.m.mem_read(address, 2))[0]

    def byte(self, address):
        return self.m.mem_read(address, 1)[0]

    def write(self, mu, access, address, size, value, _):
        assert SP - 64 <= address and address + size <= SP or \
            OUT <= address and address + size <= OUT + 14 or \
            address == 0x0200f9aa and size == 2 and self.critical or \
            self.power and any(lo <= address and address + size <= hi for lo, hi in
                               ((0x02011628, 0x02011629), (0x0200f98c, 0x0200f998),
                                (0x0200f9ac, 0x0200f9b4))), (hex(address), size)

    def hook(self, mu, address, size, _):
        if address not in MOCKS:
            assert any(lo <= address < hi for lo, hi in RANGES), hex(address)
            assert SP - 64 <= self.get(2) <= SP and self.get(2) % 16 == 0
            return
        name = MOCKS[address]
        args = [self.get(10 + i) for i in range(3)]
        self.calls.append(name)
        value = 0
        if name == 'enter':
            assert not self.critical and not self.mutex
            self.critical = 1
        elif name == 'leave':
            assert self.critical
            self.critical = 0
        elif name == 'bus_lock':
            assert args[0] == 1 and not self.bus and not self.critical
            self.bus = 1
        elif name == 'bus_unlock':
            assert args[0] == 1 and self.bus
            self.bus = 0
        elif name == 'mutex_lock':
            assert args[0] == 0x12345678 and not self.critical and not self.mutex
            assert self.half(0x0200f9aa) == (self.readers + 1) & 0xffff
            self.mutex = 1
            if self.shutdown_on_lock:
                self.m.mem_write(0x0200f9ae, b'\1')
        elif name == 'mutex_unlock':
            assert args[0] == 0x12345678 and self.mutex and not self.critical
            self.mutex = 0
        elif name == 'copy':
            assert self.mutex and args == [OUT, 0x0200f970, 14]
            self.m.mem_write(OUT, bytes(self.m.mem_read(args[1], 14)))
            value = OUT
        elif name in ('resume', 'suspend'):
            assert (self.bus or self.power) and not self.critical
        elif name == 'sleep':
            assert args[0] == 110 and self.bus and not self.critical
        elif name == 'read':
            if self.kind == 'als':
                assert self.bus and SP - 48 <= args[0] <= SP - 2 and args[0] % 2 == 0
                self.m.mem_write(args[0], struct.pack('<H', self.raw))
                if self.change_on_read is not None:
                    self.m.mem_write(0x02011628, bytes([self.change_on_read]))
            else:
                assert args == [OUT, 0, 0]
                self.m.mem_write(OUT, SAMPLE)
            value = self.error
        elif name == 'imu_force':
            assert self.power and args[0] in (0, 1)
            self.calls[-1] += f'({args[0]})'
        elif name == 'imu_resume':
            assert self.power
            value = self.error
        elif name == 'imu_signal':
            assert self.power and self.byte(args[0]) == 0
        elif name == 'imu_busy':
            value = self.busy
        elif name == 'imu_reset':
            assert self.power
        elif name == 'imu_bus_read':
            assert args[0] == 9 and args[2] == 14 and SP - 48 <= args[1] <= SP - 14
            self.m.mem_write(args[1], self.registers)
            value = self.error
        elif name != 'log_enabled':
            raise AssertionError(name)
        ret = self.get(1)
        for index in (5, 6, 7, *range(10, 18), 28, 29, 30, 31):
            self.put(index, 0xd0000000 + index)
        self.put(10, value)
        self.m.reg_write(r.UC_RISCV_REG_PC, ret)

    def run(self, entry, output=OUT, extra=()):
        for index in range(1, 32):
            self.put(index, 0xaabb0000 + index)
        self.put(1, RET)
        self.put(2, SP)
        self.put(3, GP)
        self.put(10, output)
        for index, value in enumerate(extra, 11):
            self.put(index, value)
        saved = {i: self.get(i) for i in (1, 2, 3, 4, 8, 9, *range(18, 28))}
        self.m.mem_write(OUT - 2, b'\xa5' * 20)
        self.m.emu_start(entry, RET, count=1000)
        assert self.m.reg_read(r.UC_RISCV_REG_PC) == RET
        assert not self.bus and not self.mutex and not self.critical
        for index, value in saved.items():
            assert self.get(index) == value, (index, hex(self.get(index)), hex(value))
        assert bytes(self.m.mem_read(OUT - 2, 2)) == b'\xa5' * 2
        assert bytes(self.m.mem_read(OUT + (2 if self.kind == 'als' else 14),
                                     16 - (2 if self.kind == 'als' else 14))) == \
            b'\xa5' * (16 - (2 if self.kind == 'als' else 14))
        return self.get(10)


def als(flags, *, raw=65535, error=0, table=True, read=True, resume=True, suspend=True, change=None):
    m = Machine()
    m.raw, m.error, m.change_on_read = raw, error, change
    m.word(0x02011628, flags)
    m.word(0x02011ac0, TABLE if table else 0)
    m.m.mem_write(TABLE, struct.pack('<7I', 0, RET + 16 if read else 0,
                                   RET + 48 if suspend else 0, RET + 32 if resume else 0, 0, 0, 0))
    result = m.run(0x0422b67a)
    available = bool(flags & 0x19 and flags & 2 and flags & 12 and table and read)
    assert result == int(available and error == 0)
    assert m.half(OUT) == ((0 if raw == 0 else raw * 1000 // 65536 + 1) if result else 0xa5a5)
    expected = []
    if available:
        expected = ['bus_lock']
        temporary = not flags & 4
        if temporary and resume:
            expected += ['resume', 'sleep']
        expected += ['read']
        if temporary and not (flags if change is None else change) & 4 and suspend:
            expected += ['suspend']
        expected += ['bus_unlock']
    assert m.calls == expected, (m.calls, expected)
    assert m.byte(0x02011628) == (change if available and change is not None else flags)
    return dict(kind='als', flags=flags, raw=raw, driverError=error, table=table, read=read,
                resume=resume, suspend=suspend, flagsDuringRead=change,
                result=result, output=m.half(OUT), calls=m.calls)


def cached_imu(*, shutdown=0, mutex=True, valid=1, readers=0, null=False, shutdown_on_lock=False):
    m = Machine()
    m.kind = 'imu'
    m.readers, m.shutdown_on_lock = readers, shutdown_on_lock
    m.m.mem_write(0x0200f9ae, bytes([shutdown]))
    m.m.mem_write(0x0200f9b0, bytes([valid]))
    m.m.mem_write(0x0200f9aa, struct.pack('<H', readers))
    m.word(0x0200f96c, 0x12345678 if mutex else 0)
    m.m.mem_write(0x0200f970, SAMPLE)
    result = m.run(0x04228900, 0 if null else OUT)
    expected = int(not null and not shutdown and mutex and valid & 1)
    assert result == expected and m.half(0x0200f9aa) == (0 if expected and readers == 65535 else readers)
    assert bytes(m.m.mem_read(OUT, 14)) == (SAMPLE if expected else b'\xa5' * 14)
    assert m.calls == ([] if null else ['enter', 'leave'] if not expected else
                       ['enter', 'leave', 'mutex_lock', 'copy', 'mutex_unlock', 'enter', 'leave'])
    return dict(kind='cached_imu', shutdown=shutdown, mutex=mutex, valid=valid, readers=readers,
                null=null, shutdownDuringLock=shutdown_on_lock, result=result, calls=m.calls)


def direct_imu(*, ready=1, table=True, null=False, error=0):
    m = Machine()
    m.kind, m.error = 'imu', error
    m.m.mem_write(0x0200f9b4, bytes([ready]))
    m.word(0x020124e4, TABLE if table else 0)
    m.word(TABLE + 8, RET + 16)
    result = m.run(0x0422a18c, 0 if null else OUT)
    called = ready and table and not null
    assert result == (error if called else 11)
    assert bytes(m.m.mem_read(OUT, 14)) == (SAMPLE if called else b'\xa5' * 14)
    assert m.calls == (['read'] if called else ['log_enabled'] if ready and not null else [])
    return dict(kind='direct_imu', ready=ready, table=table, null=null, driverError=error,
                result=result, calls=m.calls)


def als_power(flags, enable, *, table=True, callback=True):
    m = Machine()
    m.power = True
    m.word(0x02011628, flags)
    m.word(0x02011ac0, TABLE if table else 0)
    m.word(TABLE + 8, RET + 48 if callback else 0)
    m.word(TABLE + 12, RET + 32 if callback else 0)
    m.run(0x0422b5aa if enable else 0x0422b5e6)
    transition = flags & (7 if enable else 6) == (3 if enable else 6)
    assert m.byte(0x02011628) == ((flags | 4 if enable else flags & ~4) if transition else flags)
    assert m.calls == (['resume' if enable else 'suspend'] if transition and table and callback else [])
    return dict(kind='als_power', flags=flags, enable=enable, table=table, callback=callback,
                finalFlags=m.byte(0x02011628), calls=m.calls)


def als_setting(flags, key, value):
    m = Machine()
    m.power = True
    m.word(0x02011628, flags)
    m.word(0x02011ac0, TABLE)
    m.word(TABLE + 8, RET + 48)
    m.word(TABLE + 12, RET + 32)
    m.m.mem_write(TABLE + 64, bytes([value]))
    m.run(0x0422b620, key, (TABLE + 64,))
    changed = (flags & ~1 | value & 1) if key == 0x5004 else \
        (flags & ~8 | (value & 1) << 3) if key == 0x5904 else flags
    enable = changed & 1
    transition = changed & (7 if enable else 6) == (3 if enable else 6)
    expected = (changed | 4 if enable else changed & ~4) if transition else changed
    assert m.byte(0x02011628) == expected
    assert m.calls == (['resume' if enable else 'suspend'] if transition else [])
    assert m.byte(TABLE + 64) == value
    return dict(kind='als_setting', flags=flags, key=hex(key), value=value,
                finalFlags=expected, calls=m.calls)


def imu_power_sequence(operations, *, ready=True, queue=True, error=0, busy=0, flags=0):
    m = Machine()
    m.kind, m.power, m.error, m.busy = 'imu', True, error, busy
    m.word(0x0200f9b0, 4 if ready else 0)
    m.word(0x0200f968, 0x12345678 if queue else 0)
    m.m.mem_write(0x0200f9af, bytes([flags]))
    states = []
    for operation in operations:
        result = m.run(0x042286a2, operation)
        states.append(dict(result=result, flags=m.byte(0x0200f9af)))
    return dict(kind='imu_power', operations=operations, ready=ready, queue=queue, error=error,
                busy=busy, initialFlags=flags, states=states, calls=m.calls)


def imu_raw_enable(flags, operations):
    m = Machine()
    m.kind, m.power = 'imu', True
    m.word(0x0200f9b0, flags)
    states = []
    expected = flags
    for operation in operations:
        m.run(0x042289a2, operation)
        expected = expected & ~2 | (operation & 1) << 1
        assert m.byte(0x0200f9b0) == expected
        states.append(expected)
    assert not m.calls and m.byte(0x0200f9af) == 0
    return dict(kind='imu_raw_enable', initialFlags=flags, operations=operations, states=states)


def imu_decode(values, *, unscaled=False, error=0, manager=False):
    m = Machine()
    m.kind, m.error = 'imu', error
    m.registers = struct.pack('>7h', *values)
    m.m.mem_write(0x0200f9b4, b'\1')
    m.word(0x020124e4, TABLE)
    m.word(TABLE + 8, 0x043475cc)
    if manager:
        assert not unscaled
        result = m.run(0x0422a18c)
    else:
        result = m.run(0x043475cc, extra=(0, int(unscaled)))
    assert result == (11 if error else 0)
    if error:
        expected = b'\xa5' * 14
    elif unscaled:
        expected = struct.pack('<6h', *values[1:]) + b'\xa5\xa5'
    else:
        axes = [v >> 4 for v in values[1:]]
        axes[3] = -axes[3]
        expected = struct.pack('<7h', *axes, values[0])
    assert bytes(m.m.mem_read(OUT, 14)) == expected
    assert m.calls == ['imu_bus_read'] + (['log_enabled'] if error else [])
    return dict(kind='imu_decode', registerWords=values, unscaled=unscaled, driverError=error,
                throughManager=manager, result=result, output=expected.hex(), calls=m.calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for flags in range(32):
        for table, read in ((False, False), (True, False), (True, True)):
            rows.append(als(flags, table=table, read=read))
    for raw in (0, 1, 65, 66, 32767, 32768, 65470, 65534, 65535):
        rows.append(als(7, raw=raw))
    for flags in (7, 10):
        for error in (0, 1, 11, 0xffffffff):
            for resume, suspend in ((False, False), (False, True), (True, False), (True, True)):
                rows.append(als(flags, error=error, resume=resume, suspend=suspend))
    for flags, change in ((10, 14), (10, 0), (7, 0)):
        rows.append(als(flags, change=change))
    for shutdown in (0, 1):
        for mutex in (False, True):
            for valid in (0, 1, 2, 3):
                rows.append(cached_imu(shutdown=shutdown, mutex=mutex, valid=valid))
    rows += [cached_imu(null=True), cached_imu(readers=3), cached_imu(readers=65535),
             cached_imu(shutdown_on_lock=True)]
    for ready in (0, 1):
        for table in (False, True):
            for null in (False, True):
                for error in (0, 11):
                    rows.append(direct_imu(ready=ready, table=table, null=null, error=error))
    for flags in range(32):
        for enable in (False, True):
            for table, callback in ((False, False), (True, False), (True, True)):
                rows.append(als_power(flags, enable, table=table, callback=callback))
    for flags in range(16):
        for key in (0x5004, 0x5904, 0xffff):
            for value in (0, 1, 2, 255):
                rows.append(als_setting(flags, key, value))
    for ready, queue, error in ((False, True, 0), (True, False, 0), (True, True, 11), (True, True, 0)):
        row = imu_power_sequence([1], ready=ready, queue=queue, error=error)
        assert row['states'] == [dict(result=0, flags=6) if ready and queue and not error else dict(result=11, flags=0)]
        rows.append(row)
    row = imu_power_sequence([1, 1, 0])
    assert row['states'] == [dict(result=0, flags=6), dict(result=0, flags=6), dict(result=0, flags=0)]
    assert row['calls'].count('imu_resume') == 1
    assert row['calls'].count('imu_signal') == 1
    rows.append(row)
    row = imu_power_sequence([1, 0], busy=1)
    assert row['states'][-1] == dict(result=0, flags=4)
    rows.append(row)
    for flags in (0, 1, 4, 255):
        for operations in ([0], [1], [2], [255], [1, 1, 0]):
            rows.append(imu_raw_enable(flags, operations))
    for values in ((-32768, -32768, -17, -16, -1, 0, 32767),
                   (32767, 0, 1, 15, 16, 17, -32768), (2345, -32768, -1, 0, 1, 32767, -1234)):
        for error in (0, 1, 11):
            rows.append(imu_decode(values, error=error, manager=True))
            rows.append(imu_decode(values, error=error, unscaled=True))
    report = dict(passed=True, cases=len(rows), stockBodySHA256=STOCK_SHA, actualCodeRanges=RANGES,
                  mockBoundaries={hex(k): v for k, v in MOCKS.items()}, hardwareTested=False,
                  ownershipImplemented=False, results=rows)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Native sensor ABI: {len(rows)} cases passed')


if __name__ == '__main__':
    main()
