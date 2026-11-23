import Foundation

public enum MicrophoneCommand: UInt8, Sendable {
    case start = 1, status, stop, renew

    public func encoded() -> Data {
        var data = Data([0x4D, 0x43, 1, rawValue])
        if self == .start {
            data.append(contentsOf: [0, 1, 3, 0, 160, 0, 160, 0, 2])
        }
        return data
    }
}

public struct MicrophoneSnapshot: Equatable, Sendable {
    public let result: String
    public let serial, completed, frames, nativeStatus: UInt32
    public let pending, active, streaming, nativeActive: Bool
    public let phase, error: UInt8

    public static func decode(_ message: GMMessage) throws -> Self {
        try requireProtocol(message.service == 15 && message.command == 0x77 && message.tlvs.count == 1 && message.tlvs[0].kind == 5,
                            "Expected microphone response")
        guard let o = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 320).object,
              o["glassly"]?.string == "microphone", o["abi"]?.integer == 1,
              let result = o["result"]?.string, ["ok", "queued", "busy", "invalid", "unsupported", "unavailable", "queue-failed"].contains(result),
              let hex = o["stateHex"]?.string else { throw MemoMindProtocolError.invalid("Invalid microphone response") }
        func uint(_ key: String, maximum: UInt32 = .max) throws -> UInt32 {
            guard let n = o[key]?.integer, let value = UInt32(exactly: n), value <= maximum else {
                throw MemoMindProtocolError.invalid("Invalid microphone \(key)")
            }
            return value
        }
        let chars = Array(hex.utf8)
        try requireProtocol(chars.count == 42 && chars.allSatisfy { (48 ... 57).contains($0) || (97 ... 102).contains($0) }, "Invalid microphone state")
        func nibble(_ c: UInt8) -> UInt8 {
            c <= 57 ? c - 48 : c - 87
        }
        let b = stride(from: 0, to: 42, by: 2).map { nibble(chars[$0]) << 4 | nibble(chars[$0 + 1]) }
        try requireProtocol(Array(b[0 ... 2]) == [0x4D, 0x43, 1] && b[3] <= 1 &&
            Array(b[4 ... 11]) == [0, 1, 3, 0, 160, 0, 160, 0] && [0, 2].contains(b[12]) && b[13] <= 1 &&
            b[14] == 1 && Array(b[19 ... 20]) == [160, 0] && (b[13] == 0 || b[3] == 1 && b[12] == 2), "Unsupported microphone state")
        let serial = try uint("serial"), completed = try uint("completed"), pending = try uint("pending", maximum: 1)
        let nativeActive = try uint("nativeActive", maximum: 1)
        try requireProtocol(completed <= serial && (pending == 0 ? completed == serial : completed < serial) &&
            (b[13] == 0 || nativeActive == 1), "Inconsistent microphone state")
        return try Self(result: result, serial: serial, completed: completed,
                        frames: UInt32(b[15]) | UInt32(b[16]) << 8 | UInt32(b[17]) << 16 | UInt32(b[18]) << 24,
                        nativeStatus: uint("nativeStatus"), pending: pending != 0, active: b[3] != 0,
                        streaming: b[13] != 0, nativeActive: nativeActive != 0,
                        phase: UInt8(uint("phase", maximum: 5)), error: UInt8(uint("error", maximum: 11)))
    }
}

public extension GMSession {
    func microphone(_ command: MicrophoneCommand, event: inout UInt8) throws -> MicrophoneSnapshot {
        func requestControl(_ operation: MicrophoneCommand, event: inout UInt8) throws -> MicrophoneSnapshot {
            event = event == 255 ? 1 : event + 1
            return try MicrophoneSnapshot.decode(request(event: event, service: 15, command: 0x77,
                                                         body: GMTLV(kind: 1, value: operation.encoded()).encoded()))
        }
        var state = try requestControl(command, event: &event)
        if command == .status {
            return state
        }
        try requireProtocol(state.result == "queued", "Microphone control refused: \(state.result)")
        let serial = state.serial
        let deadline = monotonicNow() + 7
        while monotonicNow() < deadline {
            if state.completed == serial && !state.pending {
                if command == .stop {
                    if !state.nativeActive && !state.active && state.phase == 0 {
                        return state
                    }
                } else {
                    try requireProtocol(state.error == 0, "Microphone control failed: \(state.error)")
                    if state.active && state.streaming && state.phase == 3 {
                        return state
                    }
                }
            }
            Thread.sleep(forTimeInterval: 0.05)
            state = try requestControl(.status, event: &event)
            try requireProtocol(state.result == "ok" && state.serial == serial, "Microphone ownership changed")
        }
        throw MemoMindProtocolError.timeout("Microphone control did not complete")
    }
}
