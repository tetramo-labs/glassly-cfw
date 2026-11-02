import Foundation

/// Bounded carrier for one raw G2 command. Assembly is volatile and owned by the
/// glasses' display lease. Commit consumes the token before command execution;
/// a lost commit response is ambiguous and must never be retried automatically.
public struct LargeMessage {
    public static let maximumBytes = 65535
    public static let chunkBytes = 1024
    public let token: UInt32
    public let packets: [Data]
    public init(command: Data, token: UInt32) throws {
        try requireProtocol(token != 0 && !command.isEmpty && command.count <= Self.maximumBytes,
                            "Large message requires a nonzero token and 1...65535 command bytes")
        try requireProtocol(command.first != 127, "Nested large-message carriers are invalid")
        self.token = token
        func header(_ operation: UInt8) -> Data {
            Data([127, operation] + (0..<4).map { UInt8(truncatingIfNeeded: token >> ($0 * 8)) })
        }
        func little16(_ n: Int) -> Data { Data([UInt8(truncatingIfNeeded: n), UInt8(truncatingIfNeeded: n >> 8)]) }
        var result = [header(0) + little16(command.count)]
        for offset in stride(from: 0, to: command.count, by: Self.chunkBytes) {
            let start = command.startIndex + offset
            result.append(header(1) + little16(offset) + command[start..<min(start + Self.chunkBytes, command.endIndex)])
        }
        let crc = OTACodec.crc32(command)
        result.append(header(2) + Data((0..<4).map { UInt8(truncatingIfNeeded: crc >> ($0 * 8)) }))
        packets = result
    }
    public var abort: Data { Data([127, 3] + (0..<4).map { UInt8(truncatingIfNeeded: token >> ($0 * 8)) }) }
}

public extension GMSession {
    /// Caller serializes this session and supplies fresh nonzero tokens. Returns
    /// the actual command reply after all chunks have been acknowledged. Does
    /// not retry, abort after timeout, or interpret a queued frame as completion.
    func sendLargeGraphicsMessage(_ command: Data, token: UInt32, event: inout UInt8) throws -> GMMessage {
        let transfer = try LargeMessage(command: command, token: token)
        event = event == 255 ? 1 : event + 1
        let probe = try request(event: event, service: 15, command: 0x7e)
        struct Capability: Decodable {
            let version: String
            let maxMessageBytes: Int
            let largeMessage: Carrier
            struct Carrier: Decodable { let mode: Int; let chunkBytes: Int; let crc: String }
        }
        func json(_ message: GMMessage) throws -> Data {
            try requireProtocol(message.tlvs.count == 1 && message.tlvs[0].kind == 5, "Expected one JSON response")
            var data = message.tlvs[0].value
            while data.last == 0 { data.removeLast() }
            return data
        }
        let cap = try JSONDecoder().decode(Capability.self, from: json(probe))
        let revision = cap.version.split(separator: "/", omittingEmptySubsequences: false)
        try requireProtocol(revision.count == 2 && revision[0] == "GLASSLYCFW" &&
                            !revision[1].isEmpty && revision[1].utf8.allSatisfy { (48...57).contains($0) } &&
                            cap.maxMessageBytes == 65535 && cap.largeMessage.mode == 127 &&
                            cap.largeMessage.chunkBytes == 1024 && cap.largeMessage.crc == "crc32-ieee",
                            "Firmware does not advertise the bounded large-message carrier")
        for (index, packet) in transfer.packets.enumerated() {
            event = event == 255 ? 1 : event + 1
            let reply = try request(event: event, service: 15, command: 0x7d,
                                    body: GMTLV(kind: 1, value: packet).encoded(), responseFilter: { message in
                struct Result: Decodable { let result: String }
                return try JSONDecoder().decode(Result.self, from: json(message)).result != "settled"
            })
            if index == transfer.packets.count - 1 { return reply }
            try requireProtocol(json(reply) == Data("{\"glassly\":\"large-message\",\"abi\":1,\"result\":\"accepted\"}".utf8),
                                "Large-message chunk was not accepted")
        }
        throw MemoMindProtocolError.invalid("Missing commit response")
    }
}
