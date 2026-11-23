import Foundation
@testable import MemoMindCore
import XCTest

final class SessionResponseFilterTests: XCTestCase {
    private func packet(_ value: String, event: UInt8 = 37) throws -> Data {
        try GMCodec.frames(event: event, service: 15, command: 125,
                           body: GMTLV(kind: 5, value: Data(value.utf8)).encoded()).reduce(Data(), +)
    }
    private func selected(_ message: GMMessage) throws -> Bool {
        guard message.tlvs.count == 1, message.tlvs[0].kind == 5 else {
            throw MemoMindProtocolError.invalid("bad test schema")
        }
        switch String(decoding: message.tlvs[0].value, as: UTF8.self) {
        case "ok", "invalid": return true
        case "settled": return false
        default: throw MemoMindProtocolError.invalid("unknown test value")
        }
    }
    func testCoalescedSameEventNotificationsDoNotReplaceReply() throws {
        let io = try QueueTransport([packet("settled") + packet("ok") + packet("settled") + packet("settled")])
        let session = GMSession(transport: io)
        var notifications = [GMMessage]()
        session.unsolicited = { notifications.append($0) }
        let reply = try session.request(event: 37, service: 15, command: 125, responseFilter: selected)
        XCTAssertEqual(reply.tlvs[0].value, Data("ok".utf8))
        XCTAssertEqual(notifications.map { $0.tlvs[0].value }, Array(repeating: Data("settled".utf8), count: 3))
        XCTAssertEqual(io.writes.count, 1)
    }
    func testSplitLateNotificationIsRoutedOnSubsequentRead() throws {
        let first = try packet("ok") + packet("settled")
        let io = QueueTransport(first.map { Data([$0]) } + [try packet("ok", event: 38)])
        let session = GMSession(transport: io)
        var notifications = [GMMessage]()
        session.unsolicited = { notifications.append($0) }
        _ = try session.request(event: 37, service: 15, command: 125, responseFilter: selected)
        XCTAssertTrue(notifications.isEmpty, "Returning a reply is not a notification drain")
        let next = try session.request(event: 38, service: 15, command: 125, responseFilter: selected)
        XCTAssertEqual(next.event, 38)
        XCTAssertEqual(notifications.count, 1)
        XCTAssertEqual(notifications[0].event, 37)
    }
    func testFragmentACKNotificationsAndEarlyRejectionStopRemainingWrites() throws {
        let ack = try GMCodec.frames(event: 37, service: 15, command: 125)[0]
        let io = try QueueTransport([packet("settled") + ack, packet("invalid") + packet("settled")])
        let session = GMSession(transport: io)
        var seen = 0
        session.unsolicited = { _ in seen += 1 }
        let reply = try session.request(event: 37, service: 15, command: 125,
                                        body: Data(repeating: 1, count: 1500), responseFilter: selected)
        XCTAssertEqual(reply.tlvs[0].value, Data("invalid".utf8))
        XCTAssertEqual(io.writes.count, 2, "Early business rejection prevents the third request fragment")
        XCTAssertEqual(seen, 2)
    }
    func testDuplicateAcceptedRepliesRejectInFinalAndFragmentReads() throws {
        for count in [0, 1500] {
            let io = try QueueTransport([packet("ok") + packet("ok")])
            let session = GMSession(transport: io)
            XCTAssertThrowsError(try session.request(event: 37, service: 15, command: 125,
                                                     body: Data(count: count), responseFilter: selected))
            XCTAssertEqual(io.writes.count, 1)
        }
    }
    func testFilterErrorAndNotificationOnlyCannotBecomeSuccess() throws {
        for text in ["malformed", "settled"] {
            let io = try QueueTransport([packet(text)])
            let session = GMSession(transport: io)
            XCTAssertThrowsError(try session.request(event: 37, service: 15, command: 125, responseFilter: selected))
            XCTAssertEqual(io.writes.count, 1)
        }
    }
    func testFullBundleNotificationCountKeepsOrderAndDuplicates() throws {
        let notification = try packet("settled")
        let io = try QueueTransport([packet("ok") + Array(repeating: notification, count: 256).reduce(Data(), +)])
        let session = GMSession(transport: io)
        var seen = [GMMessage]()
        session.unsolicited = { seen.append($0) }
        _ = try session.request(event: 37, service: 15, command: 125, responseFilter: selected)
        XCTAssertEqual(seen.count, 256)
        XCTAssertTrue(seen.allSatisfy { $0.event == 37 && $0.tlvs[0].value == Data("settled".utf8) })
    }
}
