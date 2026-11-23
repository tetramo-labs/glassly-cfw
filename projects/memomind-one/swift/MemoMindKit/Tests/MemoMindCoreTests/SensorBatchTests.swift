import Foundation
@testable import MemoMindCore
import XCTest

final class SensorBatchTests: XCTestCase {
    func fixture() -> [UInt8] {
        var b = [UInt8](repeating: 0, count: 76)
        b.replaceSubrange(0 ..< 4, with: [83, 66, 2, 3])
        for (offset, value) in [(4, UInt32(7)), (8, 50), (12, 8), (16, 10), (20, 8), (28, 9), (32, .max - 10), (52, 10), (56, 10)] {
            for i in 0 ..< 4 {
                b[offset + i] = UInt8(truncatingIfNeeded: value >> (i * 8))
            }
        }
        b.replaceSubrange(24 ..< 28, with: [2, 32, 2, 1])
        b[36] = 1
        b.replaceSubrange(38 ..< 52, with: [128, 0, 128, 0, 255, 239, 255, 240, 255, 255, 0, 0, 127, 255])
        b[60] = 2; b[62] = 232; b[63] = 3
        return b
    }

    func message(_ b: [UInt8], result: String = "ok") throws -> GMMessage {
        try SensorCaptureTests().messageJSON(["glassly": "sensor-batch", "abi": 2, "result": result,
                                              "stateHex": b.map { String(format: "%02x", $0) }.joined()], command: 118)
    }

    func testMixedNativeSamplesAndRollover() throws {
        let batch = try SensorBatch.decode(message(fixture()))
        XCTAssertEqual(batch.generation, 7); XCTAssertEqual(batch.acknowledged, 8)
        XCTAssertEqual(batch.pending, 2); XCTAssertEqual(batch.drops, 8)
        XCTAssertEqual(batch.samples.map(\.sequence), [9, 10])
        XCTAssertEqual(batch.samples[0].imu?.accelerometer, SensorVector(x: -32768, y: -17, z: -16))
        XCTAssertEqual(batch.samples[0].ageTicks, 61)
        XCTAssertEqual(batch.samples[1].light?.normalized, 1000)
        XCTAssertEqual(try JSONDecoder().decode(SensorBatch.self, from: JSONEncoder().encode(batch)), batch)
    }

    func testRejectsMalformedOrderingBoundsAndUnits() throws {
        for (index, value) in [(3, UInt8(4)), (4, 0), (12, 11), (16, 9), (20, 11), (24, 33), (25, 31), (26, 5), (27, 2),
                               (28, 8), (36, 3), (37, 1), (52, 9), (62, 233), (64, 1)]
        {
            var b = fixture(); b[index] = value
            XCTAssertThrowsError(try SensorBatch.decode(message(b)), "offset \(index)")
        }
        XCTAssertThrowsError(try SensorBatch.decode(message(Array(fixture().dropLast()))))
        XCTAssertThrowsError(try SensorBatch.decode(message(fixture(), result: "stale")))
        var idle = Array(fixture().prefix(28)); idle[3] = 0; idle[27] = 0; idle[12] = 10; idle[24] = 0; idle[26] = 0
        XCTAssertEqual(try SensorBatch.decode(message(idle, result: "inactive")).samples, [])
        XCTAssertThrowsError(try SensorBatch.decode(message(idle)))
    }

    func testAcknowledgmentAndResponseCorrelation() throws {
        let transport = QueueTransport()
        var observed: [Data] = []
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            observed.append(request.tlvs[0].value)
            let response = try self.message(self.fixture())
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
        }
        let session = GMSession(transport: transport)
        var event: UInt8 = 255
        let a = try session.sensorBatch(generation: 7, acknowledged: 8, event: &event)
        XCTAssertEqual(try session.sensorBatch(generation: 7, acknowledged: 8, event: &event), a)
        XCTAssertEqual(observed[0], Data([83, 67, 1, 4, 7, 0, 0, 0, 8, 0, 0, 0]))
        XCTAssertEqual(observed[0], observed[1])
        XCTAssertThrowsError(try session.sensorBatch(generation: 8, acknowledged: 8, event: &event))
        XCTAssertThrowsError(try session.sensorBatch(generation: 7, acknowledged: 9, event: &event))
        XCTAssertThrowsError(try SensorBatch.command(generation: 0, acknowledged: 0))
    }

    func testDrainingPhaseAndFinishEncoding() throws {
        var b = fixture(); b[3] = 0; b[27] = 2
        XCTAssertEqual(try SensorBatch.decode(message(b)).phase, .draining)
        XCTAssertEqual(try SensorBatch.command(generation: 7, acknowledged: 8, finish: true), Data([83, 67, 1, 5, 7, 0, 0, 0, 8, 0, 0, 0]))
        for phase: UInt8 in [0, 1, 3, 255] {
            b[27] = phase
            XCTAssertThrowsError(try SensorBatch.decode(message(b)))
        }
        b[27] = 2; b[2] = 1
        XCTAssertThrowsError(try SensorBatch.decode(message(b)))
    }

    func testDrainSavesBeforeAcknowledgmentAndConfirmsEmptyTail() throws {
        let transport = QueueTransport()
        var saved: UInt32 = 0
        var writes = 0
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            let body = [UInt8](request.tlvs[0].value)
            XCTAssertEqual(body[3], writes == 0 ? 5 : 4)
            XCTAssertEqual(UInt32(body[8]), saved)
            writes += 1
            let count = min(4, 32 - Int(saved))
            var b = [UInt8](repeating: 0, count: 28 + count * 24)
            b.replaceSubrange(0 ..< 4, with: [83, 66, 2, 0]); b[4] = 7; b[8] = 50
            b[12] = UInt8(saved); b[16] = 32; b[24] = UInt8(32 - Int(saved)); b[25] = 32; b[26] = UInt8(count); b[27] = 2
            for i in 0 ..< count {
                b[28 + i * 24] = UInt8(saved + UInt32(i) + 1)
                b[36 + i * 24] = 2
            }
            let response = try self.message(b)
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
        }
        var event: UInt8 = 0
        let result = try GMSession(transport: transport).drainSensorCapture(generation: 7, acknowledged: 0, event: &event) { batch in
            saved = batch.samples.last?.sequence ?? saved
        }
        XCTAssertEqual(writes, 9); XCTAssertEqual(saved, 32)
        XCTAssertEqual(result.pending, 0); XCTAssertEqual(result.acknowledged, 32)
    }

    func testDrainDoesNotAcknowledgeFailedSave() throws {
        let transport = QueueTransport()
        var writes = 0
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            writes += 1
            var b = self.fixture(); b[3] = 0; b[27] = 2
            let response = try self.message(b)
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
        }
        var event: UInt8 = 0
        XCTAssertThrowsError(try GMSession(transport: transport).drainSensorCapture(generation: 7, acknowledged: 8, event: &event) { _ in
            throw MemoMindProtocolError.invalid("Disk full")
        })
        XCTAssertEqual(writes, 1)
    }

    func testDrainRejectsCounterChangesAndWrongGeneration() throws {
        for changedGeneration in [false, true] {
            let transport = QueueTransport()
            var writes = 0
            transport.onWrite = { bytes in
                let request = try XCTUnwrap(GMStream().feed(bytes).first)
                var b = self.fixture(); b[3] = 0; b[27] = 2
                if writes > 0 {
                    b = Array(b.prefix(28)); b[12] = 10; b[24] = 0; b[26] = 0
                    if changedGeneration {
                        b[4] = 8
                    } else {
                        b[20] = 9
                    }
                }
                writes += 1
                let response = try self.message(b)
                transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
            }
            var event: UInt8 = 0
            XCTAssertThrowsError(try GMSession(transport: transport).drainSensorCapture(generation: 7, acknowledged: 8, event: &event) { _ in })
            XCTAssertEqual(writes, 2)
        }
    }

    func testGenerationOwnedReleaseAndRefusal() throws {
        let transport = QueueTransport()
        var generation: UInt8 = 7
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            XCTAssertEqual(request.tlvs[0].value, Data([83, 67, 1, 6, 7, 0, 0, 0, 10, 0, 0, 0]))
            var b = Array(self.fixture().prefix(28)); b[3] = 0; b[4] = generation; b[12] = 10; b[24] = 0; b[26] = 0; b[27] = 0
            let response = try self.message(b, result: "released")
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
        }
        let session = GMSession(transport: transport)
        var event: UInt8 = 0
        XCTAssertEqual(try session.releaseSensorCapture(generation: 7, acknowledged: 10, event: &event).phase, .inactive)
        generation = 8
        XCTAssertThrowsError(try session.releaseSensorCapture(generation: 7, acknowledged: 10, event: &event))
        XCTAssertThrowsError(try SensorBatch.decode(message(fixture(), result: "released")))
    }
}
