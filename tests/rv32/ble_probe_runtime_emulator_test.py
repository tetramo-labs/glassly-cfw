#!/usr/bin/env python3
"""BLE probe on the pinned RV32 runtime: command 0x74 registers a Glassly GATT
service through the stock app-side server, arms and runs the registration
state machine, enables an advertising slot, and the characteristic callbacks
count writes and echo them as notifications. Stock GATT natives are mocked."""
import argparse
import json
import struct
import unittest
from pathlib import Path

import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
from sensor_capture_runtime_test import SensorMachine

GATT_NATIVES = {0x0431a7fe: "gatt_register_service", 0x0431a93a: "gatt_register_chara",
                0x043179c2: "adv_resume", 0x0431a6a8: "gatt_registration_failed", 0x0431a42e: "gatt_run_registration",
                0x04317164: "adv_enable", 0x0431a712: "gatt_notify", 0x04316df8: "adv_find_slot", 0x042efe44: "tlv_append"}
G.NATIVES.update(GATT_NATIVES)
GLOBALS = (0x02012200, 0x02012300)      # DAT_0201220a adv slots, 0x0201223c list head, 0x02012230/31 flags
SERVICE_LIST, PENDING, REGISTERING, ADV_SLOTS = 0x0201223c, 0x02012230, 0x02012231, 0x0201220a
CURSOR_CHARA, CURSOR_SERVICE = 0x02012228, 0x0201222c
LINK_FLAGS, FAKE_SLOT = 0x02012218, 0x020122c0      # status reports the BT link flags and the stock slot (0x38 bytes)


class BleMachine(SensorMachine):
    def __init__(self):
        super().__init__()
        try:
            self.uc.mem_map(GLOBALS[0] & ~4095, 4096)
        except G.u.UcError:
            pass
        self.uc.mem_write(GLOBALS[0], bytes(GLOBALS[1]-GLOBALS[0]))
        self.uc.mem_write(ADV_SLOTS, bytes([2]))
        slot = bytearray(0x38); slot[8] = 1; slot[9] = 1; slot[0xb] = 3; slot[0xd] = 1; slot[0x10:0x14] = (0x50).to_bytes(2, "little") + (0x90).to_bytes(2, "little")
        self.uc.mem_write(FAKE_SLOT, bytes(slot)); self.uc.mem_write(LINK_FLAGS, bytes([1, 0, 1, 0]))
        self.gatt_services, self.gatt_charas, self.gatt_calls, self.notifies = [], [], [], []
        self.fail_register = False
        self.fail_run = False
        self.slot_lookups = 0
        self.tlv_appends = []

    def response(self, value):
        # Real stock reply layout so the BLE serializer can walk it: node{next, hdr*}, hdr{kind 5, len24, data*}.
        node = self.request(json.dumps(value).encode(), kind=5)
        self.replies[node] = value
        return node

    def region(self, address, size, writing=False):
        if GLOBALS[0] <= address and address+size <= GLOBALS[1]:
            return "gatt-globals"
        return super().region(address, size, writing)

    def native(self, name, args):
        a0, a1, a2, a3 = args[:4]
        if name == "gatt_register_service":
            self.gatt_calls.append(name)
            desc = self.read(a0, 0x24)
            assert desc[4] == 1 and struct.unpack_from("<H", desc, 8)[0] == 0x9400
            assert struct.unpack_from("<II", desc, 0x18) == (0xf0000000, 0xffff)
            if self.fail_register: return 0
            node = self.allocate(0x24, "gatt-service", desc)
            head = self.word(SERVICE_LIST)
            if head == 0: self.native_write(SERVICE_LIST, struct.pack("<I", node))
            else:
                while self.word(head): head = self.word(head)
                self.native_write(head, struct.pack("<I", node))
            self.gatt_services.append(node); return node
        if name == "gatt_register_chara":
            self.gatt_calls.append(name)
            assert a0 in self.gatt_services
            desc = self.read(a1, 0x68)
            assert desc[4] == 1 and struct.unpack_from("<H", desc, 8)[0] == 0x9401
            assert struct.unpack_from("<I", desc, 0x18)[0] == 0xffffffff and desc[0x1e] == 0x1e
            read_cb, write_cb, cccd_cb = struct.unpack_from("<III", desc, 0x58)
            assert (read_cb, write_cb, cccd_cb) == tuple(self.symbols[s] for s in ("glassly_ble_on_read", "glassly_ble_on_write", "glassly_ble_on_cccd"))
            assert desc[0x24:0x58] == bytes(0x34), "spare descriptor bytes are zero at registration"
            node = self.allocate(0x68, "gatt-chara", desc)
            self.native_write(a0+0x20, struct.pack("<I", node))
            self.gatt_charas.append(node); return node
        if name == "adv_resume":
            self.gatt_calls.append(name); assert a0 == 0; return 0
        if name == "tlv_append":
            kind, length, data = a1, a2, self.read(a3, a2)
            node = self.request(bytes(data), kind=kind)
            head = self.word(a0)
            if head == 0: self.native_write(a0, struct.pack("<I", node))
            else:
                while self.word(head): head = self.word(head)
                self.native_write(head, struct.pack("<I", node))
            self.tlv_appends.append((kind, bytes(data))); return node
        if name == "adv_find_slot":
            self.slot_lookups += 1; assert a0 == 1, "status looks up the last stock slot"; return FAKE_SLOT
        if name == "gatt_registration_failed":
            self.gatt_calls.append(name); assert a0 == 1
            self.native_write(REGISTERING, b"\x00"); return 0
        if name == "gatt_run_registration":
            self.gatt_calls.append(name)
            # The stock kick: pending cleared, registering set, cursors on the new service.
            assert self.read(PENDING, 1) == b"\x00" and self.read(REGISTERING, 1) == b"\x01"
            assert self.word(CURSOR_CHARA) == 0 and self.word(CURSOR_SERVICE) == self.gatt_services[-1]
            if self.fail_run: return 0xb
            # Model the BT core replies landing synchronously: handles assigned, registering cleared.
            for node in self.gatt_services: self.native_write(node+0x1c, struct.pack("<H", 0x40))
            for node in self.gatt_charas: self.native_write(node+0x18, struct.pack("<HH", 0x42, 0x43))
            self.native_write(REGISTERING, b"\x00"); return 0
        if name == "adv_enable":
            self.gatt_calls.append(name); return 0 if a0 < 2 else 0xb
        if name == "gatt_notify":
            peer = self.read(a0, 6); assert a1 in self.gatt_charas
            self.notifies.append((peer, self.read(a2, a3 & 0xffff))); return 1
        return super().native(name, args)

    def probe(self, payload):
        return self.service(0x74, self.request(payload))[0]

    @staticmethod
    def state(reply):
        b = bytes.fromhex(reply["stateHex"])
        assert b[:3] == b"BP\x01"
        return {"service": b[3], "chara": b[4], "registering": b[5], "pending": b[6], "advSlots": b[7],
                "serviceHandle": struct.unpack_from("<H", b, 8)[0], "valueHandle": struct.unpack_from("<H", b, 10)[0],
                "cccdHandle": struct.unpack_from("<H", b, 12)[0], "props": b[18],
                "writes": struct.unpack_from("<I", b, 20)[0], "notified": struct.unpack_from("<I", b, 24)[0],
                "notifyFailed": struct.unpack_from("<I", b, 28)[0], "lastLen": struct.unpack_from("<H", b, 32)[0],
                "cccd": b[34], "peer": b[36:42], "last": b[42:60], "rc": struct.unpack_from("<I", b, 60)[0],
                "slot": b[64:120], "linkFlags": b[120:124]}


class BleProbeTests(unittest.TestCase):
    def test_register_arms_and_runs_the_state_machine_once(self):
        m = BleMachine()
        before = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((before["service"], before["chara"]), (0, 0))
        reply = m.probe(b"BP\x01\x01"); self.assertEqual(reply["result"], "ok")
        self.assertEqual(m.gatt_calls, ["gatt_register_service", "gatt_register_chara", "adv_resume", "gatt_run_registration"])
        after = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((after["service"], after["chara"], after["pending"], after["registering"]), (1, 1, 0, 0))
        self.assertEqual((after["serviceHandle"], after["valueHandle"], after["cccdHandle"], after["props"]), (0x40, 0x42, 0x43, 0x1e))
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "exists", "a second register is idempotent")
        self.assertEqual(len(m.gatt_calls), 4)

    def test_write_counts_and_echoes_when_notifications_are_enabled(self):
        m = BleMachine(); m.probe(b"BP\x01\x01")
        node = m.gatt_charas[0]; peer = m.allocate(6, "peer", bytes.fromhex("aabbccddeeff"), writable=False)
        data = m.allocate(5, "written", b"hello", writable=False)
        m.call("glassly_ble_on_write", peer, node+4, data, 5)
        state = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((state["writes"], state["lastLen"], state["cccd"], state["notified"]), (1, 5, 0, 0))
        self.assertEqual(state["peer"], bytes.fromhex("aabbccddeeff")); self.assertEqual(state["last"][:5], b"hello")
        self.assertEqual(m.notifies, [], "no echo before the client subscribes")
        m.call("glassly_ble_on_cccd", peer, node+4, 1)
        m.call("glassly_ble_on_write", peer, node+4, data, 5)
        state = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((state["writes"], state["cccd"], state["notified"], state["notifyFailed"]), (2, 1, 1, 0))
        self.assertEqual(m.notifies, [(bytes.fromhex("aabbccddeeff"), b"hello")])
        buf = m.allocate(4, "read-buffer")
        m.call("glassly_ble_on_read", peer, node+4, buf, 4)
        self.assertEqual(m.reg(10), 4, "the read callback returns four bytes")
        self.assertEqual(m.read(buf, 4), struct.pack("<I", 2))

    def test_notify_command_targets_the_last_peer_and_adv_enable_reports_refusals(self):
        m = BleMachine(); m.probe(b"BP\x01\x01")
        self.assertEqual(m.probe(b"BP\x01\x04ping")["result"], "no-peer")
        node = m.gatt_charas[0]; peer = m.allocate(6, "peer", bytes(6), writable=False)
        data = m.allocate(1, "written", b"x", writable=False)
        m.call("glassly_ble_on_write", peer, node+4, data, 1)
        reply = m.probe(b"BP\x01\x04ping"); self.assertEqual(reply["result"], "ok")
        self.assertEqual(m.notifies[-1], (bytes(6), b"ping"))
        self.assertEqual(m.probe(b"BP\x01\x02\x01")["result"], "ok")
        self.assertEqual(m.probe(b"BP\x01\x02\x07")["result"], "adv-refused")
        self.assertEqual(m.probe(b"BP\x01\x09")["result"], "invalid")
        self.assertEqual(m.probe(b"BP\x01\x02")["result"], "invalid", "adv enable needs a slot id")

    def test_refused_state_machine_is_reported_and_unwound(self):
        m = BleMachine(); m.fail_run = True
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "registration-refused")
        self.assertEqual(m.gatt_calls[-2:], ["gatt_run_registration", "gatt_registration_failed"])

    def test_spare_descriptor_bytes_stay_zero_until_the_handle_is_assigned(self):
        m = BleMachine(); m.fail_run = True
        m.probe(b"BP\x01\x01"); m.probe(b"BP\x01\x03")
        node = m.gatt_charas[0]
        self.assertEqual(m.read(node+0x24, 0x34), bytes(0x34), "no state marker while the handle is unassigned")
        peer = m.allocate(6, "peer", bytes(6), writable=False); data = m.allocate(1, "w", b"x", writable=False)
        m.call("glassly_ble_on_write", peer, node+4, data, 1)
        self.assertEqual(m.read(node+0x24, 0x34), bytes(0x34), "callbacks before registration change nothing")

    def test_registration_failure_is_reported_and_leaves_no_node(self):
        m = BleMachine(); m.fail_register = True
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "service-failed")
        self.assertEqual(m.gatt_calls, ["gatt_register_service"])
        self.assertEqual(m.state(m.probe(b"BP\x01\x03"))["service"], 0)

    def test_status_reports_the_stock_slot_and_link_flags_and_resume_restarts_advertising(self):
        m = BleMachine()
        s = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual(len(bytes.fromhex(m.probe(b"BP\x01\x03")["stateHex"])), 128)
        self.assertEqual((s["slot"][8], s["slot"][9], s["slot"][0xb], s["slot"][0xd]), (1, 1, 3, 1))
        self.assertEqual(struct.unpack_from("<HH", s["slot"], 0x10), (0x50, 0x90))
        self.assertEqual(s["linkFlags"], bytes([1, 0, 1, 0]))
        self.assertGreaterEqual(m.slot_lookups, 2)
        m.gatt_calls.clear()
        r = m.probe(b"BP\x01\x05")
        self.assertEqual(r["result"], "ok")
        self.assertEqual(m.gatt_calls[:1], ["adv_resume"])
        self.assertEqual(m.probe(b"BP\x01\x06")["result"], "invalid")

    def test_gm_frames_run_a_command_and_notify_the_reply(self):
        m = BleMachine(); m.probe(b"BP\x01\x01"); node = m.gatt_charas[-1]
        peer = m.allocate(6, "peer", bytes([1, 2, 3, 4, 5, 6]), writable=False)
        m.call("glassly_ble_on_cccd", peer, node+4, 1)
        frame = m.allocate(3, "frame", b"GM\x74", writable=False)
        m.call("glassly_ble_on_write", peer, node+4, frame, 3)
        self.assertEqual(m.tlv_appends, [], "a bare command carries no request node")
        self.assertEqual(len(m.notifies), 1)
        reply = json.loads(m.notifies[-1][1]); self.assertEqual(reply["result"], "invalid")
        self.assertEqual(m.notifies[-1][0], bytes([1, 2, 3, 4, 5, 6]))
        frame = m.allocate(5, "frame2", b"GM\x74BP", writable=False)   # probe status with a malformed request node
        m.call("glassly_ble_on_write", peer, node+4, frame, 5)
        self.assertEqual(m.tlv_appends, [(1, b"BP")])
        self.assertEqual(len(m.notifies), 2)
        self.assertEqual(json.loads(m.notifies[-1][1])["result"], "invalid")
        self.assertEqual(json.loads(m.notifies[-1][1])["result"], "invalid")
        s = m.state(m.probe(b"BP\x01\x03")); self.assertEqual((s["writes"], s["notified"], s["notifyFailed"]), (2, 2, 0))

    def test_fragments_assemble_into_one_command(self):
        m = BleMachine(); m.probe(b"BP\x01\x01"); node = m.gatt_charas[-1]
        peer = m.allocate(6, "peer", bytes([1, 2, 3, 4, 5, 6]), writable=False)
        m.call("glassly_ble_on_cccd", peer, node+4, 1)
        whole = b"GM\x74BP"
        first = m.allocate(7, "first", b"Gm\x01" + struct.pack("<H", len(whole)) + whole[:2], writable=False)
        m.call("glassly_ble_on_write", peer, node+4, first, 7)
        self.assertEqual(m.notifies, [], "nothing runs before the last fragment")
        last = m.allocate(6, "last", b"Gm\x02" + whole[2:], writable=False)
        m.call("glassly_ble_on_write", peer, node+4, last, 6)
        self.assertEqual(m.tlv_appends, [(1, b"BP")], "the assembled frame runs as one command")
        self.assertEqual(len(m.notifies), 1)
        self.assertEqual(json.loads(m.notifies[-1][1])["result"], "invalid")
        # A fragment without a first one is refused, and nothing leaks.
        stray = m.allocate(5, "stray", b"Gm\x02ab", writable=False)
        m.call("glassly_ble_on_write", peer, node+4, stray, 5)
        self.assertEqual(len(m.notifies), 1)

    def test_graphics_replies_to_ble_requests_go_back_over_ble(self):
        m = BleMachine(); m.probe(b"BP\x01\x01"); node = m.gatt_charas[-1]
        peer = m.allocate(6, "peer", bytes([1, 2, 3, 4, 5, 6]), writable=False)
        m.call("glassly_ble_on_cccd", peer, node+4, 1)
        frame = m.allocate(8, "frame", b"GM\x7d" + bytes([41, 0, 0, 0, 0])[:5], writable=False)
        before_sent, before_notifies = len(m.sent), len(m.notifies)
        m.call("glassly_ble_on_write", peer, node+4, frame, 8)
        self.assertTrue(m.queue, "the graphics command is queued for the display worker")
        job = m.queue.pop(0)
        self.assertEqual(job[1], 0, "BLE requests carry event 0")
        raw = bytes([0, 63, 0, 0]) + struct.pack("<HH", 0x474c, len(job)) + job
        envelope = m.allocate(len(raw), "envelope", raw, writable=False)
        m.call("glassly_graphics_display", envelope, display=True)
        self.assertEqual(len(m.sent), before_sent, "no reply on the Classic link")
        self.assertGreater(len(m.notifies), before_notifies, "the worker's reply is notified over BLE")
        self.assertEqual(m.notifies[-1][0], bytes([1, 2, 3, 4, 5, 6]))
        self.assertEqual(json.loads(m.notifies[-1][1])["glassly"], "graphics")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    G.BUILD = args.build.resolve()
    build = json.loads((G.BUILD/"build.json").read_text())
    G.PINNED_SHA = S.SCENE_SHA = build["blob_sha256"]
    assert build.get("ble_probe") is True, "Expected a --ble-probe build"
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(BleProbeTests))
    args.report.write_text(json.dumps({"passed": result.wasSuccessful(), "groups": result.testsRun, "runtimeSHA256": G.PINNED_SHA,
                                       "hardwareTested": False, "gattNativesMocked": True}, indent=2)+"\n")
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
