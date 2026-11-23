import Foundation

public struct DeviceIdentity: Codable, Equatable {
    public let model: String
    public let hardwareVersion: String
    public let frontVersion: String
    public let firmwareVersion: String
    public let mac: String
    enum CodingKeys: String, CodingKey {
        case model, hardwareVersion = "hver", frontVersion = "fver", firmwareVersion = "ver", mac
    }

    public init(model: String, hardwareVersion: String, frontVersion: String, firmwareVersion: String, mac: String) {
        self.model = model; self.hardwareVersion = hardwareVersion; self.frontVersion = frontVersion
        self.firmwareVersion = firmwareVersion; self.mac = mac
    }

    public func validate(address: String) throws {
        try requireProtocol(model == "H001Y", "Unsupported device model")
        try requireProtocol(hardwareVersion == "2.1.2" && frontVersion == "1.3", "Unsupported hardware/front version")
        try requireProtocol(["1.0.2.151", "1.0.3.127"].contains(firmwareVersion), "Unsupported source firmware")
        try requireProtocol(mac.uppercased() == address.uppercased(), "Device-info MAC differs from target")
    }

    public static func decode(_ data: Data) throws -> DeviceIdentity {
        // Official STRING values can include trailing NULs; no lossy UTF8 decoding.
        var bytes = Array(data)
        while bytes.last == 0 {
            bytes.removeLast()
        }
        return try JSONDecoder().decode(DeviceIdentity.self, from: Data(bytes))
    }
}

/// One normal RFCOMM session. Caller owns connection/lifetime and serializes access.
public final class GMSession {
    public let transport: MemoMindTransport
    public let parser: GMStream
    public let timeout: TimeInterval
    public var unsolicited: ((GMMessage) -> Void)?
    public init(transport: MemoMindTransport, timeout: TimeInterval = 15, legacyRepeatFA: Bool = true) {
        self.transport = transport; self.timeout = timeout
        parser = GMStream(legacyRepeatFA: legacyRepeatFA, fragmentACKs: true)
    }

    /// An optional filter distinguishes the command reply from notifications
    /// sharing its event/service/command. Rejected business messages go to
    /// `unsolicited`; callers must validate their notification schema there.
    /// With a filter, multiple accepted replies in one decoded read are an error.
    /// Later packets are only observed by a subsequent read; this is not a drain
    /// or a guarantee that every notification has arrived when the reply returns.
    public func awaitResponse(event: UInt8, service: UInt8, command: UInt8,
                              responseFilter: ((GMMessage) throws -> Bool)? = nil) throws -> GMMessage {
        let deadline = monotonicNow() + timeout
        while true {
            let remaining = deadline - monotonicNow()
            guard remaining > 0 else { throw MemoMindProtocolError.timeout("Timed out awaiting correlated GM business response") }
            var matched: GMMessage?
            for message in try parser.feed(transport.read(timeout: remaining)) {
                if message.matches(event, service, command) {
                    if !message.tlvs.isEmpty {
                        if let responseFilter {
                            guard try responseFilter(message) else { unsolicited?(message); continue }
                            try requireProtocol(matched == nil, "Multiple accepted GM replies in one read")
                        }
                        matched = message
                    }
                } else {
                    unsolicited?(message)
                }
            }
            if let matched {
                return matched
            }
        }
    }

    /// Checked per-fragment ACKs; an early business rejection stops subsequent writes.
    public func request(event: UInt8, service: UInt8, command: UInt8, body: Data = Data(),
                        responseFilter: ((GMMessage) throws -> Bool)? = nil) throws -> GMMessage {
        try requireProtocol(timeout.isFinite && timeout > 0, "Invalid GM timeout")
        let frames = try GMCodec.frames(event: event, service: service, command: command, body: body, fragmentPayload: 642)
        for (index, frame) in frames.enumerated() {
            try transport.write(frame)
            if index == frames.count - 1 {
                return try awaitResponse(event: event, service: service, command: command, responseFilter: responseFilter)
            }
            let deadline = monotonicNow() + timeout
            var acknowledged = false
            while !acknowledged {
                let remaining = deadline - monotonicNow()
                guard remaining > 0 else { throw MemoMindProtocolError.timeout("Timed out awaiting GM fragment acknowledgment") }
                var earlyReply: GMMessage?
                for message in try parser.feed(transport.read(timeout: remaining)) {
                    guard message.matches(event, service, command) else { unsolicited?(message); continue }
                    if !message.tlvs.isEmpty {
                        guard let responseFilter else { return message }
                        if try responseFilter(message) {
                            try requireProtocol(earlyReply == nil, "Multiple accepted GM replies in one read")
                            earlyReply = message
                        } else { unsolicited?(message) }
                        continue
                    }
                    try requireProtocol(message.head == frame.first, "GM fragment acknowledgment head mismatch")
                    acknowledged = true
                }
                if let earlyReply { return earlyReply }
            }
        }
        throw MemoMindProtocolError.invalid("Missing GM request frame")
    }

    public func probe() throws -> DeviceIdentity {
        let heartbeat = try request(event: 1, service: 1, command: 1)
        let statuses = heartbeat.tlvs.filter { $0.kind == 6 }.map(\.value)
        try requireProtocol(statuses == [Data([0])], "Heartbeat did not return STATUS 0")
        let info = try request(event: 2, service: 1, command: 2)
        let strings = info.tlvs.filter { $0.kind == 2 }
        try requireProtocol(strings.count == 1, "Device-info response did not contain exactly one STRING TLV")
        return try DeviceIdentity.decode(strings[0].value)
    }

    /// This changes transient updater state. It is not a read-only query.
    /// Keep this normal connection open while opening the separate OTA service.
    public func notifyOTA() throws {
        let reply = try request(event: 0x15, service: 1, command: 0x1C, body: Data([8, 0, 0, 1, 1]))
        try requireProtocol(reply.tlvs == [GMTLV(kind: 6, value: Data([1]))], "Unsupported pre-OTA notification reply")
    }
}
