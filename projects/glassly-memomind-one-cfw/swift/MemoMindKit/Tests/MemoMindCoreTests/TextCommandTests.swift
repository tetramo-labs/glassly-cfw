// SPDX-License-Identifier: MIT
import Foundation
@testable import MemoMindCore
import XCTest

final class TextCommandTests: XCTestCase {
    func testIndependentPinnedG2ParserFixtures() throws {
        for c in TextReferenceVectors.cases {
            let bytes = hex(c.bytes)
            XCTAssertEqual(try RasterCommands.builtinText(bytes: bytes, x: c.x, y: c.y, options: c.options), hex(c.wire), c.name)
            // Fixtures are independently validated; this initializer preserves BOM.
            let text = String(decoding: bytes, as: UTF8.self)
            XCTAssertEqual(try RasterCommands.builtinText(text, x: c.x, y: c.y, options: c.options), hex(c.wire), c.name)
        }
    }

    func testSignedCoordinatesAndOffscreenBounds() throws {
        for x in [-32768, -1, 0, 599, 600, 32767] {
            for y in [-32768, -1, 0, 349, 350, 32767] {
                let data = try RasterCommands.builtinText("A", x: x, y: y)
                XCTAssertEqual(Int(Int16(bitPattern: UInt16(data[1]) | UInt16(data[2]) << 8)), x)
                XCTAssertEqual(Int(Int16(bitPattern: UInt16(data[3]) | UInt16(data[4]) << 8)), y)
            }
        }
        for value in [Int.min, -32769, 32768, Int.max] {
            XCTAssertThrowsError(try RasterCommands.builtinText("", x: value, y: 0)) {
                XCTAssertEqual($0 as? TextCommandError, .coordinateOutOfRange)
            }
            XCTAssertThrowsError(try RasterCommands.builtinText("", x: 0, y: value)) {
                XCTAssertEqual($0 as? TextCommandError, .coordinateOutOfRange)
            }
        }
    }

    func testEveryOptionPreservedAndNoHighBitEmitted() throws {
        for value in 0 ... 255 {
            let data = try RasterCommands.builtinText("", x: -1, y: 1, options: UInt8(value))
            XCTAssertEqual(data, Data([15, 255, 255, 1, 0, UInt8(value), 0]))
        }
        XCTAssertEqual(try RasterCommands.builtinText("A", x: 0, y: 0)[5], 15)
    }

    func testAllSingleBytesAndExplicitControlSemantics() throws {
        for byte in 0 ... 255 {
            let input = Data([UInt8(byte)])
            if (1 ... 127).contains(byte) {
                XCTAssertEqual(try RasterCommands.builtinText(bytes: input, x: 0, y: 0), Data([15, 0, 0, 0, 0, 15, 1, UInt8(byte)]))
            } else {
                XCTAssertThrowsError(try RasterCommands.builtinText(bytes: input, x: 0, y: 0)) {
                    XCTAssertEqual($0 as? TextCommandError, byte == 0 ? .nulNotSupported : .invalidUTF8)
                }
            }
        }
        // LF/CR, zero-shift11 and negative/positive shifts remain raw controls.
        let bytes = Data([1, 10, 11, 13, 31, 127])
        XCTAssertEqual(try RasterCommands.builtinText(bytes: bytes, x: 0, y: 0).dropFirst(7), bytes)
        XCTAssertEqual(try RasterCommands.builtinText("A\n\rB", x: 0, y: 0).dropFirst(7), Data([65, 10, 13, 66]))
    }

    func testMalformedUTF8RejectedWithoutRepair() throws {
        for encoded in TextReferenceVectors.invalid {
            let bytes = hex(encoded)
            XCTAssertThrowsError(try RasterCommands.builtinText(bytes: bytes, x: 0, y: 0)) {
                XCTAssertEqual($0 as? TextCommandError, bytes.contains(0) ? .nulNotSupported : .invalidUTF8, encoded)
            }
        }
        XCTAssertThrowsError(try RasterCommands.builtinText("\0", x: 0, y: 0)) {
            XCTAssertEqual($0 as? TextCommandError, .nulNotSupported)
        }
    }

    func testByteLimitNotCharacterCountOrGlyphAvailability() throws {
        XCTAssertEqual(try RasterCommands.builtinText(String(repeating: "A", count: 255), x: 0, y: 0).count, 262)
        let maximum = String(repeating: "é", count: 127) + "A"
        XCTAssertEqual(try RasterCommands.builtinText(maximum, x: 0, y: 0)[6], 255)
        let controls = Data(repeating: 11, count: 248) + Data("TEXT 15".utf8)
        XCTAssertEqual(try RasterCommands.builtinText(bytes: controls, x: 70, y: 100, options: 31).count, 262)
        for text in [String(repeating: "A", count: 256), String(repeating: "é", count: 128), String(repeating: "🙂", count: 64)] {
            XCTAssertThrowsError(try RasterCommands.builtinText(text, x: 0, y: 0)) {
                XCTAssertEqual($0 as? TextCommandError, .textTooLong(byteCount: 256))
            }
        }
        // A valid scalar can lack a native glyph: encoding still succeeds.
        XCTAssertEqual(try RasterCommands.builtinText("\u{10FFFF}", x: 0, y: 0).suffix(4), Data([244, 143, 191, 191]))
        XCTAssertEqual(try RasterCommands.builtinText("e\u{301}", x: 0, y: 0).suffix(3), Data([101, 204, 129]))
    }

    func testSlicedDataHasNoHiddenPrefixAndBundlePreservesHighBit() throws {
        let bytes = (Data([0]) + Data("Aé".utf8)).dropFirst()
        let normal = try RasterCommands.builtinText(bytes: bytes, x: -2, y: 3, options: 0xCF)
        XCTAssertEqual(normal, hex("0ffeff0300cf0341c3a9"))
        var high = normal; high[0] = 0x8F
        let bundle = try RasterCommands.bundle([normal, high])
        XCTAssertEqual(bundle, Data([8, 2, 10, 0]) + normal + Data([10, 0]) + high)
    }
}
