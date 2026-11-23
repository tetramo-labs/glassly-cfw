import Foundation

/// A connected byte stream. Reads may return partial or multiple protocol frames.
/// Throw on EOF; callers never retry an ambiguous write or transaction.
public protocol MemoMindTransport: AnyObject {
    func read(timeout: TimeInterval) throws -> Data
    func write(_ data: Data) throws
}

public enum MemoMindProtocolError: Error, CustomStringConvertible, LocalizedError {
    public var errorDescription: String? {
        description
    }

    case invalid(String)
    case timeout(String)
    case stopped(phase: String, reason: String)
    public var description: String {
        switch self {
        case let .invalid(reason): reason
        case let .timeout(reason): reason
        case let .stopped(phase, reason):
            "Stopped during \(phase): \(reason). No retry was sent; device state may be ambiguous. Close connection and inspect logs."
        }
    }
}

func requireProtocol(_ condition: Bool, _ reason: String) throws {
    if !condition {
        throw MemoMindProtocolError.invalid(reason)
    }
}

func beBytes(_ value: UInt32, _ count: Int) -> [UInt8] {
    (0 ..< count).reversed().map { UInt8(truncatingIfNeeded: value >> ($0 * 8)) }
}

func readBE(_ bytes: ArraySlice<UInt8>) -> UInt32 {
    bytes.reduce(0) { ($0 << 8) | UInt32($1) }
}

func monotonicNow() -> TimeInterval {
    ProcessInfo.processInfo.systemUptime
}

public struct GMTLV: Equatable {
    public let kind: UInt8
    public let value: Data
    public init(kind: UInt8, value: Data) {
        self.kind = kind; self.value = value
    }

    public func encoded() throws -> Data {
        try requireProtocol(value.count <= 0xFFFFFF, "GM TLV exceeds wire length")
        return Data([kind] + beBytes(UInt32(value.count), 3)) + value
    }
}

public struct GMMessage: Equatable {
    public let head: UInt8
    public let event: UInt8
    public let service: UInt8
    public let command: UInt8
    public let body: Data
    public let tlvs: [GMTLV]
    func matches(_ event: UInt8, _ service: UInt8, _ command: UInt8) -> Bool {
        self.event == event && self.service == service && self.command == command
    }
}

public enum GMCodec {
    public static let maximumLogicalLength = 80 * 1024
    /// Default/public body is 503 bytes. H001Y ingress explicitly uses 642.
    public static func frames(event: UInt8, service: UInt8, command: UInt8,
                              body: Data = Data(), fragmentPayload: Int = 503) throws -> [Data]
    {
        try requireProtocol(fragmentPayload == 503 || fragmentPayload == 642,
                            "Unsupported GM fragment payload profile")
        try requireProtocol(body.count <= maximumLogicalLength - 9, "GM logical message exceeds documented limit")
        let bytes = Array(body), logical = bytes.count + 9
        return stride(from: 0, to: max(1, bytes.count), by: fragmentPayload).enumerated().map { index, offset in
            var packet = [UInt8(index == 0 ? 0xFA : index)] + beBytes(UInt32(logical), 3)
            packet += [event, service, command]
            packet += bytes[offset ..< min(offset + fragmentPayload, bytes.count)]
            let checksum = packet.reduce(UInt32(0)) { $0 + UInt32($1) } & 0xFFFF
            packet += beBytes(checksum, 2)
            return Data(packet)
        }
    }

    public static func parseTLVs(_ data: Data) throws -> [GMTLV] {
        let bytes = Array(data)
        var offset = 0, result = [GMTLV]()
        while offset < bytes.count {
            try requireProtocol(bytes.count - offset >= 4, "Truncated GM TLV header")
            let kind = bytes[offset], length = Int(readBE(bytes[(offset + 1) ..< (offset + 4)]))
            offset += 4
            try requireProtocol(length <= bytes.count - offset, "Truncated GM TLV value")
            if let fixed = [UInt8(3): 4, 6: 1, 7: 2, 8: 1][kind] {
                try requireProtocol(length == fixed, "Invalid fixed-width GM TLV")
            }
            result.append(GMTLV(kind: kind, value: Data(bytes[offset ..< (offset + length)])))
            offset += length
        }
        return result
    }
}

/// Reply-side 503-byte fragments; accepts legacy repeated FA only when requested.
public final class GMStream {
    public let legacyRepeatFA: Bool
    public let fragmentACKs: Bool
    private var buffer = [UInt8](), body = [UInt8]()
    private var key: [UInt32]?
    private var fragment = 0
    public init(legacyRepeatFA: Bool = false, fragmentACKs: Bool = false) {
        self.legacyRepeatFA = legacyRepeatFA; self.fragmentACKs = fragmentACKs
    }

    public func reset() {
        buffer.removeAll(); body.removeAll(); key = nil; fragment = 0
    }

    public func feed(_ data: Data) throws -> [GMMessage] {
        buffer += data
        var messages = [GMMessage]()
        do {
            while buffer.count >= 7 {
                let head = buffer[0], logical = Int(readBE(buffer[1 ..< 4]))
                let nextKey = [UInt32(logical), UInt32(buffer[4]), UInt32(buffer[5]), UInt32(buffer[6])]
                try requireProtocol((9 ... GMCodec.maximumLogicalLength).contains(logical), "Invalid GM logical length")
                let ack = fragmentACKs && logical == 9 && (head == 0xFA || (head >= 1 && head < 0xF0))
                let repeated = legacyRepeatFA && key == nextKey && head == 0xFA
                let first = head == 0xFA && !repeated
                if !ack && !first {
                    try requireProtocol(key == nextKey && (Int(head) == fragment || repeated),
                                        "GM continuation identity or order mismatch")
                }
                let physical = ack ? 9 : min(512, logical - (first ? 0 : body.count))
                try requireProtocol(physical >= 9, "Invalid GM continuation length")
                if buffer.count < physical {
                    break
                }
                let packet = Array(buffer.prefix(physical))
                let checksum = packet.dropLast(2).reduce(UInt32(0)) { $0 + UInt32($1) } & 0xFFFF
                try requireProtocol(checksum == readBE(packet[(physical - 2) ..< physical]), "GM additive checksum mismatch")
                buffer.removeFirst(physical)
                if ack {
                    messages.append(GMMessage(head: head, event: UInt8(nextKey[1]), service: UInt8(nextKey[2]), command: UInt8(nextKey[3]), body: Data(), tlvs: []))
                    continue
                }
                if first {
                    key = nextKey; body.removeAll(); fragment = 0
                }
                body += packet[7 ..< (physical - 2)]
                fragment += 1
                if body.count == logical - 9 {
                    let data = Data(body)
                    try messages.append(GMMessage(head: head, event: UInt8(nextKey[1]), service: UInt8(nextKey[2]), command: UInt8(nextKey[3]), body: data, tlvs: GMCodec.parseTLVs(data)))
                    body.removeAll(); key = nil; fragment = 0
                }
            }
            return messages
        } catch { reset(); throw error }
    }
}

public enum OTACodec {
    public static func frame(command: UInt8, sequence: UInt8, parameters: Data = Data(), flags: UInt8 = 0xC0) throws -> Data {
        try requireProtocol(parameters.count <= 65534, "Payload exceeds wire length field")
        return Data([0x70, 0x07, 0x6E, flags, command] + beBytes(UInt32(parameters.count + 1), 2) + [sequence]) + parameters + Data([0x33])
    }

    /// RFC1952/zlib CRC32, initial and final XOR FFFFFFFF.
    public static func crc32(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFF_FFFF
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0 ..< 8 {
                crc = (crc >> 1) ^ (crc & 1 == 0 ? 0 : 0xEDB8_8320)
            }
        }
        return crc ^ 0xFFFF_FFFF
    }

    public static func chunk(sequence: UInt8, offset: UInt32, data: Data) throws -> Data {
        try requireProtocol(data.count <= 630, "Chunk length outside observed format")
        return try frame(command: 0xE5, sequence: sequence,
                         parameters: Data(beBytes(offset, 4)) + data + Data(beBytes(crc32(data), 4)))
    }
}

public final class OTAStream {
    private var buffer = [UInt8]()
    public var bufferedByteCount: Int {
        buffer.count
    }

    public init() {}
    public func feed(_ data: Data) throws -> [Data] {
        buffer += data
        var frames = [Data]()
        while buffer.count >= 7 {
            try requireProtocol(Array(buffer.prefix(3)) == [0x70, 7, 0x6E], "Unrecognized prefix in OTA stream; refusing resynchronization")
            let total = Int(readBE(buffer[5 ..< 7])) + 8
            if buffer.count < total {
                break
            }
            try requireProtocol(buffer[total - 1] == 0x33, "Invalid OTA frame footer")
            frames.append(Data(buffer.prefix(total)))
            buffer.removeFirst(total)
        }
        return frames
    }
}
