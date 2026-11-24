#!/usr/bin/env python3
"""Pinned real RV32 input C/native wrappers with explicit firmware API mocks.

Separate profile/pin; legacy graphics and scene emulator sources are unchanged.
Actual native hide/send wrappers execute. Only external firmware calls are
mocked; no device input or physical LVGL behavior is asserted.
"""
import argparse
import json
from pathlib import Path
import struct
import unittest

import graphics_runtime_emulator_test as graphics

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT/'runtime/build/input-004'
PINNED_SHA = '3f8e637dff1f9da760b8842d1041eb88579cabc1b864bb5605d21bb9205167b4'
graphics.NATIVES[0x042cde58] = 'input_hide'
REPLIES = []


def subscribe(nonce=123, mask=3): return bytes([1, 1, mask])+struct.pack('<I', nonce)
def poll(nonce=123, ack=0): return bytes([1, 2])+struct.pack('<II', nonce, ack)
def stop(nonce=123): return bytes([1, 3])+struct.pack('<I', nonce)


class InputMachine(graphics.Machine):
    def __init__(self, *, four_aligned=False):
        self.four_aligned = four_aligned
        super().__init__()
        assert self.build['input_observer'] is True and self.build['scene_session'] is True
        self.hidden, self.native_send_commands = set(), []

    def allocate(self, size, tag, data=None, writable=True):
        if not self.four_aligned or tag != 'owned':
            return super().allocate(size, tag, data, writable)
        pointer = ((self.next_heap+7) & ~7)+4
        self.next_heap = pointer+size+32
        assert 0 < size < 0x200000 and self.next_heap < graphics.HEAP+0x400000
        self.allocations[pointer] = {'size': size, 'tag': tag, 'live': True, 'writable': writable}
        self.uc.mem_write(pointer, bytes(size) if data is None else data)
        return pointer

    def native(self, name, args):
        a0, a1, a2, a3, a4 = args[:5]
        if name == 'input_hide':
            assert a0 in self.images and a1 == 1 and a0 not in self.hidden
            assert not self.images[a0]['callback'], 'Image must be hidden immediately after creation'
            self.hidden.add(a0)
            self.native_write(a0+0x24, struct.pack('<I', self.word(a0+0x24)|1))
            return 0
        if name == 'send' and a2 == 0x7c:
            assert (a1, a4) == (15, 1) and a3 in self.replies and self.allocations[a3]['live']
            self.sent.append((a0, self.replies[a3])); self.native_send_commands.append(a2)
            self.events.append(('send_copy', a3)); return 1
        if name == 'on_delete' and a1 == self.symbols['input_deleted']:
            assert a0 in self.hidden and a2 == 0x21
            if self.fail_event: return 0
            spec = self.allocate(40, 'native-spec')
            record = self.allocate(12, 'native-event-record', struct.pack('<IIB3x', a1, a3, a2))
            self.native_write(a0+8, struct.pack('<I', spec))
            self.native_write(spec+12, struct.pack('<I', record))
            self.native_write(spec+0x22, struct.pack('<H', 1))
            self.images[a0].update(callback=a1, owner=a3, extra=[spec, record])
            return record
        if name == 'timer_create' and a0 == self.symbols['input_tick']:
            assert a1 == 20
            if self.fail_timer: return 0
            timer = self.allocate(16, 'native-timer')
            self.native_write(timer+12, struct.pack('<I', a2))
            self.timers[timer] = {'callback': a0, 'owner': a2}; return timer
        return super().native(name, args)

    def finish_image_delete(self, image):
        self.hidden.discard(image)
        super().finish_image_delete(image)

    def execute(self, data, *, expected='ok', sequence=0xa7):
        sent = len(self.sent)
        reply, _ = self.service(0x7c, self.request(data), sequence)
        assert reply is None and self.queue, 'Expected copied deferred input job'
        job = self.queue.pop(0)
        assert job == bytes([2, sequence])+struct.pack('<H', len(data))+data
        raw = bytes([0, 63, 0, 0])+struct.pack('<HH', 0x474c, len(job))+job
        envelope = self.allocate(len(raw), 'worker-input-envelope', raw, writable=False)
        self.call('glassly_graphics_display', envelope, display=True)
        assert self.allocations[envelope]['live'], 'Input freed borrowed worker envelope'
        self.discard(envelope)  # Model stock worker cleanup after return.
        assert len(self.sent) == sent+1 and self.sent[-1][0] == sequence
        result = self.sent[-1][1]; assert result['result'] == expected, result
        assert self.native_send_commands[-1] == 0x7c
        REPLIES.append(result)
        return result

    def observe(self, class_byte, event, length=0):
        raw = bytes([0, class_byte, 0, 0])+struct.pack('<HH', event, length)
        envelope = self.allocate(8, 'borrowed-input-event', raw, writable=False)
        old_owned, old_sent = self.owned_live(), list(self.sent)
        start = len(self.calls)
        self.call('glassly_input_observe', envelope, display=True)
        assert self.owned_live() == old_owned and self.sent == old_sent
        assert not set(self.calls[start:]) & {'try_alloc', 'free', 'json', 'status', 'send', 'post',
                                           'image_delete', 'timer_create', 'timer_delete', 'input_hide'}
        self.discard(envelope)

    def owner(self):
        assert len(self.images) == 1
        owner = next(iter(self.images.values()))['owner']
        assert self.word(owner) == 0x474c4932 and self.allocations[owner]['size'] == 428
        return owner

    def tick(self, now):
        self.now = now & 0xffffffff
        timer = next(iter(self.timers))
        self.call('input_tick', timer, display=True)

    def assert_stopped(self):
        assert not self.images and not self.timers and not self.owned_live() and not self.hidden
        assert not self.image_sources, 'Hidden owner installed an image source/canvas'


class InputRuntimeTests(unittest.TestCase):
    def test_identity_status_native_hide_and_stop(self):
        m = InputMachine(four_aligned=True)
        identity, _ = m.service(0x7e)
        self.assertEqual(identity['inputObserver'], {'command':124, 'capacity':32, 'leaseTicks':30000})
        value = m.execute(bytes([1, 0])); self.assertFalse(value['active']); m.assert_stopped()
        m.active_launcher = False  # Independent from graphics launcher ownership.
        value = m.execute(subscribe()); self.assertTrue(value['active'])
        self.assertEqual(len(m.owned_live()), 1); self.assertEqual(m.owner()%8, 4)
        m.observe(2, 0x1f7b); m.observe(3, 2)
        value = m.execute(poll()); self.assertEqual([x['sequence'] for x in value['records']], [1, 2])
        self.assertEqual([x['class'] for x in value['records']], [2, 3])
        m.execute(stop()); m.assert_stopped()

    def test_all_class_bytes_and_payload_filters(self):
        m = InputMachine(); m.execute(subscribe())
        for cls in range(256):
            for event in (0, 1, 0x1f7b, 0x1fb9, 0x474c, 65535): m.observe(cls, event)
        value = m.execute(poll()); self.assertEqual(value['sequence'], 12)
        for cls in (2, 3, 0x42, 0x43, 0x82, 0x83, 0xc2, 0xc3):
            for length in (1, 255, 256, 65535): m.observe(cls, 1 if cls&63 == 3 else 0x1f7b, length)
        self.assertEqual(m.execute(poll())['sequence'], 12)
        m.execute(stop()); m.assert_stopped()

    def test_ack_retention_overflow_nonce_and_exhaustion(self):
        m = InputMachine(four_aligned=True); m.execute(subscribe())
        for i in range(40): m.now = i+100; m.observe(3, 1)
        first = m.execute(poll()); self.assertEqual(first['drops'], 8)
        self.assertEqual([x['sequence'] for x in first['records']], list(range(9, 17)))
        self.assertEqual(m.execute(poll()), first)  # lost reply: same unacked page
        next_page = m.execute(poll(ack=16)); self.assertEqual(next_page['ack'], 16)
        self.assertEqual(next_page['records'][0]['sequence'], 17)
        self.assertEqual(m.execute(poll(ack=1)), next_page)
        m.execute(poll(ack=41), expected='invalid')
        m.execute(poll(nonce=999), expected='session-conflict')
        m.execute(subscribe(mask=1), expected='session-conflict')
        m.execute(stop(999), expected='session-conflict')
        m.execute(subscribe()); self.assertEqual(m.execute(poll(ack=40))['records'], [])
        # Explicit internal saturation boundary; no firmware mutation interface.
        owner = m.owner()
        m.native_write(owner+12, struct.pack('<III', 0xfffffffe, 0xfffffffe, 0xfffffffe))
        m.observe(3, 8); last = m.execute(poll(ack=0xfffffffe))
        self.assertTrue(last['exhausted']); self.assertEqual(last['records'][0]['sequence'], 0xffffffff)
        m.observe(3, 8); m.observe(3, 8)
        self.assertEqual(m.execute(poll(ack=0xffffffff))['drops'], 0xffffffff)
        m.execute(stop()); m.assert_stopped()

    def test_lease_wrap_expired_observer_and_screen_cleanup(self):
        m = InputMachine(); m.now = 0xfffffff0; m.execute(subscribe()); m.tick(10)
        m.observe(2, 0x1f7b); self.assertEqual(m.execute(poll())['sequence'], 1)
        m.now = 30010; m.observe(2, 0x1f7b)
        self.assertEqual(m.word(m.owner()+12), 1)  # skips expired, never deletes
        m.execute(poll(), expected='no-session'); m.assert_stopped()
        m.execute(subscribe()); m.screen_present = False; m.tick(30030); m.assert_stopped()
        m.screen_present = True; m.execute(subscribe()); m.now = 40000
        m.execute(subscribe()); m.tick(69999); self.assertTrue(m.images)
        m.tick(70000); m.assert_stopped()

    def test_head_state_transitions_report_raise_and_lower(self):
        m = InputMachine(); m.execute(subscribe(mask=2))
        m.tick(100); self.assertEqual(m.execute(poll())['records'], [])
        m.observe(3, 2); m.observe(3, 2); m.observe(3, 5)
        m.uc.mem_write(graphics.HEAD_STATE, b'\x04'); m.tick(120)
        m.uc.mem_write(graphics.HEAD_STATE, b'\x00'); m.tick(140); m.observe(3, 3)
        m.uc.mem_write(graphics.HEAD_STATE, b'\x03'); m.tick(160)
        records = m.execute(poll())['records']
        self.assertEqual([(x['class'], x['id'], x['tick']) for x in records], [(3, 2, 100), (3, 3, 140), (3, 2, 160)])
        m.execute(stop()); m.execute(subscribe(mask=1)); m.tick(180)
        self.assertEqual(m.execute(poll())['records'], [])
        m.uc.mem_write(graphics.HEAD_STATE, b'\x00'); m.execute(stop()); m.assert_stopped()

    def test_actual_native_failure_paths_and_queue_lifetime(self):
        for failure in ('owner', 'image', 'event', 'timer', 'headroom', 'screen'):
            m = InputMachine()
            if failure == 'owner': m.fail_alloc_sizes.add(428)
            if failure == 'image': m.fail_image = True
            if failure == 'event': m.fail_event = True
            if failure == 'timer': m.fail_timer = True
            if failure == 'headroom': m.free_bytes = 65536
            if failure == 'screen': m.screen_present = False
            m.execute(subscribe(), expected='allocation-failed'); m.assert_stopped()
        m = InputMachine(); m.fail_alloc_sizes.add(2048)
        m.execute(subscribe(), expected='allocation-failed'); self.assertTrue(m.images)
        m.fail_alloc_sizes.clear(); m.execute(subscribe()); m.execute(stop()); m.assert_stopped()
        for payload in (b'', b'\x01', b'\x01\x01\x03'+bytes(4), poll()+b'\x00'):
            m = InputMachine(); result, _ = m.service(0x7c, m.request(payload))
            self.assertEqual(result['result'], 'invalid'); self.assertFalse(m.queue); m.assert_stopped()
        m = InputMachine(); m.drop_queue = True
        reply, _ = m.service(0x7c, m.request(subscribe()))
        self.assertIsNone(reply); self.assertFalse(m.queue); m.assert_stopped()
        m = InputMachine(); m.free_bytes = 32768
        reply, _ = m.service(0x7c, m.request(subscribe()))
        self.assertEqual(reply['result'], 'allocation-failed'); m.assert_stopped()
        m = InputMachine(); m.fail_alloc_sizes.add(11)
        reply, _ = m.service(0x7c, m.request(subscribe()))
        self.assertEqual(reply['result'], 'allocation-failed'); m.assert_stopped()
        m = InputMachine()
        reply, _ = m.service(0x7c, m.request(subscribe()), sequence=None)
        self.assertEqual(reply['result'], 'invalid'); m.assert_stopped()

    def test_hidden_and_graphics_owners_are_independent(self):
        m = InputMachine(); m.execute(subscribe())
        hidden = next(iter(m.images)); owner = m.owner()
        m.execute_display(graphics.point_message())
        self.assertEqual(len(m.images), 2); self.assertEqual(len(m.hidden), 1)
        self.assertTrue(m.image_sources)
        m.observe(3, 2); self.assertEqual(m.execute(poll())['sequence'], 1)
        m.execute_display(b'\x0b')
        self.assertEqual(list(m.images), [hidden]); self.assertEqual(m.owner(), owner)
        # Parent/ancestor deletion invokes the actual native DELETE callback,
        # with the native image-delete routine mocked at its proven address.
        m.call(0x042cf61c, hidden, display=True)
        self.assertFalse(m.images or m.timers or m.owned_live() or m.hidden)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=BUILD)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(); graphics.BUILD = args.build.resolve(); graphics.PINNED_SHA = PINNED_SHA
    graphics.RESULTS.clear(); REPLIES.clear()
    assert graphics.u.__version__ == '2.1.4'
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(InputRuntimeTests))
    report = {'format':'memomind-input-runtime-emulation-v1', 'build':str(graphics.BUILD),
              'blob_sha256':PINNED_SHA, 'all_passed':result.wasSuccessful(), 'test_groups':result.testsRun,
              'handler_calls':len(graphics.RESULTS), 'calls':graphics.RESULTS, 'replies':REPLIES,
              'native_stubs':{hex(address):name for address,name in graphics.NATIVES.items()},
              'limitations':['Actual RV32 C/native wrappers execute; external LVGL, allocator, queue, JSON and sender calls are mocked.',
                             'Gate observer-to-stock forwarding has separate machine tests; this harness calls the real C observer directly.',
                             'No device actions or physical input/display verification; native OOM/assert behavior remains untested.',
                             'Measured synthetic4KiB BT /8KiB display stacks exclude native helper frames and interrupts.',
                             'Sequence saturation uses explicit internal boundary state injection, not a public command.']}
    if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__': main()
