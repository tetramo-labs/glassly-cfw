import Foundation
@testable import MemoMindCore
import XCTest

final class FirmwareImageTests: XCTestCase {
    private let stockSHA = "08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712"
    private let readerSHA = "270dfe85438e6ff0f904a09215e15419292e16b8c7bbc36aafec50543c780c55"

    private let canarySHA = "79a4158c5d82b97c248d0dd2b7e366df03206393c1c2a7275677b8985d81398a"

    private let rasterSHA = "b89a6adab63bb8e09c2b05a261af4ae9b80f5b7fc4e81c15c016dc457dfba261"

    /// Fixtures are required, never skipped. Resolve from source location rather
    /// than the test process's working directory or an optional environment var.
    private func repositoryRoot() throws -> URL {
        var directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0 ..< 10 {
            if FileManager.default.fileExists(atPath: directory.appendingPathComponent("captures/firmware/ota-1.0.3.127-jhv3_release.bin").path) {
                return directory
            }
            let parent = directory.deletingLastPathComponent()
            if parent == directory {
                break
            }
            directory = parent
        }
        throw NSError(domain: "RequiredFirmwareFixturesMissing", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "Repository stock, boot-verified reader and reviewed offline canary/raster fixtures are required"])
    }

    private func fixture(_ relative: String) throws -> Data {
        try Data(contentsOf: repositoryRoot().appendingPathComponent(relative))
    }

    private func stock() throws -> Data {
        try fixture("captures/firmware/ota-1.0.3.127-jhv3_release.bin")
    }

    /// Independent bit-at-a-time reference; production uses a lookup table.
    private func crc(_ bytes: ArraySlice<UInt8>) -> UInt32 {
        var value = UInt32.max
        for byte in bytes {
            value ^= UInt32(byte)
            for _ in 0 ..< 8 {
                value = (value & 1) != 0 ? (value >> 1) ^ 0xEDB8_8320 : value >> 1
            }
        }
        return ~value
    }

    private func write(_ value: UInt64, at: Int, count: Int = 4, big: Bool = false, into bytes: inout [UInt8]) {
        for i in 0 ..< count {
            bytes[at + i] = UInt8(truncatingIfNeeded: value >> (8 * (big ? count - 1 - i : i)))
        }
    }

    private func repair(_ bytes: inout [UInt8]) {
        let trailer = bytes.count - 4
        write(UInt64(bytes.count - 18), at: 6, big: true, into: &bytes)
        let packedCRC = crc(bytes[150 ..< trailer]); write(UInt64(packedCRC), at: trailer, into: &bytes)
        let tableCRC = crc(bytes[34 ..< 146]); write(UInt64(tableCRC), at: 146, into: &bytes)
        let outerCRC = crc(bytes[18...]); write(UInt64(outerCRC), at: 14, big: true, into: &bytes)
    }

    /// Seven syntactically framed streams, deliberately NOT real compressed
    /// images. This tests layout checks independently and makes their limits
    /// explicit: only byte-exact catalog eligibility can authorize an image.
    private func synthetic(length: Int = 245) -> [UInt8] {
        precondition(length >= 245)
        var bytes = [UInt8](repeating: 0, count: length)
        bytes.replaceSubrange(0 ..< 6, with: [0x4D, 0x45, 2, 1, 0x10, 1])
        write(0xABCD_6543, at: 18, into: &bytes)
        var offset = 150
        for i in 0 ... 6 {
            let size = i == 0 ? 344 : 32
            let packed = i == 6 ? length - 4 - offset : 13
            let table = i == 0 ? 34 : 50 + (i - 1) * 16
            write(UInt64(size), at: table, into: &bytes)
            write(UInt64(packed), at: table + 4, into: &bytes)
            if i != 0 {
                write(UInt64(i * 4096), at: table + 8, into: &bytes)
                write(UInt64((i + 1) * 4096), at: table + 12, into: &bytes)
            }
            bytes.replaceSubrange(offset ..< offset + 5, with: [0x5D, 0, 0x80, 0, 0])
            write(UInt64(size), at: offset + 5, count: 8, into: &bytes)
            offset += packed
        }
        repair(&bytes)
        return bytes
    }

    private func malformed(_ bytes: [UInt8], contains text: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertThrowsError(try FirmwareContainer.inspect(bytes), file: file, line: line) { error in
            guard case let FirmwareImageError.malformedContainer(reason) = error else {
                XCTFail("Unexpected error \(error)", file: file, line: line); return
            }
            XCTAssertTrue(reason.contains(text), reason, file: file, line: line)
        }
    }

    func testIndependentHashAndCRCVectors() {
        XCTAssertEqual(FirmwareIntegrity.sha256(Data()), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        XCTAssertEqual(FirmwareIntegrity.sha256(Data("abc".utf8)), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        XCTAssertEqual(FirmwareIntegrity.crc32([UInt8]()), 0)
        XCTAssertEqual(FirmwareIntegrity.crc32(Array("123456789".utf8)), 0xCBF4_3926)
        XCTAssertEqual(FirmwareIntegrity.crc32((0 ... 255).map(UInt8.init)), 0x2905_8C73)
    }

    func testRequiredActualStockFixture() throws {
        let bytes = try stock()
        let image = try EligibleFirmware.load(data: bytes, expectedSHA256: stockSHA)
        XCTAssertEqual(image.data, bytes); XCTAssertEqual(image.sha256, stockSHA)
        XCTAssertFalse(image.modified); XCTAssertEqual(image.releaseName, "stock-1.0.3.127-jhv3-release")
        XCTAssertEqual(image.profile, "H001Y-1.0.3.127")
        let parsed = try FirmwareContainer.inspect(Array(bytes))
        XCTAssertEqual(parsed.streams.count, 7)
        XCTAssertEqual(parsed.streams[3].packedSize, 914_600)
        XCTAssertEqual(parsed.streams[6].offset + parsed.streams[6].packedSize, bytes.count - 4)
    }

    func testRequiredActualBootVerifiedReaderFixture() throws {
        let bytes = try fixture("captures/firmware/exclusive-store-reader-001/firmware.bin")
        let image = try EligibleFirmware.load(data: bytes, expectedSHA256: readerSHA.uppercased())
        XCTAssertEqual(image.data, bytes); XCTAssertEqual(image.sha256, readerSHA)
        XCTAssertTrue(image.modified); XCTAssertEqual(image.releaseName, "exclusive-store-reader-001")
        XCTAssertEqual(image.profile, "H001Y-1.0.3.127-full-store-read-v1")
        let parsed = try FirmwareContainer.inspect(Array(bytes))
        XCTAssertEqual(parsed.streams[0].packedSize, 171)
        XCTAssertEqual(parsed.streams[3].unpackedSize, 1_827_232)
        XCTAssertEqual(try XCTUnwrap(parsed.streams[3].flashEnd) - parsed.streams[3].flashStart!, 0x200000)
    }

    func testRequiredActualReviewedOfflineCanaryFixture() throws {
        let bytes = try fixture("captures/firmware/flash-canary-001/firmware.bin")
        let image = try EligibleFirmware.load(data: bytes, expectedSHA256: canarySHA)
        XCTAssertEqual(bytes.count, 2_226_788)
        XCTAssertEqual(image.data, bytes); XCTAssertEqual(image.sha256, canarySHA)
        XCTAssertTrue(image.modified); XCTAssertEqual(image.releaseName, "flash-canary-001")
        XCTAssertEqual(image.profile, "H001Y-1.0.3.127-flash-canary-v1")
        let parsed = try FirmwareContainer.inspect(Array(bytes))
        XCTAssertEqual(parsed.headerSHA256, "40a000fa3a707aff2a1376857bf88f62fd5db453caec3827f757c51768887993")
        XCTAssertEqual(parsed.streams[0].packedSHA256, "e5a3cc0e3836694bb98e295d89620ec76550daa276491758f87beb58830a557b")
        XCTAssertEqual(parsed.streams[3].packedSize, 955_686)
        XCTAssertEqual(parsed.streams[3].unpackedSize, 1_832_800)
        XCTAssertEqual(parsed.streams[3].packedSHA256, "e4bbda6bea9c13e830b82e50bcc071385039ee9b06395ec8001dc38942509299")
        XCTAssertEqual(parsed.streams[6].offset + parsed.streams[6].packedSize, bytes.count - 4)
    }

    func testCanaryEligibilityDoesNotAdmitAlteredBytesOrRawRuntime() throws {
        var bytes = try Array(fixture("captures/firmware/flash-canary-001/firmware.bin"))
        // Alter opaque packed data while preserving every container CRC.
        bytes[919_369 + 100] ^= 1
        repair(&bytes)
        XCTAssertThrowsError(try EligibleFirmware.load(data: Data(bytes), expectedSHA256: canarySHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .sha256Mismatch)
        }
        let rawRuntime = try fixture("captures/firmware/flash-canary-001/runtime.bin")
        XCTAssertThrowsError(try EligibleFirmware.load(data: rawRuntime, expectedSHA256: canarySHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .wrongLength(expected: 2_226_788, actual: 59584))
        }
        XCTAssertThrowsError(try EligibleFirmware.load(data: rawRuntime, expectedSHA256: FirmwareIntegrity.sha256(rawRuntime))) {
            XCTAssertEqual($0 as? FirmwareImageError, .releaseNotInCatalog)
        }
    }

    func testRequiredActualReviewedOfflineRasterFixture() throws {
        let bytes = try fixture("captures/firmware/raster-commands-001/firmware.bin")
        let image = try EligibleFirmware.load(data: bytes, expectedSHA256: rasterSHA)
        XCTAssertEqual(bytes.count, 2_227_971)
        XCTAssertEqual(image.data, bytes); XCTAssertEqual(image.sha256, rasterSHA)
        XCTAssertTrue(image.modified); XCTAssertEqual(image.releaseName, "raster-commands-001")
        XCTAssertEqual(image.profile, "H001Y-1.0.3.127-flash-canary-v1")
        let parsed = try FirmwareContainer.inspect(Array(bytes))
        XCTAssertEqual(parsed.headerSHA256, "5c86bd35693aba72250297f0e63fc568579d6f572cc3a1a93d7eaa3d9f65f85c")
        XCTAssertEqual(parsed.streams[0].packedSHA256, "07c6f9bb617f88b29367641c0abdfbd669e62710449a0b8c0c88eba41d4c62c2")
        XCTAssertEqual(parsed.streams[3].packedSize, 956_869)
        XCTAssertEqual(parsed.streams[3].unpackedSize, 1_834_608)
        XCTAssertEqual(parsed.streams[3].packedSHA256, "750f7970025f86d4721ce3095139121254ca7969577f0fbbe5020eb22bb18cc3")
        XCTAssertEqual(parsed.streams[6].offset + parsed.streams[6].packedSize, bytes.count - 4)
        let previous = try FirmwareContainer.inspect(Array(fixture("captures/firmware/flash-canary-001/firmware.bin")))
        for index in [1, 2, 4, 5, 6] {
            XCTAssertEqual(parsed.streams[index].packedSHA256, previous.streams[index].packedSHA256)
        }
    }

    func testRasterEligibilityRejectsRepairedCRCsAndRawRuntime() throws {
        var bytes = try Array(fixture("captures/firmware/raster-commands-001/firmware.bin"))
        bytes[919_369 + 100] ^= 1
        repair(&bytes)
        XCTAssertThrowsError(try EligibleFirmware.load(data: Data(bytes), expectedSHA256: rasterSHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .sha256Mismatch)
        }
        let runtime = try fixture("captures/firmware/raster-commands-001/runtime.bin")
        XCTAssertThrowsError(try EligibleFirmware.load(data: runtime, expectedSHA256: rasterSHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .wrongLength(expected: 2_227_971, actual: 61392))
        }
        XCTAssertThrowsError(try EligibleFirmware.load(data: runtime, expectedSHA256: FirmwareIntegrity.sha256(runtime))) {
            XCTAssertEqual($0 as? FirmwareImageError, .releaseNotInCatalog)
        }
    }

    func testInvalidOrUntrustedExpectedDigestCannotExpandCatalog() throws {
        for expected in ["", stockSHA + "0", " " + stockSHA, String(repeating: "g", count: 64), String(repeating: "é", count: 64)] {
            XCTAssertThrowsError(try EligibleFirmware.load(data: Data(), expectedSHA256: expected)) {
                XCTAssertEqual($0 as? FirmwareImageError, .invalidExpectedSHA256)
            }
        }
        for expected in [String(repeating: "0", count: 64), "c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992"] {
            XCTAssertThrowsError(try EligibleFirmware.load(data: Data(), expectedSHA256: expected)) {
                XCTAssertEqual($0 as? FirmwareImageError, .releaseNotInCatalog)
            }
        }
        XCTAssertThrowsError(try EligibleFirmware.load(data: stock(), expectedSHA256: readerSHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .wrongLength(expected: 2_223_753, actual: 2_185_697))
        }
    }

    func testTruncationLengthAndOuterVersion() {
        for length in [0, 1, 17, 149, 153] {
            malformed([UInt8](repeating: 0, count: length), contains: "truncated")
        }
        for offset in 0 ..< 6 {
            var bytes = synthetic(); bytes[offset] ^= 1
            malformed(bytes, contains: "signature/version")
        }
        var bytes = synthetic(); bytes[9] ^= 1
        malformed(bytes, contains: "payload length")
        bytes = synthetic(); bytes[18] ^= 1; repair(&bytes)
        malformed(bytes, contains: "inner magic")
    }

    func testThreeIndependentCRCLayers() throws {
        var bytes = synthetic(); bytes[150] ^= 1
        XCTAssertThrowsError(try FirmwareContainer.inspect(bytes)) { XCTAssertEqual($0 as? FirmwareImageError, .checksumMismatch("outer payload")) }
        bytes = synthetic(); bytes[34] ^= 1
        let outerCRC = crc(bytes[18...]); write(UInt64(outerCRC), at: 14, big: true, into: &bytes)
        XCTAssertThrowsError(try FirmwareContainer.inspect(bytes)) { XCTAssertEqual($0 as? FirmwareImageError, .checksumMismatch("compression table")) }
        bytes = synthetic(); bytes[163] ^= 1
        let outerOnly = crc(bytes[18...]); write(UInt64(outerOnly), at: 14, big: true, into: &bytes)
        XCTAssertThrowsError(try FirmwareContainer.inspect(bytes)) { XCTAssertEqual($0 as? FirmwareImageError, .checksumMismatch("compressed streams")) }
    }

    func testBoundsHugeLengthsAndAllocationRanges() {
        for size in [UInt64(0), 12, UInt64(UInt32.max)] {
            var bytes = synthetic(); write(size, at: 38, into: &bytes); repair(&bytes)
            malformed(bytes, contains: "stream 0 bounds")
        }
        var bytes = synthetic(); write(343, at: 34, into: &bytes); repair(&bytes)
        malformed(bytes, contains: "metadata unpacked length")
        bytes = synthetic(); write(4096, at: 62, into: &bytes); repair(&bytes)
        malformed(bytes, contains: "flash range")
        for size in [UInt64(31), 4097, UInt64(UInt32.max)] {
            bytes = synthetic(); write(size, at: 50, into: &bytes); repair(&bytes)
            malformed(bytes, contains: "allocation")
        }
    }

    func testLZMAHeadersAndExactTrailerBoundary() {
        for offset in [150, 151, 152, 153, 154] {
            var bytes = synthetic(); bytes[offset] ^= 1; repair(&bytes)
            malformed(bytes, contains: "LZMA properties/dictionary")
        }
        for offset in 155 ..< 163 {
            var bytes = synthetic(); bytes[offset] ^= 1; repair(&bytes)
            malformed(bytes, contains: "LZMA length")
        }
        var bytes = synthetic(); bytes.insert(0, at: bytes.count - 4); repair(&bytes)
        malformed(bytes, contains: "unaccounted bytes")
    }

    func testValidCRCsAndSyntaxNeverAuthorizeUncatalogedBytes() throws {
        let bytes = synthetic(length: 2_185_697)
        XCTAssertEqual(try FirmwareContainer.inspect(bytes).streams.count, 7)
        XCTAssertThrowsError(try EligibleFirmware.load(data: Data(bytes), expectedSHA256: stockSHA)) {
            XCTAssertEqual($0 as? FirmwareImageError, .sha256Mismatch)
        }
        XCTAssertThrowsError(try EligibleFirmware.load(data: Data(bytes), expectedSHA256: FirmwareIntegrity.sha256(Data(bytes)))) {
            XCTAssertEqual($0 as? FirmwareImageError, .releaseNotInCatalog)
        }
    }

    func testSnapshotDoesNotRetainMutableCallerStorage() throws {
        let fixture = try stock()
        let pointer = UnsafeMutableRawPointer.allocate(byteCount: fixture.count, alignment: 8)
        defer { pointer.deallocate() }
        fixture.withUnsafeBytes { pointer.copyMemory(from: $0.baseAddress!, byteCount: fixture.count) }
        let borrowed = Data(bytesNoCopy: pointer, count: fixture.count, deallocator: .none)
        let image = try EligibleFirmware.load(data: borrowed, expectedSHA256: stockSHA)
        pointer.storeBytes(of: UInt8(0), as: UInt8.self)
        XCTAssertEqual(image.data[0], 0x4D)
        var copy = image.data; copy[1] = 0
        XCTAssertEqual(image.data[1], 0x45)
        XCTAssertEqual(FirmwareIntegrity.sha256(image.data), stockSHA)
    }
}
