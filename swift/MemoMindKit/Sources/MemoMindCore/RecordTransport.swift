import Foundation
import zlib

public struct GraphicsRecord {
    public let packets: [Data]
    public let streamID: UInt8
    public let checksum: UInt16
    public let decodedBytes: Int

    public static func crc16(_ data: Data) -> UInt16 {
        var crc: UInt16 = 0xFFFF
        for byte in data {
            crc ^= UInt16(byte) << 8
            for _ in 0 ..< 8 {
                crc = (crc &<< 1) ^ (crc & 0x8000 == 0 ? 0 : 0x1021)
            }
        }
        return crc
    }

    public init(command: Data, compressed: Data? = nil, resetContext: Bool, sequence: UInt8) throws {
        try requireProtocol(!command.isEmpty && command.count <= 65535 && command.first != 126 && command.first != 127,
                            "Invalid record command")
        let wire = compressed ?? command
        try requireProtocol(!wire.isEmpty && wire.count <= 65535, "Record wire length exceeds capacity")
        if compressed != nil {
            try requireProtocol(wire.suffix(4) == Data([0, 0, 255, 255]), "Compressed record needs SYNC_FLUSH")
        }
        checksum = Self.crc16(command); streamID = sequence; decodedBytes = command.count
        let flags: UInt8 = 1 | (compressed == nil ? 0 : 4) | (resetContext ? 8 : 0)
        let record = Data([flags, UInt8(truncatingIfNeeded: wire.count), UInt8(truncatingIfNeeded: wire.count >> 8),
                           UInt8(truncatingIfNeeded: checksum), UInt8(truncatingIfNeeded: checksum >> 8)]) + wire
        packets = stride(from: 0, to: record.count, by: 128).enumerated().map { index, offset in
            let end = min(offset + 128, record.count)
            let packetFlags: UInt8 = 1 | (offset == 0 ? 128 : 0) | (end == record.count ? 64 : 0)
            return Data([126, 1, sequence &+ UInt8(truncatingIfNeeded: index), packetFlags]) + record[offset ..< end]
        }
    }
}

final class RecordDeflater {
    private let stream = UnsafeMutablePointer<z_stream>.allocate(capacity: 1)
    private var initialized = false

    init() throws {
        stream.initialize(to: z_stream())
        let result = deflateInit_(stream, Z_DEFAULT_COMPRESSION, zlibVersion(), Int32(MemoryLayout<z_stream>.size))
        initialized = result == Z_OK
        try requireProtocol(initialized, "Could not initialize record compression")
    }

    deinit {
        if initialized {
            deflateEnd(stream)
        }
        stream.deinitialize(count: 1); stream.deallocate()
    }

    func reset() throws {
        try requireProtocol(deflateReset(stream) == Z_OK, "Could not reset record compression")
    }

    func encode(_ data: Data) throws -> Data {
        try requireProtocol(!data.isEmpty && data.count <= 65535, "Invalid compression input length")
        var output = Data(count: 65536)
        defer {
            stream.pointee.next_in = nil; stream.pointee.next_out = nil
            stream.pointee.avail_in = 0; stream.pointee.avail_out = 0
        }
        let result = data.withUnsafeBytes { input in
            output.withUnsafeMutableBytes { buffer in
                stream.pointee.next_in = UnsafeMutablePointer(mutating: input.bindMemory(to: UInt8.self).baseAddress!)
                stream.pointee.avail_in = UInt32(data.count)
                stream.pointee.next_out = buffer.bindMemory(to: UInt8.self).baseAddress!
                stream.pointee.avail_out = 65536
                return deflate(stream, Z_SYNC_FLUSH)
            }
        }
        try requireProtocol(result == Z_OK && stream.pointee.avail_in == 0 && stream.pointee.avail_out > 0,
                            "Compressed record exceeds wire capacity")
        output.count = 65536 - Int(stream.pointee.avail_out)
        return output
    }
}

/// Serialized session; any failed or ambiguous send poisons it. No automatic retries.
public final class GraphicsRecordSession {
    private let session: GMSession
    private let deflater: RecordDeflater
    private var sequence: UInt8
    private var resetContext = true
    private var checked = false
    private var usable = true
    private var lastSend = 0.0

    public init(session: GMSession, sequence: UInt8 = 0) throws {
        self.session = session; self.sequence = sequence; deflater = try RecordDeflater()
    }

    private func json(_ message: GMMessage) throws -> Data {
        try requireProtocol(message.tlvs.count == 1 && message.tlvs[0].kind == 5, "Expected record JSON")
        var data = message.tlvs[0].value
        while data.last == 0 {
            data.removeLast()
        }
        return data
    }

    private func capability(event: inout UInt8) throws {
        struct Capability: Decodable {
            struct Carrier: Decodable {
                let mode, version, maxPacketBytes, maxRecordBytes, replyCapacity, endpoint, leaseTicks: Int
            }

            let recordTransport: Carrier
        }
        event = event == 255 ? 1 : event + 1
        let reply = try session.request(event: event, service: 15, command: 126)
        let c = try JSONDecoder().decode(Capability.self, from: json(reply)).recordTransport
        try requireProtocol(c.mode == 126 && c.version == 1 && c.maxPacketBytes == 128 && c.maxRecordBytes == 65535 &&
            c.replyCapacity == 64 && c.endpoint == 1 && c.leaseTicks == 30000, "Unsupported record carrier")
        checked = true
    }

    @discardableResult
    public func send(_ command: Data, compressed: Bool = true, event: inout UInt8) throws -> Data? {
        try requireProtocol(usable, "Record session is unusable after a failed send")
        do {
            if !checked {
                try capability(event: &event)
            }
            if !compressed || ProcessInfo.processInfo.systemUptime - lastSend >= 25 {
                try deflater.reset(); resetContext = true
            }
            let wire = compressed ? try deflater.encode(command) : nil
            let record = try GraphicsRecord(command: command, compressed: wire, resetContext: resetContext, sequence: sequence)
            struct Batch: Decodable {
                let glassly: String
                let abi, status, closing: Int
                let frames: [String]
            }
            var dataReply: Data?
            for (index, packet) in record.packets.enumerated() {
                event = event == 255 ? 1 : event + 1
                let response = try session.request(event: event, service: 15, command: 125,
                                                   body: GMTLV(kind: 1, value: packet).encoded(), responseFilter: { message in
                                                       struct Kind: Decodable { let result: String? }
                                                       return try JSONDecoder().decode(Kind.self, from: self.json(message)).result != "settled"
                                                   })
                let batch = try JSONDecoder().decode(Batch.self, from: json(response))
                try requireProtocol(batch.glassly == "record-transport" && batch.abi == 1 && batch.status == 0 &&
                    (0 ... 1).contains(batch.closing) && batch.frames.count <= 2, "Record packet refused")
                let frames = try batch.frames.map { hex -> Data in
                    try requireProtocol(hex.count % 2 == 0 && hex.count >= 10 && hex.count <= 128, "Invalid record reply length")
                    let chars = Array(hex.utf8)
                    var bytes = Data()
                    for offset in stride(from: 0, to: chars.count, by: 2) {
                        guard let value = UInt8(String(decoding: chars[offset ..< offset + 2], as: UTF8.self), radix: 16) else {
                            throw MemoMindProtocolError.invalid("Invalid record reply hex")
                        }
                        bytes.append(value)
                    }
                    return bytes
                }
                if index != record.packets.count - 1 {
                    try requireProtocol(frames.isEmpty && batch.closing == 0, "Early record completion or rejection")
                    continue
                }
                try requireProtocol(!frames.isEmpty, "Missing record ACK")
                for (i, frame) in frames.enumerated() {
                    try requireProtocol(frame[1] == record.streamID && frame[2] == 0 && frame[3] == 0 && frame[4] == 1,
                                        "Uncorrelated record reply")
                    if i == frames.count - 1 {
                        try requireProtocol(frame[0] == 1 && frame.count >= 9 && frame.count <= 30 && (frame.count - 9) % 7 == 0,
                                            "Record rejected or malformed ACK")
                        try requireProtocol(Int(frame[5]) | Int(frame[6]) << 8 == command.count &&
                            UInt16(frame[7]) | UInt16(frame[8]) << 8 == record.checksum, "Record ACK length/CRC differs")
                    } else {
                        try requireProtocol(frame[0] == 5 && frame.count > 5, "Invalid record data reply")
                        dataReply = Data(frame.dropFirst(5))
                    }
                }
                resetContext = batch.closing != 0
                if resetContext {
                    try deflater.reset()
                }
            }
            sequence &+= UInt8(truncatingIfNeeded: record.packets.count)
            lastSend = ProcessInfo.processInfo.systemUptime
            return dataReply
        } catch {
            usable = false
            throw error
        }
    }
}
