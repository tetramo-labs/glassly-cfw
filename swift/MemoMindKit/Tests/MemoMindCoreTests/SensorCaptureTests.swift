import Foundation
@testable import MemoMindCore
import XCTest

final class SensorCaptureTests: XCTestCase {
    func fixture() -> [UInt8] {
        var b = [UInt8](repeating: 0, count: 52)
        b.replaceSubrange(0 ..< 6, with: [83, 67, 1, 3, 3, 3])
        for (offset, value) in [(8, UInt32(7)), (12, 50), (16, 90000), (20, 4), (24, .max - 10), (28, 2), (32, 10)] {
            for i in 0 ..< 4 {
                b[offset + i] = UInt8(truncatingIfNeeded: value >> (i * 8))
            }
        }
        b.replaceSubrange(36 ..< 52, with: [128, 0, 128, 0, 255, 239, 255, 240, 255, 255, 0, 0, 127, 255, 232, 3])
        return b
    }

    func message(_ b: [UInt8], result: String = "ok") throws -> GMMessage {
        try messageJSON(["glassly": "sensors", "abi": 1, "result": result,
                         "stateHex": b.map { String(format: "%02x", $0) }.joined()], command: 0x76)
    }

    func messageJSON(_ o: [String: Any], command: UInt8) throws -> GMMessage {
        try GMStream().feed(GMCodec.frames(event: 1, service: 15, command: command,
                                           body: GMTLV(kind: 5, value: JSONSerialization.data(withJSONObject: o)).encoded())
                .reduce(into: Data()) { $0.append($1) }).first!
    }

    func testFullResolutionAndClockRollover() throws {
        let state = try SensorCaptureSnapshot.decode(message(fixture()))
        XCTAssertEqual(state.generation, 7)
        XCTAssertEqual(state.imu?.temperature, -32768)
        XCTAssertEqual(state.imu?.accelerometer, SensorVector(x: -32768, y: -17, z: -16))
        XCTAssertEqual(state.imu?.gyroscope, SensorVector(x: -1, y: 0, z: 32767))
        XCTAssertEqual(state.imu?.ageTicks, 61)
        XCTAssertEqual(state.light?.normalized, 1000)
        XCTAssertEqual(state.light?.ageTicks, 40)
        XCTAssertEqual(try JSONDecoder().decode(SensorCaptureSnapshot.self, from: JSONEncoder().encode(state)), state)
    }

    func testRejectsContradictoryOrMalformedSamples() throws {
        for (index, value) in [(3, UInt8(4)), (4, 4), (5, 0), (6, 1), (7, 1), (8, 0), (20, 0), (28, 0), (50, 233)] {
            var b = fixture(); b[index] = value
            XCTAssertThrowsError(try SensorCaptureSnapshot.decode(message(b)), "offset \(index)")
        }
        var invalid = fixture(); invalid[4] = 0; invalid[5] = 0
        XCTAssertThrowsError(try SensorCaptureSnapshot.decode(message(invalid)))
        XCTAssertThrowsError(try SensorCaptureSnapshot.decode(message(Array(fixture().dropLast()))))
        XCTAssertThrowsError(try SensorCaptureSnapshot.decode(message(fixture(), result: "queued")))
        var idle = [UInt8](repeating: 0, count: 52); idle[0] = 83; idle[1] = 67; idle[2] = 1
        let state = try SensorCaptureSnapshot.decode(message(idle))
        XCTAssertNil(state.imu); XCTAssertNil(state.light); XCTAssertEqual(state.activeMask, 0)
        idle[16] = 1
        XCTAssertThrowsError(try SensorCaptureSnapshot.decode(message(idle)))
    }

    func testCapabilityAndCorrelatedCommands() throws {
        let sensors: [String: Any] = ["command": 118, "version": 1, "capture": "passive-buffered", "capacity": 32, "batch": 4, "batchVersion": 2, "finish": 5, "release": 6, "drainTicks": 30000, "imu": "icm42670-registers",
                                      "als": "native-0-1000", "leaseTicks": 90000]
        for version in ["GLASSLYCFW/10", "GLASSLYCFW/9", "GLASSLYCFW/7", "GLASSLYCFW/+8", "GLASSLYCFW/8beta"] {
            let caps = try messageJSON(["glassly": "graphics-runtime", "abi": 1, "version": version, "sensors": sensors], command: 0x7E)
            if ["GLASSLYCFW/10"].contains(version) {
                XCTAssertNoThrow(try SensorCaptureSnapshot.validateCapability(caps))
            } else {
                XCTAssertThrowsError(try SensorCaptureSnapshot.validateCapability(caps))
            }
        }
        let transport = QueueTransport()
        var seen: [UInt8] = []
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            XCTAssertEqual(request.command, 118)
            let command = try XCTUnwrap(SensorCaptureCommand(rawValue: request.tlvs[0].value[3]))
            XCTAssertEqual(request.tlvs[0].value, command.encoded())
            seen.append(request.event)
            var b = self.fixture()
            if command == .stop {
                b = [83, 67, 1] + [UInt8](repeating: 0, count: 49)
            }
            let response = try self.message(b)
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 118, body: response.tlvs[0].encoded())
        }
        let session = GMSession(transport: transport)
        var event: UInt8 = 254
        XCTAssertNotNil(try session.sensorCapture(.start, event: &event).imu)
        XCTAssertEqual(try session.sensorCapture(.renew, event: &event).generation, 7)
        XCTAssertEqual(try session.sensorCapture(.stop, event: &event).activeMask, 0)
        XCTAssertEqual(seen, [255, 1, 2])
    }
}
