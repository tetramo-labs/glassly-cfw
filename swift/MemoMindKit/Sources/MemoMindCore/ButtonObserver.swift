import Foundation

/// Cooked events; correlate with physical presses before assigning actions.
public struct ButtonRecord: Equatable, Encodable, Sendable {
    public let tick: UInt32
    public let sequence: UInt32
    public let identifier: UInt16
    public enum PrimaryAction: UInt16, Sendable {
        case single = 0x1F7B, double, long, veryLong, release
    }

    public var primaryAction: PrimaryAction? {
        PrimaryAction(rawValue: identifier)
    }
}

public struct ButtonSnapshot: Equatable, Encodable, Sendable {
    public let active: Bool
    public let nonce: UInt32
    public let sequence: UInt32
    public let acknowledged: UInt32
    public let drops: UInt32
    public let exhausted: Bool
    public let records: [ButtonRecord]

    public static func decode(_ message: GMMessage) throws -> Self {
        try requireProtocol(message.service == 15 && message.command == 0x7C &&
            message.tlvs.count == 1 && message.tlvs[0].kind == 5,
            "Expected button observer JSON response")
        guard let object = try StrictDeviceJSON.decode(message.tlvs[0].value, maximumBytes: 1536).object else {
            throw MemoMindProtocolError.invalid("Expected button observer object")
        }
        func number(_ o: [String: StrictDeviceJSON], _ key: String, _ max: Int64 = Int64(UInt32.max)) throws -> UInt32 {
            guard let n = o[key]?.integer, n >= 0, n <= max else {
                throw MemoMindProtocolError.invalid("Invalid observer integer: \(key)")
            }
            return UInt32(n)
        }
        try requireProtocol(object["glassly"]?.string == "input" && object["abi"]?.integer == 1,
                            "Unknown input observer identity")
        try requireProtocol(object["result"]?.string == "ok", "Input observer refused request: \(object["result"]?.string ?? "missing result")")
        guard let active = object["active"]?.boolean, let exhausted = object["exhausted"]?.boolean,
              let rows = object["records"]?.array
        else {
            throw MemoMindProtocolError.invalid("Invalid observer flags or records")
        }
        let nonce = try number(object, "nonce"), sequence = try number(object, "sequence")
        let ack = try number(object, "ack"), drops = try number(object, "drops")
        let mask = try number(object, "mask", 3)
        try requireProtocol(object["capacity"]?.integer == 32 && object["leaseTicks"]?.integer == 30000 &&
            ack <= sequence && exhausted == (sequence == UInt32.max) && rows.count <= 8,
            "Invalid bounded observer metadata")
        try requireProtocol(active ? (nonce != 0 && mask == 1) :
            (nonce == 0 && mask == 0 && sequence == 0 && ack == 0 && drops == 0 && !exhausted && rows.isEmpty),
            "Unexpected observer session")
        var records = [ButtonRecord](), previous = ack
        for value in rows {
            guard let row = value.object else { throw MemoMindProtocolError.invalid("Invalid button record") }
            let tick = try number(row, "tick"), serial = try number(row, "sequence")
            let id = try number(row, "id", Int64(UInt16.max))
            try requireProtocol(row["class"]?.integer == 2 &&
                ((0x1F7B ... 0x1F7F).contains(id) || (0x1FB0 ... 0x1FB9).contains(id)) &&
                previous < serial && serial <= sequence,
                "Invalid cooked button event or sequence")
            records.append(ButtonRecord(tick: tick, sequence: serial, identifier: UInt16(id)))
            previous = serial
        }
        return Self(active: active, nonce: nonce, sequence: sequence, acknowledged: ack,
                    drops: drops, exhausted: exhausted, records: records)
    }
}

/// Serialize with GMSession. Save polls before acknowledging; errors stop the client.
public final class ButtonObserverClient {
    private let session: GMSession
    private var event: UInt8
    private var nonce: UInt32 = 0, ack: UInt32 = 0, delivered: UInt32 = 0
    private var sequence: UInt32 = 0, drops: UInt32 = 0
    private var failed = false
    public init(session: GMSession, initialEvent: UInt8 = 0x70) {
        self.session = session; event = initialEvent
    }

    private func le(_ n: UInt32) -> Data {
        Data((0 ..< 4).map { UInt8(truncatingIfNeeded: n >> ($0 * 8)) })
    }

    private func request(_ body: Data, check: (ButtonSnapshot) throws -> Void) throws -> ButtonSnapshot {
        try requireProtocol(!failed, "Observer client stopped after an earlier failure")
        do {
            event = event == 255 ? 1 : event + 1
            let reply = try session.request(event: event, service: 15, command: 0x7C,
                                            body: GMTLV(kind: 1, value: body).encoded())
            let result = try ButtonSnapshot.decode(reply)
            try check(result)
            return result
        } catch { failed = true; throw error }
    }

    private func sameSession(_ reply: ButtonSnapshot) throws {
        try requireProtocol(reply.active && reply.nonce == nonce && reply.sequence >= sequence && reply.drops >= drops,
                            "Button session or counters changed")
    }

    public func status() throws -> ButtonSnapshot {
        try request(Data([1, 0])) { reply in
            try requireProtocol(reply.records.isEmpty, "Status returned records")
            if nonce != 0 {
                try sameSession(reply)
            }
        }
    }

    public func subscribe(nonce newNonce: UInt32) throws -> ButtonSnapshot {
        try requireProtocol(nonce == 0 && newNonce != 0, "Subscribe requires a fresh nonzero nonce")
        let result = try request(Data([1, 1, 1]) + le(newNonce)) { reply in
            try requireProtocol(reply.active && reply.nonce == newNonce && reply.records.isEmpty &&
                reply.sequence == 0 && reply.acknowledged == 0 && reply.drops == 0,
                "Subscribe attached to an unexpected or nonempty session")
        }
        nonce = newNonce; ack = 0; delivered = 0; sequence = 0; drops = 0
        return result
    }

    public func poll() throws -> ButtonSnapshot {
        try requireProtocol(nonce != 0, "Subscribe before polling")
        let result = try request(Data([1, 2]) + le(nonce) + le(ack)) { reply in
            try sameSession(reply)
            try requireProtocol(reply.acknowledged == ack, "Observer ACK differs from request")
        }
        sequence = result.sequence; drops = result.drops
        if let last = result.records.last {
            delivered = max(delivered, last.sequence)
        }
        return result
    }

    public func acknowledge(savedThrough serial: UInt32) throws {
        try requireProtocol(!failed && nonce != 0 && ack <= serial && serial <= delivered,
                            "ACK must cover only delivered, durably saved records")
        ack = serial
    }

    public func stop() throws -> ButtonSnapshot {
        try requireProtocol(nonce != 0, "No button subscription to stop")
        let result = try request(Data([1, 3]) + le(nonce)) { reply in
            try requireProtocol(!reply.active, "Observer remains active after stop")
        }
        nonce = 0
        return result
    }
}
