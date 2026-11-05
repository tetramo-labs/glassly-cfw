import Foundation
@testable import MemoMindCore
import XCTest
final class LargeMessageTests: XCTestCase {
    private let accepted = "{\"glassly\":\"large-message\",\"abi\":1,\"result\":\"accepted\"}"
    private let caps = "{\"version\":\"GLASSLYCFW/1\",\"maxMessageBytes\":65535,\"largeMessage\":{\"mode\":127,\"chunkBytes\":1024,\"crc\":\"crc32-ieee\"}}"
    private func response(_ value: String, event: UInt8, command: UInt8) throws -> Data {
        try GMCodec.frames(event: event, service: 15, command: command,
                           body: GMTLV(kind: 5, value: Data(value.utf8)).encoded()).reduce(Data(), +)
    }
    func testMaximumReconstructionCRCAndSlicedData() throws {
        let bytes = Data([8,0] + (0..<65533).map { UInt8(truncatingIfNeeded: $0 * 37) })
        let transfer = try LargeMessage(command: bytes, token: 0x12345678)
        XCTAssertEqual(transfer.packets.count, 66)
        XCTAssertEqual(transfer.packets[0], Data([127,0,0x78,0x56,0x34,0x12,255,255]))
        var restored = Data()
        for packet in transfer.packets.dropFirst().dropLast() {
            XCTAssertLessThanOrEqual(packet.count, 1032)
            let offset = Int(packet[6]) | (Int(packet[7]) << 8)
            XCTAssertEqual(offset, restored.count); restored.append(packet.dropFirst(8))
        }
        XCTAssertEqual(restored, bytes)
        let crc = OTACodec.crc32(bytes)
        XCTAssertEqual(transfer.packets.last?.suffix(4), Data((0..<4).map { UInt8(truncatingIfNeeded: crc >> ($0 * 8)) }))
        let prefixed = Data([255]) + bytes
        XCTAssertEqual(try LargeMessage(command: prefixed.dropFirst(), token: 0x12345678).packets, transfer.packets)
        XCTAssertEqual(transfer.abort, Data([127,3,0x78,0x56,0x34,0x12]))
    }
    func testInvalidBoundsAndExplicitEncoderCapacity() throws {
        for command in [Data(), Data(repeating: 1, count: 65536), Data([127,0])] {
            XCTAssertThrowsError(try LargeMessage(command: command, token: 1))
        }
        XCTAssertThrowsError(try LargeMessage(command: Data([8,0]), token: 0))
        var child = Data(repeating: 0, count: 65531); child[0] = 37
        XCTAssertThrowsError(try RasterCommands.bundle([child]))
        XCTAssertEqual(try RasterCommands.bundle([child], maximumCommandBytes: 65535).count, 65535)
        child.append(0)
        XCTAssertThrowsError(try RasterCommands.bundle([child], maximumCommandBytes: 65535))
        let pixels = Data((0..<105000).map { i -> UInt8 in
            let left = UInt8((i * 2 / 5) % 16)
            let right = UInt8(((i * 2 + 1) / 5) % 16)
            return (left << 4) | right
        })
        XCTAssertThrowsError(try RasterCommands.fullFrame(pixels: pixels))
        let command = try RasterCommands.fullFrame(pixels: pixels, maximumCommandBytes: 65535)
        XCTAssertGreaterThan(command.count, 8192); XCTAssertLessThanOrEqual(command.count, 65535)
    }
    func testSessionChunkACKsEventWrapAndNoCommitRetry() throws {
        let command = Data([8,0]) + Data(repeating: 17, count: 2000)
        let transfer = try LargeMessage(command: command, token: 33)
        var replies = [try response(caps, event: 255, command: 126)]
        var event: UInt8 = 255
        var expectedWrites = 1
        for (index, packet) in transfer.packets.enumerated() {
            event = event == 255 ? 1 : event + 1
            let frames = try GMCodec.frames(event: event, service: 15, command: 125,
                                            body: GMTLV(kind: 1, value: packet).encoded(), fragmentPayload: 642)
            expectedWrites += frames.count
            for frame in frames.dropLast() {
                var ack = Data([frame[0],0,0,9,event,15,125])
                let sum = ack.reduce(0) { $0 + Int($1) } & 65535
                ack.append(UInt8(sum >> 8)); ack.append(UInt8(sum & 255)); replies.append(ack)
            }
            replies.append(try response(index == transfer.packets.count - 1 ? "{\"result\":\"ok\"}" : accepted,
                                        event: event, command: 125))
        }
        let io = QueueTransport(replies); var start: UInt8 = 254
        let result = try GMSession(transport: io).sendLargeGraphicsMessage(command, token: 33, event: &start)
        XCTAssertEqual(result.event, event); XCTAssertEqual(io.writes.count, expectedWrites)
        let lost = QueueTransport(Array(replies.dropLast())); start = 254
        XCTAssertThrowsError(try GMSession(transport: lost).sendLargeGraphicsMessage(command, token: 33, event: &start))
        XCTAssertEqual(lost.writes.count, expectedWrites)
    }
    func testFrameSizedChunksWithVerifiedCarrierSendOneFramePerPacket() throws {
        let command = Data([8,0]) + Data((0..<2000).map { UInt8(truncatingIfNeeded: $0 * 7) })
        let transfer = try LargeMessage(command: command, token: 7, chunkBytes: 491)
        XCTAssertEqual(transfer.packets.count, 2 + (command.count + 490) / 491)
        XCTAssertTrue(transfer.packets.allSatisfy { $0.count <= 499 })
        XCTAssertEqual(Data(transfer.packets.dropFirst().dropLast().flatMap { $0.dropFirst(8) }), command)
        for size in [0, 1025] {
            XCTAssertThrowsError(try LargeMessage(command: command, token: 7, chunkBytes: size))
        }
        var event: UInt8 = 10
        var replies = [Data]()
        for index in transfer.packets.indices {
            event += 1
            replies.append(try response(index == transfer.packets.count - 1 ? "{\"result\":\"ok\"}" : accepted,
                                        event: event, command: 125))
        }
        let io = QueueTransport(replies); var start: UInt8 = 10
        let result = try GMSession(transport: io).sendLargeGraphicsMessage(command, token: 7, event: &start,
                                                                           chunkBytes: 491, carrierVerified: true)
        XCTAssertEqual(result.event, event)
        XCTAssertEqual(io.writes.count, transfer.packets.count)
        XCTAssertTrue(io.writes.allSatisfy { $0.count <= 512 && $0[0] == 0xFA && $0[6] == 125 })
    }
    func testUnsupportedCapabilityStopsBeforeBegin() throws {
        let io = QueueTransport([try response(caps.replacingOccurrences(of: "GLASSLYCFW/1", with: "GLASSLYCFW/x"), event: 1, command: 126)])
        var event: UInt8 = 0
        XCTAssertThrowsError(try GMSession(transport: io).sendLargeGraphicsMessage(Data([8,0]), token: 1, event: &event))
        XCTAssertEqual(io.writes.count, 1)
    }
}
