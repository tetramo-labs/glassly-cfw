#!/usr/bin/env python3
"""Recorded successful stock transcript plus targeted failure injection."""
import copy
from pathlib import Path
import unittest
from memomind_flasher import (STOCK_SHA256, ROOT, TransactionError, StockTransaction,
                              ReplayTransport, read_transcript, replay, load_image)

TRANSCRIPT = ROOT / 'analysis/protocol/ota-final/rfcomm.tsv'
IMAGE = ROOT / 'captures/firmware/ota-1.0.3.127-jhv3_release.bin'


class RecordedTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, _ = load_image(IMAGE, STOCK_SHA256)
        cls.rows, cls.device = read_transcript(TRANSCRIPT)

    def driver(self, rows=None, device=None, transport_type=ReplayTransport):
        transport = transport_type(copy.deepcopy(self.rows if rows is None else rows))
        driver = StockTransaction(transport, self.image, device or self.device,
                                  self.device['mac'], pace=0)
        return driver, transport

    def mutated(self, command, index, value):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row['channel'] == 6 and row['direction'] == 1 and row['data'][4] == command:
                raw = bytearray(row['data'])
                raw[index] = value
                row['data'] = bytes(raw)
                return rows
        self.fail('Recorded response missing')

    def assert_no_entry_or_data(self, transport):
        sent = [r['data'][4] for r in transport.rows[:transport.position]
                if r['direction'] == 0 and r['channel'] == 6]
        self.assertEqual(sent, [2, 0xe1, 0xe2])

    def test_complete_raw_recorded_replay(self):
        result = replay(TRANSCRIPT, self.image)
        self.assertEqual(result['outgoing_packets_identical'], 3464)
        self.assertEqual(result['incoming_packets_consumed'], 501)
        self.assertEqual(result['records_consumed'], result['records_total'])
        self.assertEqual((result['blocks'], result['chunks']), (494, 3457))
        self.assertEqual(result['transferred_range'], [162757, len(self.image)])
        self.assertEqual(result['outgoing_wire_sha256'],
                         'f4acaa5ca1a8a02001328eebc88c52be4ab65216cf8f42c70e09e77dda294004')
        self.assertFalse(result['post_reboot_version_verified'])

    def test_check_only_stops_before_entry(self):
        driver, transport = self.driver()
        result = driver.run(check_only=True)
        self.assertEqual(result['chunks'], 0)
        self.assertEqual(transport.position, 8)
        self.assert_no_entry_or_data(transport)

    def test_unsupported_can_update_result_stops_before_entry(self):
        driver, transport = self.driver(self.mutated(0xe2, 9, 2))
        with self.assertRaisesRegex(TransactionError, 'can-update result 3'):
            driver.run()
        self.assert_no_entry_or_data(transport)

    def test_wrong_image_and_identity_fail_before_commands(self):
        with self.assertRaisesRegex(TransactionError, 'expected SHA'):
            load_image(IMAGE, '0' * 64)
        bad_image = bytearray(self.image)
        bad_image[-1] ^= 1
        transport = ReplayTransport(self.rows)
        with self.assertRaisesRegex(TransactionError, 'Unsupported image'):
            StockTransaction(transport, bad_image, self.device, self.device['mac'])
        for key, value in [('model', 'G2'), ('hver', '99'), ('ver', '1.0.4.0'), ('mac', '00')]:
            with self.subTest(key=key), self.assertRaises(TransactionError):
                StockTransaction(transport, self.image, {**self.device, key: value}, self.device['mac'])
        self.assertEqual(transport.position, 0)

    def test_mismatched_ack_does_not_retry(self):
        driver, transport = self.driver(self.mutated(0xe5, 8, 99))
        with self.assertRaisesRegex(TransactionError, 'status/sequence'):
            driver.run()
        self.assertEqual(driver.chunks, 7)
        self.assertEqual(transport.writes, 12)

    def test_nonzero_delay_does_not_retry(self):
        driver, transport = self.driver(self.mutated(0xe5, -2, 1))
        with self.assertRaisesRegex(TransactionError, 'delay/retry'):
            driver.run()
        self.assertEqual(driver.chunks, 7)
        self.assertEqual(transport.writes, 12)

    def test_entry_bounds_reject_before_data(self):
        driver, transport = self.driver(self.mutated(0xe3, 10, 255))
        with self.assertRaisesRegex(TransactionError, 'bounds'):
            driver.run()
        self.assertEqual(driver.chunks, 0)
        self.assertEqual(transport.writes, 5)

    def test_timeout_after_write_does_not_retry(self):
        class TimeoutAtFirstBlock(ReplayTransport):
            def read(self, timeout=None):
                row = self.rows[self.position]
                if row['channel'] == 6 and row['data'][4] == 0xe5:
                    raise TimeoutError('injected lost ACK')
                return super().read(timeout)
        driver, transport = self.driver(transport_type=TimeoutAtFirstBlock)
        with self.assertRaisesRegex(TransactionError, 'state may be ambiguous'):
            driver.run()
        self.assertEqual(driver.chunks, 7)
        self.assertEqual(transport.writes, 12)

    def test_partial_socket_reads_reassemble(self):
        class SplitReads(ReplayTransport):
            remainder = b''
            def read(self, timeout=None):
                data = self.remainder or super().read(timeout)
                self.remainder = data[3:]
                return data[:3]
        driver, transport = self.driver(transport_type=SplitReads)
        result = driver.run()
        self.assertEqual(result['chunks'], 3457)
        self.assertEqual(transport.position, len(self.rows))

    def test_private_notify_uses_command_specific_status_one(self):
        rows = copy.deepcopy(self.rows)
        raw = bytearray(rows[1]['data'])
        raw[-3] = 0
        raw[-2:] = (sum(raw[:-2]) & 65535).to_bytes(2, 'big')
        rows[1]['data'] = bytes(raw)
        driver, transport = self.driver(rows)
        with self.assertRaisesRegex(TransactionError, 'notification reply'):
            driver.run()
        self.assertEqual(transport.writes, 1)
        self.assertEqual(transport.service, 'control')

    def test_noncontiguous_request_stops_after_first_block(self):
        rows = self.mutated(0xe5, 13, 0)
        driver, transport = self.driver(rows)
        with self.assertRaisesRegex(TransactionError, 'Noncontiguous'):
            driver.run()
        self.assertEqual(driver.chunks, 7)



class ManifestEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from memomind_ota import unpack_ota, repack, sha
        cls.source = IMAGE.read_bytes()
        _, streams = unpack_ota(cls.source)
        body = streams[3]['raw'][32:]
        # In-memory byte fixture only: no output file or live transport.
        changed = bytes([body[0] ^ 1]) + body[1:]
        cls.image = repack(cls.source, {3: changed})
        cls.manifest = {'format': 'memomind-body-patch-v1', 'source_sha256': sha(cls.source),
                        'output_sha256': sha(cls.image), 'edits': [
                            {'component': 3, 'body_sha256': sha(body), 'offset': 0,
                             'before': body[:1].hex(), 'after': changed[:1].hex(),
                             'reason': 'In-memory eligibility validation fixture only'}]}
        cls.rows, cls.device = read_transcript(TRANSCRIPT)

    def test_requires_both_manifest_and_exact_stock(self):
        from memomind_flasher import validate_image
        for manifest, source in ((None, None), (self.manifest, None), (None, self.source),
                                 (self.manifest, self.image)):
            with self.subTest(manifest=manifest is not None, source=source is not None):
                with self.assertRaises(TransactionError):
                    validate_image(self.image, manifest, source)
        report, modified = validate_image(self.image, self.manifest, self.source)
        self.assertTrue(modified)
        self.assertEqual(report['patch_verification']['output_sha256'], self.manifest['output_sha256'])

    def test_modified_staging_capacity_is_enforced_before_parsing(self):
        from memomind_flasher import validate_image, MAX_STAGED_PAYLOAD
        oversized = b'X' * (MAX_STAGED_PAYLOAD + 19)
        with self.assertRaisesRegex(TransactionError, 'staging capacity'):
            validate_image(oversized, self.manifest, self.source)

    def test_manifest_reproduction_cannot_be_bypassed_with_output_hash(self):
        from memomind_flasher import validate_image
        manifest = copy.deepcopy(self.manifest)
        manifest['edits'][0]['after'] = manifest['edits'][0]['before']
        with self.assertRaisesRegex(ValueError, 'must change'):
            validate_image(self.image, manifest, self.source)
        manifest = copy.deepcopy(self.manifest)
        manifest['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Source differs'):
            validate_image(self.image, manifest, self.source)
        with self.assertRaisesRegex(TransactionError, 'byte-identical'):
            validate_image(self.source, self.manifest, self.source)

    def patched_rows(self, start):
        from decode_memomind import encode_ota
        rows = copy.deepcopy(self.rows[:10])
        for row in rows:
            if row['channel'] == 6 and row['direction'] == 0 and row['data'][4] == 0xe2:
                row['data'] = encode_ota(0xe2, 3, self.image[:18])
            if row['channel'] == 6 and row['direction'] == 1 and row['data'][4] == 0xe3:
                raw = bytearray(row['data'])
                raw[10:14] = start.to_bytes(4, 'big')
                row['data'] = bytes(raw)
        return rows

    def test_modified_resume_rejected_before_any_chunk(self):
        for start in (0, 19, 162757):
            with self.subTest(start=start):
                transport = ReplayTransport(self.patched_rows(start))
                driver = StockTransaction(transport, self.image, self.device, self.device['mac'],
                                          pace=0, patch_manifest=self.manifest, stock_source=self.source)
                with self.assertRaisesRegex(TransactionError, 'fresh offset 18'):
                    driver.run()
                self.assertEqual(driver.chunks, 0)
                self.assertEqual(transport.writes, 5)

    def test_modified_fresh_start_generates_first_chunk_from_verified_image(self):
        from decode_memomind import encode_chunk
        class StopAtFirstChunk(ReplayTransport):
            first_chunk = None
            def write(self, data):
                if data[4] == 0xe5:
                    self.first_chunk = data
                    raise RuntimeError('intentional test boundary before transfer')
                super().write(data)
        transport = StopAtFirstChunk(self.patched_rows(18))
        driver = StockTransaction(transport, self.image, self.device, self.device['mac'],
                                  pace=0, patch_manifest=self.manifest, stock_source=self.source)
        with self.assertRaisesRegex(TransactionError, 'intentional test boundary'):
            driver.run()
        self.assertEqual(transport.first_chunk, encode_chunk(5, 18, self.image[18:648]))

    def test_check_only_accepts_reproduced_manifest_without_entry(self):
        transport = ReplayTransport(self.patched_rows(18))
        driver = StockTransaction(transport, self.image, self.device, self.device['mac'],
                                  pace=0, patch_manifest=self.manifest, stock_source=self.source)
        result = driver.run(check_only=True)
        self.assertTrue(result['modified_image'])
        self.assertEqual(result['image_sha256'], self.manifest['output_sha256'])
        self.assertEqual(transport.position, 8)


class PreservedControlTests(unittest.TestCase):
    def test_full_recorded_replay_on_two_sessions_keeps_control_connected(self):
        import time
        rows, device = read_transcript(TRANSCRIPT)
        class Control(ReplayTransport):
            def read(self, timeout=None):
                if self.position == len(self.rows):
                    time.sleep(0.005)
                    raise TimeoutError('idle control link')
                return super().read(timeout)
            def request(self, operation):
                raise AssertionError('Control link must not be disconnected')
        control = Control(rows[:2])
        ota = ReplayTransport(rows[2:])
        result = StockTransaction(control, IMAGE.read_bytes(), device, device['mac'],
                                  pace=0, ota_transport=ota).run()
        self.assertTrue(result['control_link_preserved'])
        self.assertEqual(control.writes, 1)
        self.assertEqual(ota.writes, 3463)
        self.assertEqual(ota.position, len(rows) - 2)

    def test_control_loss_is_reported_by_monitor(self):
        from memomind_flasher import ControlLinkMonitor
        class LostControl:
            def read(self, timeout):
                raise RuntimeError('injected control socket loss')
        monitor = ControlLinkMonitor(LostControl())
        monitor.start()
        monitor.thread.join(timeout=1)
        with self.assertRaisesRegex(TransactionError, 'control socket loss'):
            monitor.check()
        monitor.stop()


class RuntimeEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build_memomind_runtime import construct_runtime
        cls.source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        cls.blob = bytes.fromhex('8280') + b'\0' * 14  # In-memory fixture only; never emitted or flashed.
        cls.image, cls.manifest, _ = construct_runtime(cls.source, cls.blob)
        cls.rows, cls.device = read_transcript(TRANSCRIPT)

    def test_reproduced_runtime_image_is_eligible(self):
        from memomind_flasher import validate_image
        report, modified = validate_image(self.image, stock_source=self.source,
                                         runtime_manifest=self.manifest, runtime_blob=self.blob)
        self.assertTrue(modified)
        self.assertEqual(report['runtime_verification']['manifest'], self.manifest)

    def test_incomplete_or_mixed_modes_rejected(self):
        from memomind_flasher import validate_image
        for options in ({'runtime_manifest': self.manifest}, {'runtime_blob': self.blob},
                        {'runtime_manifest': self.manifest, 'runtime_blob': self.blob},
                        {'stock_source': self.source, 'runtime_manifest': self.manifest},
                        {'stock_source': self.source, 'runtime_blob': self.blob},
                        {'stock_source': self.source, 'runtime_manifest': self.manifest,
                         'runtime_blob': self.blob, 'patch_manifest': {}}):
            with self.subTest(options=list(options)), self.assertRaises(TransactionError):
                validate_image(self.image, **options)

    def test_reproduction_rejects_wrong_source_or_blob_or_result(self):
        from memomind_flasher import validate_image
        with self.assertRaisesRegex(ValueError, 'visually verified'):
            validate_image(self.image, stock_source=IMAGE.read_bytes(),
                           runtime_manifest=self.manifest, runtime_blob=self.blob)
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            validate_image(self.image, stock_source=self.source,
                           runtime_manifest=self.manifest, runtime_blob=b'\x00' * 16)
        with self.assertRaisesRegex(TransactionError, 'byte-identical'):
            validate_image(self.source, stock_source=self.source,
                           runtime_manifest=self.manifest, runtime_blob=self.blob)

    def driver(self):
        from decode_memomind import encode_ota
        rows = copy.deepcopy(self.rows[:10])
        for row in rows:
            if row['channel'] == 6 and row['direction'] == 0 and row['data'][4] == 0xe2:
                row['data'] = encode_ota(0xe2, 3, self.image[:18])
        transport = ReplayTransport(rows)
        driver = StockTransaction(transport, self.image, self.device, self.device['mac'], pace=0,
                                  stock_source=self.source, runtime_manifest=self.manifest,
                                  runtime_blob=self.blob)
        return driver, transport

    def test_runtime_check_only_stops_before_entry(self):
        driver, transport = self.driver()
        result = driver.run(check_only=True)
        self.assertTrue(result['modified_image'])
        self.assertEqual(result['image_sha256'], self.manifest['output_sha256'])
        self.assertEqual(transport.position, 8)
        self.assertEqual(driver.chunks, 0)

    def test_runtime_cannot_resume_partial_stock_transfer(self):
        driver, transport = self.driver()
        with self.assertRaisesRegex(TransactionError, 'fresh offset 18'):
            driver.run()
        self.assertEqual(driver.chunks, 0)
        self.assertEqual(transport.writes, 5)


if __name__ == '__main__':
    unittest.main()
