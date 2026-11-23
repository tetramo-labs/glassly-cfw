import Foundation

public enum OwnershipCommand: UInt8, CaseIterable, Sendable {
    case status, acquireWake, releaseWake, claim, ready, acquireFrame, releaseFrame

    public func encoded(nonce: UInt16 = 1) throws -> Data {
        Data([0x46, 0x43, 1, rawValue, UInt8(truncatingIfNeeded: nonce), UInt8(nonce >> 8)])
    }
}

public struct OwnershipSnapshot: Equatable, Encodable, Sendable {
    public enum Event: UInt8, Encodable, Sendable { case wake = 1, press, longPress, release }
    public let wakeLease: Bool
    public let frameLease: Bool
    public let pending: Bool
    public let nonce: UInt16
    public let screenOn: Bool
    public let powerBlocked: Bool
    public let framePresented: Bool
    public let event: Event?

    public static func decode(_ message: GMMessage) throws -> Self {
        try requireProtocol(message.service == 15 && message.command == 0x79 && message.tlvs.count == 1 && message.tlvs[0].kind == 5,
                            "Expected ownership response")
        guard let o = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 256).object,
              o["glassly"]?.string == "ownership", o["abi"]?.integer == 1,
              let result = o["result"]?.string, result == "ok" || result == "event",
              let hex = o["stateHex"]?.string
        else {
            throw MemoMindProtocolError.invalid("Ownership request refused or invalid response")
        }
        let chars = Array(hex.utf8)
        try requireProtocol(chars.count == 18 && chars.allSatisfy { (48 ... 57).contains($0) || (97 ... 102).contains($0) },
                            "Invalid ownership snapshot")
        func nibble(_ c: UInt8) -> UInt8 {
            c <= 57 ? c - 48 : c - 87
        }
        let b = stride(from: 0, to: 18, by: 2).map { nibble(chars[$0]) << 4 | nibble(chars[$0 + 1]) }
        let nonce = UInt16(b[3]) | UInt16(b[4]) << 8
        try requireProtocol([0, 1, 2, 5, 6, 7].allSatisfy { b[$0] <= 1 } && b[8] <= 4 &&
            (b[2] == 0 ? nonce == 0 : b[0] == 1) && (b[7] == 0 || b[1] == 1) &&
            (result == "event" ? (message.event == 0 && b[8] != 0 && b[0] == 1) : b[8] == 0),
            "Inconsistent ownership state")
        return Self(wakeLease: b[0] != 0, frameLease: b[1] != 0, pending: b[2] != 0, nonce: nonce,
                    screenOn: b[5] != 0, powerBlocked: b[6] != 0, framePresented: b[7] != 0,
                    event: Event(rawValue: b[8]))
    }
}

public extension GMSession {
    func ownership(_ command: OwnershipCommand, nonce: UInt16 = 1, event: inout UInt8) throws -> OwnershipSnapshot {
        let body = try GMTLV(kind: 1, value: command.encoded(nonce: nonce)).encoded()
        event = event == 255 ? 1 : event + 1
        return try OwnershipSnapshot.decode(request(event: event, service: 15, command: 0x79, body: body))
    }
}
