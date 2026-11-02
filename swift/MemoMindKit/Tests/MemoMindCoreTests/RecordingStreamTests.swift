import Foundation
@testable import MemoMindCore
import XCTest

final class RecordingStreamTests: XCTestCase {
    private func packet(_ format: RecordingFormat, count: Int = 8, command: UInt8 = 0x92) -> Data {
        var bytes = Data([0x52, command, 0, 0, 9, 255, UInt8(count), 1, 2, 3, 4, 255])
        for index in 0 ..< count {
            if format == .legacy {
                bytes.append(contentsOf: [0, 0, 0, 0, 40, 0, 0, 0, 0])
            }
            bytes.append(Data(repeating: UInt8(index + 1), count: 40))
        }
        return bytes
    }

    func testEverySplitAndCoalescedFormats() throws {
        for format in [RecordingFormat.legacy, .compact] {
            let bytes = Data([0x52, 0x13, format.rawValue, 49, 40, 0, 0x52, 0x11, 1, 0x12, 0x34, 0x56]) + packet(format)
            let expected: [RecordingEvent] = [.format(format), .started(noiseMode: 1, timestamp: 0x123456),
                                              .audio(command: 0x92, metadata: Data([9, 255, 8, 1, 2, 3, 4]),
                                                     frames: (1 ... 8).map { Data(repeating: UInt8($0), count: 40) })]
            for split in 0 ... bytes.count {
                let parser = RecordingStream()
                let events = try parser.feed(Data(bytes.prefix(split))) + parser.feed(Data(bytes.dropFirst(split)))
                XCTAssertEqual(events, expected)
                XCTAssertEqual(parser.pendingBytes, 0)
            }
            let parser = RecordingStream()
            var events = [RecordingEvent]()
            for byte in bytes {
                events += try parser.feed(Data([byte]))
            }
            XCTAssertEqual(events, expected)
        }
    }

    func testInvalidFramingPoisonsUntilReset() throws {
        var mutations = [Data([0x51, 0x92]), Data([0x52, 0x95]), Data([0x52, 0x13, 2, 49, 40, 0]),
                         Data([0x52, 0x13, 1, 48, 40, 0]), Data([0x52, 0x11, 2, 0, 0, 0])]
        for (offset, value) in [(2, 1), (3, 1), (6, 0), (6, 9), (11, 0), (16, 39)] {
            var bad = packet(.legacy)
            bad[offset] = UInt8(value)
            mutations.append(bad)
        }
        for bytes in mutations {
            let parser = RecordingStream()
            XCTAssertThrowsError(try parser.feed(bytes))
            XCTAssertThrowsError(try parser.feed(packet(.legacy)))
            parser.reset()
            XCTAssertEqual(try parser.feed(packet(.legacy)).count, 1)
        }
        XCTAssertThrowsError(try RecordingStream().feed(Data(repeating: 0, count: 65537)))
    }

    func testTruncationResetAndDistinctStreams() throws {
        let bytes = packet(.legacy)
        for end in 0 ..< bytes.count {
            let parser = RecordingStream()
            XCTAssertTrue(try parser.feed(Data(bytes.prefix(end))).isEmpty)
            XCTAssertEqual(parser.pendingBytes, end)
            parser.reset(format: .compact)
            XCTAssertEqual(parser.pendingBytes, 0)
            XCTAssertEqual(try parser.feed(packet(.compact, count: 1)).count, 1)
        }
        let parser = RecordingStream()
        let events = try parser.feed((0x90 ... 0x94).reduce(into: Data()) { $0.append(packet(.legacy, count: 1, command: UInt8($1))) })
        XCTAssertEqual(events.count, 5)
        for (index, event) in events.enumerated() {
            guard case let .audio(command, _, frames) = event else { return XCTFail("Expected audio") }
            XCTAssertEqual(Int(command), 0x90 + index)
            XCTAssertEqual(frames.count, 1)
        }
    }
}
