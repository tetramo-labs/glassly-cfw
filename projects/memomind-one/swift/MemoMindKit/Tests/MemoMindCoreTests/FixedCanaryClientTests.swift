// Original test scenario source SHA256 43fec77d0e91173698208b22774b1b1105ff4eaf47f4f47fe3a23e944e15bbdf
import Foundation
@testable import MemoMindCore
import XCTest

/// Fixtures preserve scripts/test_memomind_flash_canary.py's original eight scenarios
/// and the native runtime/graphics/flash_canary.c wire schema. These are synthetic
/// protocol tests, not evidence that flash programming ran on hardware.
private func canaryIdle() -> [String: Any] {
    ["glassly": "flash-canary", "abi": 1, "result": "ok", "state": "idle", "operation": 0,
     "phase": 0, "error": 0, "nativeStatus": 0, "mapSource": 0, "mutationStarted": false,
     "restored": false, "neighborVerified": false, "device": 1, "offset": 0x7FF000,
     "neighbor": 0x7FE000, "sectorBytes": 4096]
}

private func canaryStarted(_ operation: Int = 2) -> [String: Any] {
    var value = canaryIdle(); value["state"] = "starting"; value["operation"] = operation; value["phase"] = 1
    return value
}

private func canaryPassed(_ operation: Int = 2) -> [String: Any] {
    var value = canaryStarted(operation)
    value["state"] = "passed"; value["phase"] = 8; value["mapSource"] = 1
    value["mutationStarted"] = operation == 2; value["restored"] = operation == 2; value["neighborVerified"] = true
    return value
}

private func canaryJSON(_ object: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
}

private func canaryMessage(_ raw: Data, kind: UInt8 = 5) -> GMMessage {
    GMMessage(head: 0xFA, event: 0x61, service: 15, command: 0x7A, body: Data(), tlvs: [GMTLV(kind: kind, value: raw)])
}

private final class CanaryWire: MemoMindTransport {
    struct Request { let event: UInt8; let command: UInt8; let body: Data }
    var requests = [Request](), replies = [[String: Any]](), incoming = [Data]()
    var change: (([String: Any]) -> [String: Any])?
    var rawReply: Data?
    var drop = false, duplicate = false, delta: UInt8 = 0, failWrite = false
    var fragmentSize = 13
    var timeouts = [TimeInterval]()
    var beforeRead: (() -> Void)?
    /// Independent physical reply encoder, intentionally not GMCodec.
    private func frames(_ raw: Data, event: UInt8, command: UInt8) -> Data {
        let body = [UInt8(5), UInt8(raw.count >> 16), UInt8((raw.count >> 8) & 255), UInt8(raw.count & 255)] + Array(raw)
        let logical = body.count + 9
        var result = Data()
        for offset in stride(from: 0, to: body.count, by: 503) {
            // Known firmware legacy repeated-FA reply continuation.
            var bytes: [UInt8] = [0xFA, UInt8(logical >> 16), UInt8((logical >> 8) & 255), UInt8(logical & 255), event, 15, command]
            bytes += body[offset ..< min(offset + 503, body.count)]
            let sum = bytes.reduce(0) { $0 + Int($1) } & 65535
            bytes += [UInt8(sum >> 8), UInt8(sum & 255)]
            result += bytes
        }
        return result
    }

    func write(_ data: Data) throws {
        let bytes = Array(data)
        guard bytes.count >= 13, bytes[0] == 0xFA, bytes[5] == 15, bytes[7] == 1,
              (Int(bytes[1]) << 16 | Int(bytes[2]) << 8 | Int(bytes[3])) == bytes.count,
              bytes.dropLast(2).reduce(0, { $0 + Int($1) }) & 65535 == Int(bytes[bytes.count - 2]) << 8 | Int(bytes.last!),
              (Int(bytes[8]) << 16 | Int(bytes[9]) << 8 | Int(bytes[10])) == bytes.count - 13
        else {
            throw FixedCanaryError.protocolViolation("Test receiver rejected request framing")
        }
        let event = bytes[4], command = bytes[6], body = Data(bytes[11 ..< (bytes.count - 2)])
        requests.append(Request(event: event, command: command, body: body))
        if failWrite {
            throw FixedCanaryError.protocolViolation("injected ambiguous write")
        }
        var object: [String: Any]
        if command == 0x7B {
            guard body == Data([0]) else { throw FixedCanaryError.protocolViolation("Wrong profile query") }
            object = ["glassly": "flash-read", "abi": 1, "result": "ok", "profile": "H001Y-1.0.3.127-flash-canary-v1",
                      "maxRead": 256, "alignment": 256, "ranges": [
                          ["device": 0, "start": 0, "end": 65536],
                          ["device": 0, "start": 0x1EB000, "end": 0x1EB100],
                          ["device": 0, "start": 0x7FC000, "end": 0x7FE000],
                          ["device": 1, "start": 0x500000, "end": 0x800000],
                      ]]
        } else {
            guard command == 0x7A, !replies.isEmpty else { throw FixedCanaryError.protocolViolation("Missing test response") }
            object = replies.removeFirst()
        }
        if let change {
            object = change(object)
        }
        let raw = try rawReply ?? canaryJSON(object)
        var wire = frames(raw, event: event &+ delta, command: command)
        if duplicate {
            wire += wire
        }
        if !drop {
            if duplicate {
                incoming.append(wire)
            } else {
                for offset in stride(from: 0, to: wire.count, by: fragmentSize) {
                    incoming.append(wire.subdata(in: offset ..< min(offset + fragmentSize, wire.count)))
                }
            }
        }
    }

    func read(timeout: TimeInterval) throws -> Data {
        timeouts.append(timeout); beforeRead?()
        guard !incoming.isEmpty else { throw MemoMindProtocolError.timeout("injected lost reply") }
        return incoming.removeFirst()
    }
}

final class FixedCanaryClientTests: XCTestCase {
    private func ready() throws -> (CanaryWire, FixedCanaryClient) {
        let wire = CanaryWire(), client = try FixedCanaryClient(transport: wire)
        try client.verifyProfile(); wire.replies.append(canaryIdle()); _ = try client.status()
        return (wire, client)
    }

    private func decoded(_ object: [String: Any]) throws -> CanaryStatus {
        try FixedCanaryClient.decodeStatus(canaryMessage(canaryJSON(object)))
    }

    func testExplicitProfileIdleAndOneStartExactWireToken() throws {
        let wire = CanaryWire(), client = try FixedCanaryClient(transport: wire)
        XCTAssertThrowsError(try client.status()); XCTAssertThrowsError(try client.runFixedCanary()); XCTAssertTrue(wire.requests.isEmpty)
        let profile = try client.verifyProfile()
        XCTAssertEqual(profile.profile, CanaryProfile.identifier); XCTAssertEqual(profile.ranges.count, 4)
        XCTAssertEqual(wire.requests[0].event, 0x91); XCTAssertEqual(wire.requests[0].command, 0x7B)
        XCTAssertThrowsError(try client.runFixedCanary()); XCTAssertFalse(client.attempted)
        wire.replies.append(canaryIdle()); XCTAssertEqual(try client.status().state, .idle)
        wire.replies.append(canaryStarted()); XCTAssertEqual(try client.runFixedCanary().state, .starting)
        XCTAssertEqual(wire.requests.last?.event, 0x62); XCTAssertEqual(wire.requests.last?.command, 0x7A)
        XCTAssertEqual(wire.requests.last?.body, Data([2, 0x31, 0x4E, 0x41, 0x43]))
        let count = wire.requests.count
        XCTAssertThrowsError(try client.runFixedCanary()); XCTAssertThrowsError(try client.validateWorker())
        XCTAssertEqual(wire.requests.count, count); XCTAssertTrue(client.attempted)
        wire.replies.append(canaryPassed()); XCTAssertEqual(try client.status().state, .passed)
    }

    func testValidationOperationAndImmediateCompletion() throws {
        let (wire, client) = try ready(); wire.replies.append(canaryPassed(1))
        let status = try client.validateWorker()
        XCTAssertEqual(status.state, .passed); XCTAssertFalse(status.mutationStarted); XCTAssertFalse(status.restored)
        XCTAssertEqual(wire.requests.last?.body, Data([1, 0x31, 0x4E, 0x41, 0x43]))
        XCTAssertThrowsError(try client.runFixedCanary())
        let encoded = try JSONEncoder().encode(status)
        XCTAssertEqual(try FixedCanaryClient.decodeStatus(canaryMessage(encoded)), status)
    }

    func testRebootMismatchRegressionAndTerminalChangesStop() throws {
        var phaseZero = canaryStarted(); phaseZero["phase"] = 0
        for changed in [canaryIdle(), canaryStarted(1), phaseZero] {
            let (wire, client) = try ready(); wire.replies.append(canaryStarted()); _ = try client.runFixedCanary()
            wire.replies.append(changed); XCTAssertThrowsError(try client.status()); XCTAssertTrue(client.failed)
        }
        let (wire, client) = try ready(); wire.replies.append(canaryPassed()); _ = try client.runFixedCanary()
        var changed = canaryPassed(); changed["mapSource"] = 2; wire.replies.append(changed)
        XCTAssertThrowsError(try client.status()); XCTAssertTrue(client.failed)
    }

    func testLostDuplicateWrongEventAndWriteFailureNeverRepeat() throws {
        for mode in 0 ..< 4 {
            let (wire, client) = try ready(); wire.replies.append(canaryStarted())
            wire.drop = mode == 0; wire.duplicate = mode == 1; wire.delta = mode == 2 ? 1 : 0; wire.failWrite = mode == 3
            XCTAssertThrowsError(try client.runFixedCanary())
            let count = wire.requests.count
            XCTAssertThrowsError(try client.runFixedCanary()); XCTAssertThrowsError(try client.status()); XCTAssertThrowsError(try client.verifyProfile())
            XCTAssertEqual(wire.requests.count, count); XCTAssertTrue(client.attempted); XCTAssertTrue(client.failed)
        }
    }

    func testWrongProfileAndEveryRangeMismatchNeverSendCanary() throws {
        for mode in 0 ..< 7 {
            let wire = CanaryWire(), client = try FixedCanaryClient(transport: wire)
            wire.change = { original in
                var value = original
                switch mode {
                case 0: value["profile"] = "H001Y-1.0.3.127-full-store-read-v1"
                case 1: value["maxRead"] = true
                case 2: value["alignment"] = 512
                case 3: value["ranges"] = [["device": 1, "start": 0x500000, "end": 0x800000]]
                case 4:
                    var ranges = value["ranges"] as! [[String: Int]]; ranges[3]["start"] = 0x700000; value["ranges"] = ranges
                case 5: value["abi"] = true
                default: value["extra"] = 0
                }
                return value
            }
            XCTAssertThrowsError(try client.verifyProfile()); XCTAssertTrue(client.failed); XCTAssertFalse(client.verified)
            XCTAssertEqual(wire.requests.count, 1); XCTAssertEqual(wire.requests[0].command, 0x7B)
            XCTAssertThrowsError(try client.status()); XCTAssertEqual(wire.requests.count, 1)
        }
    }

    func testSuccessSchemaAndSemanticRejections() throws {
        var failure = canaryStarted(); failure["state"] = "failed"; failure["error"] = -20001
        for good in [canaryIdle(), canaryStarted(), canaryPassed(), canaryPassed(1), failure] {
            XCTAssertNoThrow(try decoded(good))
        }
        let patches: [[String: Any]] = [["operation": true], ["phase": 9], ["offset": 0x7FE000], ["device": true],
                                        ["error": Int64(Int32.min) - 1], ["nativeStatus": Int64(Int32.max) + 1], ["restored": 1], ["state": "other"],
                                        ["extra": 0], ["mapSource": 0], ["neighborVerified": false], ["mutationStarted": false], ["abi": true], ["phase": 8.5], ["operation": NSNull()]]
        for patch in patches {
            var bad = canaryPassed(); bad.merge(patch) { _, new in new }; XCTAssertThrowsError(try decoded(bad), "\(patch)")
        }
        for key in canaryPassed().keys {
            var bad = canaryPassed(); bad.removeValue(forKey: key); XCTAssertThrowsError(try decoded(bad), key)
        }
        for key in ["operation", "phase", "error", "nativeStatus", "mapSource", "mutationStarted", "restored", "neighborVerified"] {
            var bad = canaryIdle(); bad[key] = ["mutationStarted", "restored", "neighborVerified"].contains(key) ? true : 1
            XCTAssertThrowsError(try decoded(bad), key)
        }
    }

    func testStrictJSONTLVAndNativeErrors() throws {
        for result in ["invalid", "wrong-image", "registry-invalid", "already-used", "allocation-failed"] {
            XCTAssertThrowsError(try decoded(["glassly": "flash-canary", "abi": 1, "result": result])) { error in
                guard case let FixedCanaryError.nativeRejected(code) = error else { return XCTFail("Wrong error type: \(error)") }
                XCTAssertEqual(code, result)
            }
        }
        let bad: [Data] = try [Data("[]".utf8), Data("null".utf8), Data([255]), Data("{\"abi\":1,\"abi\":1}".utf8),
                               Data("{\"x\":NaN}".utf8), Data(repeating: 32, count: 769), canaryJSON(canaryIdle()) + Data([0, 0]),
                               Data("{\"abi\":1,\"\\u0061bi\":1}".utf8), Data("{\"x\":{\"a\":1,\"a\":2}}".utf8),
                               Data("{\"abi\":1e0}".utf8), Data("{\"abi\":01}".utf8), Data("{\"abi\":1.0}".utf8),
                               Data((String(repeating: "[", count: 26) + "0" + String(repeating: "]", count: 26)).utf8)]
        for raw in bad {
            XCTAssertThrowsError(try FixedCanaryClient.decodeStatus(canaryMessage(raw)))
        }
        XCTAssertNoThrow(try FixedCanaryClient.decodeStatus(canaryMessage(canaryJSON(canaryIdle()) + Data([0]))))
        for tlvs in [[], [GMTLV(kind: 6, value: Data([4]))], [GMTLV(kind: 5, value: Data()), GMTLV(kind: 5, value: Data())]] {
            let message = GMMessage(head: 0xFA, event: 0x61, service: 15, command: 0x7A, body: Data(), tlvs: tlvs)
            XCTAssertThrowsError(try FixedCanaryClient.decodeStatus(message))
        }
    }

    func testTerminalFailureIsObservableAndImmutable() throws {
        let (wire, client) = try ready()
        var failure = canaryStarted(); failure["state"] = "failed"; failure["phase"] = 5; failure["error"] = -19718
        failure["mapSource"] = 2; failure["mutationStarted"] = true
        wire.replies.append(failure); let first = try client.runFixedCanary()
        XCTAssertEqual(first.state, .failed); XCTAssertEqual(first.error, -19718); XCTAssertFalse(first.restored)
        wire.replies.append(failure); XCTAssertEqual(try client.status(), first); XCTAssertFalse(client.failed)
    }

    func testMonotonicPhaseFlagsAndStartOperationMismatch() throws {
        for flag in ["mutationStarted", "restored", "neighborVerified"] {
            let (wire, client) = try ready()
            var running = canaryStarted(); running["state"] = "running"; running["phase"] = 7; running["mapSource"] = 1
            running["mutationStarted"] = true; running["restored"] = true; running["neighborVerified"] = true
            wire.replies.append(running); _ = try client.runFixedCanary()
            running[flag] = false; wire.replies.append(running)
            XCTAssertThrowsError(try client.status()); XCTAssertTrue(client.failed)
        }
        let (wire, client) = try ready(); wire.replies.append(canaryStarted(1))
        XCTAssertThrowsError(try client.runFixedCanary()); XCTAssertTrue(client.failed)
    }

    func testProfileDuplicateAndRequestDeadlineAreFailClosed() throws {
        for mode in 0 ..< 2 {
            let wire = CanaryWire(), client = try FixedCanaryClient(transport: wire)
            wire.duplicate = mode == 0; wire.delta = mode == 1 ? 1 : 0
            XCTAssertThrowsError(try client.verifyProfile()); XCTAssertTrue(client.failed)
        }
        for timeout in [0, -1, 61, Double.nan, Double.infinity] {
            XCTAssertThrowsError(try FixedCanaryClient(transport: CanaryWire(), timeout: timeout))
        }
        let wire = CanaryWire(), client = try FixedCanaryClient(transport: wire, timeout: 0.001)
        wire.beforeRead = { Thread.sleep(forTimeInterval: 0.002) }
        XCTAssertThrowsError(try client.verifyProfile()); XCTAssertTrue(client.failed)
        XCTAssertEqual(wire.requests.count, 1)
        XCTAssertTrue(wire.timeouts.allSatisfy { $0 > 0 && $0 <= 0.001 })
    }

    func testEventWrapAndRunningPhaseProgression() throws {
        let (wire, client) = try ready()
        for _ in 0 ..< 270 {
            wire.replies.append(canaryIdle())
            XCTAssertEqual(try client.status().state, .idle)
        }
        let events = wire.requests.filter { $0.command == 0x7A }.map(\.event)
        XCTAssertTrue(events.contains(255)); XCTAssertTrue(events.contains(1)); XCTAssertFalse(events.contains(0))
        for i in 1 ..< events.count {
            XCTAssertEqual(events[i], events[i - 1] == 255 ? 1 : events[i - 1] + 1)
        }
        var running = canaryStarted(); running["state"] = "running"; running["phase"] = 2; running["mapSource"] = 1
        wire.replies.append(running); XCTAssertEqual(try client.runFixedCanary().phase, 2)
        running["phase"] = 3; wire.replies.append(running); XCTAssertEqual(try client.status().phase, 3)
        running["phase"] = 2; wire.replies.append(running); XCTAssertThrowsError(try client.status()); XCTAssertTrue(client.failed)
    }

    func testUnsolicitedBusinessAndSplitDuplicateCorrelation() throws {
        let (wire, client) = try ready()
        var unsolicitedCount = 0
        client.unsolicited = { message in XCTAssertEqual(message.command, 0x30); unsolicitedCount += 1 }
        let unrelated = try GMCodec.frames(event: 4, service: 1, command: 0x30, body: GMTLV(kind: 8, value: Data([2])).encoded())[0]
        wire.incoming.append(unrelated)
        wire.replies.append(canaryStarted()); _ = try client.runFixedCanary()
        XCTAssertEqual(unsolicitedCount, 1); XCTAssertFalse(client.failed)
        // A duplicate arriving in a later read is rejected on the next exchange;
        // no client can prove that future queued bytes do not exist at return time.
        let duplicate = try GMCodec.frames(event: 0x62, service: 15, command: 0x7A, body: GMTLV(kind: 5, value: canaryJSON(canaryStarted())).encoded())[0]
        wire.incoming.append(duplicate); wire.replies.append(canaryPassed())
        XCTAssertThrowsError(try client.status()); XCTAssertTrue(client.failed)
        let count = wire.requests.count
        XCTAssertThrowsError(try client.status()); XCTAssertEqual(wire.requests.count, count)
    }
}
