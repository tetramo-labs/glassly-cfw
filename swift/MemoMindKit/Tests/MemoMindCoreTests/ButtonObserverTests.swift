import Foundation
@testable import MemoMindCore
import XCTest

final class ButtonObserverTests: XCTestCase {
    private func snapshot(active: Bool = true, sequence: UInt32 = 0, ack: UInt32 = 0,
                          rows: [[String: Any]] = []) -> [String: Any]
    {
        ["glassly": "input", "abi": 1, "result": "ok", "active": active,
         "nonce": active ? 0x1234_5678 : 0, "mask": active ? 1 : 0,
         "capacity": 32, "leaseTicks": 30000, "sequence": sequence, "ack": ack,
         "drops": 0, "exhausted": sequence == UInt32.max, "records": rows]
    }

    private func record(_ serial: UInt32, _ id: UInt16 = 0x1F7B) -> [String: Any] {
        ["tick": UInt32.max, "sequence": serial, "id": id, "class": 2]
    }

    private func wire(_ object: [String: Any], event: UInt8) throws -> Data {
        try GMCodec.frames(event: event, service: 15, command: 0x7C,
                           body: GMTLV(kind: 5, value: JSONSerialization.data(withJSONObject: object)).encoded()).reduce(Data(),+)
    }

    private func decode(_ bytes: Data) throws -> ButtonSnapshot {
        let parser = GMStream()
        let framed = try GMCodec.frames(event: 1, service: 15, command: 0x7C,
                                        body: GMTLV(kind: 5, value: bytes).encoded()).reduce(Data(),+)
        return try ButtonSnapshot.decode(XCTUnwrap(parser.feed(framed).last))
    }

    func testBoundedRecordsAndPrimaryActions() throws {
        let values = (0 ..< 5).map { record(UInt32($0 + 1), UInt16(0x1F7B + $0)) }
        let decoded = try decode(JSONSerialization.data(withJSONObject: snapshot(sequence: 5, rows: values)))
        XCTAssertEqual(decoded.records.map(\.primaryAction), [.single, .double, .long, .veryLong, .release])
        XCTAssertEqual(decoded.records.first?.tick, UInt32.max)
        var overflow = snapshot(sequence: UInt32.max, ack: UInt32.max - 1, rows: [record(UInt32.max)])
        overflow["drops"] = UInt32.max
        XCTAssertTrue(try decode(JSONSerialization.data(withJSONObject: overflow)).exhausted)
    }

    func testMalformedMetadataAndRecordsRejected() throws {
        var cases = [[String: Any]]()
        for (key, value) in [("nonce", true as Any), ("sequence", 4_294_967_296 as Any), ("ack", 1 as Any),
                             ("mask", 3 as Any), ("capacity", 33 as Any), ("active", 1 as Any), ("exhausted", true as Any)]
        {
            var item = snapshot(); item[key] = value; cases.append(item)
        }
        cases.append(snapshot(active: false, sequence: 1))
        cases.append(snapshot(sequence: 2, rows: [record(2), record(1)]))
        cases.append(snapshot(sequence: 9, rows: (1 ... 9).map { record(UInt32($0)) }))
        cases.append(snapshot(sequence: 1, rows: [record(1, 0xFFFF)]))
        var wrong = record(1); wrong["class"] = 3
        cases.append(snapshot(sequence: 1, rows: [wrong]))
        for item in cases {
            XCTAssertThrowsError(try decode(JSONSerialization.data(withJSONObject: item)))
        }
        let valid = try String(decoding: JSONSerialization.data(withJSONObject: snapshot()), as: UTF8.self)
        XCTAssertThrowsError(try decode(Data(valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":1,\"abi\":1").utf8)))
    }

    func testExplicitDurableACKReplayAndStop() throws {
        let page = snapshot(sequence: 2, rows: [record(1), record(2, 0x1F7F)])
        let io = try QueueTransport([wire(snapshot(), event: 255), wire(page, event: 1), wire(page, event: 2),
                                     wire(snapshot(sequence: 2, ack: 2), event: 3), wire(snapshot(active: false), event: 4)])
        let client = ButtonObserverClient(session: GMSession(transport: io), initialEvent: 254)
        _ = try client.subscribe(nonce: 0x1234_5678)
        XCTAssertThrowsError(try client.acknowledge(savedThrough: 1))
        XCTAssertEqual(try client.poll().records.count, 2)
        XCTAssertEqual(try client.poll().records.count, 2) // no ACK until explicitly saved
        XCTAssertThrowsError(try client.acknowledge(savedThrough: 3))
        try client.acknowledge(savedThrough: 2)
        XCTAssertEqual(try client.poll().acknowledged, 2)
        XCTAssertFalse(try client.stop().active)
        let parser = GMStream()
        let commands = try io.writes.flatMap { try parser.feed($0) }.map { $0.tlvs[0].value }
        XCTAssertEqual(commands, [Data([1, 1, 1, 0x78, 0x56, 0x34, 0x12]),
                                  Data([1, 2, 0x78, 0x56, 0x34, 0x12, 0, 0, 0, 0]), Data([1, 2, 0x78, 0x56, 0x34, 0x12, 0, 0, 0, 0]),
                                  Data([1, 2, 0x78, 0x56, 0x34, 0x12, 2, 0, 0, 0]), Data([1, 3, 0x78, 0x56, 0x34, 0x12])])
    }

    func testLostReplyAndChangedSessionPoisonClient() throws {
        for changed in [false, true] {
            var replies = try [wire(snapshot(), event: 113)]
            if changed {
                var other = snapshot(); other["nonce"] = 7; try replies.append(wire(other, event: 114))
            }
            let io = QueueTransport(replies), client = ButtonObserverClient(session: GMSession(transport: io))
            _ = try client.subscribe(nonce: 0x1234_5678)
            XCTAssertThrowsError(try client.poll())
            let count = io.writes.count
            XCTAssertThrowsError(try client.poll()); XCTAssertThrowsError(try client.stop())
            XCTAssertEqual(io.writes.count, count)
        }
    }
}
