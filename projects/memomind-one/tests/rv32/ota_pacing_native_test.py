#!/usr/bin/env python3
"""Execute the stock E5 ACK builder; mock peer state, logging and transport."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
BODY_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
BASE = 0x041eb020


def case(body, cursor, remaining, busy, state, send_result=0):
    uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
    uc.mem_map(BASE & ~4095, ((BASE + len(body) + 4095) & ~4095) - (BASE & ~4095))
    uc.mem_write(BASE, body)
    uc.mem_map(0x02000000, 0x20000)
    uc.mem_map(0x03000000, 0x2000)
    uc.mem_map(0x05000000, 4096)
    uc.mem_write(0x02003d9c, bytes.fromhex('67800000'))
    uc.mem_write(0x02011b50, struct.pack('<I', cursor + remaining))
    uc.mem_write(0x02011b65, b'\xf7')
    uc.reg_write(r.UC_RISCV_REG_SP, 0x03002000)
    uc.reg_write(r.UC_RISCV_REG_GP, 0x02011688)
    uc.reg_write(r.UC_RISCV_REG_RA, 0x05000000)
    uc.reg_write(r.UC_RISCV_REG_A0, cursor)
    sent = []

    def hook(uc, address, size, _):
        if address not in (0x04214bae, 0x04214b0c, 0x02003d9c, 0x04238b70):
            return
        result = 0
        if address == 0x04214bae:
            assert uc.reg_read(r.UC_RISCV_REG_A0) == 0
            result = busy
        elif address == 0x04214b0c:
            result = state
        elif address == 0x04238b70:
            assert uc.reg_read(r.UC_RISCV_REG_A0) == 0xe5
            assert uc.reg_read(r.UC_RISCV_REG_A2) == 11
            sent.append(bytes(uc.mem_read(uc.reg_read(r.UC_RISCV_REG_A1), 11)))
            result = send_result
        ret = uc.reg_read(r.UC_RISCV_REG_RA)
        for index in (1, 5, 6, 7, *range(10, 18), *range(28, 32)):
            uc.reg_write(getattr(r, f'UC_RISCV_REG_X{index}'), 0xb0000000 + index)
        uc.reg_write(r.UC_RISCV_REG_A0, result)
        uc.reg_write(r.UC_RISCV_REG_PC, ret)

    uc.hook_add(u.UC_HOOK_CODE, hook)
    try:
        uc.emu_start(0x04238da8, 0x05000000, count=1000)
    except u.UcError as error:
        raise AssertionError(f"Native case {(cursor, remaining, busy, state, send_result)} PC {uc.reg_read(r.UC_RISCV_REG_PC):08x}") from error
    assert uc.reg_read(r.UC_RISCV_REG_PC) == 0x05000000
    assert uc.reg_read(r.UC_RISCV_REG_SP) == 0x03002000
    assert uc.reg_read(r.UC_RISCV_REG_A0) == send_result
    pacing = 2000 if busy or state == 4 else 0
    length = (1024 if pacing else 4096) if remaining > 4096 else remaining
    offset = cursor + 18 if remaining else 0
    assert sent == [b'\x00\xf7\x00' + struct.pack('>IHH', offset, length, pacing)]
    if send_result == 0:
        for address, expected in ((0x02011b3c, cursor), (0x02011b54, cursor), (0x02011b74, cursor + length)):
            assert struct.unpack('<I', uc.mem_read(address, 4))[0] == expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    body = (ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
    assert hashlib.sha256(body).hexdigest() == BODY_SHA
    cases = 0
    for cursor in (0, 16384, 0x200000):
        for remaining in (0, 1, 1024, 4096, 4097, 65536):
            for busy, state in ((0, 1), (0, 4), (1, 1), (1, 4)):
                for send_result in (0, 3):
                    case(body, cursor, remaining, busy, state, send_result)
                    cases += 1
    args.report.write_text(json.dumps(dict(passed=True, cases=cases, stockBodySHA256=BODY_SHA,
        nativeEntry='04238da8', pacingValues=[0, 2000], peerStateAndTransportMocked=True,
        timingUnitsProven=False, chargingTriggerProven=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
