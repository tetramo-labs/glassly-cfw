import Foundation

public struct SensorBufferedSample: Codable, Equatable, Sendable {
    public let sequence, tick, ageTicks: UInt32
    public let imu: IMURegisterSample?
    public let light: AmbientLightSample?
}

public enum SensorCapturePhase: UInt8, Codable, Sendable {
    case inactive, capturing, draining
}

public struct SensorBatch: Codable, Equatable, Sendable {
    public let result: String
    public let activeMask: UInt8
    public let phase: SensorCapturePhase
    public let generation, now, acknowledged, sequence, drops: UInt32
    public let pending: Int
    public let samples: [SensorBufferedSample]

    public static func command(generation: UInt32, acknowledged: UInt32, finish: Bool = false) throws -> Data {
        try requireProtocol(generation != 0, "Invalid sensor generation")
        var b = Data([83, 67, 1, finish ? 5 : 4])
        for n in [generation, acknowledged] {
            for i in 0 ..< 4 {
                b.append(UInt8(truncatingIfNeeded: n >> (i * 8)))
            }
        }
        return b
    }

    public static func decode(_ message: GMMessage) throws -> Self {
        try requireProtocol(message.service == 15 && message.command == 118 && message.tlvs.count == 1 && message.tlvs[0].kind == 5,
                            "Expected sensor batch")
        guard let o = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 384).object,
              o["glassly"]?.string == "sensor-batch", o["abi"]?.integer == 2,
              let result = o["result"]?.string, ["ok", "released", "invalid", "inactive", "stale"].contains(result),
              let hex = o["stateHex"]?.string else { throw MemoMindProtocolError.invalid("Invalid sensor batch") }
        let chars = Array(hex.utf8)
        try requireProtocol((56 ... 248).contains(chars.count) && chars.count % 2 == 0 &&
            chars.allSatisfy { (48 ... 57).contains($0) || (97 ... 102).contains($0) }, "Invalid batch hex")
        func nibble(_ c: UInt8) -> UInt8 {
            c <= 57 ? c - 48 : c - 87
        }
        let b = stride(from: 0, to: chars.count, by: 2).map { nibble(chars[$0]) << 4 | nibble(chars[$0 + 1]) }
        func word(_ i: Int) -> UInt32 {
            UInt32(b[i]) | UInt32(b[i + 1]) << 8 | UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
        }
        func signed(_ i: Int) -> Int16 {
            Int16(bitPattern: UInt16(b[i]) << 8 | UInt16(b[i + 1]))
        }
        func vector(_ i: Int) -> SensorVector {
            SensorVector(x: signed(i), y: signed(i + 2), z: signed(i + 4))
        }
        let active = b[3], generation = word(4), now = word(8), ack = word(12), sequence = word(16), drops = word(20)
        let pending = Int(b[24]), count = Int(b[26])
        guard let phase = SensorCapturePhase(rawValue: b[27]) else { throw MemoMindProtocolError.invalid("Invalid sensor phase") }
        try requireProtocol(Array(b[0 ..< 3]) == [83, 66, 2] && active <= 3 && b[25] == 32 &&
            (phase == .capturing ? active != 0 : active == 0) && (phase != .inactive || pending == 0) &&
            pending <= 32 && count <= 4 && count <= pending && b.count == 28 + count * 24 &&
            ack <= sequence && drops <= sequence && UInt32(pending) <= sequence - ack, "Contradictory batch state")
        try requireProtocol(result == "ok" ? phase != .inactive && generation != 0 && count == min(pending, 4) : count == 0,
                            "Contradictory batch result")
        try requireProtocol(result != "released" || phase == .inactive, "Sensor release is still active")
        var samples: [SensorBufferedSample] = []
        for i in 0 ..< count {
            let offset = 28 + i * 24, serial = word(offset), tick = word(offset + 4), age = now &- tick
            let kind = b[offset + 8], data = offset + 10
            try requireProtocol(serial == sequence - UInt32(pending) + UInt32(i) + 1 && serial > ack &&
                age <= 0x7FFF_FFFF && (kind == 1 || kind == 2) && b[offset + 9] == 0, "Invalid buffered sample")
            var imu: IMURegisterSample?
            var light: AmbientLightSample?
            if kind == 1 {
                imu = IMURegisterSample(sequence: serial, tick: tick, ageTicks: age, fresh: age <= 1000,
                                        temperature: signed(data), accelerometer: vector(data + 2), gyroscope: vector(data + 8))
            } else {
                let normalized = UInt16(b[data]) | UInt16(b[data + 1]) << 8
                try requireProtocol(normalized <= 1000 && b[data + 2 ..< data + 14].allSatisfy { $0 == 0 }, "Invalid buffered light sample")
                light = AmbientLightSample(sequence: serial, tick: tick, ageTicks: age, fresh: age <= 5000, normalized: normalized)
            }
            samples.append(SensorBufferedSample(sequence: serial, tick: tick, ageTicks: age, imu: imu, light: light))
        }
        return Self(result: result, activeMask: active, phase: phase, generation: generation, now: now, acknowledged: ack,
                    sequence: sequence, drops: drops, pending: pending, samples: samples)
    }
}

public extension GMSession {
    func sensorBatch(generation: UInt32, acknowledged: UInt32, finish: Bool = false, event: inout UInt8) throws -> SensorBatch {
        let body = try SensorBatch.command(generation: generation, acknowledged: acknowledged, finish: finish)
        event = event == 255 ? 1 : event + 1
        let batch = try SensorBatch.decode(request(event: event, service: 15, command: 118, body: GMTLV(kind: 1, value: body).encoded()))
        try requireProtocol(batch.result == "ok" && batch.generation == generation && batch.acknowledged == acknowledged &&
            (!finish || batch.phase == .draining),
            "Sensor batch refused or capture changed")
        return batch
    }

    func releaseSensorCapture(generation: UInt32, acknowledged: UInt32, event: inout UInt8) throws -> SensorBatch {
        var body = try SensorBatch.command(generation: generation, acknowledged: acknowledged)
        body[3] = 6
        event = event == 255 ? 1 : event + 1
        let batch = try SensorBatch.decode(request(event: event, service: 15, command: 118, body: GMTLV(kind: 1, value: body).encoded()))
        try requireProtocol(batch.result == "released" && batch.generation == generation && batch.acknowledged == acknowledged,
                            "Sensor release refused or capture changed")
        return batch
    }

    func drainSensorCapture(generation: UInt32, acknowledged: UInt32, event: inout UInt8,
                            save: (SensorBatch) throws -> Void) throws -> SensorBatch
    {
        var ack = acknowledged
        var terminal: (sequence: UInt32, drops: UInt32)?
        for index in 0 ..< 9 {
            let batch = try sensorBatch(generation: generation, acknowledged: ack, finish: index == 0, event: &event)
            try requireProtocol(batch.phase == .draining, "Sensor capture did not freeze")
            if let terminal {
                try requireProtocol(batch.sequence == terminal.sequence && batch.drops == terminal.drops, "Frozen sensor counters changed")
            } else {
                terminal = (batch.sequence, batch.drops)
            }
            try save(batch)
            if batch.pending == 0 {
                try requireProtocol(batch.acknowledged == batch.sequence, "Sensor tail was not acknowledged")
                return batch
            }
            ack = batch.samples.last!.sequence
        }
        throw MemoMindProtocolError.invalid("Sensor drain exceeded buffer capacity")
    }
}
