import Foundation
@testable import MemoMindCore
import XCTest

final class RecordTransportTests: XCTestCase {
    private let caps = "{\"recordTransport\":{\"mode\":126,\"version\":1,\"maxPacketBytes\":128,\"maxRecordBytes\":65535,\"replyCapacity\":64,\"endpoint\":1,\"leaseTicks\":30000}}"
    private func hex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    private func response(_ json: String, event: UInt8, command: UInt8) throws -> Data {
        try GMCodec.frames(event: event, service: 15, command: command,
                           body: GMTLV(kind: 5, value: Data(json.utf8)).encoded()).reduce(Data(), +)
    }

    private func batch(_ frames: [Data], closing: Int = 0) -> String {
        "{\"glassly\":\"record-transport\",\"abi\":1,\"status\":0,\"closing\":\(closing),\"frames\":[\(frames.map { "\"\(hex($0))\"" }.joined(separator: ","))]}"
    }

    private func ack(_ record: GraphicsRecord) -> Data {
        Data([1, record.streamID, 0, 0, 1, UInt8(truncatingIfNeeded: record.decodedBytes),
              UInt8(truncatingIfNeeded: record.decodedBytes >> 8), UInt8(truncatingIfNeeded: record.checksum),
              UInt8(truncatingIfNeeded: record.checksum >> 8)])
    }

    func testPythonCompressionDictionaryAndCRC() throws {
        let body = Data([8, 0] + (0 ..< 2048).map { UInt8(truncatingIfNeeded: $0) })
        let second = Data([8, 0]) + body.suffix(1024)
        let compressor = try RecordDeflater()
        XCTAssertEqual(try hex(compressor.encode(body)), RecordReferenceVectors.firstHex)
        XCTAssertEqual(try hex(compressor.encode(second)), RecordReferenceVectors.secondHex)
        XCTAssertEqual(GraphicsRecord.crc16(body), RecordReferenceVectors.firstCRC)
        XCTAssertEqual(GraphicsRecord.crc16(Data("123456789".utf8)), 0x29B1)
        try compressor.reset()
        XCTAssertEqual(try hex(compressor.encode(body)), RecordReferenceVectors.firstHex)
    }

    func testMaximumRecordBoundariesSequenceWrapAndSlicedInput() throws {
        let body = Data([8, 0]) + Data(repeating: 23, count: 65533)
        let record = try GraphicsRecord(command: body, resetContext: true, sequence: 255)
        XCTAssertEqual(record.packets.count, 513)
        XCTAssertEqual(record.packets[0].prefix(4), Data([126, 1, 255, 129]))
        XCTAssertEqual(record.packets[1][2], 0)
        XCTAssertEqual(record.packets.last?[3], 65)
        let recovered = record.packets.reduce(Data()) { $0 + $1.dropFirst(4) }
        XCTAssertEqual(recovered.prefix(3), Data([9, 255, 255]))
        XCTAssertEqual(recovered.dropFirst(5), body)
        XCTAssertEqual(try GraphicsRecord(command: (Data([99]) + body).dropFirst(), resetContext: true, sequence: 255).packets, record.packets)
        for bad in [Data(), Data([126]), Data([127]), Data(repeating: 1, count: 65536)] {
            XCTAssertThrowsError(try GraphicsRecord(command: bad, resetContext: true, sequence: 0))
        }
        XCTAssertThrowsError(try GraphicsRecord(command: body, compressed: Data([1, 2, 3, 4]), resetContext: true, sequence: 0))
    }

    func testSessionAcknowledgmentsAndBinaryReply() throws {
        let command = Data([8, 0]) + Data(repeating: 7, count: 300)
        let record = try GraphicsRecord(command: command, resetContext: true, sequence: 254)
        var replies = try [response(caps, event: 255, command: 126)]
        var event: UInt8 = 255
        for i in record.packets.indices {
            event = event == 255 ? 1 : event + 1
            let frames = i == record.packets.count - 1 ? [Data([5, 254, 0, 0, 1, 42]), ack(record)] : []
            try replies.append(response(batch(frames), event: event, command: 125))
        }
        let io = QueueTransport(replies)
        let sender = try GraphicsRecordSession(session: GMSession(transport: io), sequence: 254)
        var start: UInt8 = 254
        XCTAssertEqual(try sender.send(command, compressed: false, event: &start), Data([42]))
        XCTAssertEqual(start, event)
        XCTAssertEqual(io.writes.count, record.packets.count + 1)
    }

    func testRefusalLossAndWrongACKPoisonWithoutRetry() throws {
        let command = Data([36, 0])
        let record = try GraphicsRecord(command: command, resetContext: true, sequence: 9)
        for field in [0, 1, 2, 4, 5, 7] {
            var bad = ack(record); bad[field] ^= 2
            let io = try QueueTransport([response(caps, event: 1, command: 126),
                                         response(batch([bad]), event: 2, command: 125)])
            let sender = try GraphicsRecordSession(session: GMSession(transport: io), sequence: 9)
            var event: UInt8 = 0
            XCTAssertThrowsError(try sender.send(command, compressed: false, event: &event))
            XCTAssertThrowsError(try sender.send(command, event: &event))
            XCTAssertEqual(io.writes.count, 2)
        }
        let io = try QueueTransport([response(caps, event: 1, command: 126)])
        let sender = try GraphicsRecordSession(session: GMSession(transport: io))
        var event: UInt8 = 0
        XCTAssertThrowsError(try sender.send(command, event: &event))
        XCTAssertEqual(io.writes.count, 2)
    }

    func testUnsupportedCapabilityAndEarlyNACKStopRemainingPackets() throws {
        let command = Data([8, 0]) + Data(repeating: 7, count: 300)
        let io = try QueueTransport([response(caps, event: 1, command: 126),
                                     response(batch([Data([3, 0, 0, 0, 1, 0, 0, 0, 0])]), event: 2, command: 125)])
        let sender = try GraphicsRecordSession(session: GMSession(transport: io))
        var event: UInt8 = 0
        XCTAssertThrowsError(try sender.send(command, compressed: false, event: &event))
        XCTAssertEqual(io.writes.count, 2)
        let old = try QueueTransport([response("{}", event: 1, command: 126)])
        let unsupported = try GraphicsRecordSession(session: GMSession(transport: old))
        event = 0
        XCTAssertThrowsError(try unsupported.send(command, event: &event))
        XCTAssertEqual(old.writes.count, 1)
    }
}
