// Protocol source pins (offline port; no Python runtime dependency):
// scripts/memomind_flash_canary.py SHA256 3911c5f9b7fa9bdfae01e577dfda5d52a3ddacd8ca46e507bc9db53d151d939f
// scripts/memomind_flash_read.py SHA256 5e23e168444d2d8b84cd4681ec505b5757099648c2854d5bf2475abad8e4f57e
// runtime/graphics/flash_canary.c SHA256 e8481493ee488d480821ea9841efa1d5f67017e28025f908741f9eb77885cf95
import Foundation

/// Fixed canary commands are explicit operations, not authentication. The caller
/// must separately verify the exact installed image/header, full flash backup and
/// owner-disabled boot. Profile discovery cannot establish those preconditions.
public enum FixedCanaryError: Error, LocalizedError, CustomStringConvertible {
    case protocolViolation(String)
    case nativeRejected(String)
    case admission(String)
    public var description: String {
        switch self {
        case let .protocolViolation(reason): "Canary protocol: \(reason)"
        case let .nativeRejected(result): "Canary rejected: \(result)"
        case let .admission(reason): "Canary admission: \(reason)"
        }
    }

    public var errorDescription: String? {
        description
    }
}

public struct CanaryProfile: Codable, Equatable {
    public struct Range: Codable, Equatable {
        public let device: Int
        public let start: Int
        public let end: Int
    }

    public static let identifier = "H001Y-1.0.3.127-flash-canary-v1"
    public let profile: String
    public let maxRead: Int
    public let alignment: Int
    public let ranges: [Range]
    static let expectedRanges = [Range(device: 0, start: 0, end: 0x10000),
                                 Range(device: 0, start: 0x1EB000, end: 0x1EB100),
                                 Range(device: 0, start: 0x7FC000, end: 0x7FE000),
                                 Range(device: 1, start: 0x500000, end: 0x800000)]
}

public struct CanaryStatus: Codable, Equatable {
    public enum State: String, Codable { case idle, starting, running, passed, failed }
    public let glassly: String
    public let abi: Int
    public let result: String
    public let state: State
    public let operation: Int
    public let phase: Int
    public let error: Int32
    public let nativeStatus: Int32
    public let mapSource: Int
    public let mutationStarted: Bool
    public let restored: Bool
    public let neighborVerified: Bool
    public let device: Int
    public let offset: Int
    public let neighbor: Int
    public let sectorBytes: Int
}

/// Synchronous and single-owner: do not concurrently use the underlying normal
/// RFCOMM stream. There are no tasks, retries, address selectors or reset methods.
/// A request failure poisons this instance. A new instance can query status only;
/// the native once-per-boot registry remains the final admission authority.
public final class FixedCanaryClient {
    public static let service: UInt8 = 15
    public static let command: UInt8 = 0x7A
    public static let token: UInt32 = 0x4341_4E31
    private let transport: MemoMindTransport
    private let timeout: TimeInterval
    private let parser = GMStream(legacyRepeatFA: true, fragmentACKs: true)
    private var event: UInt8 = 0x60
    public private(set) var failed = false
    public private(set) var verified = false
    public private(set) var attempted = false
    public private(set) var previous: CanaryStatus?
    public var unsolicited: ((GMMessage) -> Void)?

    public init(transport: MemoMindTransport, timeout: TimeInterval = 10) throws {
        guard timeout.isFinite, timeout > 0, timeout <= 60 else {
            throw FixedCanaryError.admission("timeout must be positive and at most 60 seconds")
        }
        self.transport = transport; self.timeout = timeout
    }

    private static func object(_ message: GMMessage, identity: String) throws -> [String: StrictDeviceJSON] {
        guard message.tlvs.count == 1, message.tlvs[0].kind == 5 else {
            throw FixedCanaryError.protocolViolation("Expected one bounded JSON TLV")
        }
        guard let object = try StrictDeviceJSON.decode(message.tlvs[0].value).object,
              object["glassly"]?.string == identity, object["abi"]?.integer == 1
        else {
            throw FixedCanaryError.protocolViolation("Wrong identity")
        }
        return object
    }

    /// Public decoder permits validation of saved raw replies without transport.
    public static func decodeStatus(_ message: GMMessage) throws -> CanaryStatus {
        let object = try object(message, identity: "flash-canary")
        if object["result"]?.string != "ok" {
            guard Set(object.keys) == ["glassly", "abi", "result"], let result = object["result"]?.string,
                  ["invalid", "wrong-image", "registry-invalid", "already-used", "allocation-failed"].contains(result)
            else {
                throw FixedCanaryError.protocolViolation("Unknown error")
            }
            throw FixedCanaryError.nativeRejected(result)
        }
        let expected: Set = ["glassly", "abi", "result", "state", "operation", "phase", "error", "nativeStatus", "mapSource", "mutationStarted", "restored", "neighborVerified", "device", "offset", "neighbor", "sectorBytes"]
        guard Set(object.keys) == expected else { throw FixedCanaryError.protocolViolation("Unexpected fields") }
        func number(_ key: String, _ low: Int64, _ high: Int64) throws -> Int64 {
            guard let value = object[key]?.integer, low <= value, value <= high else {
                throw FixedCanaryError.protocolViolation("Invalid \(key)")
            }
            return value
        }
        func boolean(_ key: String) throws -> Bool {
            guard let value = object[key]?.boolean else { throw FixedCanaryError.protocolViolation("Invalid boolean \(key)") }
            return value
        }
        guard let name = object["state"]?.string, let state = CanaryStatus.State(rawValue: name) else {
            throw FixedCanaryError.protocolViolation("Unknown state")
        }
        let status = try CanaryStatus(glassly: "flash-canary", abi: 1, result: "ok", state: state,
                                      operation: Int(number("operation", 0, 2)), phase: Int(number("phase", 0, 8)),
                                      error: Int32(number("error", Int64(Int32.min), Int64(Int32.max))),
                                      nativeStatus: Int32(number("nativeStatus", Int64(Int32.min), Int64(Int32.max))),
                                      mapSource: Int(number("mapSource", 0, 2)), mutationStarted: boolean("mutationStarted"),
                                      restored: boolean("restored"), neighborVerified: boolean("neighborVerified"),
                                      device: Int(number("device", 1, 1)), offset: Int(number("offset", 0x7FF000, 0x7FF000)),
                                      neighbor: Int(number("neighbor", 0x7FE000, 0x7FE000)), sectorBytes: Int(number("sectorBytes", 4096, 4096)))
        if state == .idle {
            guard status.operation == 0, status.phase == 0, status.error == 0, status.nativeStatus == 0,
                  status.mapSource == 0, !status.mutationStarted, !status.restored, !status.neighborVerified
            else {
                throw FixedCanaryError.protocolViolation("Dirty idle registry")
            }
        } else {
            guard status.operation != 0, status.phase != 0 else { throw FixedCanaryError.protocolViolation("Missing operation") }
            guard state == .failed ? status.error != 0 : status.error == 0 else {
                throw FixedCanaryError.protocolViolation("State/error mismatch")
            }
            if state == .starting {
                guard status.phase == 1, status.mapSource == 0, !status.mutationStarted, !status.restored, !status.neighborVerified else {
                    throw FixedCanaryError.protocolViolation("Dirty admission")
                }
            }
            guard status.operation != 1 || (!status.mutationStarted && !status.restored) else {
                throw FixedCanaryError.protocolViolation("Readonly operation mutated")
            }
            guard !status.restored || status.mutationStarted else { throw FixedCanaryError.protocolViolation("Restore without mutation") }
            if state == .passed {
                guard status.phase == 8, status.mapSource != 0, status.neighborVerified, status.nativeStatus == 0,
                      status.operation != 2 || (status.mutationStarted && status.restored)
                else {
                    throw FixedCanaryError.protocolViolation("Incomplete success")
                }
            }
        }
        return status
    }

    /// Only a fixed profile query, not a flash read or ownership check.
    @discardableResult public func verifyProfile() throws -> CanaryProfile {
        guard !failed else { throw FixedCanaryError.admission("Stopped after error") }
        do {
            let message = try exchange(event: 0x91, command: 0x7B, bytes: Data([0]))
            let object = try Self.object(message, identity: "flash-read")
            guard object["result"]?.string == "ok", Set(object.keys) == ["glassly", "abi", "result", "profile", "maxRead", "alignment", "ranges"],
                  object["profile"]?.string == CanaryProfile.identifier,
                  object["maxRead"]?.integer == 256, object["alignment"]?.integer == 256,
                  let values = object["ranges"]?.array, values.count == CanaryProfile.expectedRanges.count
            else {
                throw FixedCanaryError.protocolViolation("Unknown flash profile or read limits")
            }
            var ranges = [CanaryProfile.Range]()
            for value in values {
                guard let range = value.object, Set(range.keys) == ["device", "start", "end"],
                      let device = range["device"]?.integer, let start = range["start"]?.integer, let end = range["end"]?.integer,
                      0 ... 1 ~= device, 0 ... 0x800000 ~= start, 0 ... 0x800000 ~= end
                else {
                    throw FixedCanaryError.protocolViolation("Malformed flash range")
                }
                ranges.append(CanaryProfile.Range(device: Int(device), start: Int(start), end: Int(end)))
            }
            func order(_ a: CanaryProfile.Range, _ b: CanaryProfile.Range) -> Bool {
                if a.device != b.device {
                    return a.device < b.device
                }
                if a.start != b.start {
                    return a.start < b.start
                }
                return a.end < b.end
            }
            guard ranges.sorted(by: order) == CanaryProfile.expectedRanges.sorted(by: order) else {
                throw FixedCanaryError.protocolViolation("Compiled flash allowlist differs from pinned profile")
            }
            verified = true
            return CanaryProfile(profile: CanaryProfile.identifier, maxRead: 256, alignment: 256, ranges: ranges)
        } catch { failed = true; throw error }
    }

    /// Entire exchange shares one monotonic deadline, including its write. Every
    /// business reply for either fixed command is checked before returning a match.
    private func exchange(event: UInt8, command: UInt8, bytes: Data) throws -> GMMessage {
        let deadline = monotonicNow() + timeout
        let body = try GMTLV(kind: 1, value: bytes).encoded()
        let frames = try GMCodec.frames(event: event, service: Self.service, command: command, body: body, fragmentPayload: 642)
        guard frames.count == 1 else { throw FixedCanaryError.protocolViolation("Fixed request unexpectedly fragmented") }
        try transport.write(frames[0])
        while true {
            let remaining = deadline - monotonicNow()
            guard remaining > 0 else { throw MemoMindProtocolError.timeout("Canary reply timeout; do not repeat an ambiguous start") }
            var matched: GMMessage?
            for message in try parser.feed(transport.read(timeout: remaining)) {
                if message.service == Self.service, [Self.command, 0x7B].contains(message.command), !message.tlvs.isEmpty {
                    guard message.matches(event, Self.service, command), matched == nil else {
                        throw FixedCanaryError.protocolViolation("Uncorrelated or duplicate reply")
                    }
                    matched = message
                } else {
                    unsolicited?(message)
                }
            }
            if let matched {
                return matched
            }
        }
    }

    private func request(_ bytes: Data, operation: Int? = nil) throws -> CanaryStatus {
        guard !failed && verified else { throw FixedCanaryError.admission("Verify profile first; no recovery after an error") }
        event = event == 255 ? 1 : event + 1
        do {
            let status = try Self.decodeStatus(exchange(event: event, command: Self.command, bytes: bytes))
            if let operation, status.operation != operation {
                throw FixedCanaryError.protocolViolation("Start operation mismatch")
            }
            if let old = previous, old.state != .idle {
                guard status.operation == old.operation, status.phase >= old.phase else {
                    throw FixedCanaryError.protocolViolation("Registry regressed or rebooted")
                }
                if old.state == .passed || old.state == .failed {
                    guard status == old else { throw FixedCanaryError.protocolViolation("Terminal registry changed") }
                }
                guard !old.mutationStarted || status.mutationStarted, !old.restored || status.restored, !old.neighborVerified || status.neighborVerified else {
                    throw FixedCanaryError.protocolViolation("Registry flag regressed")
                }
            }
            previous = status
            return status
        } catch { failed = true; throw error }
    }

    public func status() throws -> CanaryStatus {
        try request(Data([0]))
    }

    private func start(operation: UInt8) throws -> CanaryStatus {
        guard !attempted, previous?.state == .idle else {
            throw FixedCanaryError.admission("An observed idle registry and one explicit attempt are required")
        }
        attempted = true // Set before write: even ambiguous delivery consumes this client attempt.
        return try request(Data([operation, 0x31, 0x4E, 0x41, 0x43]), operation: Int(operation))
    }

    /// Consumes the device's once-per-boot admission without erase/program.
    public func validateWorker() throws -> CanaryStatus {
        try start(operation: 1)
    }

    /// Erase/program/verify/restore of the sole fixed sector. Never auto-retries.
    public func runFixedCanary() throws -> CanaryStatus {
        try start(operation: 2)
    }
}
