"""Offline partial decoder for Yichip's radio instruction format.

Encoding reference: YC1121_Stack c9e8ada, format/command.format and bt.format.
Zero 2 memory transfers use a 17-bit address / count at bit 17 (the YC1121
reference uses bit 15). This is checked against the stock attribute constructor:
0x280002 writes 3 bytes; 0x01280302 writes 4; 0x02290202 writes 8.
Addresses are radio instruction indices, NOT ARM byte addresses. Names describe
encoding only: cross-chip ROM symbols and memory meanings are never imported.
Unknown/reserved encodings remain .word. This is not an assembler or patcher.
"""
import argparse
from pathlib import Path

from radio_config import parse_script

REGS = {0: 'mark', 2: 'temp', 3: 'contru', 5: 'contw', 6: 'contr',
        7: 'queue', 17: 'rega', 18: 'regb', 19: 'regc', 57: 'loopcnt',
        58: 'stack', 59: 'stack_ptr', 61: 'pc', 62: 'null', 63: 'pdata'}
FLAGS = {0: 'always', 1: 'true', 2: 'positive', 5: 'zero', 40: 'user',
         43: 'wake', 52: 'blank', 63: 'never'}


def decode(word):
    """Return mnemonic, operands, and a direct target (if encoded)."""
    if not 0 <= word <= 0xffffffff:
        raise ValueError('Expected unsigned 32-bit instruction')
    op, a, b, c = word >> 27, (word >> 21) & 63, (word >> 15) & 63, (word >> 9) & 63
    low, target = word & 511, word & 32767
    reg = lambda n: REGS.get(n, f'r{n}')
    if op == 4:
        inverse, sub = a >> 5, a & 31
        if sub in (1, 2, 3) and (sub != 3 or target == 0):
            name = ('n' if inverse else '') + {1: 'branch', 2: 'call', 3: 'rtn'}[sub]
            flag = FLAGS.get(b, f'flag{b}')
            return name, (f'0x{target:04x}, ' if sub != 3 else '') + flag, target if sub != 3 else None
        if a == 0 and b == 0:
            return 'nop', str(target), None
        if a == 4 and b == 0 and target == 0:
            return 'clear_stack', '', None
    if op == 0x18:
        sub, imm = (word >> 23) & 15, (word >> 15) & 255
        names = {0: 'beq', 1: 'bne', 2: 'rtneq', 3: 'rtnne', 4: 'loop',
                 5: 'bbit1', 6: 'bbit0', 7: 'rtnbit1', 8: 'rtnbit0',
                 10: 'bmark1', 11: 'bmark0', 12: 'rtnmark1', 13: 'rtnmark0'}
        returns = sub in (2, 3, 7, 8, 12, 13)
        if sub in names and (not returns or target == 0) and (sub != 4 or imm == 0):
            args = '' if sub == 4 else f'0x{imm:02x}'
            if not returns:
                args += (', ' if args else '') + f'0x{target:04x}'
            return names[sub], args, None if returns else target
    if op in (12, 13):
        size = (word >> 17) & 15
        addr = word & 0x1ffff
        if 1 <= size <= 8:
            name = 'fetch' if op == 13 else 'store'
            if a == 2:
                name += 't'
            elif a != 63:
                name += 'r'
            args = (f'{reg(a)}, ' if a not in (2, 63) else '') + f'{size}, 0x{addr:04x}'
            return name, args, None
    if op in (28, 29) and (word & 0x1ffc0) == 0:
        size = (word >> 17) & 15
        if 1 <= size <= 8:
            name = 'ifetch' if op == 29 else 'istore'
            name += '' if a == 63 else 't' if a == 2 else 'r'
            return name, (f'{reg(a)}, ' if a not in (2, 63) else '') + f'{size}, {reg(word & 63)}', None
    if op == 14 and (word >> 24) & 7 == 0:
        return 'jam', f'0x{word & 255:02x}, 0x{(word >> 8) & 65535:04x}', None
    if op == 11:
        return 'setarg', f'0x{word & 0x7ffffff:x}', None
    if op == 27:
        return 'arg', f'0x{word & 0x1fffff:x}, {reg(a)}', None
    if op in (3, 19):
        names = {0: 'force', 1: 'add', 2: 'and', 3: 'or', 4: 'copy',
                 5: 'xor', 8: 'invert', 12: 'sub', 31: 'mul32'}
        valid = b in names and (op != 19 or (low == 0 and b not in (4, 8)))
        valid = valid and (b != 0 or a == 0) and (b not in (4, 8) or low == 0)
        if valid:
            name = ('i' if op == 19 else '') + names[b]
            if b == 0:
                args = (f'0x{low:x}, ' if op == 3 else '') + reg(c)
            elif b in (4, 8) and low == 0:
                args = f'{reg(a)}, {reg(c)}'
            else:
                args = f'{reg(a)}, ' + (f'0x{low:x}, ' if op == 3 else '') + reg(c)
            return name, args, None
    return '.word', f'0x{word:08x}', None


def decode_blob(blob):
    """Decode complete words; caller must retain/report any trailing bytes."""
    return [dict(pc=i // 4, word=int.from_bytes(blob[i:i + 4], 'big'),
                 mnemonic=(d := decode(int.from_bytes(blob[i:i + 4], 'big')))[0],
                 operands=d[1], target=d[2]) for i in range(0, len(blob) - 3, 4)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('file', type=Path, help='Decrypted Yichip section')
    p.add_argument('start', type=lambda s: int(s, 0), help='Radio instruction index')
    p.add_argument('end', type=lambda s: int(s, 0))
    p.add_argument('--script-offset', type=lambda s: int(s, 0), default=0xda6e)
    a = p.parse_args()
    records, _ = parse_script(a.file.read_bytes(), a.script_offset)
    blob = records[0]['payload']
    insns = decode_blob(blob)
    if not 0 <= a.start <= a.end <= len(insns):
        p.error('Range outside complete radio words')
    for ins in insns[a.start:a.end]:
        target = ins['target']
        external = ' ; outside supplied microcode' if target is not None and target >= len(insns) else ''
        print(f"{ins['pc']:04x}: {ins['word']:08x} {ins['mnemonic']:10} {ins['operands']}{external}")
    tail = blob[len(insns) * 4:]
    if tail:
        print(f'Trailing bytes (not instructions): {tail.hex()}')


if __name__ == '__main__':
    main()
