@testable import MemoMindCore
import XCTest

final class OTABoundaryTests: XCTestCase {
    private let identity = DeviceIdentity(model: "H001Y", hardwareVersion: "2.1.2", frontVersion: "1.3", firmwareVersion: "1.0.3.127", mac: "AA")
    private let image = Data((0 ..< 1320).map { UInt8($0 % 251) })
    /// Independent literal reply envelope: status byte precedes echoed sequence.
    private func reply(_ command: UInt8, _ sequence: UInt8, _ payload: [UInt8]) -> Data {
        let n = payload.count + 2
        return Data([0x70, 7, 0x6E, 0, command, UInt8(n >> 8), UInt8(n & 255), 0, sequence] + payload + [0x33])
    }

    private func initial(_ entry: [UInt8] = [0, 0, 0, 0, 18, 5, 22, 1]) -> [Data] {
        [reply(2, 1, [5, 1, 0, 1, 2, 3, 3, 2, 100, 100]),
         reply(0xE1, 2, [0, 0, 0, 0, 0, 18]), reply(0xE2, 3, [3]), reply(0xE3, 4, entry)]
    }

    private func driver(_ io: QueueTransport) throws -> OTATransaction {
        try OTATransaction(transport: io, image: image, modified: true, identity: identity, address: "aa", pace: 0)
    }

    func testModifiedFreshDynamicBlocksAndFinalPartialChunk() throws {
        // Two 651-byte ranges split into630+21; second base is6 despite first lastseq6.
        let entry: [UInt8] = [0, 0, 0, 0, 18, 2, 139, 1]
        let io = QueueTransport(initial(entry) + [reply(0xE5, 6, [0, 0, 0, 2, 157, 2, 139, 0, 0]),
                                                  reply(0xE5, 7, [0, 0, 0, 0, 0, 0, 0, 0, 0]), reply(0xE6, 7, [0]), reply(3, 8, [0])])
        let transaction = try driver(io)
        let result = try transaction.run()
        XCTAssertEqual(result.transferredRange, [18, 1320]); XCTAssertEqual(result.blocks, 2); XCTAssertEqual(result.chunks, 4)
        let chunks = io.writes.filter { $0[4] == 0xE5 }
        XCTAssertEqual(chunks.map { $0[7] }, [5, 6, 6, 7])
        XCTAssertEqual(chunks.map(\.count), [647, 38, 647, 38])
        XCTAssertEqual(chunks[0].subdata(in: 12 ..< 642), image.subdata(in: 18 ..< 648))
        XCTAssertEqual(transaction.blocks.map(\.baseSequence), [5, 6])
    }

    func testNativePacingWaitsBeforeNextBlockAndCompletion() throws {
        let entry: [UInt8] = [0, 0, 0, 0, 18, 2, 139, 1]
        let io = QueueTransport(initial(entry) + [reply(0xE5, 6, [0, 0, 0, 2, 157, 2, 139, 7, 208]),
                                                  reply(0xE5, 7, [0, 0, 0, 0, 0, 0, 0, 7, 208]), reply(0xE6, 7, [0]), reply(3, 8, [0])])
        var waits: [(Int, TimeInterval)] = []
        let transaction = try OTATransaction(transport: io, image: image, modified: true,
                                             identity: identity, address: "aa", pace: 0, waitForPacing: { waits.append((io.writes.count, $0)) })
        let result = try transaction.run()
        XCTAssertEqual(result.transferredRange, [18, 1320])
        XCTAssertEqual(waits.count, 40)
        XCTAssertTrue(waits.prefix(20).allSatisfy { $0.0 == 6 && $0.1 == 0.1 })
        XCTAssertTrue(waits.suffix(20).allSatisfy { $0.0 == 8 && $0.1 == 0.1 })
        XCTAssertEqual(result.chunks, 4)
    }

    func testPacingCannotHideInvalidRangeOrContinueAfterLinkLoss() throws {
        let entry: [UInt8] = [0, 0, 0, 0, 18, 2, 139, 1]
        for invalidRange in [true, false] {
            let io = QueueTransport(initial(entry) + [reply(0xE5, 6, [0, 0, 0, 2, invalidRange ? 156 : 157, 2, 139, 7, 208])])
            var waits = 0
            let transaction = try OTATransaction(transport: io, image: image, modified: true,
                                                 identity: identity, address: "aa", pace: 0,
                                                 checkControlLink: {
                                                     if waits == 1 {
                                                         throw MemoMindProtocolError.timeout("link lost")
                                                     }
                                                 },
                                                 waitForPacing: { _ in waits += 1 })
            XCTAssertThrowsError(try transaction.run())
            XCTAssertEqual(waits, invalidRange ? 0 : 1)
            XCTAssertEqual(io.writes.count, 6)
        }
    }

    func testModifiedNonFreshOffsetRejectsAllBeforeChunks() throws {
        for offset: UInt8 in [0, 17, 19, 255] {
            let io = QueueTransport(initial([0, 0, 0, 0, offset, 5, 22, 1]))
            let transaction = try driver(io)
            XCTAssertThrowsError(try transaction.run()); XCTAssertEqual(transaction.chunks, 0); XCTAssertEqual(io.writes.count, 4)
        }
    }

    func testDuplicateMalformedAttachAndUnsupportedIdentification() throws {
        for payload: [UInt8] in [[0], [5, 1, 0], [5, 1, 0, 1, 2, 3, 1, 1], [5, 1, 0, 1, 2, 4]] {
            let io = QueueTransport([reply(2, 1, payload)])
            XCTAssertThrowsError(try driver(io).run()); XCTAssertEqual(io.writes.count, 1)
        }
        var reads = initial(); reads[1] = reply(0xE1, 2, [0, 0, 0, 0, 0, 19])
        let io = QueueTransport(reads)
        XCTAssertThrowsError(try driver(io).run()); XCTAssertEqual(io.writes.count, 2)
    }

    func testPrematureTerminalAndBadEntryStatusFailWithoutCompletion() throws {
        let io = QueueTransport(initial([0, 0, 0, 0, 18, 0, 1, 1]) + [reply(0xE5, 5, [0, 0, 0, 0, 0, 0, 0, 0, 0])])
        XCTAssertThrowsError(try driver(io).run()); XCTAssertEqual(io.writes.count, 5)
        for entry: [UInt8] in [[1, 0, 0, 0, 18, 5, 22, 1], [0, 0, 0, 0, 18, 5, 22, 0], [0]] {
            let io = QueueTransport(initial(entry)); XCTAssertThrowsError(try driver(io).run()); XCTAssertEqual(io.writes.count, 4)
        }
    }

    func testDuplicateCompleteReplyAndWrongEnvelopeFailClosed() throws {
        for variant in 0 ..< 4 {
            var reads = initial()
            if variant == 0 {
                reads[0] += reads[0]
            }
            if variant == 1 {
                reads[0][3] = 0xC0
            }
            if variant == 2 {
                reads[0][4] = 3
            }
            if variant == 3 {
                reads[0][7] = 1
            }
            let io = QueueTransport(reads)
            XCTAssertThrowsError(try driver(io).run()); XCTAssertEqual(io.writes.count, 1)
        }
    }

    func testCompletionAndRebootStatusMustBeZero() throws {
        for failure in [0xE6, 3] {
            let io = QueueTransport(initial() + [reply(0xE5, 7, [0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                                 reply(0xE6, 6, [failure == 0xE6 ? 1 : 0]), reply(3, 7, [1])])
            let transaction = try driver(io)
            XCTAssertThrowsError(try transaction.run()); XCTAssertEqual(transaction.chunks, 3)
            XCTAssertEqual(io.writes.last?[4], UInt8(failure))
        }
    }
}
