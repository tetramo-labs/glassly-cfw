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
                0x0431b504: "gatt_arm_pending", 0x0431a42e: "gatt_run_registration",
                0x04317164: "adv_enable", 0x0431a712: "gatt_notify"}
G.NATIVES.update(GATT_NATIVES)
GLOBALS = (0x02012200, 0x02012300)      # DAT_0201220a adv slots, 0x0201223c list head, 0x02012230/31 flags
SERVICE_LIST, PENDING, REGISTERING, ADV_SLOTS = 0x0201223c, 0x02012230, 0x02012231, 0x0201220a


class BleMachine(SensorMachine):
    def __init__(self):
        super().__init__()
        try:
            self.uc.mem_map(GLOBALS[0] & ~4095, 4096)
        except G.u.UcError:
            pass
        self.uc.mem_write(GLOBALS[0], bytes(GLOBALS[1]-GLOBALS[0]))
        self.uc.mem_write(ADV_SLOTS, bytes([2]))
        self.gatt_services, self.gatt_charas, self.gatt_calls, self.notifies = [], [], [], []
        self.fail_register = False

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
        if name == "gatt_arm_pending":
            self.gatt_calls.append(name); assert a0 == 1
            self.native_write(PENDING, b"\x01"); self.native_write(REGISTERING, b"\x00"); return 0
        if name == "gatt_run_registration":
            self.gatt_calls.append(name)
            assert self.read(PENDING, 1) == b"\x01", "registration runs only when armed"
            for node in self.gatt_services: self.native_write(node+0x1c, struct.pack("<H", 0x40))
            for node in self.gatt_charas: self.native_write(node+0x18, struct.pack("<HH", 0x42, 0x43))
            self.native_write(PENDING, b"\x00"); return 0
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
                "cccd": b[34], "peer": b[36:42], "last": b[42:60], "rc": struct.unpack_from("<I", b, 60)[0]}


class BleProbeTests(unittest.TestCase):
    def test_register_arms_and_runs_the_state_machine_once(self):
        m = BleMachine()
        before = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((before["service"], before["chara"]), (0, 0))
        reply = m.probe(b"BP\x01\x01"); self.assertEqual(reply["result"], "ok")
        self.assertEqual(m.gatt_calls, ["gatt_register_service", "gatt_register_chara", "gatt_arm_pending", "gatt_run_registration"])
        after = m.state(m.probe(b"BP\x01\x03"))
        self.assertEqual((after["service"], after["chara"], after["pending"]), (1, 1, 0))
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

    def test_registration_failure_is_reported_and_leaves_no_node(self):
        m = BleMachine(); m.fail_register = True
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "service-failed")
        self.assertEqual(m.gatt_calls, ["gatt_register_service"])
        self.assertEqual(m.state(m.probe(b"BP\x01\x03"))["service"], 0)


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
