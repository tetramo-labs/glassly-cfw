import json
import socket
import threading
import unittest

from memomind_transport import BridgeError, RfcommBridge, GmStream, gm_frames, parse_tlvs, request_gm
from probe_memomind import probe


def tlv(kind, value):
    return bytes([kind]) + len(value).to_bytes(3, "big") + value


class GmCodecTests(unittest.TestCase):
    def test_native_ingress_size_is_asymmetric_and_matches_receiver_witness(self):
        body=tlv(1,bytes(5102))
        frames=gm_frames(37,15,125,body,fragment_payload=642)
        self.assertEqual([len(f) for f in frames],[651]*7+[621])
        self.assertEqual([f[0] for f in frames],[250,1,2,3,4,5,6,7])
        self.assertEqual(b''.join(f[7:-2] for f in frames),body)
        self.assertEqual(frames[0][:7],bytes.fromhex('fa0013fb250f7d'))
        # Reproduce the observed bug: the native651B receiver combines a512B
        # public frame with139B of the next frame and fails its checksum.
        wrong=b''.join(gm_frames(37,15,125,body))[:651]
        self.assertNotEqual(sum(wrong[:-2])&65535,int.from_bytes(wrong[-2:],'big'))
        with self.assertRaises(ValueError):gm_frames(1,1,1,fragment_payload=640)

    def test_numbered_empty_ack_is_explicit_and_does_not_consume_reply_state(self):
        raw=bytes.fromhex('01000009250f7d')
        ack=raw+(sum(raw)&65535).to_bytes(2,'big')
        with self.assertRaises(ValueError):GmStream().feed(ack)
        parser=GmStream(fragment_acks=True)
        packets=gm_frames(9,15,126,tlv(5,b'x'*600))
        self.assertEqual(parser.feed(packets[0]),[])
        self.assertEqual(parser.feed(ack)[0]['head'],1)
        self.assertEqual(parser.feed(packets[1])[0]['tlvs'],[(5,b'x'*600)])

    def test_public_heartbeat_vector(self):
        self.assertEqual(gm_frames(1, 1, 1), [bytes.fromhex("fa0000090101010106")])

    def test_fragmentation_crosses_tlv_header_and_value(self):
        body = tlv(2, b"x" * 496) + tlv(1, b"hello" * 100)
        packets = gm_frames(7, 1, 2, body)
        parser = GmStream()
        messages = []
        for byte in b"".join(packets):
            messages.extend(parser.feed(bytes([byte])))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["tlvs"], [(2, b"x" * 496), (1, b"hello" * 100)])
        self.assertEqual(packets[1][0], 1)

    def test_bad_checksum_clears_partial_state(self):
        packet = gm_frames(1, 1, 1, tlv(6, b"\0"))[0]
        parser = GmStream()
        with self.assertRaises(ValueError):
            parser.feed(packet[:-1] + bytes([packet[-1] ^ 1]))
        self.assertFalse(parser.buffer)
        self.assertIsNone(parser.key)
        self.assertEqual(parser.feed(packet)[0]["tlvs"], [(6, b"\0")])

    def test_missing_continuation_rejected(self):
        packets = gm_frames(1, 1, 2, tlv(2, b"x" * 600))
        with self.assertRaises(ValueError):
            GmStream().feed(packets[1])

    def test_unknown_tlv_preserved_and_truncation_rejected(self):
        self.assertEqual(parse_tlvs(tlv(0x99, b"abc")), [(0x99, b"abc")])
        with self.assertRaises(ValueError):
            parse_tlvs(tlv(2, b"abc")[:-1])

    def test_legacy_repeated_head_is_explicit(self):
        packets = gm_frames(1, 1, 2, tlv(2, b"x" * 600))
        body = b"\xfa" + packets[1][1:-2]
        packets[1] = body + (sum(body) & 0xffff).to_bytes(2, "big")
        parser = GmStream(legacy_repeat_fa=True)
        self.assertEqual(parser.feed(b"".join(packets))[0]["tlvs"], [(2, b"x" * 600)])

    def test_reset_discards_half_frame(self):
        packet = gm_frames(1, 1, 1, tlv(6, b"\0"))[0]
        parser = GmStream()
        parser.feed(packet[:8])
        parser.reset()
        self.assertEqual(len(parser.feed(packet)), 1)


class BridgeTransportTests(unittest.TestCase):
    def server(self, sock, fail=False):
        reader = sock.makefile("rb")
        def send(obj):
            sock.sendall((json.dumps(obj) + "\n").encode())
        try:
            send({"event": "ready", "protocol": 1})
            for raw in reader:
                request = json.loads(raw)
                if fail:
                    send({"id": request["id"], "ok": False, "error": "permission denied"})
                    break
                if request["op"] == "connect":
                    self.assertEqual(request["service"], "control")
                    send({"id": request["id"], "ok": True, "result": {"service": "control"}})
                elif request["op"] == "write":
                    data = bytes.fromhex(request["hex"])
                    self.assertEqual((data[5], data[6]), (1, data[4]))
                    self.assertIn(data[6], (1, 2))
                    if data[6] == 1:
                        reply = gm_frames(1, 1, 1, tlv(6, b"\0"))[0]
                    else:
                        # Large valid device info tests continuation over arbitrary reads.
                        value = json.dumps({"model": "H001Y", "ver": "1.0.3.127", "padding": "x" * 600}).encode()
                        reply = b"".join(gm_frames(2, 1, 2, tlv(2, value)))
                    # Data deliberately arrives before the local write acknowledgment.
                    for offset in range(0, len(reply), 17):
                        send({"event": "data", "hex": reply[offset:offset+17].hex()})
                    send({"id": request["id"], "ok": True, "result": {"written": len(data)}})
        finally:
            reader.close()
            sock.close()

    def test_readonly_probe_through_real_socket_pair(self):
        client, server = socket.socketpair()
        worker = threading.Thread(target=self.server, args=(server,), daemon=True)
        worker.start()
        with RfcommBridge(connected_socket=client) as bridge:
            result = probe(bridge, "4C:3C:8F:90:CC:C3")
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["device"]["ver"], "1.0.3.127")
        self.assertEqual(result["heartbeat_status"], 0)
        self.assertEqual(result["operations_sent"], ["heartbeat", "device_information"])


    def test_permission_failure_propagated(self):
        client, server = socket.socketpair()
        worker = threading.Thread(target=self.server, args=(server, True), daemon=True)
        worker.start()
        with RfcommBridge(connected_socket=client) as bridge:
            with self.assertRaisesRegex(BridgeError, "permission denied"):
                bridge.connect("4C:3C:8F:90:CC:C3")
        worker.join(2)

    def test_socket_loss_fails_pending_request(self):
        client, server = socket.socketpair()
        server.sendall(b'{"event":"ready","protocol":1}\n')
        bridge = RfcommBridge(connected_socket=client)
        server.close()
        with self.assertRaises((BridgeError, BrokenPipeError)):
            bridge.request("status")
        bridge.close()


class NativeRequestTests(unittest.TestCase):
    class Receiver:
        """Native-derived642B receiver contract, independent of reply parser."""
        def __init__(self,reject_after=None,wrong_ack=False):
            self.writes=[];self.pending=None;self.body=bytearray();self.reject_after=reject_after;self.wrong_ack=wrong_ack
        def write(self,frame):
            assert self.pending is None,'Sender failed to wait for fragment acknowledgment'
            n=len(self.writes);self.writes.append(frame)
            total=int.from_bytes(frame[1:4],'big')-9
            assert len(frame)==min(total-len(self.body),642)+9
            assert sum(frame[:-2])&65535==int.from_bytes(frame[-2:],'big')
            assert frame[0]==(250 if n==0 else n)
            self.body.extend(frame[7:-2])
            if self.reject_after==n:
                self.pending=gm_frames(37,15,125,tlv(6,b'\x08'))[0]
            elif len(self.body)==total:
                self.pending=gm_frames(37,15,125,tlv(5,b'{"result":"ok"}'))[0]
            else:
                h=2 if self.wrong_ack else frame[0]
                raw=bytes((h,0,0,9,37,15,125));self.pending=raw+(sum(raw)&65535).to_bytes(2,'big')
        def read(self,timeout):
            assert self.pending is not None
            p=self.pending;self.pending=None;return p

    def test_maximum_request_waits_for_each_ack_and_preserves_body(self):
        r=self.Receiver();body=tlv(1,bytes(5102))
        reply=request_gm(r,GmStream(fragment_acks=True),37,15,125,body)
        self.assertEqual(len(r.writes),8);self.assertEqual(r.body,body)
        self.assertEqual(reply['tlvs'],[(5,b'{"result":"ok"}')])

    def test_native_rejection_stops_before_remaining_fragments(self):
        r=self.Receiver(reject_after=1)
        reply=request_gm(r,GmStream(fragment_acks=True),37,15,125,tlv(1,bytes(5102)))
        self.assertEqual(reply['tlvs'],[(6,b'\x08')]);self.assertEqual(len(r.writes),2)

    def test_wrong_ack_stops_without_retry(self):
        r=self.Receiver(wrong_ack=True)
        with self.assertRaises(BridgeError):request_gm(r,GmStream(fragment_acks=True),37,15,125,tlv(1,bytes(5102)))
        self.assertEqual(len(r.writes),1)



if __name__ == "__main__":
    unittest.main()
