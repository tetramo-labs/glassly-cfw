// SPDX-License-Identifier: MIT
import CryptoKit
import Foundation
@testable import MemoMindCore
import XCTest

final class RasterCommandsTests: XCTestCase {
    private func packed(_ nibbles: [UInt8]) -> Data {
        precondition(nibbles.count % 2 == 0)
        return Data(stride(from: 0, to: nibbles.count, by: 2).map { nibbles[$0] << 4 | nibbles[$0 + 1] })
    }

    private func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func capacityPixels(alternating: Int) -> Data {
        packed((0 ..< alternating).map { UInt8($0 % 2) } + Array(repeating: 2, count: 210_000 - alternating))
    }

    func testAllCanonicalCountFormsAnd65535SplitAgainstDualReference() throws {
        for vector in RasterReferenceVectors.runs {
            let pixels = packed(Array(repeating: 5, count: vector.count) + Array(repeating: 10, count: 210_000 - vector.count))
            XCTAssertEqual(try RasterCommands.fullFrame(pixels: pixels), Data([6]) + hex(vector.rleHex), "run \(vector.count)")
        }
        // 65536 is one maximal65535 token, then one short1 token; never a zero16 count.
        let split = try XCTUnwrap(RasterReferenceVectors.runs.first { $0.count == 65536 })
        XCTAssertEqual(Array(hex(split.rleHex).prefix(5)), [5, 0, 255, 255, 0x15])
    }

    func testEveryColorFullFrameAgainstDualReference() throws {
        for color in 0 ..< 16 {
            let pixels = Data(repeating: UInt8(color * 17), count: 105_000)
            let command = try RasterCommands.fullFrame(pixels: pixels)
            XCTAssertEqual(command, Data([6]) + hex(RasterReferenceVectors.colors[color]))
            XCTAssertEqual(command.count, 17)
        }
        XCTAssertEqual(RasterCommands.width, 600); XCTAssertEqual(RasterCommands.height, 350)
        XCTAssertEqual(RasterCommands.tightFrameBytes, 105_000)
    }

    func testBoxHeaderLittleEndianFIDAndHighNibbleFirst() throws {
        let pixels = Data([0x12, 0x34, 0x56, 0x78])
        XCTAssertEqual(try RasterCommands.boundingBox(pixels: pixels, x: 596, y: 348, width: 4, height: 2, frameID: 0xABCD),
                       hex("0395ae0101cdab1112131415161718"))
        for fid: UInt16 in [0, 1, 255, 256, 65535] {
            let command = try RasterCommands.boundingBox(pixels: pixels, x: 0, y: 0, width: 4, height: 2, frameID: fid)
            XCTAssertEqual(command[5], UInt8(truncatingIfNeeded: fid)); XCTAssertEqual(command[6], UInt8(fid >> 8))
        }
    }

    func testRowPaddingIgnoredAndCrossRowRunsMatchReference() throws {
        let tight = packed(Array(repeating: 0, count: 15) + Array(repeating: 1, count: 16) + Array(repeating: 2, count: 17))
        var padded = Data()
        for row in 0 ..< 4 {
            padded += tight.subdata(in: row * 6 ..< (row + 1) * 6); padded += Data([0xAB, 0xCD, 0xEF])
        }
        let header = hex("0393ad0302cdab")
        let expected = header + hex(RasterReferenceVectors.crossRow)
        XCTAssertEqual(try RasterCommands.boundingBox(pixels: tight, x: 588, y: 346, width: 12, height: 4, frameID: 0xABCD), expected)
        XCTAssertEqual(try RasterCommands.boundingBox(pixels: padded, x: 588, y: 346, width: 12, height: 4, frameID: 0xABCD, rowStride: 9), expected)
        var full = Data()
        for _ in 0 ..< 350 {
            full += Data(repeating: 0x55, count: 300); full += Data(repeating: 0xEF, count: 20)
        }
        XCTAssertEqual(try RasterCommands.fullFrame(pixels: full, rowStride: 320), Data([6]) + hex(RasterReferenceVectors.colors[5]))
        XCTAssertEqual(padded.suffix(3), Data([0xAB, 0xCD, 0xEF])) // Input remains unchanged.
    }

    func testExact8192ByteAdmissionAndOneByteOverflow() throws {
        XCTAssertEqual(RasterCommands.maximumCommandBytes, 8192)
        let full = try RasterCommands.fullFrame(pixels: capacityPixels(alternating: 8175))
        XCTAssertEqual(full.count, 8192); XCTAssertEqual(digest(full), RasterReferenceVectors.capacityFullSHA256)
        let box = try RasterCommands.boundingBox(pixels: capacityPixels(alternating: 8169), x: 0, y: 0, width: 600, height: 350, frameID: 0xABCD)
        XCTAssertEqual(box.count, 8192); XCTAssertEqual(digest(box), RasterReferenceVectors.capacityBoxSHA256)
        XCTAssertThrowsError(try RasterCommands.fullFrame(pixels: capacityPixels(alternating: 8176))) {
            XCTAssertEqual($0 as? RasterCommandError, .capacityExceeded(maximumCommandBytes: 8192))
        }
        XCTAssertThrowsError(try RasterCommands.boundingBox(pixels: capacityPixels(alternating: 8170), x: 0, y: 0, width: 600, height: 350, frameID: 0)) {
            XCTAssertEqual($0 as? RasterCommandError, .capacityExceeded(maximumCommandBytes: 8192))
        }
        XCTAssertThrowsError(try RasterCommands.fullFrame(pixels: Data(repeating: 0x01, count: 105_000)))
    }

    func testMalformedBoundsIncludingIntOverflowRejected() throws {
        let boxes = [(-4, 0, 4, 2), (0, -2, 4, 2), (2, 0, 4, 2), (0, 1, 4, 2),
                     (0, 0, 2, 2), (0, 0, 4, 3), (0, 0, 0, 2), (0, 0, 4, 0),
                     (600, 0, 4, 2), (0, 350, 4, 2), (0, 0, 604, 2), (0, 0, 4, 352),
                     (Int.max, 0, 4, 2), (0, Int.max, 4, 2), (0, 0, Int.max, 2), (0, 0, 4, Int.max),
                     (Int.min, 0, 4, 2), (0, 0, Int.min, 2)]
        for (x, y, width, height) in boxes {
            XCTAssertThrowsError(try RasterCommands.boundingBox(pixels: Data(), x: x, y: y, width: width, height: height, frameID: 0)) {
                XCTAssertEqual($0 as? RasterCommandError, .invalidBounds)
            }
        }
    }

    func testExactByteCountStrideAndOverflowRejectedBeforeIndexing() throws {
        for count in [0, 104_999, 105_001] {
            XCTAssertThrowsError(try RasterCommands.fullFrame(pixels: Data(count: count)))
        }
        for stride in [Int.min, -1, 0, 299, Int.max] {
            XCTAssertThrowsError(try RasterCommands.fullFrame(pixels: Data(), rowStride: stride)) {
                XCTAssertEqual($0 as? RasterCommandError, .invalidStride)
            }
        }
        for count in [0, 3, 5] {
            XCTAssertThrowsError(try RasterCommands.boundingBox(pixels: Data(count: count), x: 0, y: 0, width: 4, height: 2, frameID: 0)) {
                XCTAssertEqual($0 as? RasterCommandError, .incorrectByteCount(expected: 4, actual: count))
            }
        }
        // Last-row padding is required too: stride3*rows2 is six bytes, not five.
        XCTAssertThrowsError(try RasterCommands.boundingBox(pixels: Data(count: 5), x: 0, y: 0, width: 4, height: 2, frameID: 0, rowStride: 3))
        XCTAssertThrowsError(try RasterCommands.boundingBox(pixels: Data(), x: 0, y: 0, width: 4, height: 2, frameID: 0, rowStride: Int.max))
    }

    func testDataSliceAndRepeatEncodingHaveNoState() throws {
        let full = Data([0xFF]) + Data(repeating: 0x55, count: 105_000)
        let slice = full.dropFirst()
        let expected = Data([6]) + hex(RasterReferenceVectors.colors[5])
        XCTAssertEqual(try RasterCommands.fullFrame(pixels: slice), expected)
        XCTAssertEqual(try RasterCommands.fullFrame(pixels: slice), expected)
        // Encoding a delta is pure; prior keyframe admission remains a receiver duty.
        XCTAssertNoThrow(try RasterCommands.boundingBox(pixels: Data(repeating: 0, count: 4), x: 0, y: 0, width: 4, height: 2, frameID: 0))
    }
}
