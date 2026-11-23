import Foundation
@testable import MemoMindCore
import XCTest

final class OwnershipTests: XCTestCase {
    func message(_ state: [UInt8], result: String = "ok", event: UInt8 = 1) throws -> GMMessage {
        let hex = state.map { String(format: "%02x", $0) }.joined()
        let json = Data("{\"glassly\":\"ownership\",\"abi\":1,\"result\":\"\(result)\",\"stateHex\":\"\(hex)\"}".utf8)
        return try GMStream().feed(GMCodec.frames(event: event, service: 15, command: 0x79, body: GMTLV(kind: 5, value: json).encoded()).reduce(into: Data()) { $0.append($1) }).first!
    }

    func testG2ControlBytes() throws {
        for operation in OwnershipCommand.allCases {
            XCTAssertEqual(try operation.encoded(), Data([0x46, 0x43, 1, operation.rawValue, 1, 0]))
            XCTAssertEqual(try operation.encoded(nonce: 0x1234).suffix(2), Data([0x34, 0x12]))
        }
        // Original vector-protocol.test.ts field101 payloads, without its protobuf wrapper.
        for op in [OwnershipCommand.acquireFrame, .acquireFrame, .releaseFrame] {
            XCTAssertEqual(try op.encoded(), Data([70, 67, 1, op.rawValue, 1, 0]))
        }
    }

    func testSnapshotsAndAsynchronousEvents() throws {
        let snapshot = try OwnershipSnapshot.decode(message([1, 1, 1, 0x34, 0x12, 1, 0, 1, 0]))
        XCTAssertTrue(snapshot.wakeLease && snapshot.frameLease && snapshot.pending && snapshot.screenOn && snapshot.framePresented)
        XCTAssertEqual(snapshot.nonce, 0x1234)
        XCTAssertNil(snapshot.event)
        for event in UInt8(1) ... 4 {
            let snapshot = try OwnershipSnapshot.decode(message([1, 0, 1, 1, 0, 1, 0, 0, event], result: "event", event: 0))
            XCTAssertEqual(snapshot.event?.rawValue, event)
        }
        let empty = try OwnershipSnapshot.decode(message(Array(repeating: 0, count: 9)))
        XCTAssertFalse(empty.wakeLease || empty.frameLease || empty.pending || empty.framePresented)
    }

    func testMalformedAndRefusedResponses() throws {
        for bytes in [[UInt8](), Array(repeating: UInt8(0), count: 10),
                      [2, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 1, 0, 0, 0, 0, 0],
                      [0, 0, 0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 1, 0],
                      [1, 1, 0, 0, 0, 0, 0, 0, 1]]
        {
            XCTAssertThrowsError(try OwnershipSnapshot.decode(message(bytes)))
        }
        XCTAssertThrowsError(try OwnershipSnapshot.decode(message(Array(repeating: 0, count: 9), result: "busy")))
        XCTAssertThrowsError(try OwnershipSnapshot.decode(message([1, 0, 1, 1, 0, 1, 0, 0, 1], result: "event", event: 5)))
    }
}
