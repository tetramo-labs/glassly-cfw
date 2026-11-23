// SPDX-License-Identifier: MIT
import Foundation
@testable import MemoMindCore
import XCTest

final class BundleCommandTests: XCTestCase {
    private let minima: [(UInt8, Int)] = [(3, 8), (0x83, 12), (6, 3), (0x86, 3), (9, 17), (0x89, 33),
                                          (19, 10), (0x93, 10), (20, 11), (0x94, 11), (36, 2), (0xA4, 2),
                                          (37, 5), (0xA5, 5), (38, 10), (0xA6, 10), (39, 7), (0xA7, 7),
                                          (40, 9), (0xA8, 9), (41, 6), (0xA9, 6)]
    private func command(_ mode: UInt8, count: Int) -> Data {
        Data([mode]) + Data(count: count - 1)
    }

    private func unpackCanonical(_ wire: Data) throws -> [Data] {
        guard wire.count >= 2, wire[0] == 8 else { throw BundleCommandError.emptyCommand(index: 0) }
        var offset = 2, children = [Data]()
        for index in 0 ..< Int(wire[1]) {
            guard wire.count - offset >= 2 else { throw BundleCommandError.emptyCommand(index: index) }
            let length = Int(wire[offset]) | Int(wire[offset + 1]) << 8
            offset += 2
            guard length > 0, wire.count - offset >= length else { throw BundleCommandError.emptyCommand(index: index) }
            children.append(wire.subdata(in: offset ..< (offset + length))); offset += length
        }
        XCTAssertEqual(offset, wire.count)
        return children
    }

    func testIndependentPinnedOriginalBranchVectors() throws {
        for vector in BundleReferenceVectors.cases {
            let children = vector.children.map(hex)
            let wire = try RasterCommands.bundle(children)
            XCTAssertEqual(wire, hex(vector.wire), vector.name)
            XCTAssertEqual(try unpackCanonical(wire), children)
        }
    }

    func testZeroAnd255CountsAnd256Rejection() throws {
        XCTAssertEqual(try RasterCommands.bundle([]), Data([8, 0]))
        let children = Array(repeating: Data([36, 0]), count: 255)
        let wire = try RasterCommands.bundle(children)
        XCTAssertEqual(wire.count, 1022); XCTAssertEqual(wire[1], 255)
        XCTAssertEqual(try unpackCanonical(wire), children)
        XCTAssertThrowsError(try RasterCommands.bundle(children + [Data([36, 0])])) {
            XCTAssertEqual($0 as? BundleCommandError, .tooManyCommands(256))
        }
    }

    func testEverySupportedBaseAndHighBitEnvelopePreserved() throws {
        let children = minima.map { command($0.0, count: $0.1) }
        let wire = try RasterCommands.bundle(children)
        XCTAssertEqual(wire[0], 8)
        XCTAssertEqual(try unpackCanonical(wire), children)
        XCTAssertEqual(try unpackCanonical(wire).map { $0.first! }, minima.map(\.0))
    }

    func testEveryUnsupportedModeIncludingNestedControlAndNative15Rejected() throws {
        let supported: Set<UInt8> = [3, 6, 9, 19, 20, 36, 37, 38, 39, 40, 41]
        for value in 0 ... 255 where !supported.contains(UInt8(value) & 127) {
            let raw = UInt8(value)
            XCTAssertThrowsError(try RasterCommands.bundle([command(raw, count: 40)])) {
                XCTAssertEqual($0 as? BundleCommandError, .unsupportedMode(index: 0, mode: raw))
            }
        }
        XCTAssertThrowsError(try RasterCommands.bundle([Data([36, 0]), Data([8, 0])])) {
            XCTAssertEqual($0 as? BundleCommandError, .unsupportedMode(index: 1, mode: 8))
        }
    }

    func testEveryTruncatedEnvelopeAndDeclaredStringLengthRejected() throws {
        for (mode, minimum) in minima {
            for length in 1 ..< minimum {
                XCTAssertThrowsError(try RasterCommands.bundle([command(mode, count: length)])) {
                    XCTAssertEqual($0 as? BundleCommandError, .invalidEnvelope(index: 0, mode: mode))
                }
            }
        }
        XCTAssertThrowsError(try RasterCommands.bundle([Data()])) {
            XCTAssertEqual($0 as? BundleCommandError, .emptyCommand(index: 0))
        }
        for mode: UInt8 in [19, 0x93] {
            XCTAssertThrowsError(try RasterCommands.bundle([command(mode, count: 11)]))
        }
        for mode: UInt8 in [20, 0x94] {
            var text = command(mode, count: 14); text[10] = 3; text.replaceSubrange(11 ..< 14, with: Data("abc".utf8))
            XCTAssertEqual(try unpackCanonical(RasterCommands.bundle([text])), [text])
            XCTAssertThrowsError(try RasterCommands.bundle([Data(text.dropLast())]))
            XCTAssertThrowsError(try RasterCommands.bundle([text + Data([0])]))
            text[10] = 255; XCTAssertThrowsError(try RasterCommands.bundle([text]))
        }
    }

    func testLittleEndianLengthAndExact8192Admission() throws {
        for length in [255, 256, 4096, 8188] {
            let child = command(37, count: length)
            let wire = try RasterCommands.bundle([child])
            XCTAssertEqual(wire.count, length + 4)
            XCTAssertEqual(wire[2], UInt8(truncatingIfNeeded: length)); XCTAssertEqual(wire[3], UInt8(length >> 8))
            XCTAssertEqual(try unpackCanonical(wire), [child])
        }
        XCTAssertEqual(try RasterCommands.bundle([command(37, count: 8188)]).count, 8192)
        for length in [8189, 8192, 65535] {
            XCTAssertThrowsError(try RasterCommands.bundle([command(37, count: length)])) {
                XCTAssertEqual($0 as? BundleCommandError, .capacityExceeded(maximumCommandBytes: 8192))
            }
        }
        XCTAssertThrowsError(try RasterCommands.bundle([command(37, count: 65536)])) {
            XCTAssertEqual($0 as? BundleCommandError, .commandTooLarge(index: 0, length: 65536))
        }
        let two = [command(37, count: 4093), command(37, count: 4093)]
        XCTAssertEqual(try RasterCommands.bundle(two).count, 8192)
        XCTAssertThrowsError(try RasterCommands.bundle(two + [Data([36, 0])]))
    }

    func testOrderDataSlicesAndTypedChildComposition() throws {
        let copy = try RasterCommands.rectangleCopy(source: RasterRectangle(x: 1, y: 3, width: 7, height: 5),
                                                    destination: RasterRectangle(x: 2, y: 4, width: 7, height: 5))
        let delta = try RasterCommands.boundingBox(pixels: Data(repeating: 0xFF, count: 4), x: 0, y: 0, width: 4, height: 2, frameID: 1)
        let slice = (Data([0xFF]) + copy).dropFirst()
        let wire = try RasterCommands.bundle([slice, delta])
        XCTAssertEqual(try unpackCanonical(wire), [copy, delta])
        XCTAssertNotEqual(wire, try RasterCommands.bundle([delta, copy]))
        XCTAssertEqual(wire, try RasterCommands.bundle([copy, delta]))
    }

    func testEnvelopeChecksDoNotClaimChildSemanticAcceptance() throws {
        // These satisfy envelopes but native semantic validation rejects them:
        // zero RLE count; zero rectangle dimensions; missing shape records;
        // absent asset id; malformed retained PUT entry. No fake full validation.
        let children = [Data([6, 0, 0]), command(9, count: 17), Data([36, 255]),
                        command(19, count: 10), command(37, count: 6)]
        XCTAssertEqual(try unpackCanonical(RasterCommands.bundle(children)), children)
    }
}
