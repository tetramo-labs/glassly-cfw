import Foundation
@testable import MemoMindCore
import XCTest

final class MicrophoneControlTests: XCTestCase {
    func message(_ changes: [String: Any] = [:]) throws -> GMMessage {
        var object: [String: Any] = ["glassly": "microphone", "abi": 1, "result": "ok",
                                     "stateHex": "4d43010100010300a000a00002010101000000a000", "serial": 1, "completed": 1,
                                     "pending": 0, "phase": 3, "error": 0, "nativeStatus": 0, "nativeActive": 1]
        changes.forEach { object[$0.key] = $0.value }
        return try GMStream().feed(GMCodec.frames(event: 1, service: 15, command: 0x77,
                                                  body: GMTLV(kind: 5, value: JSONSerialization.data(withJSONObject: object)).encoded()).reduce(into: Data()) { $0.append($1) }).first!
    }

    func testNativeOpusContract() throws {
        XCTAssertEqual(MicrophoneCommand.start.encoded(), Data([77, 67, 1, 1, 0, 1, 3, 0, 160, 0, 160, 0, 2]))
        for op in [MicrophoneCommand.status, .stop, .renew] {
            XCTAssertEqual(op.encoded(), Data([77, 67, 1, op.rawValue]))
        }
        let state = try MicrophoneSnapshot.decode(message())
        XCTAssertTrue(state.active && state.streaming && state.nativeActive)
        XCTAssertEqual(state.frames, 1)
        let stopping = try MicrophoneSnapshot.decode(message(["stateHex": "4d43010000010300a000a00002000101000000a000", "phase": 4, "error": 5, "nativeStatus": 9]))
        XCTAssertFalse(stopping.streaming)
        XCTAssertTrue(stopping.nativeActive)
    }

    func testQueuedStartAndVerifiedStop() throws {
        let transport = QueueTransport()
        var operations: [UInt8] = []
        var replies: [[String: Any]] = [
            ["result": "queued", "completed": 0, "pending": 1],
            [:],
            ["result": "queued", "serial": 2, "pending": 1, "phase": 4],
            ["serial": 2, "completed": 2, "phase": 4, "error": 5],
            ["serial": 2, "completed": 2, "phase": 0, "nativeActive": 0,
             "stateHex": "4d43010000010300a000a00002000101000000a000"],
        ]
        transport.onWrite = { bytes in
            let request = try XCTUnwrap(GMStream().feed(bytes).first)
            XCTAssertEqual(request.command, 119)
            operations.append(request.tlvs[0].value[3])
            let response = try self.message(replies.removeFirst())
            transport.reads += try GMCodec.frames(event: request.event, service: 15, command: 119,
                                                  body: response.tlvs[0].encoded())
        }
        let session = GMSession(transport: transport)
        var event: UInt8 = 254
        XCTAssertTrue(try session.microphone(.start, event: &event).streaming)
        XCTAssertFalse(try session.microphone(.stop, event: &event).nativeActive)
        XCTAssertEqual(operations, [1, 2, 3, 2, 2])
        XCTAssertTrue(replies.isEmpty)
    }

    func testInvalidAndInconsistentState() throws {
        for change: [String: Any] in [["serial": -1], ["serial": 4_294_967_296 as UInt64], ["completed": 2],
                                      ["pending": 1], ["phase": 6], ["error": 12], ["nativeActive": 0], ["result": "unexpected"],
                                      ["stateHex": ""], ["stateHex": "4d43010100010000a000a00002010101000000a000"]]
        {
            XCTAssertThrowsError(try MicrophoneSnapshot.decode(message(change)))
        }
        let queued = try MicrophoneSnapshot.decode(message(["result": "queued", "serial": 2, "pending": 1]))
        XCTAssertTrue(queued.pending)
    }
}
