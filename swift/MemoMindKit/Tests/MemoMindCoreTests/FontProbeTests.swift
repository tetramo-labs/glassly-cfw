import Foundation
@testable import MemoMindCore
import XCTest

/// Synthetic repertoires behind a fake mode-15 draw; nothing here touches a device.
final class FontProbeTests: XCTestCase {
    /// A glasses font that draws a string only when every scalar is in `runs`,
    /// as the native adapter does.
    private func font(_ runs: [ClosedRange<UInt32>], log: ((Data) -> Void)? = nil) -> (Data) throws -> Bool {
        { data in
            log?(data)
            XCTAssertLessThanOrEqual(data.count, FontProbe.maxStringBytes)
            let text = String(decoding: data, as: UTF8.self)
            XCTAssertFalse(text.unicodeScalars.contains { $0.value < 0x20 })
            return text.unicodeScalars.allSatisfy { scalar in runs.contains { $0.contains(scalar.value) } }
        }
    }

    private let ascii: ClosedRange<UInt32> = 0x20 ... 0x7E

    func testChunksRespectTheStringBudgetAndKeepOrder() {
        let scalars = Array(UInt32(0x4E00) ... 0x4FFF)
        let chunks = FontProbe.chunks(scalars)
        XCTAssertEqual(chunks.flatMap { $0 }, scalars)
        XCTAssertEqual(chunks[0].count, 85, "three UTF-8 bytes per ideograph")
        for chunk in chunks {
            XCTAssertLessThanOrEqual(FontProbe.utf8(chunk).count, 255)
        }
        XCTAssertEqual(FontProbe.chunks(Array(UInt32(0x20) ... 0x7F))[0].count, 96)
        XCTAssertEqual(FontProbe.chunks(Array(UInt32(0x1F600) ... 0x1F64F))[0].count, 63)
        XCTAssertEqual(FontProbe.utf8([0x41, 0xE9, 0x4E00, 0x1F600]), Data("A\u{E9}\u{4E00}\u{1F600}".utf8))
    }

    func testScalarsSkipControlsSurrogatesAndNoncharacters() {
        XCTAssertEqual(FontProbe.scalars(FontProbe.Block("x", 0x0000, 0x0020)), [0x20])
        XCTAssertTrue(FontProbe.scalars(FontProbe.Block("x", 0x0020, 0x007F)).contains(0x7F), "DEL is a glyph to the decoder")
        XCTAssertEqual(FontProbe.scalars(FontProbe.Block("x", 0xD7FF, 0xE000)), [0xD7FF, 0xE000])
        XCTAssertEqual(FontProbe.scalars(FontProbe.Block("x", 0xFDCF, 0xFDF0)), [0xFDCF, 0xFDF0])
        XCTAssertEqual(FontProbe.scalars(FontProbe.Block("x", 0xFFFD, 0xFFFF)), [0xFFFD])
        XCTAssertEqual(FontProbe.scalars(FontProbe.Block("x", 0x1FFFD, 0x1FFFF)), [0x1FFFD])
        for block in FontProbe.blocks {
            XCTAssertLessThanOrEqual(block.first, block.last, block.name)
        }
        XCTAssertEqual(FontProbe.blocks.map(\.first), FontProbe.blocks.map(\.first).sorted(), "blocks ascend")
    }

    func testExactBlocksRecoverEveryRun() throws {
        let runs: [ClosedRange<UInt32>] = [ascii, 0xE9 ... 0xE9, 0x2013 ... 0x2014, 0x2026 ... 0x2026]
        let blocks = [FontProbe.Block("Basic Latin", 0x20, 0x7F), FontProbe.Block("Latin-1 Supplement", 0xA0, 0xFF),
                      FontProbe.Block("General Punctuation", 0x2000, 0x206F)]
        var seen: [FontProbe.BlockResult] = []
        let report = try FontProbe.probe(blocks: blocks, draw: font(runs)) { seen.append($0) }
        XCTAssertEqual(report.runs, [.init(first: 0x20, last: 0x7E), .init(first: 0xE9, last: 0xE9),
                                     .init(first: 0x2013, last: 0x2014), .init(first: 0x2026, last: 0x2026)])
        XCTAssertEqual(report.blocks, seen)
        XCTAssertEqual(report.blocks.map(\.present), [95, 1, 3])
        XCTAssertEqual(report.blocks.map(\.absent), [1, 95, 109])
        XCTAssertEqual(report.blocks.map(\.unresolved), [0, 0, 0])
        XCTAssertEqual(report.requests, 2 + report.blocks.map(\.requests).reduce(0, +))
        // Every absent scalar has to be refused on its own, so a refused chunk costs
        // about two requests per scalar; a drawn chunk costs one.
        XCTAssertLessThanOrEqual(report.requests, 2 + 2 * (96 + 96 + 112))
        XCTAssertGreaterThan(report.requests, 96 + 96 + 112)
        XCTAssertEqual(report.swiftRanges, "0x0020 ... 0x007E, 0x00E9 ... 0x00E9, 0x2013 ... 0x2014, 0x2026 ... 0x2026")
        XCTAssertEqual(report.kotlinRanges, "0x0020..0x007E, 0x00E9..0x00E9, 0x2013..0x2014, 0x2026..0x2026")
    }

    func testSampledBlocksSettleWhatTheSamplesReachAndLeaveTheRestUnresolved() throws {
        // GB2312-like: a long ideograph run, then a short run no chunk sample lands on.
        let runs: [ClosedRange<UInt32>] = [ascii, 0x4E00 ... 0x5000, 0x5060 ... 0x5063]
        let blocks = [FontProbe.Block("CJK Unified Ideographs", 0x4E00, 0x51FF, .sampled)]
        var strings = 0
        let report = try FontProbe.probe(blocks: blocks, draw: font(runs) { _ in strings += 1 })
        XCTAssertEqual(report.runs, [.init(first: 0x4E00, last: 0x5000)])
        let block = try XCTUnwrap(report.blocks.first)
        // 1024 scalars in chunks of 85: six drawn whole, the seventh (0x4FFE..0x5052)
        // bisected because its first sample draws, the rest silent, the last one 4 wide.
        XCTAssertEqual(block.present, 0x201)
        XCTAssertEqual(block.absent, 85 - 3)
        XCTAssertEqual(block.unresolved, 5 * 85 + 4, "silent chunks stay whole, the short last one too")
        XCTAssertEqual(block.present + block.absent + block.unresolved, 0x400)
        XCTAssertEqual(strings, report.requests)
        XCTAssertLessThanOrEqual(report.requests, 2 + 6 + 2 + 2 * 85 + 6 * 4, "silent chunks cost four requests, bisection two per scalar")
        XCTAssertGreaterThan(report.requests, 2 + 6 + 6 * 4)
    }

    func testCalibrationStopsWhenNothingCanBeMeasured() {
        XCTAssertThrowsError(try FontProbe.probe(blocks: [], draw: { _ in false })) {
            XCTAssertEqual($0 as? FontProbe.Failure, .asciiRefused)
        }
        XCTAssertThrowsError(try FontProbe.probe(blocks: [], draw: { _ in true })) {
            XCTAssertEqual($0 as? FontProbe.Failure, .unassignedDrawn)
        }
        var sent: [Data] = []
        XCTAssertEqual(try FontProbe.probe(blocks: [], draw: { sent.append($0); return $0 != Data("\u{378}".utf8) }).requests, 2)
        XCTAssertEqual(sent.last, Data("\u{378}".utf8))
    }

    func testReportRoundTripsThroughJSON() throws {
        let report = try FontProbe.probe(blocks: [FontProbe.Block("Basic Latin", 0x20, 0x7F)], draw: font([ascii]))
        let data = try JSONEncoder().encode(report)
        XCTAssertEqual(try JSONDecoder().decode(FontProbe.Report.self, from: data), report)
    }
}
