import Foundation

public enum SensorCaptureCommand: UInt8, Sendable {
    case status, start, stop, renew

    public func encoded() -> Data {
        Data([0x53, 0x43, 1, rawValue] + (self == .start ? [3] : []))
    }

    /// Revision 14: a start with an interval makes the glasses sample the light
    /// sensor themselves at that cadence (100...5000 ms, light must be in the
    /// mask) instead of waiting for the stock reader.
    public static func activeStart(mask: UInt8 = 3, intervalMilliseconds: Int) throws -> Data {
        try requireProtocol(mask & 2 != 0 && mask <= 3, "Active light sampling needs the light sensor in the mask")
        try requireProtocol((100 ... 5000).contains(intervalMilliseconds), "Light sampling interval is outside 100...5000 ms")
        return Data([0x53, 0x43, 1, SensorCaptureCommand.start.rawValue, mask,
                     UInt8(intervalMilliseconds & 255), UInt8(intervalMilliseconds >> 8)])
    }
}

public struct SensorVector: Codable, Equatable, Sendable {
    public let x, y, z: Int16
}

public struct IMURegisterSample: Codable, Equatable, Sendable {
    public let sequence, tick, ageTicks: UInt32
    public let fresh: Bool
    public let temperature: Int16
    public let accelerometer, gyroscope: SensorVector
}

public struct AmbientLightSample: Codable, Equatable, Sendable {
    public let sequence, tick, ageTicks: UInt32
    public let fresh: Bool
    public let normalized: UInt16
}

public struct SensorCaptureSnapshot: Codable, Equatable, Sendable {
    public let result: String
    public let activeMask: UInt8
    public let generation, now, deadline: UInt32
    public let imu: IMURegisterSample?
    public let light: AmbientLightSample?

    public static func validateCapability(_ message: GMMessage) throws {
        try requireProtocol(message.service == 15 && message.command == 0x7E && message.tlvs.count == 1 && message.tlvs[0].kind == 5,
                            "Expected sensor capabilities")
        guard let object = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 8192).object,
              object["glassly"]?.string == "graphics-runtime", object["abi"]?.integer == 1,
              let version = object["version"]?.string, version.hasPrefix("GLASSLYCFW/"),
              version.dropFirst(11).utf8.allSatisfy({ (48 ... 57).contains($0) }),
              let revision = UInt32(version.dropFirst(11)), (10 ... 65535).contains(revision),
              let sensor = object["sensors"]?.object, sensor["command"]?.integer == 118, sensor["version"]?.integer == 1,
              sensor["capture"]?.string == "passive-buffered", sensor["capacity"]?.integer == 32, sensor["batch"]?.integer == 4,
              sensor["batchVersion"]?.integer == 2, sensor["finish"]?.integer == 5, sensor["release"]?.integer == 6, sensor["drainTicks"]?.integer == 30000, sensor["imu"]?.string == "icm42670-registers",
              sensor["als"]?.string == "native-0-1000", sensor["leaseTicks"]?.integer == 90000
        else {
            throw MemoMindProtocolError.invalid("Passive sensor capture is unavailable")
        }
    }

    public static func decode(_ message: GMMessage) throws -> Self {
        try requireProtocol(message.service == 15 && message.command == 0x76 && message.tlvs.count == 1 && message.tlvs[0].kind == 5,
                            "Expected sensor capture response")
        guard let o = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 208).object,
              o["glassly"]?.string == "sensors", o["abi"]?.integer == 1,
              let result = o["result"]?.string, ["ok", "invalid", "unavailable", "exhausted", "inactive", "allocation-failed", "schedule-failed"].contains(result),
              let hex = o["stateHex"]?.string else { throw MemoMindProtocolError.invalid("Invalid sensor response") }
        let chars = Array(hex.utf8)
        try requireProtocol(chars.count == 104 && chars.allSatisfy { (48 ... 57).contains($0) || (97 ... 102).contains($0) }, "Invalid sensor state")
        func nibble(_ c: UInt8) -> UInt8 {
            c <= 57 ? c - 48 : c - 87
        }
        let b = stride(from: 0, to: 104, by: 2).map { nibble(chars[$0]) << 4 | nibble(chars[$0 + 1]) }
        func word(_ i: Int) -> UInt32 {
            UInt32(b[i]) | UInt32(b[i + 1]) << 8 | UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
        }
        func signed(_ i: Int) -> Int16 {
            Int16(bitPattern: UInt16(b[i]) << 8 | UInt16(b[i + 1]))
        }
        func vector(_ i: Int) -> SensorVector {
            SensorVector(x: signed(i), y: signed(i + 2), z: signed(i + 4))
        }
        try requireProtocol(Array(b[0 ... 2]) == [0x53, 0x43, 1] && b[3] <= 3 && b[4] & ~b[3] == 0 && b[5] & ~b[4] == 0 && b[6] == 0 && b[7] == 0,
                            "Inconsistent sensor flags")
        let generation = word(8), now = word(12), deadline = word(16)
        let remaining = Int32(bitPattern: deadline &- now)
        try requireProtocol(b[3] == 0 ? deadline == 0 : generation != 0 && remaining > 0 && remaining <= 90000, "Invalid sensor lease")
        var imu: IMURegisterSample?
        var light: AmbientLightSample?
        for (mask, offset, data, length, freshness) in [(UInt8(1), 20, 36, 14, UInt32(1000)), (UInt8(2), 28, 50, 2, UInt32(5000))] {
            if b[4] & mask == 0 {
                try requireProtocol(b[offset ..< offset + 8].allSatisfy { $0 == 0 } && b[data ..< data + length].allSatisfy { $0 == 0 }, "Invalid sensor contains a sample")
                continue
            }
            let sequence = word(offset), tick = word(offset + 4), age = now &- tick
            let fresh = b[5] & mask != 0
            try requireProtocol(sequence != 0 && age <= 0x7FFF_FFFF && fresh == (age <= freshness), "Invalid sensor freshness")
            if mask == 1 {
                imu = IMURegisterSample(sequence: sequence, tick: tick, ageTicks: age, fresh: fresh,
                                        temperature: signed(36), accelerometer: vector(38), gyroscope: vector(44))
            } else {
                let normalized = UInt16(b[50]) | UInt16(b[51]) << 8
                try requireProtocol(normalized <= 1000, "Invalid normalized ambient light")
                light = AmbientLightSample(sequence: sequence, tick: tick, ageTicks: age, fresh: fresh, normalized: normalized)
            }
        }
        return Self(result: result, activeMask: b[3], generation: generation, now: now, deadline: deadline, imu: imu, light: light)
    }
}

public extension GMSession {
    /// Starts a capture with active light sampling (revision 14 `activeAls`).
    func sensorCaptureActiveStart(mask: UInt8 = 3, intervalMilliseconds: Int, event: inout UInt8) throws -> SensorCaptureSnapshot {
        let body = try SensorCaptureCommand.activeStart(mask: mask, intervalMilliseconds: intervalMilliseconds)
        event = event == 255 ? 1 : event + 1
        let state = try SensorCaptureSnapshot.decode(request(event: event, service: 15, command: 0x76,
                                                             body: GMTLV(kind: 1, value: body).encoded()))
        try requireProtocol(state.result == "ok", "Sensor control refused: \(state.result)")
        try requireProtocol(state.activeMask == mask, "Sensor capture did not restart")
        return state
    }

    func sensorCapture(_ command: SensorCaptureCommand, event: inout UInt8) throws -> SensorCaptureSnapshot {
        event = event == 255 ? 1 : event + 1
        let state = try SensorCaptureSnapshot.decode(request(event: event, service: 15, command: 0x76,
                                                             body: GMTLV(kind: 1, value: command.encoded()).encoded()))
        try requireProtocol(state.result == "ok", "Sensor control refused: \(state.result)")
        if command == .stop {
            try requireProtocol(state.activeMask == 0, "Sensor capture did not stop")
        }
        if command == .start {
            try requireProtocol(state.activeMask == 3, "Sensor capture did not restart")
        }
        if command == .renew {
            try requireProtocol(state.activeMask != 0, "Sensor capture lease is inactive")
        }
        return state
    }
}
