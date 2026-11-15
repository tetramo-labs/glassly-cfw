#!/usr/bin/env python3
"""Glassly BLE link on the pinned RV32 runtime: service 0x9400 with the GM
characteristic 0x9401 and the OTA characteristic 0x9402, the bonded-peer
acceptance window, GM ingress posted to the BT app task, the GM writer gate,
the OTA transport send, and the advertising stop gate. Stock natives are mocked."""
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
                0x04317164: "adv_enable", 0x0431a712: "gatt_notify", 0x04316df8: "adv_find_slot",
                0x04319adc: "gatt_add_listener", 0x042d52bc: "adv_start", 0x042d556a: "adv_stop",
                0x042361b8: "bt_post", 0x0423cc32: "ota_rx", 0x042388e0: "ota_drop", 0x0424eef2: "known_ring",
                0x042db00e: "gm_writer_stock", 0x043199d2: "bt_send", 0x042133e2: "is_phone",
                0x04212eec: "is_bonded_addr"}
G.NATIVES.update(GATT_NATIVES)
GLOBALS = (0x02011f00, 0x02012300)
SERVICE_LIST, PENDING, REGISTERING, ADV_SLOTS = 0x0201223c, 0x02012230, 0x02012231, 0x0201220a
CURSOR_CHARA, CURSOR_SERVICE = 0x02012228, 0x0201222c
LINK_FLAGS, FAKE_SLOT = 0x02012218, 0x020122c0
GM_BLE_LINK, GM_PHONE, ADVERTISING, LE_CONNECTED = 0x02012077, 0x02012088, 0x02011ffc, 0x02012004
PEER = bytes.fromhex("a1b2c3d4e5f6")
OTHER = bytes.fromhex("010203040506")
REVISION = 0


class BleMachine(SensorMachine):
    def __init__(self):
        super().__init__()
        for page in (0x02011000, 0x02012000):
            try:
                self.uc.mem_map(page, 4096)
            except G.u.UcError:
                pass
        self.uc.mem_write(GLOBALS[0], bytes(GLOBALS[1]-GLOBALS[0]))
        self.uc.mem_write(ADV_SLOTS, bytes([2]))
        slot = bytearray(0x38); slot[8] = 1; slot[9] = 1; slot[0xb] = 3; slot[0xd] = 1
        slot[0x10:0x14] = (0x50).to_bytes(2, "little") + (0x90).to_bytes(2, "little")
        self.uc.mem_write(FAKE_SLOT, bytes(slot)); self.uc.mem_write(LINK_FLAGS, bytes([1, 0, 1, 0]))
        self.gatt_services, self.gatt_charas, self.gatt_calls, self.notifies = [], [], [], []
        self.listeners, self.posts, self.ota_frames, self.ota_drops, self.stock_writes = [], [], [], [], []
        self.fail_register = self.fail_run = self.fail_notify = False
        self.rings = set()
        self.bt_sends, self.phones, self.bonded_addr, self.bt_send_rc = [], set(), None, 0

    def region(self, address, size, writing=False):
        if GLOBALS[0] <= address and address+size <= GLOBALS[1]:
            return "gatt-globals"
        return super().region(address, size, writing)

    def chara(self, uuid):
        return next(c for c in self.gatt_charas if struct.unpack_from("<H", self.read(c, 0x68), 8)[0] == uuid)

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
            assert desc[4] == 1 and struct.unpack_from("<H", desc, 8)[0] in (0x9401, 0x9402)
            assert struct.unpack_from("<I", desc, 0x18)[0] == 0xffffffff and desc[0x1e] == 0x1e and desc[0x1f] == 0
            callbacks = struct.unpack_from("<III", desc, 0x58)
            assert callbacks == tuple(self.symbols[s] for s in ("glassly_ble_on_read", "glassly_ble_on_write", "glassly_ble_on_cccd"))
            assert desc[0x24:0x58] == bytes(0x34), "spare descriptor bytes are zero at registration"
            node = self.allocate(0x68, "gatt-chara", desc)
            head = self.word(a0+0x20)
            if head == 0: self.native_write(a0+0x20, struct.pack("<I", node))
            else:
                while self.word(head): head = self.word(head)
                self.native_write(head, struct.pack("<I", node))
            self.gatt_charas.append(node); return node
        if name == "adv_resume":
            self.gatt_calls.append(name); assert a0 == 0; return 0
        if name == "adv_find_slot":
            assert a0 == 1; return FAKE_SLOT
        if name == "gatt_registration_failed":
            self.gatt_calls.append(name); assert a0 == 1
            self.native_write(REGISTERING, b"\x00"); return 0
        if name == "gatt_run_registration":
            self.gatt_calls.append(name)
            assert self.read(PENDING, 1) == b"\x00" and self.read(REGISTERING, 1) == b"\x01"
            assert self.word(CURSOR_CHARA) == 0 and self.word(CURSOR_SERVICE) == self.gatt_services[-1]
            if self.fail_run: return 0xb
            self.assign_handles()
            self.native_write(REGISTERING, b"\x00"); return 0
        if name == "adv_enable":
            self.gatt_calls.append(name); return 0 if a0 < 2 else 0xb
        if name == "gatt_notify":
            peer = self.read(a0, 6); assert a1 in self.gatt_charas
            if self.fail_notify: return 0
            self.notifies.append((peer, a1, self.read(a2, a3 & 0xffff))); return 1
        if name == "gatt_add_listener":
            self.gatt_calls.append(name)
            if a0 not in self.listeners: self.listeners.append(a0)
            return 0
        if name in ("adv_start", "adv_stop"):
            self.gatt_calls.append(name); return 0
        if name == "bt_post":
            self.posts.append((a0, a1, self.read(a2, a3))); return 0
        if name == "ota_rx":
            self.ota_frames.append((a0, self.read(a1, a2))); return 0
        if name == "ota_drop":
            self.ota_drops.append(a0); return 0
        if name == "known_ring":
            return 1 if self.read(a0, 6) in self.rings else 0
        if name == "bt_send":
            self.bt_sends.append((a0, self.read(a1, a2))); return self.bt_send_rc
        if name == "is_phone":
            return 1 if self.read(a0, 6) in self.phones else 0
        if name == "is_bonded_addr":
            return 1 if self.bonded_addr is not None and self.read(a0, 6) == self.bonded_addr else 0
        if name == "gm_writer_stock":
            sp = self.reg(2)
            assert self.word(sp+0x38) == self.reg(8) and self.word(sp+0x30) == self.reg(18) and self.word(sp+0x28) == self.reg(20)
            self.stock_writes.append(self.read(a0, a1))
            self.set(2, sp+0x40)
            return 1
        return super().native(name, args)

    def assign_handles(self):
        for node in self.gatt_services: self.native_write(node+0x1c, struct.pack("<H", 0x40))
        for i, node in enumerate(self.gatt_charas): self.native_write(node+0x18, struct.pack("<HH", 0x42+3*i, 0x43+3*i))

    def probe(self, payload):
        return self.service(0x74, self.request(payload))[0]

    def status(self):
        b = bytes.fromhex(self.probe(b"BP\x01\x03")["stateHex"])
        assert b[:3] == b"BP\x02" and len(b) == 136
        u16 = lambda o: struct.unpack_from("<H", b, o)[0]
        u32 = lambda o: struct.unpack_from("<I", b, o)[0]
        return {"service": b[3], "gm": b[4], "ota": b[19], "serviceHandle": u16(8), "gmValue": u16(10), "gmCccd": u16(12),
                "otaValue": u16(14), "otaCccd": u16(16), "gmWrites": u32(20), "gmNotified": u32(24), "gmFailed": u32(28),
                "notifyMax": u16(32), "gmCccdOn": b[34], "link": b[35], "peer": b[36:42], "otaWrites": u32(42),
                "otaNotified": u32(46), "otaCccdOn": b[54], "bleLink": b[55], "age": u32(56), "rejected": u16(60),
                "rc": u16(62), "slot": b[64:120], "linkFlags": b[120:124], "advertising": b[124], "leConnected": b[125],
                "peerType": b[126], "peerKind": b[127], "bonded": b[128], "paramRc": b[129], "securityRc": b[130],
                "requests": b[131]}

    def bytes_at(self, data, tag="data"):
        return self.allocate(len(data), tag, data, writable=False)

    def registered(self):
        assert self.probe(b"BP\x01\x01")["result"] == "ok"
        return self.chara(0x9401), self.chara(0x9402)

    def link(self, peer=PEER, connected=1, peripheral=1):
        self.call("glassly_ble_on_link", self.bytes_at(peer + bytes([1, 2]), "conn"), peripheral, connected)

    @staticmethod
    def control_reply(op, status, bonded=False, requested=True, rc=0, detail=0):
        flags = (1 if bonded else 0) | (2 if requested else 0) | (4 if rc == 0 else 0)
        return bytes([0x80, op, status, REVISION, flags, detail])

    @staticmethod
    def conn_request(peer=PEER, params=(12, 24, 0, 400)):
        return (0x27a, peer + struct.pack("<6H", *params, 0, 0))

    def write(self, node, data, peer=PEER):
        self.call("glassly_ble_on_write", self.bytes_at(peer, "peer"), node+4, self.bytes_at(data), len(data))

    def cccd(self, node, enabled=1, peer=PEER):
        self.call("glassly_ble_on_cccd", self.bytes_at(peer, "peer"), node+4, enabled)

    def hello(self, node, limit=180, peer=PEER):
        self.write(node, bytes([0x80, 1]) + struct.pack("<H", limit), peer)

    def accepted(self):
        gm, ota = self.registered()
        self.now = 1000; self.link(); self.cccd(gm); self.now = 11000; self.hello(gm)
        assert self.notifies[-1][2] == self.control_reply(1, 0)
        self.notifies.clear()
        return gm, ota

    @staticmethod
    def fragments(frame, size):
        out, offset = [], 0
        while offset < len(frame) or not out:
            first = offset == 0
            room = size - (3 if first else 1)
            piece = frame[offset:offset+room]; offset += len(piece)
            flags = (1 if first else 0) | (2 if offset >= len(frame) else 0)
            out.append(bytes([flags]) + (struct.pack("<H", len(frame)) if first else b"") + piece)
        return out


class BleLinkTests(unittest.TestCase):
    def test_register_adds_both_characteristics_and_the_listener_once(self):
        m = BleMachine()
        before = m.status()
        self.assertEqual((before["service"], before["gm"], before["ota"]), (0, 0, 0))
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "ok")
        self.assertEqual(m.gatt_calls, ["gatt_register_service", "gatt_register_chara", "gatt_register_chara",
                                        "adv_resume", "gatt_run_registration", "gatt_add_listener"])
        self.assertEqual(m.listeners, [m.symbols["glassly_ble_on_link"]])
        s = m.status()
        self.assertEqual((s["service"], s["gm"], s["ota"]), (1, 1, 1))
        self.assertEqual((s["serviceHandle"], s["gmValue"], s["gmCccd"], s["otaValue"], s["otaCccd"]), (0x40, 0x42, 0x43, 0x45, 0x46))
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "exists")
        self.assertEqual(m.gatt_calls.count("gatt_run_registration"), 1)

    def test_boot_registration_appends_nodes_without_its_own_kick(self):
        m = BleMachine()
        m.call("glassly_ble_boot_register")
        self.assertEqual(m.gatt_calls, ["gatt_register_service", "gatt_register_chara", "gatt_register_chara", "gatt_add_listener"])
        m.assign_handles()
        s = m.status(); self.assertEqual((s["gm"], s["ota"], s["gmValue"]), (1, 1, 0x42))

    def test_the_bonded_window_gates_acceptance(self):
        m = BleMachine(); gm, _ = m.registered()
        m.now = 1000; m.link(); m.cccd(gm)
        self.assertEqual(m.bt_sends, [m.conn_request()], "a faster connection interval is asked for as the link comes up")
        m.now = 5000; m.hello(gm, 244)
        self.assertEqual(m.notifies[-1], (PEER, gm, m.control_reply(1, 1)), "too early: wait")
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x00")
        m.write(gm, bytes([3]) + struct.pack("<H", 4) + b"\xfa\x00\x00\x09")
        self.assertEqual(m.posts, [], "GM traffic before acceptance is dropped")
        self.assertEqual(m.status()["rejected"], 1)
        m.now = 11000; m.hello(gm, 244)
        self.assertEqual(m.notifies[-1], (PEER, gm, m.control_reply(1, 0)))
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x01")
        self.assertEqual(m.read(GM_PHONE, 6), PEER)
        s = m.status(); self.assertEqual((s["link"], s["notifyMax"], s["peer"], s["bleLink"]), (2, 244, PEER, 1))
        self.assertEqual(s["age"], 10000)
        self.assertEqual((s["peerType"], s["peerKind"], s["bonded"], s["paramRc"], s["securityRc"], s["requests"]), (1, 2, 0, 0, 0xff, 1))

    def test_the_bonded_phone_is_accepted_at_the_first_hello(self):
        for bond in ("phone", "address"):
            m = BleMachine(); gm, _ = m.registered()
            if bond == "phone": m.phones.add(PEER)
            else: m.bonded_addr = PEER
            m.now = 1000; m.link(); m.cccd(gm); m.now = 1600; m.hello(gm, 244)
            self.assertEqual(m.notifies[-1], (PEER, gm, m.control_reply(1, 0, bonded=True)), bond)
            self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x01")
            self.assertEqual(m.status()["bonded"], 1)
        m = BleMachine(); gm, _ = m.registered(); m.phones.add(OTHER)
        m.now = 1000; m.link(); m.cccd(gm); m.now = 1600; m.hello(gm, 244)
        self.assertEqual(m.notifies[-1][2], m.control_reply(1, 1), "another phone's bond does not count")

    def test_refused_connection_update_is_reported_in_the_hello(self):
        m = BleMachine(); gm, _ = m.registered(); m.bt_send_rc = 0xb
        m.now = 1000; m.link(); m.cccd(gm); m.now = 11000; m.hello(gm, 244)
        self.assertEqual(m.notifies[-1][2], m.control_reply(1, 0, rc=0xb, detail=0xb))
        self.assertEqual(m.status()["paramRc"], 0xb)

    def test_control_ops_request_parameters_and_security(self):
        m = BleMachine(); gm, _ = m.registered()
        m.now = 1000; m.link(); m.cccd(gm); m.bt_sends.clear()
        m.write(gm, bytes([0x80, 2]) + struct.pack("<4H", 12, 12, 0, 400))
        self.assertEqual((m.bt_sends, m.notifies[-1][2]), ([], m.control_reply(2, 1, detail=0xff)), "not before acceptance")
        m.now = 11000; m.hello(gm); m.notifies.clear()
        m.write(gm, bytes([0x80, 2]) + struct.pack("<4H", 12, 12, 0, 400))
        self.assertEqual(m.bt_sends, [m.conn_request(params=(12, 12, 0, 400))])
        self.assertEqual(m.notifies[-1][2], m.control_reply(2, 0))
        m.write(gm, bytes([0x80, 2, 12, 0, 12]))
        self.assertEqual(len(m.notifies), 1, "a short parameter request gets no reply")
        m.write(gm, bytes([0x80, 3]))
        self.assertEqual(m.bt_sends[-1], (0x2bc, PEER + bytes([1, 2])))
        self.assertEqual(m.notifies[-1][2], m.control_reply(3, 0))
        m.bt_send_rc = 0xb; m.write(gm, bytes([0x80, 3]))
        self.assertEqual(m.notifies[-1][2], m.control_reply(3, 2, detail=0xb))
        s = m.status(); self.assertEqual((s["requests"], s["paramRc"], s["securityRc"]), (2, 0, 0xb))
        m.write(gm, bytes([0x80, 9]))
        self.assertEqual(m.notifies[-1][2], m.control_reply(3, 2, detail=0xb), "unknown control ops are ignored")

    def test_other_peers_and_rings_are_ignored(self):
        m = BleMachine(); gm, _ = m.registered()
        m.rings.add(OTHER); m.now = 0; m.link(OTHER)
        self.assertEqual(m.status()["link"], 0, "a ring connection is not a phone link")
        m.link(); m.cccd(gm); m.now = 20000
        m.hello(gm, peer=OTHER)
        self.assertEqual(m.notifies, [])
        m.link(peripheral=0)
        self.assertEqual(m.status()["link"], 1, "central-role links are not tracked")
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x00")

    def test_hello_clamps_the_notify_size(self):
        m = BleMachine(); gm, _ = m.registered()
        m.now = 0; m.link(); m.cccd(gm); m.now = 10000
        m.hello(gm, 5); self.assertEqual(m.status()["notifyMax"], 20)
        m.hello(gm, 4000); self.assertEqual(m.status()["notifyMax"], 512)

    def test_gm_fragments_post_one_packet_to_the_bt_app_task(self):
        m = BleMachine(); gm, _ = m.accepted()
        packet = bytes([0xfa, 0, 0, 0x30, 7, 1, 0x1c]) + bytes(range(39)) + b"\x12\x34"
        parts = m.fragments(packet, 20)
        self.assertGreater(len(parts), 2)
        for part in parts[:-1]:
            m.write(gm, part); self.assertEqual(m.posts, [])
        m.write(gm, parts[-1])
        self.assertEqual(m.posts, [(0xd, 0x3a, packet)])
        m.write(gm, bytes([3]) + struct.pack("<H", 3) + b"abc")
        self.assertEqual(m.posts[-1], (0xd, 0x3a, b"abc"))
        m.write(gm, bytes([2]) + b"stray")
        m.write(gm, bytes([1]) + struct.pack("<H", 3) + b"abcd")
        self.assertEqual(len(m.posts), 2, "strays and overlong fragments are dropped")
        self.assertTrue(all(not a["live"] or a["tag"] != "owned" for a in m.allocations.values()), "no fragment buffer leaks")

    def test_gm_writer_gate_notifies_in_hello_sized_chunks(self):
        m = BleMachine(); gm, _ = m.accepted()
        frame = bytes(range(250)) + bytes(200)
        self.assertEqual(m.call("glassly_gm_write", m.bytes_at(frame), len(frame)) and m.reg(10), 1)
        self.assertEqual([len(n[2]) for n in m.notifies], [180, 180, 90])
        self.assertEqual(b"".join(n[2] for n in m.notifies), frame)
        self.assertTrue(all(n[0] == PEER and n[1] == gm for n in m.notifies))
        m.fail_notify = True
        m.call("glassly_gm_write", m.bytes_at(b"x"), 1); self.assertEqual(m.reg(10), 2)

    def test_gm_writer_entry_falls_through_to_stock_without_a_link(self):
        m = BleMachine(); m.registered()
        m.call("glassly_gm_write_entry", m.bytes_at(b"classic"), 7)
        self.assertEqual(m.reg(10), 1)
        self.assertEqual(m.stock_writes, [b"classic"], "stock writer continues with the original arguments")
        self.assertEqual(m.notifies, [])

    def test_gm_writer_entry_returns_the_ble_result(self):
        m = BleMachine(); m.accepted()
        m.call("glassly_gm_write_entry", m.bytes_at(b"reply"), 5)
        self.assertEqual((m.reg(10), m.stock_writes, m.notifies[-1][2]), (1, [], b"reply"))
        m.fail_notify = True
        m.call("glassly_gm_write_entry", m.bytes_at(b"reply"), 5)
        self.assertEqual((m.reg(10), m.stock_writes), (0, []))

    def test_cccd_off_hands_the_writer_back_to_stock(self):
        m = BleMachine(); gm, _ = m.accepted()
        m.cccd(gm, 0)
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x00")
        m.call("glassly_gm_write_entry", m.bytes_at(b"c"), 1)
        self.assertEqual(m.stock_writes, [b"c"])

    def test_ota_frames_and_replies_use_the_ota_characteristic(self):
        m = BleMachine(); gm, ota = m.accepted()
        frame = bytes([0x70, 7, 0xe5]) + bytes(range(200)) + b"\x33"
        for part in m.fragments(frame, 180): m.write(ota, part)
        self.assertEqual(m.ota_frames, [(0, frame)])
        m.call("glassly_ota_ble_send", 0, m.bytes_at(b"\x70\x07\x6e"), 3)
        self.assertEqual(m.reg(10), 1, "no OTA reply before the OTA characteristic is subscribed")
        m.cccd(ota)
        m.call("glassly_ota_ble_send", 0, m.bytes_at(b"\x70\x07\x6e\x33"), 4)
        self.assertEqual(m.reg(10), 0)
        self.assertEqual(m.notifies[-1], (PEER, ota, b"\x70\x07\x6e\x33"))
        s = m.status(); self.assertEqual((s["otaCccdOn"], s["otaNotified"]), (1, 1))

    def test_ota_before_acceptance_is_refused(self):
        m = BleMachine(); _, ota = m.registered()
        m.now = 0; m.link(); m.cccd(ota)
        m.write(ota, bytes([3]) + struct.pack("<H", 2) + b"\x70\x33")
        self.assertEqual(m.ota_frames, [])
        m.call("glassly_ota_ble_send", 0, m.bytes_at(b"x"), 1); self.assertEqual(m.reg(10), 1)

    def test_disconnect_releases_the_link_aborts_ota_and_readvertises(self):
        m = BleMachine(); gm, ota = m.accepted()
        m.write(ota, bytes([3]) + struct.pack("<H", 2) + b"\x70\x33")
        m.write(gm, bytes([1]) + struct.pack("<H", 10) + b"half")
        m.gatt_calls.clear(); m.link(OTHER, connected=0)
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x01", "another peer's disconnect changes nothing")
        m.link(connected=0)
        self.assertEqual(m.read(GM_BLE_LINK, 1), b"\x00")
        self.assertEqual(m.ota_drops, [0])
        self.assertEqual(m.gatt_calls, ["adv_start"])
        s = m.status(); self.assertEqual((s["link"], s["gmCccdOn"], s["otaCccdOn"]), (0, 0, 0))
        self.assertTrue(all(not a["live"] or a["tag"] != "owned" for a in m.allocations.values()), "partial frame freed")
        m.link(connected=0); self.assertEqual(m.ota_drops, [0], "OTA abort only once")

    def test_reconnect_without_ota_does_not_touch_the_ota_session(self):
        m = BleMachine(); m.accepted()
        m.link(connected=0)
        self.assertEqual(m.ota_drops, [])

    def test_advertising_stop_is_skipped_while_the_service_exists(self):
        m = BleMachine()
        m.call("glassly_adv_stop"); self.assertEqual(m.gatt_calls, ["adv_stop"])
        m.registered(); m.gatt_calls.clear()
        m.call("glassly_adv_stop"); self.assertEqual(m.gatt_calls, [])

    def test_probe_ops_and_status_fields(self):
        m = BleMachine(); m.registered()
        self.assertEqual(m.probe(b"BP\x01\x02\x01")["result"], "ok")
        self.assertEqual(m.probe(b"BP\x01\x02\x07")["result"], "adv-refused")
        self.assertEqual(m.probe(b"BP\x01\x04")["result"], "invalid")
        self.assertEqual(m.probe(b"BP\x01\x09")["result"], "invalid")
        m.gatt_calls.clear()
        self.assertEqual(m.probe(b"BP\x01\x05")["result"], "ok"); self.assertEqual(m.gatt_calls, ["adv_resume"])
        self.assertEqual(m.probe(b"BP\x01\x06")["result"], "ok"); self.assertEqual(m.gatt_calls[-1], "adv_start")
        m.native_write(ADVERTISING, b"\x01"); m.native_write(LE_CONNECTED, b"\x01")
        s = m.status()
        self.assertEqual((s["advertising"], s["leConnected"], s["linkFlags"]), (1, 1, bytes([1, 0, 1, 0])))
        self.assertEqual((s["slot"][8], s["slot"][9]), (1, 1))

    def test_refused_registration_is_reported_and_unwound(self):
        m = BleMachine(); m.fail_run = True
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "registration-refused")
        self.assertIn("gatt_registration_failed", m.gatt_calls)
        node = m.chara(0x9401)
        self.assertEqual(m.read(node+0x24, 0x34), bytes(0x34))
        m.write(node, b"\x80\x01\x14\x00")
        self.assertEqual(m.read(node+0x24, 0x34), bytes(0x34), "callbacks before handles exist change nothing")

    def test_service_failure_leaves_no_node(self):
        m = BleMachine(); m.fail_register = True
        self.assertEqual(m.probe(b"BP\x01\x01")["result"], "service-failed")
        self.assertEqual(m.status()["service"], 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    G.BUILD = args.build.resolve()
    build = json.loads((G.BUILD/"build.json").read_text())
    G.PINNED_SHA = S.SCENE_SHA = build["blob_sha256"]
    assert build.get("ble_probe") is True, "Expected a --ble-probe build"
    global REVISION
    REVISION = build["cfw_revision"] & 0xff
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(BleLinkTests))
    args.report.write_text(json.dumps({"passed": result.wasSuccessful(), "groups": result.testsRun, "runtimeSHA256": G.PINNED_SHA,
                                       "hardwareTested": False, "gattNativesMocked": True}, indent=2)+"\n")
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
