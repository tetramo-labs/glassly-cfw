import Foundation
@testable import MemoMindCore
import XCTest

final class SensorBatchTests: XCTestCase {
    func fixture() -> [UInt8] {
        var b = [UInt8](repeating: 0, count: 76)
        b.replaceSubrange(0 ..< 4, with: [83, 66, 1, 3])
        for (offset, value) in [(4, UInt32(7)), (8, 50), (12, 8), (16, 10), (20, 8), (28, 9), (32, .max - 10), (52, 10), (56, 10)] {
            for i in 0 ..< 4 {
                b[offset + i] = UInt8(truncatingIfNeeded: value >> (i * 8))
            }
        }
        b.replaceSubrange(24 ..< 28, with: [2, 32, 2, 0])
        b[36] = 1
        b.replaceSubrange(38 ..< 52, with: [128, 0, 128, 0, 255, 239, 255, 240, 255, 255, 0, 0, 127, 255])
        b[60] = 2; b[62] = 232; b[63] = 3
        return b
    }

    func message(_ b: [UInt8], result: String = "ok") throws -> GMMessage {
        try SensorCaptureTests().messageJSON(["glassly": "sensor-batch", "abi": 1, "result": result,
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
        for (index, value) in [(3, UInt8(4)), (4, 0), (12, 11), (16, 9), (20, 11), (24, 33), (25, 31), (26, 5), (27, 1),
                               (28, 8), (36, 3), (37, 1), (52, 9), (62, 233), (64, 1)]
        {
            var b = fixture(); b[index] = value
            XCTAssertThrowsError(try SensorBatch.decode(message(b)), "offset \(index)")
        }
        XCTAssertThrowsError(try SensorBatch.decode(message(Array(fixture().dropLast()))))
        XCTAssertThrowsError(try SensorBatch.decode(message(fixture(), result: "stale")))
        var idle = Array(fixture().prefix(28)); idle[3] = 0; idle[12] = 10; idle[24] = 0; idle[26] = 0
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
}
