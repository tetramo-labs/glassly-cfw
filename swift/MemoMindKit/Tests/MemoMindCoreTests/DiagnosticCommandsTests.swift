// SPDX-License-Identifier: MIT
// Literal wire fixtures independently checked by verbatim pinned G2 branches.
// G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce patches/zlib_glue.c.
// Evidence: analysis/diagnostics-swift-20261102/reference.json (2071 checks).
import Foundation
@testable import MemoMindCore
import XCTest

final class DiagnosticCommandsTests: XCTestCase {
    func testDefinedDiagnosticsMatchPinnedContract() {
        let fixtures: [(DiagnosticControl, Data)] = [
            (.clear, Data([0x07, 0x00])),
            (.hide, Data([0x07, 0x01])),
            (.show, Data([0x07, 0x02])),
        ]
        XCTAssertEqual(DiagnosticControl.allCases, fixtures.map(\.0))
        for (action, wire) in fixtures {
            XCTAssertEqual(RasterCommands.diagnostics(action), wire)
            XCTAssertEqual(wire.count, 2)
        }
        // Raw upstream unknown/missing subcommands succeed without action;
        // this typed API intentionally has no way to manufacture those no-ops.
        for value in 0 ... 255 {
            XCTAssertEqual(DiagnosticControl(rawValue: UInt8(value)) != nil, value <= 2)
        }
    }

    func testCleanupUsesCanonicalSingleByte() {
        XCTAssertEqual(RasterCommands.cleanupSession(), Data([0x0B]))
        XCTAssertEqual(RasterCommands.cleanupSession().count, 1)
        // Every call returns a value; changing one cannot add trailing data
        // or a highbit to later commands.
        var changed = RasterCommands.cleanupSession()
        changed[0] |= 0x80; changed.append(255)
        XCTAssertEqual(changed, Data([0x8B, 255]))
        XCTAssertEqual(RasterCommands.cleanupSession(), Data([0x0B]))
    }

    func testDiagnosticsAndCleanupRemainForbiddenInBundles() {
        var commands = DiagnosticControl.allCases.map(RasterCommands.diagnostics)
        commands.append(RasterCommands.cleanupSession())
        for original in commands {
            for high: UInt8 in [0, 0x80] {
                var command = original; command[0] |= high
                for trailing in [Data(), Data([0, 255])] {
                    XCTAssertThrowsError(try RasterCommands.bundle([Data([36, 0]), command + trailing])) {
                        XCTAssertEqual($0 as? BundleCommandError, .unsupportedMode(index: 1, mode: command[0]))
                    }
                }
            }
        }
        // Upstream's accepted one-byte diagnostic no-op is not a bundle child.
        for raw: UInt8 in [7, 0x87] {
            XCTAssertThrowsError(try RasterCommands.bundle([Data([raw])])) {
                XCTAssertEqual($0 as? BundleCommandError, .unsupportedMode(index: 0, mode: raw))
            }
        }
    }
}

final class DiagnosticSnapshotTests: XCTestCase {
    private let golden = "070100013412cdab78563412ffffffffa500efbe"
    private func json(_ state: String) -> String {
        "{\"glassly\":\"diagnostics\",\"abi\":1,\"result\":\"ok\",\"presentation\":\"unchanged\",\"stateHex\":\"\(state)\"}"
    }

    private func message(_ raw: Data, event: UInt8 = 9, service: UInt8 = 15, command: UInt8 = 0x7D, kind: UInt8 = 5) throws -> GMMessage {
        let tlv = GMTLV(kind: kind, value: raw)
        return try GMMessage(head: 0xFA, event: event, service: service, command: command, body: tlv.encoded(), tlvs: [tlv])
    }

    private func decode(_ raw: String) throws -> DiagnosticSnapshot {
        try DiagnosticSnapshot.decode(message(Data(raw.utf8)), expectedEvent: 9)
    }

    func testIndependentLittleEndianGoldenAndCodable() throws {
        // Independent layout: flags7, hidden1, seen0, resync1; LE1234/abcd,
        // LE12345678/ffffffff; modea5, reserved0, LEbeef. No cross-field inference.
        let value = try decode(json(golden))
        XCTAssertEqual(value.flags, 7); XCTAssertTrue(value.reordered); XCTAssertTrue(value.skipped); XCTAssertTrue(value.duplicated)
        XCTAssertTrue(value.hidden); XCTAssertFalse(value.seen); XCTAssertTrue(value.resync)
        XCTAssertEqual(value.lastFrameID, 0x1234); XCTAssertEqual(value.highFrameID, 0xABCD)
        XCTAssertEqual(value.displayWorkerFailures, 0x1234_5678); XCTAssertEqual(value.displayAllocationFailures, UInt32.max)
        XCTAssertEqual(value.lastFailedMode, 0xA5); XCTAssertEqual(value.savedSceneEpoch, 0xBEEF)
        XCTAssertEqual(try JSONDecoder().decode(DiagnosticSnapshot.self, from: JSONEncoder().encode(value)), value)
        let zero = try decode(json(String(repeating: "0", count: 40)))
        XCTAssertFalse(zero.reordered); XCTAssertFalse(zero.skipped); XCTAssertFalse(zero.duplicated)
        XCTAssertEqual(zero.savedSceneEpoch, 0)
    }

    func testExactSchemaTypesAndDuplicateRejection() throws {
        let valid = json(golden)
        for raw in [valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":true"),
                    valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":1.0"),
                    valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":\"1\""),
                    valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":2"),
                    valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":1,\"abi\":1"),
                    valid.replacingOccurrences(of: "\"abi\":1", with: "\"abi\":1,\"a\\u0062i\":1"),
                    valid.replacingOccurrences(of: "\"ok\"", with: "\"invalid\""),
                    valid.replacingOccurrences(of: "\"unchanged\"", with: "\"presented\""),
                    valid.replacingOccurrences(of: "\"diagnostics\"", with: "\"graphics\""),
                    valid.replacingOccurrences(of: "{", with: "{\"extra\":0,"),
                    valid.replacingOccurrences(of: "\"abi\":1,", with: "")]
        {
            XCTAssertThrowsError(try decode(raw), raw)
        }
    }

    func testEveryFlagBooleanReservedAndHexBoundary() throws {
        for flag in 0 ... 255 {
            let state = String(format: "%02x", flag) + String(golden.dropFirst(2))
            if flag <= 7 {
                XCTAssertEqual(try decode(json(state)).flags, UInt8(flag))
            } else {
                XCTAssertThrowsError(try decode(json(state)))
            }
        }
        for offset in [1, 2, 3, 17] {
            for bad: UInt8 in [2, 127, 255] {
                var bytes = Array(hex(golden)); bytes[offset] = bad
                XCTAssertThrowsError(try decode(json(bytes.map { String(format: "%02x", $0) }.joined())))
            }
        }
        var reserved = Array(hex(golden)); reserved[17] = 1
        XCTAssertThrowsError(try decode(json(reserved.map { String(format: "%02x", $0) }.joined())))
        for state in ["", String(golden.dropLast()), golden + "0", golden.uppercased(), " " + golden, golden + " ", String(repeating: "é", count: 40), "g" + golden.dropFirst()] {
            XCTAssertThrowsError(try decode(json(state)))
        }
    }

    func testCorrelationTLVAndBodyConsistency() throws {
        let raw = Data(json(golden).utf8)
        for msg in try [message(raw, event: 10), message(raw, service: 14), message(raw, command: 0x7E), message(raw, kind: 2)] {
            XCTAssertThrowsError(try DiagnosticSnapshot.decode(msg, expectedEvent: 9))
        }
        let original = try message(raw)
        for tlvs in [[GMTLV](), original.tlvs + original.tlvs] {
            let bad = GMMessage(head: 0xFA, event: 9, service: 15, command: 0x7D, body: original.body, tlvs: tlvs)
            XCTAssertThrowsError(try DiagnosticSnapshot.decode(bad))
        }
        for body in [Data(), original.body + Data([0]), Data(original.body.dropLast())] {
            let bad = GMMessage(head: 0xFA, event: 9, service: 15, command: 0x7D, body: body, tlvs: original.tlvs)
            XCTAssertThrowsError(try DiagnosticSnapshot.decode(bad))
        }
    }

    func testActualGMFramingAndOneByteReads() throws {
        let response = try message(Data(json(golden).utf8))
        let frames = try GMCodec.frames(event: 9, service: 15, command: 0x7D, body: response.body)
        let stream = GMStream()
        var received = [GMMessage]()
        for byte in frames.reduce(Data(), +) {
            received += try stream.feed(Data([byte]))
        }
        XCTAssertEqual(received.count, 1)
        XCTAssertEqual(try DiagnosticSnapshot.decode(XCTUnwrap(received.first), expectedEvent: 9), try decode(json(golden)))
    }

    func testTruncationBoundsNulAndSlicedData() throws {
        let raw = Data(json(golden).utf8), expected = try decode(json(golden))
        for length in 0 ..< raw.count {
            XCTAssertThrowsError(try DiagnosticSnapshot.decode(message(raw.prefix(length))))
        }
        XCTAssertEqual(try DiagnosticSnapshot.decode(message(raw + Data([0]))), expected)
        for suffix in [Data([0, 0]), Data([255]), Data("{}".utf8)] {
            XCTAssertThrowsError(try DiagnosticSnapshot.decode(message(raw + suffix)))
        }
        XCTAssertThrowsError(try DiagnosticSnapshot.decode(message(Data(repeating: 32, count: 257))))
        let sliced = (Data([255]) + raw).dropFirst()
        XCTAssertEqual(try DiagnosticSnapshot.decode(message(sliced)), expected)
    }
}
