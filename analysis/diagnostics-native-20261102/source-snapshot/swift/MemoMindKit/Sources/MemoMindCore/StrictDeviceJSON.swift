import Foundation

/// Small device-response JSON grammar. Unlike JSONDecoder keyed containers, this
/// rejects duplicate keys (including escaped spellings) before dictionary creation.
/// The supported wire schemas contain only exact integers, never floats/exponents.
indirect enum StrictDeviceJSON: Equatable {
    case object([String: StrictDeviceJSON]), array([StrictDeviceJSON])
    case string(String), integer(Int64), bool(Bool), null

    static func decode(_ data: Data, maximumBytes: Int = 768) throws -> StrictDeviceJSON {
        guard data.count <= maximumBytes else { throw FixedCanaryError.protocolViolation("JSON exceeds bounded response length") }
        var bytes = Array(data)
        if bytes.last == 0 {
            bytes.removeLast()
        } // Exactly one optional NUL, as on native wire.
        guard String(bytes: bytes, encoding: .utf8) != nil else { throw FixedCanaryError.protocolViolation("Malformed UTF-8") }
        var parser = StrictDeviceJSONParser(bytes: bytes)
        let value = try parser.value(depth: 0)
        parser.whitespace()
        guard parser.offset == bytes.count else { throw FixedCanaryError.protocolViolation("Trailing JSON bytes") }
        return value
    }

    var object: [String: StrictDeviceJSON]? {
        if case let .object(value) = self {
            return value
        }; return nil
    }

    var array: [StrictDeviceJSON]? {
        if case let .array(value) = self {
            return value
        }; return nil
    }

    var string: String? {
        if case let .string(value) = self {
            return value
        }; return nil
    }

    var integer: Int64? {
        if case let .integer(value) = self {
            return value
        }; return nil
    }

    var boolean: Bool? {
        if case let .bool(value) = self {
            return value
        }; return nil
    }
}

private struct StrictDeviceJSONParser {
    let bytes: [UInt8]
    var offset = 0
    mutating func whitespace() {
        while offset < bytes.count, [9, 10, 13, 32].contains(bytes[offset]) {
            offset += 1
        }
    }

    mutating func consume(_ byte: UInt8) -> Bool {
        if offset < bytes.count, bytes[offset] == byte {
            offset += 1; return true
        }
        return false
    }

    func invalid() -> FixedCanaryError {
        .protocolViolation("Malformed or unsupported device JSON")
    }

    mutating func literal(_ text: String, _ result: StrictDeviceJSON) throws -> StrictDeviceJSON {
        let expected = Array(text.utf8)
        guard bytes.count - offset >= expected.count,
              Array(bytes[offset ..< (offset + expected.count)]) == expected else { throw invalid() }
        offset += expected.count
        return result
    }

    mutating func string() throws -> String {
        let start = offset
        guard consume(34) else { throw invalid() }
        var escaped = false
        while offset < bytes.count {
            let byte = bytes[offset]; offset += 1
            if escaped {
                escaped = false; continue
            }
            if byte == 92 {
                escaped = true; continue
            }
            if byte == 34 {
                do { return try JSONDecoder().decode(String.self, from: Data(bytes[start ..< offset])) }
                catch { throw invalid() }
            }
            if byte < 32 {
                throw invalid()
            }
        }
        throw invalid()
    }

    mutating func value(depth: Int) throws -> StrictDeviceJSON {
        guard depth <= 24 else { throw invalid() }
        whitespace()
        guard offset < bytes.count else { throw invalid() }
        switch bytes[offset] {
        case 123:
            offset += 1; whitespace()
            var object = [String: StrictDeviceJSON]()
            if consume(125) {
                return .object(object)
            }
            while true {
                whitespace(); let key = try string(); whitespace()
                guard object[key] == nil, consume(58) else { throw invalid() }
                object[key] = try value(depth: depth + 1); whitespace()
                if consume(125) {
                    return .object(object)
                }
                guard consume(44) else { throw invalid() }
            }
        case 91:
            offset += 1; whitespace()
            var array = [StrictDeviceJSON]()
            if consume(93) {
                return .array(array)
            }
            while true {
                try array.append(value(depth: depth + 1)); whitespace()
                if consume(93) {
                    return .array(array)
                }
                guard consume(44) else { throw invalid() }
            }
        case 34: return try .string(string())
        case 116: return try literal("true", .bool(true))
        case 102: return try literal("false", .bool(false))
        case 110: return try literal("null", .null)
        case 45, 48 ... 57:
            let start = offset
            _ = consume(45)
            guard offset < bytes.count else { throw invalid() }
            if !consume(48) {
                guard (49 ... 57).contains(bytes[offset]) else { throw invalid() }
                while offset < bytes.count, (48 ... 57).contains(bytes[offset]) {
                    offset += 1
                }
            }
            guard offset == bytes.count || !([46, 69, 101] + Array(48 ... 57)).contains(bytes[offset]),
                  let number = Int64(String(decoding: bytes[start ..< offset], as: UTF8.self)) else { throw invalid() }
            return .integer(number)
        default: throw invalid()
        }
    }
}
