#!/usr/bin/env python3
"""Execute the linked broker and stock queue-constructor wrapper.

The scheduler is deliberately refused after both queues are created. This tests
the real ABI and failure cleanup without pretending to emulate task scheduling.
The separate pthread suite covers persistent-worker RPC and flash operations.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
import graphics_runtime_emulator_test as G
sys.path.insert(0, str(G.ROOT / 'scripts'))
from memomind_ota import unpack_ota

G.HEAP = 0x02060000
G.NATIVES.update({0x0200dbf4: 'queue_primitive', 0x0200f168: 'task_refused',
                  0x0200f08c: 'queue_delete', 0x0200a23a: 'enter',
                  0x0200a264: 'leave'})
POOL, REGISTRY = 0x0205d5f8, 0x0205e128

class Machine(G.Machine):
    def __init__(self, body):
        self.critical = False
        self.queues = []
        self.deleted = []
        self.created = 0
        super().__init__()
        for page in (0x0200e000, POOL & ~4095, REGISTRY & ~4095):
            self.uc.mem_map(page, 4096)
        # Startup copies app-body[0x64:0xf918] to 0x02000000.
        self.wrapper = body[0x64 + 0xee6a:0x64 + 0xee7e]
        assert self.wrapper[:16].hex() == '411122c6000832442e85b28501464101'
        self.uc.mem_write(0x0200ee6a, self.wrapper)
        self.uc.mem_write(POOL, struct.pack('<4I', 2, 0x0205e228, 0x020fedc0, 0x0205e228))

    def region(self, address, size, writing=False):
        if POOL <= address and address + size <= POOL + 16:
            assert not writing
            return 'pool'
        if REGISTRY <= address and address + size <= REGISTRY + 128:
            assert self.critical
            return 'registry'
        return super().region(address, size, writing)

    def instruction(self, uc, address, size, userdata):
        if 0x0200ee6a <= address < 0x0200ee7e:
            assert self.stack_base <= self.reg(2) <= self.stack_top and not self.reg(2) % 16
            self.instructions += 1
            self.min_sp = min(self.min_sp, self.reg(2))
            return
        return super().instruction(uc, address, size, userdata)

    def native(self, name, args):
        a0, a1, a2, a3, a4 = args[:5]
        if name == 'enter':
            assert not self.critical
            self.critical = True
            return 0
        if name == 'leave':
            assert self.critical
            self.critical = False
            return 0
        assert not self.critical
        if name == 'queue_primitive':
            # Independent of the C signature: these are the actual kernel args
            # after native 0200ee6a shuffles a1/a2 and zeroes queue type.
            assert (a0, a1, a2) == (1, (16, 4)[len(self.queues)], 0), (a0, a1, a2)
            q = self.allocate(32, 'queue')
            self.queues.append(q)
            return q
        if name == 'task_refused':
            assert a0 == self.symbols['glassly_flash_broker_entry']
            assert a1 in self.owned_live() and (a2, a3) == (5, 0x800)
            assert self.cstring(a4) == 'glassly_flash'
            self.created += 1
            return 0
        if name == 'queue_delete':
            assert a0 in self.queues and a0 not in self.deleted
            self.deleted.append(a0)
            self.discard(a0)
            return 0
        return super().native(name, args)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    G.BUILD = a.build.resolve()
    G.PINNED_SHA = json.loads((G.BUILD / 'build.json').read_text())['blob_sha256']
    body = unpack_ota(a.image.read_bytes())[1][3]['raw'][32:]
    m = Machine(body)
    out, bad = m.allocate(16, 'callbacks'), m.allocate(32, 'map')
    m.call('glassly_flash_broker_bind', out, bad, display=True)
    assert m.reg(10) != 0 and m.created == 1 and m.deleted == m.queues
    assert not m.owned_live()
    # A failed boot registry does not retry task creation or reuse deleted queues.
    m.call('glassly_flash_broker_bind', out, bad, display=True)
    assert m.reg(10) != 0 and m.created == 1 and len(m.queues) == 2
    a.report.write_text(json.dumps(dict(passed=True, runtime_sha256=G.PINNED_SHA,
        wrapper_sha256=hashlib.sha256(m.wrapper).hexdigest(), calls=G.RESULTS,
        kernel_queue_arguments=[[1,16,0],[1,4,0]], hardware_tested=False,
        mock_boundaries=['Kernel allocation/delete', 'Task creation refused', 'Heap/critical sections']), indent=2) + '\n')

if __name__ == '__main__':
    main()
