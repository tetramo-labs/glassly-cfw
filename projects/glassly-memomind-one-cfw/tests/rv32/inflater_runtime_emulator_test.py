#!/usr/bin/env python3
"""Run the pinned production inflater as RV32 code with bounded allocator mocks."""
import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
CODE, HEAP, STACK, DATA, STUB, STOP = 0x01000000, 0x02000000, 0x03000000, 0x04000000, 0x05000000, 0x06000000


def build(out):
    cc = ROOT / '.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc'
    vendor = ROOT / 'runtime/vendor/zlib'
    manifest = json.loads((vendor / 'UPSTREAM.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((vendor / name).read_bytes()).hexdigest() == digest
    sources = [ROOT / 'runtime/portable/inflater.c', ROOT / 'tests/rv32/inflater_probe.c',
               ROOT / 'runtime/graphics/freestanding.c']
    sources += [vendor / name for name in ('inflate.c', 'inffast.c', 'inftrees.c', 'adler32.c', 'zutil.c')]
    flags = ['-march=rv32imafc', '-mabi=ilp32f', '-mstrict-align', '-mno-relax', '-msmall-data-limit=0',
             '-Os', '-ffreestanding', '-fno-builtin', '-fno-pic', '-fno-common', '-ffunction-sections',
             '-fdata-sections', '-fstack-usage', '-DZ_SOLO', '-DNO_GZIP', '-I' + str(ROOT / 'runtime/portable'), '-I' + str(vendor)]
    objects = []
    for source in sources:
        obj = out / (source.parent.name + '-' + source.stem + '.o')
        subprocess.run([str(cc), *flags, '-c', str(source), '-o', str(obj)], check=True)
        objects.append(obj)
    script = out / 'image.ld'
    script.write_text('SECTIONS { . = 0x01000000; .text : { *(.text*) } .rodata : { *(.rodata* .srodata*) } '
                      '.data : { *(.data* .sdata*) } .bss : { *(.bss* .sbss* COMMON) } '
                      'ASSERT(SIZEOF(.data)==0 && SIZEOF(.bss)==0,"Writable globals") '
                      '/DISCARD/ : { *(.comment .note* .eh_frame* .riscv.attributes) } }')
    elf = out / 'inflater.elf'
    subprocess.run([str(cc), *flags, '-nostdlib', '-Wl,--gc-sections,--no-relax,--build-id=none',
                    '-Wl,-e,probe_decode,-u,mm_inflater_end,--defsym,probe_allocate=0x05000000,--defsym,probe_release=0x05000010',
                    '-T', str(script), *map(str, objects), '-o', str(elf)], check=True)
    prefix = str(cc).removesuffix('gcc')
    assert not subprocess.check_output([prefix + 'nm', '-u', str(elf)]).strip()
    symbols = {}
    for line in subprocess.check_output([prefix + 'nm', '-n', str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    binary = out / 'inflater.bin'
    subprocess.run([prefix + 'objcopy', '-O', 'binary', str(elf), str(binary)], check=True)
    return binary.read_bytes(), symbols, {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}


class Machine:
    def __init__(self, code, symbols, fail_at=0):
        self.uc = uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        self.symbols, self.live, self.cursor = symbols, {}, HEAP
        self.allocations, self.fail_at, self.peak, self.stack = 0, fail_at, 0, 0
        for base, size in ((CODE, 0x10000), (HEAP, 0x40000), (STACK, 0x4000), (DATA, 0x40000), (STUB, 4096), (STOP, 4096)):
            uc.mem_map(base, size)
        uc.mem_write(CODE, code)
        for address in (STUB, STUB + 16):
            uc.mem_write(address, bytes.fromhex('67800000'))
        uc.hook_add(u.UC_HOOK_CODE, self.instruction)
        uc.hook_add(u.UC_HOOK_MEM_READ | u.UC_HOOK_MEM_WRITE, self.memory)

    def memory(self, uc, access, address, size, value, _):
        if HEAP <= address < HEAP + 0x40000:
            assert any(p <= address and address + size <= p + n for p, n in self.live.items()), ('heap bound/lifetime', hex(address), size)

    def instruction(self, uc, address, size, _):
        self.stack = max(self.stack, STACK + 0x4000 - uc.reg_read(r.UC_RISCV_REG_SP))
        if address not in (STUB, STUB + 16):
            return
        ret = uc.reg_read(r.UC_RISCV_REG_RA)
        value = 0
        if address == STUB:
            self.allocations += 1
            n = uc.reg_read(r.UC_RISCV_REG_A1)
            if self.allocations != self.fail_at:
                value = (self.cursor + 31) & ~15
                assert value + n + 16 < HEAP + 0x40000
                self.cursor = value + n + 16
                self.live[value] = n
                uc.mem_write(value, b'\xa5' * n)
                self.peak = max(self.peak, sum(self.live.values()))
        else:
            pointer = uc.reg_read(r.UC_RISCV_REG_A1)
            assert pointer in self.live, ('invalid/double free', hex(pointer))
            del self.live[pointer]
        for index in (1, 5, 6, 7, *range(10, 18), *range(28, 32)):
            uc.reg_write(getattr(r, f'UC_RISCV_REG_X{index}'), 0xb0000000 + index)
        uc.reg_write(r.UC_RISCV_REG_A0, value)
        uc.reg_write(r.UC_RISCV_REG_PC, ret)

    def call(self, name, *args):
        uc = self.uc
        for index in (3, 4, 8, 9, *range(18, 28)):
            uc.reg_write(getattr(r, f'UC_RISCV_REG_X{index}'), 0xa0000000 + index)
        uc.reg_write(r.UC_RISCV_REG_SP, STACK + 0x4000)
        uc.reg_write(r.UC_RISCV_REG_RA, STOP)
        for i, value in enumerate(args):
            uc.reg_write(getattr(r, f'UC_RISCV_REG_A{i}'), value)
        uc.emu_start(self.symbols[name], STOP, count=10000000)
        assert uc.reg_read(r.UC_RISCV_REG_PC) == STOP
        assert uc.reg_read(r.UC_RISCV_REG_SP) == STACK + 0x4000
        for index in (3, 4, 8, 9, *range(18, 28)):
            assert uc.reg_read(getattr(r, f'UC_RISCV_REG_X{index}')) == 0xa0000000 + index
        return uc.reg_read(r.UC_RISCV_REG_A0)

    def decode(self, wire, capacity, slot=0):
        assert len(wire) <= 65535 and capacity <= 65536
        self.uc.mem_write(DATA + 0x1000, wire)
        self.uc.mem_write(DATA + 0x12000, b'\xcc' * (capacity + 8))
        rc = self.call('probe_decode', DATA + slot * 4, DATA + 0x1000, len(wire), DATA + 0x12000, capacity, DATA + 0x100)
        produced = struct.unpack('<I', self.uc.mem_read(DATA + 0x100, 4))[0]
        assert produced <= capacity
        assert bytes(self.uc.mem_read(DATA + 0x12000 + capacity, 8)) == b'\xcc' * 8
        # The z_stream starts at the context pointer; no borrowed input/output survives.
        state = struct.unpack('<I', self.uc.mem_read(DATA + slot * 4, 4))[0]
        if state:
            for offset in (0, 4, 12, 16):
                assert bytes(self.uc.mem_read(state + offset, 4)) == b'\0' * 4
        return rc, bytes(self.uc.mem_read(DATA + 0x12000, produced))

    def end(self, slot=0):
        self.call('mm_inflater_end', DATA + slot * 4)
        assert bytes(self.uc.mem_read(DATA + slot * 4, 4)) == b'\0' * 4


def records(messages, **kwargs):
    compressor = zlib.compressobj(**kwargs)
    return [compressor.compress(m) + compressor.flush(zlib.Z_SYNC_FLUSH) for m in messages]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    code, symbols, sources = build(args.output)
    seed = 1
    data = bytearray()
    for _ in range(32768):
        seed = (seed * 1664525 + 1013904223) & 0xffffffff
        data.append(seed >> 24)
    messages = [bytes(data), bytes(data[-4096:]), b'x' * 65535]
    wire = records(messages)
    assert len(wire[1]) < 100
    machines, cases = [], []
    def machine(**kw):
        m = Machine(code, symbols, **kw); machines.append(m); return m
    m = machine()
    for payload, compressed in zip(messages, wire):
        assert m.decode(compressed, len(payload) + 1) == (0, payload)
    allocations = m.allocations
    m.end(); m.end(); assert not m.live
    cases.append('persistent dictionary and maximum record')
    for fail in range(1, allocations + 1):
        m = machine(fail_at=fail)
        assert m.decode(wire[0], 32769)[0] != 0
        m.end(); assert not m.live
    cases.append('every allocation failure disposes')
    for compressed, capacity in ((wire[1], 4097), (wire[0], 32768), (b'bad!', 1024), (zlib.compress(b'x' * 100), 101)):
        m = machine(); assert m.decode(compressed, capacity)[0] != 0
        assert m.decode(wire[0], 32769)[0] != 0
        m.end(); assert not m.live
    cases.append('missing dictionary, full output, malformed and finished stream poison')
    m = machine()
    for slot in (0, 1):
        assert m.decode(wire[0], 32769, slot) == (0, messages[0])
    m.end(0)
    assert m.decode(wire[1], 4097, 1) == (0, messages[1])
    assert m.decode(wire[1], 4097, 0)[0] != 0
    m.end(0); m.end(1); assert not m.live
    cases.append('independent contexts and reset isolation')
    for strategy in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FIXED, zlib.Z_HUFFMAN_ONLY):
        payload = bytes(data[:2048]) + b'abcd' * 1024
        m = machine(); assert m.decode(records([payload], strategy=strategy)[0], len(payload) + 1) == (0, payload)
        m.end(); assert not m.live
    cases.append('dynamic, fixed and Huffman-only blocks')
    report = dict(passed=True, cases=cases, machineRuns=len(machines), codeBytes=len(code),
                  codeSHA256=hashlib.sha256(code).hexdigest(), sourceSHA256=sources,
                  maxObservedStackBytes=max(m.stack for m in machines), maxOwnedHeapBytes=max(m.peak for m in machines),
                  singleContextAllocationCount=allocations, allocatorAndCallerMocked=True, hardwareTested=False)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sourceSHA256'}))


if __name__ == '__main__':
    main()
