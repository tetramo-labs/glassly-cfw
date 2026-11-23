// SPDX-License-Identifier: MIT
import Foundation
@testable import MemoMindCore
import XCTest

final class RectangleCopyCommandTests: XCTestCase {
    private func rectangle(_ fields: [Int]) -> RasterRectangle {
        RasterRectangle(x: fields[0], y: fields[1], width: fields[2], height: fields[3])
    }

    private func fields(_ bytes: Data) -> [Int] {
        stride(from: 1, to: 17, by: 2).map { Int(bytes[$0]) | (Int(bytes[$0 + 1]) << 8) }
    }

    func testPinnedOriginalDispatcherWireVectors() throws {
        for vector in RectangleCopyVectors.cases {
            let data = try RasterCommands.rectangleCopy(source: rectangle(vector.source), destination: rectangle(vector.destination))
            XCTAssertEqual(data, hex(vector.hex), vector.name)
            XCTAssertEqual(data.count, 17); XCTAssertEqual(data[0], 9)
            XCTAssertEqual(fields(data), vector.source + vector.destination)
            XCTAssertLessThanOrEqual(data.count, RasterCommands.maximumCommandBytes)
        }
    }

    func testOddAlignmentOverlapAndSelfCopyAreAllowed() throws {
        // Every combination here is valid; mode9 must not inherit mode3 alignment.
        for width in [1, 3, 4, 15, 257] {
            for height in [1, 3, 4, 17] {
                let source = RasterRectangle(x: 1, y: 3, width: width, height: height)
                for destination in [source,
                                    RasterRectangle(x: 0, y: 2, width: width, height: height),
                                    RasterRectangle(x: 2, y: 4, width: width, height: height)]
                {
                    let data = try RasterCommands.rectangleCopy(source: source, destination: destination)
                    XCTAssertEqual(fields(data), [source.x, source.y, width, height, destination.x, destination.y, width, height])
                }
            }
        }
    }

    func testSourceAndDestinationMustFitWithoutClippingOrOverflow() throws {
        let good = RasterRectangle(x: 0, y: 0, width: 1, height: 1)
        let invalid = [(-1, 0, 1, 1), (0, -1, 1, 1), (0, 0, 0, 1), (0, 0, 1, 0),
                       (0, 0, -1, 1), (0, 0, 1, -1), (600, 0, 1, 1), (0, 350, 1, 1),
                       (599, 0, 2, 1), (0, 349, 1, 2), (0, 0, 601, 1), (0, 0, 1, 351),
                       (65535, 0, 1, 1), (0, 65535, 1, 1), (0, 0, 65535, 1),
                       (Int.max, 0, 1, 1), (0, Int.max, 1, 1), (0, 0, Int.max, 1), (0, 0, 1, Int.max),
                       (Int.min, 0, 1, 1), (0, Int.min, 1, 1), (0, 0, Int.min, 1), (0, 0, 1, Int.min)]
        for (x, y, width, height) in invalid {
            let bad = RasterRectangle(x: x, y: y, width: width, height: height)
            XCTAssertThrowsError(try RasterCommands.rectangleCopy(source: bad, destination: good)) {
                XCTAssertEqual($0 as? RectangleCopyCommandError, .invalidSource)
            }
            XCTAssertThrowsError(try RasterCommands.rectangleCopy(source: good, destination: bad)) {
                XCTAssertEqual($0 as? RectangleCopyCommandError, .invalidDestination)
            }
        }
    }

    func testBothDimensionMismatchesRejected() throws {
        let source = RasterRectangle(x: 1, y: 1, width: 4, height: 5)
        for destination in [RasterRectangle(x: 1, y: 1, width: 5, height: 5),
                            RasterRectangle(x: 1, y: 1, width: 4, height: 6),
                            RasterRectangle(x: 1, y: 1, width: 5, height: 6)]
        {
            XCTAssertThrowsError(try RasterCommands.rectangleCopy(source: source, destination: destination)) {
                XCTAssertEqual($0 as? RectangleCopyCommandError, .mismatchedDimensions)
            }
        }
    }

    func testRepeatEncodingAndCodableDoNotChangeCoordinates() throws {
        let source = RasterRectangle(x: 3, y: 5, width: 9, height: 7)
        let saved = try JSONEncoder().encode(source)
        let restored = try JSONDecoder().decode(RasterRectangle.self, from: saved)
        XCTAssertEqual(restored, source)
        let first = try RasterCommands.rectangleCopy(source: source, destination: source)
        XCTAssertEqual(try RasterCommands.rectangleCopy(source: restored, destination: restored), first)
        // Always ordinary09. No unused/right rectangle, trailing bytes, RLE or zlib.
        XCTAssertEqual(first.count, 17); XCTAssertEqual(first.first, 9)
    }
}
