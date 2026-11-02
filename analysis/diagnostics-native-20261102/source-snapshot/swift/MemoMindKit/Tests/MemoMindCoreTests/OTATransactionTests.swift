import CryptoKit
@testable import MemoMindCore
import XCTest

/// Independent raw HCI/RFCOMM capture, not Swift-generated responses.
/// Selection is identical to Python read_transcript: frames 1615/1617 + channel 6.
private struct CapturedRow { let frame: Int; let direction: Int; var data: Data }
private final class CapturedTransport: MemoMindTransport {
    var rows: [CapturedRow]
    var position = 0, writes = 0, reads = 0
    var outgoing = Data()
    var split = false, remainder = Data(), timeoutCommand: UInt8?
    init(_ rows: [CapturedRow]) {
        self.rows = rows
    }

    func write(_ data: Data) throws {
        guard position < rows.count, rows[position].direction == 0, rows[position].data == data else {
            throw MemoMindProtocolError.invalid("Capture write/order mismatch at record \(position)")
        }
        outgoing += data; writes += 1; position += 1
    }

    func read(timeout _: TimeInterval) throws -> Data {
        if remainder.isEmpty {
            guard position < rows.count, rows[position].direction == 1 else {
                throw MemoMindProtocolError.invalid("Capture read/order mismatch at record \(position)")
            }
            if let command = timeoutCommand, rows[position].data.count > 4, rows[position].data[4] == command {
                throw MemoMindProtocolError.timeout("injected lost ACK")
            }
            remainder = rows[position].data; reads += 1; position += 1
        }
        let count = split ? min(3, remainder.count) : remainder.count
        let part = Data(remainder.prefix(count)); remainder.removeFirst(count)
        return part
    }
}

final class OTATransactionTests: XCTestCase {
    private var identity: DeviceIdentity {
        DeviceIdentity(model: "H001Y", hardwareVersion: "2.1.2", frontVersion: "1.3", firmwareVersion: "1.0.2.151", mac: "4C:3C:8F:90:CC:C3")
    }

    private func fixture() throws -> (Data, [CapturedRow]) {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0 ..< 5 {
            root.deleteLastPathComponent()
        }
        let transcript = try Data(contentsOf: root.appendingPathComponent("analysis/protocol/ota-final/rfcomm.tsv"))
        let image = try Data(contentsOf: root.appendingPathComponent("captures/firmware/ota-1.0.3.127-jhv3_release.bin"))
        XCTAssertEqual(digest(transcript), "385e9feab4d41d55b84d3cae6cd06882e1cbaacfbd2b467eb66dc70975f05d99")
        XCTAssertEqual(digest(image), "08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712")
        let rows = String(decoding: transcript, as: UTF8.self).split(separator: "\n").compactMap { line -> CapturedRow? in
            let fields = line.split(separator: "\t"); let frame = Int(fields[0])!, channel = Int(fields[4])!
            guard frame == 1615 || frame == 1617 || channel == 6 else { return nil }
            return CapturedRow(frame: frame, direction: Int(fields[2].dropFirst(2), radix: 16)!, data: hex(String(fields[5])))
        }
        XCTAssertEqual(rows.first?.frame, 1615)
        return (image, rows)
    }

    private func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func prepare(_ image: Data, _ rows: [CapturedRow], modified: Bool = false, split: Bool = false,
                         health: (() throws -> Void)? = nil) throws -> (OTATransaction, CapturedTransport)
    {
        let transport = CapturedTransport(rows); transport.split = split
        try GMSession(transport: transport).notifyOTA()
        return try (OTATransaction(transport: transport, image: image, modified: modified, identity: identity,
                                   address: identity.mac, pace: 0, checkControlLink: health), transport)
    }

    private func mutate(_ rows: [CapturedRow], command: UInt8, index: Int, value: UInt8) -> [CapturedRow] {
        var result = rows
        let i = result.firstIndex { $0.direction == 1 && $0.data.starts(with: [0x70, 7, 0x6E]) && $0.data[4] == command }!
        let offset = index < 0 ? result[i].data.count + index : index
        result[i].data[offset] = value
        return result
    }

    func testEveryCapturedWriteAndAll494BlockACKs() throws {
        let (image, rows) = try fixture()
        let (driver, io) = try prepare(image, rows)
        let result = try driver.run()
        XCTAssertEqual(result.blocks, 494); XCTAssertEqual(result.chunks, 3457)
        XCTAssertEqual(result.transferredRange, [162_757, image.count])
        XCTAssertEqual(result.state, "reboot acknowledged")
        XCTAssertFalse(result.postRebootVersionVerified)
        XCTAssertEqual(io.position, rows.count); XCTAssertEqual(io.writes, 3464); XCTAssertEqual(io.reads, 501)
        XCTAssertEqual(digest(io.outgoing), "f4acaa5ca1a8a02001328eebc88c52be4ab65216cf8f42c70e09e77dda294004")
        XCTAssertThrowsError(try driver.run())
        XCTAssertEqual(io.position, rows.count)
        // Captured transfer crosses the sequence wrap and uses per-block base advancement,
        // not last-fragment+1. These are asserted independently of byte equality.
        XCTAssertEqual(driver.blocks[0].baseSequence, 5)
        XCTAssertEqual(driver.blocks[0].ackSequence, 11)
        XCTAssertEqual(driver.blocks[1].baseSequence, 6)
        XCTAssertTrue(driver.blocks.contains { $0.baseSequence == 0 })
    }

    func testCompleteCaptureWithThreeByteReads() throws {
        let (image, rows) = try fixture(); let (driver, io) = try prepare(image, rows, split: true)
        XCTAssertEqual(try driver.run().chunks, 3457); XCTAssertEqual(io.position, rows.count)
    }

    func testCheckOnlyStopsBeforeEntry() throws {
        let (image, rows) = try fixture(); let (driver, io) = try prepare(image, rows)
        let result = try driver.run(checkOnly: true)
        XCTAssertEqual(result.blocks, 0); XCTAssertEqual(result.chunks, 0)
        XCTAssertEqual(io.position, 8); XCTAssertEqual(io.writes, 4)
    }

    func testUnsupportedCanUpdateNeverEnters() throws {
        let (image, rows) = try fixture()
        for status: UInt8 in [0, 1, 2, 4, 255] {
            let (driver, io) = try prepare(image, mutate(rows, command: 0xE2, index: 9, value: status))
            XCTAssertThrowsError(try driver.run()) { XCTAssertTrue(String(describing: $0).contains("can-update result 3")) }
            XCTAssertEqual(io.position, 8); XCTAssertEqual(driver.chunks, 0)
        }
    }

    func testLostACKWrongSequenceAndDelayNeverRetry() throws {
        let (image, rows) = try fixture()
        for variant in 0 ..< 3 {
            let chosen = variant == 1 ? mutate(rows, command: 0xE5, index: 8, value: 99) :
                variant == 2 ? mutate(rows, command: 0xE5, index: -2, value: 1) : rows
            let (driver, io) = try prepare(image, chosen)
            if variant == 0 {
                io.timeoutCommand = 0xE5
            }
            XCTAssertThrowsError(try driver.run()) { XCTAssertTrue(String(describing: $0).contains("No retry was sent")) }
            XCTAssertEqual(driver.chunks, 7); XCTAssertEqual(io.writes, 12)
        }
    }

    func testInvalidBoundsNoncontiguousAndModifiedResumeStop() throws {
        let (image, rows) = try fixture()
        let (bounds, _) = try prepare(image, mutate(rows, command: 0xE3, index: 10, value: 255))
        XCTAssertThrowsError(try bounds.run()); XCTAssertEqual(bounds.chunks, 0)
        let (noncontiguous, _) = try prepare(image, mutate(rows, command: 0xE5, index: 13, value: 0))
        XCTAssertThrowsError(try noncontiguous.run()); XCTAssertEqual(noncontiguous.chunks, 7)
        let (modified, _) = try prepare(image, rows, modified: true)
        XCTAssertThrowsError(try modified.run()) { XCTAssertTrue(String(describing: $0).contains("fresh offset 18")) }
        XCTAssertEqual(modified.chunks, 0)
    }

    func testAdditionalReplyBytesFailClosed() throws {
        let (image, source) = try fixture()
        var rows = source; rows[3].data += Data([0])
        let (driver, io) = try prepare(image, rows)
        XCTAssertThrowsError(try driver.run()) { XCTAssertTrue(String(describing: $0).contains("additional OTA reply")) }
        XCTAssertEqual(io.writes, 2)
    }

    func testControlHealthFailurePreventsNextWrite() throws {
        let (image, rows) = try fixture()
        let (driver, io) = try prepare(image, rows, health: { throw MemoMindProtocolError.invalid("control link lost") })
        XCTAssertThrowsError(try driver.run()); XCTAssertEqual(io.writes, 1)
    }

    func testIdentityAndTimingRejectedBeforeWrites() throws {
        let (image, rows) = try fixture(); let io = CapturedTransport(rows)
        XCTAssertThrowsError(try OTATransaction(transport: io, image: image, modified: false, identity: identity, address: "00"))
        XCTAssertThrowsError(try OTATransaction(transport: io, image: image, modified: false, identity: identity, address: identity.mac, timeout: 0))
        XCTAssertEqual(io.writes, 0)
    }
}
