import CryptoKit
import Foundation

public enum FirmwareImageError: Error, Equatable, CustomStringConvertible {
    case invalidExpectedSHA256
    case releaseNotInCatalog
    case wrongLength(expected: Int, actual: Int)
    case malformedContainer(String)
    case checksumMismatch(String)
    case sha256Mismatch
    case catalogMismatch(String)

    public var description: String {
        switch self {
        case .invalidExpectedSHA256: "Expected SHA-256 must contain exactly 64 hexadecimal ASCII characters"
        case .releaseNotInCatalog: "Firmware SHA-256 is not in the internal trusted release catalog"
        case let .wrongLength(expected, actual): "Firmware length differs from catalog: expected \(expected), got \(actual)"
        case let .malformedContainer(reason): "Invalid observed ME container: \(reason)"
        case let .checksumMismatch(layer): "Firmware CRC32 mismatch: \(layer)"
        case .sha256Mismatch: "Firmware bytes differ from the explicitly expected SHA-256"
        case let .catalogMismatch(reason): "Firmware layout differs from its pinned catalog entry: \(reason)"
        }
    }
}

/// A byte-exact catalog release, validated natively before OTA eligibility.
///
/// This validates compressed-container framing, CRCs, LZMA headers and pinned
/// bytes. It does not decompress, reconstruct patches, validate decoded image
/// headers/body CRCs, establish signature policy, or guarantee a future boot.
/// Decoded reconstruction and any historical boot evidence belong to catalog
/// provenance; catalog membership alone does not mean hardware-tested. There is no public initializer/decoder or external trust file.
public struct EligibleFirmware: Sendable {
    public let data: Data
    public let sha256: String
    public let modified: Bool
    public let profile: String
    public let releaseName: String

    private init(bytes: [UInt8], release: FirmwareRelease) {
        // Own a snapshot; never retain caller-provided bytesNoCopy/NSMutableData.
        data = Data(bytes)
        sha256 = release.sha256
        modified = release.modified
        profile = release.profile
        releaseName = release.name
    }

    public static func load(data: Data, expectedSHA256: String) throws -> EligibleFirmware {
        let ascii = Array(expectedSHA256.utf8)
        guard ascii.count == 64, ascii.allSatisfy({
            (48 ... 57).contains($0) || (65 ... 70).contains($0) || (97 ... 102).contains($0)
        }) else { throw FirmwareImageError.invalidExpectedSHA256 }
        let expected = expectedSHA256.lowercased()
        guard let release = FirmwareRelease.catalog.first(where: { $0.sha256 == expected }) else {
            throw FirmwareImageError.releaseNotInCatalog
        }
        guard data.count == release.byteCount else {
            throw FirmwareImageError.wrongLength(expected: release.byteCount, actual: data.count)
        }
        // Bound allocation by catalog length before copying untrusted input.
        let bytes = Array(data)
        let layout = try FirmwareContainer.inspect(bytes)
        guard FirmwareIntegrity.sha256(Data(bytes)) == expected else { throw FirmwareImageError.sha256Mismatch }
        guard layout.headerSHA256 == release.headerSHA256 else { throw FirmwareImageError.catalogMismatch("header") }
        guard layout.streams == release.streams else { throw FirmwareImageError.catalogMismatch("seven compressed streams") }
        return EligibleFirmware(bytes: bytes, release: release)
    }
}

/// Internal helpers are testable, but cannot manufacture an EligibleFirmware.
struct FirmwareStreamPin: Equatable, Sendable {
    let offset: Int
    let packedSize: Int
    let unpackedSize: UInt32
    let flashStart: UInt32?
    let flashEnd: UInt32?
    let packedSHA256: String
}

struct FirmwareContainer {
    let headerSHA256: String
    let streams: [FirmwareStreamPin]

    static func inspect(_ bytes: [UInt8]) throws -> FirmwareContainer {
        func require(_ condition: Bool, _ reason: String) throws {
            if !condition {
                throw FirmwareImageError.malformedContainer(reason)
            }
        }
        try require(bytes.count >= 154, "truncated header/trailer")
        func little(_ offset: Int, _ count: Int = 4) -> UInt64 {
            var value: UInt64 = 0
            for i in 0 ..< count {
                value |= UInt64(bytes[offset + i]) << (8 * i)
            }
            return value
        }
        func big32(_ offset: Int) -> UInt32 {
            (0 ..< 4).reduce(UInt32(0)) { ($0 << 8) | UInt32(bytes[offset + $1]) }
        }
        try require(Array(bytes[0 ..< 6]) == [0x4D, 0x45, 2, 1, 0x10, 1], "unsupported outer signature/version")
        try require(UInt64(big32(6)) == UInt64(bytes.count - 18), "outer payload length")
        guard big32(14) == FirmwareIntegrity.crc32(bytes[18...]) else { throw FirmwareImageError.checksumMismatch("outer payload") }
        try require(little(18) == 0xABCD_6543, "inner magic")
        guard little(0x92) == UInt64(FirmwareIntegrity.crc32(bytes[0x22 ..< 0x92])) else { throw FirmwareImageError.checksumMismatch("compression table") }
        let trailer = bytes.count - 4
        guard little(trailer) == UInt64(FirmwareIntegrity.crc32(bytes[0x96 ..< trailer])) else { throw FirmwareImageError.checksumMismatch("compressed streams") }
        try require(little(0x22) == 344, "metadata unpacked length")
        var result = [FirmwareStreamPin]()
        var offset = 0x96
        // The observed profile has one metadata stream and exactly six images.
        for index in 0 ... 6 {
            let table = index == 0 ? 0x22 : 0x32 + (index - 1) * 16
            let unpacked = UInt32(little(table))
            let packedWord = little(table + 4)
            guard let packed = Int(exactly: packedWord) else { throw FirmwareImageError.malformedContainer("unrepresentable packed length") }
            try require(packed >= 13 && offset <= trailer && packed <= trailer - offset, "stream \(index) bounds")
            var start: UInt32? = nil, end: UInt32? = nil
            if index != 0 {
                let lo = UInt32(little(table + 8)), hi = UInt32(little(table + 12))
                try require(lo < hi, "component \(index) flash range")
                try require(unpacked >= 32 && unpacked <= hi - lo, "component \(index) allocation")
                start = lo; end = hi
            }
            try require(Array(bytes[offset ..< (offset + 5)]) == [0x5D, 0, 0x80, 0, 0], "stream \(index) LZMA properties/dictionary")
            try require(little(offset + 5, 8) == UInt64(unpacked), "stream \(index) LZMA length")
            result.append(FirmwareStreamPin(offset: offset, packedSize: packed, unpackedSize: unpacked,
                                            flashStart: start, flashEnd: end,
                                            packedSHA256: FirmwareIntegrity.sha256(Data(bytes[offset ..< (offset + packed)]))))
            offset += packed // bounded above by trailer; no unchecked addition
        }
        try require(offset == trailer, "unaccounted bytes before trailer")
        return FirmwareContainer(headerSHA256: FirmwareIntegrity.sha256(Data(bytes[0 ..< 0x96])), streams: result)
    }
}

enum FirmwareIntegrity {
    static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static let crcTable: [UInt32] = (0 ..< 256).map { index in
        var value = UInt32(index)
        for _ in 0 ..< 8 {
            value = (value >> 1) ^ ((value & 1) == 0 ? 0 : 0xEDB8_8320)
        }
        return value
    }

    static func crc32(_ bytes: some Sequence<UInt8>) -> UInt32 {
        var value = UInt32.max
        for byte in bytes {
            value = (value >> 8) ^ crcTable[Int((value ^ UInt32(byte)) & 0xFF)]
        }
        return value ^ UInt32.max
    }
}

private struct FirmwareRelease {
    let name: String
    let sha256: String
    let byteCount: Int
    let modified: Bool
    let profile: String
    let headerSHA256: String
    let streams: [FirmwareStreamPin]

    /// Deliberately compiled-in. No JSON, environment, signature supplied by a
    /// caller, CLI flag or alternate initializer can add a trusted release.
    static let catalog: [FirmwareRelease] = [
        FirmwareRelease(name: "stock-1.0.3.127-jhv3-release",
                        sha256: "08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712",
                        byteCount: 2_185_697, modified: false, profile: "H001Y-1.0.3.127",
                        headerSHA256: "f3d52497fd45144f8f5b3dac06c04e20ecfa1fb8ec99e2c67770cece9a4c1579",
                        streams: streamPins(.stock)),
        FirmwareRelease(name: "exclusive-store-reader-001",
                        sha256: "270dfe85438e6ff0f904a09215e15419292e16b8c7bbc36aafec50543c780c55",
                        byteCount: 2_223_753, modified: true, profile: "H001Y-1.0.3.127-full-store-read-v1",
                        headerSHA256: "6d15986b6b44e8717e948c424e57dc7aff06eb351faa71f0ba53f57c2523417e",
                        streams: streamPins(.reader)),
        // Reviewed offline reconstruction only; no canary hardware execution
        // or successful boot is claimed by admitting these exact bytes.
        FirmwareRelease(name: "flash-canary-001",
                        sha256: "79a4158c5d82b97c248d0dd2b7e366df03206393c1c2a7275677b8985d81398a",
                        byteCount: 2_226_788, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "40a000fa3a707aff2a1376857bf88f62fd5db453caec3827f757c51768887993",
                        streams: streamPins(.canary)),
        // Exact reviewed raster release; retained canary/owner/heap edits are
        // included, but this image has no hardware boot/raster proof here.
        FirmwareRelease(name: "raster-commands-001",
                        sha256: "b89a6adab63bb8e09c2b05a261af4ae9b80f5b7fc4e81c15c016dc457dfba261",
                        byteCount: 2_227_971, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "5c86bd35693aba72250297f0e63fc568579d6f572cc3a1a93d7eaa3d9f65f85c",
                        streams: streamPins(.raster)),
        // Exact reconstructed mode9 release; admission alone is not boot proof.
        FirmwareRelease(name: "rect-copy-001",
                        sha256: "680163e3789831cd3eda89a60b208cb0e85eaa61c46067dbd6d59ff26cee1885",
                        byteCount: 2_228_668, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "873f44726e712b0b3a2f234397db184b12073a55e23c3bc01a33aca488f8b55f",
                        streams: streamPins(.rectCopy)),
        // Exact reconstructed mode8 release; admission alone is not boot proof.
        FirmwareRelease(name: "bundle-commands-001",
                        sha256: "0f54b4569ef2960e2916abfcff4a434c0f1164f05d059a8418100f3da3f8fce5",
                        byteCount: 2_229_182, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "aa42bd320c3aa574c9c4b04592698e699a57ee036f04ca49a356d01002917ffc",
                        streams: streamPins(.bundle)),
        // Exact reconstructed mode15 release; admission alone is not boot proof.
        FirmwareRelease(name: "text-commands-001",
                        sha256: "e5409e0d42da0009b759852289915e92517a185c1255ad8de28a56c49c070d31",
                        byteCount: 2_229_380, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "f70265e4218854cd2abb66e3be39f6c128a47625f939388659a957afb8718feb",
                        streams: streamPins(.text)),
        // Exact reconstructed diagnostics/cleanup release; admission alone is not boot proof.
        FirmwareRelease(name: "diagnostic-commands-001",
                        sha256: "a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917",
                        byteCount: 2_230_267, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "7787494fdb8d50c1a0d578c2494cd0127a1cbcb954dc8aa2541faaa766baf016",
                        streams: streamPins(.diagnostic)),
        // Six reviewed cold-boot UI gates; existing diagnostic runtime unchanged.
        // Exact-byte admission is separate from successful hardware boot.
        FirmwareRelease(name: "dashboard-ram-002",
                        sha256: "f56376fde20515c0ad2a421eb352f774b4c21f274cda2d38f012a0d008c6d14a",
                        byteCount: 2_230_671, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "3e0ed487f355806dafd975fb2849c2e146ab8d7b8fc0e5431420c332434bc13c",
                        streams: streamPins(.dashboardRAM)),
        // Standalone RESET scratch trimming; native mutation rollback required.
        FirmwareRelease(name: "reset-undo-trim-001",
                        sha256: "3bf52f5a2a6137759ddc3546c47b1ceed42a401953e75379712044d32e2206a9",
                        byteCount: 2_226_404, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "ebe404e8435d9a0fb469e43a0784ca4547cccf130fd6921530b43315749d99b8",
                        streams: streamPins(.resetUndoTrim)),
        // Minimal launcher + 256KiB COW assets and 65535-byte raw carrier.
        // Exact reviewed 96KiB RX allocation; catalog admission is not boot proof.
        // Active light sampling: the CFW reads the sensor at a requested interval (GLASSLYCFW/14).
        // BLE frames: 'G','m' fragments reassemble, replies to BLE requests (event 0) notify over BLE (GLASSLYCFW/24).
        FirmwareRelease(name: "ble-frames-001",
                        sha256: "17a69ad20d7e364f0185eb0d6ec61e34dd08ed2c057a76648d67c8c554b3d0a8", byteCount: 2_242_788, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "841c961e21bfc0b11c33c70101889ebe7e4bb614e5b88cd203b6cd972f1cd009",
                        streams: streamPins(.bleFrames24)),
        FirmwareRelease(name: "latency-001",
                        sha256: "d2a11d71346511988c6e05adb1ab5fed9fcc89d8cb18f642cac12964eaf77206", byteCount: 2_244_038, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "87691c979384307040dcd149bd40c14b8e62c6f1e04fb1bf33617879da264662",
                        streams: streamPins(.latency27)),
        FirmwareRelease(name: "ble-link-002",
                        sha256: "e5b09e22634f2d2f996e4117b867809753e62adedac954845dd5b323149a5027", byteCount: 2_243_927, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "47a13db4278143edfa84234c38d11391d7662d50c1e02cd995320f42e05058a6",
                        streams: streamPins(.bleLink26)),
        FirmwareRelease(name: "ble-link-001",
                        sha256: "9cdd04786fceee283c30dafc20a01d680894d60026fdc78dbb7a8195fe54fae1", byteCount: 2_243_544, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "e6b967699f3425c305b6fd5f5bf65004f0ebe697366429498d5b601614c2f8f5",
                        streams: streamPins(.bleLink25)),
        // Eye-tagged objects (id bit 31; bit 30 right) render and present once per eye, so tweens run with depth; no record transport (GLASSLYCFW/23).
        FirmwareRelease(name: "stereo-002",
                        sha256: "a50afd695659cfebc44f1b13f61f71d991685d2ef33d25da5e348d97a1e01eb8", byteCount: 2_242_382, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "b6e1342e66f8c4585fbc1ae86703b73494dd3662de611d149539640ba9adcb92",
                        streams: streamPins(.stereo23)),
        // A SHOW naming one eye (flag bits 4-5) is presented to that eye's panel only: per-element depth (GLASSLYCFW/22).
        FirmwareRelease(name: "stereo-001",
                        sha256: "ee9029bd3f75cb9ec203b77f3ec1f485dd2a72397df8c225cadd48b1378a4bb2", byteCount: 2_251_853, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "f3eaffb1435017dccc30e626ad45337fc342990a55a906b025580ff8bb306479",
                        streams: streamPins(.stereo22)),
        // Glassly GATT service registered at boot inside the stock batch, so 0x9400 exists before any phone connects (GLASSLYCFW/21).
        FirmwareRelease(name: "ble-probe-006",
                        sha256: "35738944836157122267cb5c0250e33d49ea75a5aa6d953cf035bdf3f81f01a7", byteCount: 2_251_426, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "f879deeff433412fe14be442e6f66ba521ac2a45deba1644b7bb58ff94d6a292",
                        streams: streamPins(.bleProbe21)),
        // BLE command ingress: 'G','M',command,TLV writes run through the service entry, replies notified (GLASSLYCFW/20).
        FirmwareRelease(name: "ble-probe-005",
                        sha256: "783c3d974026c0ea6422857afe2549565c80c82346dd6bf4ca78aca37cc862d1", byteCount: 2_251_457, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "c668ba07e7196bbfa5f27b38ffc69152c6b4654ab64af596a514d1492995ad49",
                        streams: streamPins(.bleProbe20)),
        // GATT probe with a single registration kick, slot/link state in its status and a resume op (GLASSLYCFW/19).
        FirmwareRelease(name: "ble-probe-004",
                        sha256: "ff06f107b078d2c464f4c4f5e64189bccbfdcaab9b3650732863d33315a2826b", byteCount: 2_251_180, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "1d33a3c06552e26db4598f2de35b498bee4637c05f8c8699958d627ec1790b2e",
                        streams: streamPins(.bleProbe19)),
        // GATT probe that leaves the characteristic's spare bytes alone until its handle exists (GLASSLYCFW/18).
        FirmwareRelease(name: "ble-probe-003",
                        sha256: "80364527bd91081bb31c36fa29899d958af827d6e04d2124ab5b9dd663e3b1bb", byteCount: 2_251_153, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "133ca7d69449be87f7c3629dcbe81e781ba29733e069df3a3030d13ac9bc1360",
                        streams: streamPins(.bleProbe18)),
        // GATT probe whose registration kick mirrors the stock one (GLASSLYCFW/17).
        FirmwareRelease(name: "ble-probe-002",
                        sha256: "88cfc79005e75da0af10350d6d09088907c4aa55b9c4cf99e53798ce72afe507", byteCount: 2_250_786, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "2d0d89d1e06a9795a68f05f1a461ead51eb35165e9941e2ea3d1908e80479637",
                        streams: streamPins(.bleProbe17)),
        // Raw presents plus the post-boot GATT service probe on command 0x74 (GLASSLYCFW/16).
        FirmwareRelease(name: "ble-probe-001",
                        sha256: "50400aadfecdd3c6693b3233613ba5e6b0b637c3156f4989f5fe0adb47473a84", byteCount: 2_251_154, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "6de746a501f08aea3e2e92eff13a597548c529ede2234686008fe33e4f450529",
                        streams: streamPins(.bleProbe16)),
        // Raw presents: changed boxes go straight into the panel slices (GLASSLYCFW/15).
        FirmwareRelease(name: "raw-present-001",
                        sha256: "9d8a7bffc7804a923bd6f6cd9387cd5bd62a0b27dbace9219f0c21b5a54a4488", byteCount: 2_250_013, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "401a001fd8720b275ea792a7883723254094d2f965c6dcb07c2b5d840e736e77",
                        streams: streamPins(.rawPresent15)),
        FirmwareRelease(name: "active-als-001",
                        sha256: "e9e42be73f1a45052d2091237a87c1131d6abfb896c0d48c3db7188ceddf553f", byteCount: 2_249_519, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "e950fee8585c60adb17f675c1cb846ddf6670e1456c246a6864e0133fec5d7eb",
                        streams: streamPins(.activeAls14)),
        // Default text drawn at 4/5 of the resource font, the G2's 27 px line (GLASSLYCFW/13).
        FirmwareRelease(name: "text-scale-001",
                        sha256: "5c638151d3a29d7847e7e8cfbdcc3362648cf3c4185c61a054f79b73aef9a1de", byteCount: 2_249_152, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "547a16092929877521ca07a9a341b02703c5d7a6bc2ee7512f9d89bc102d2803",
                        streams: streamPins(.textScale13)),
        // Partial scene renders and the relaxed 94,000-byte runtime (GLASSLYCFW/12).
        FirmwareRelease(name: "partial-render-001",
                        sha256: "fc6c4d1f14bdc1d04e610b25b80140d7e2b82375cf57b3f34b21ae54fd1df31c", byteCount: 2_248_988, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "88099a0bb7665f189c91a265b680476afb3e3548dc16e4a8e28f4495c0bc805f",
                        streams: streamPins(.partialRender12)),
        FirmwareRelease(name: "first-run-owner-001",
                        sha256: "cb040a3439a0355e5cb2800742d05edd97648c7dfa456850acf9f3fb02e18f12", byteCount: 2_247_074, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "507d24a319e2269d45ae5b8cc866df86b8fe36943c7210bcb318214d309c5fe0",
                        streams: streamPins(.firstRunOwner11)),
        FirmwareRelease(name: "sensor-drain-001",
                        sha256: "9e0b2e114a21ac910f2d8b044b260af3944291b7a8d1bef2ec5f8c2d2cde0cd0", byteCount: 2_247_403, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "b947fe9870ec41eca1c6e123fd730460b86f276ad53ebe513f0be24c76c23df1",
                        streams: streamPins(.sensorDrain10)),
        FirmwareRelease(name: "sensor-buffer-001",
                        sha256: "fa230c0c893d9b810d0901dcfec2798dc4a78f043069aef865a07c94b883eb86", byteCount: 2_247_245, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "fd93ed4c6da4f0aa3dbcfa1f923cf708c5de55677f8256d2debba6162a3834e8",
                        streams: streamPins(.sensorBuffer9)),
        FirmwareRelease(name: "sensor-capture-001",
                        sha256: "5658977cd0653d3c8722aa0751024eedf57c227425d9bec031ec00c0f6a0e00f", byteCount: 2_246_211, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "1f801d0c3a32088091c02e16dfa63119e3a47e450f134e15447370c6c4aa0c39",
                        streams: streamPins(.sensorCapture8)),
        FirmwareRelease(name: "microphone-owner-001",
                        sha256: "e43e0f1b2745774104f84d6d406092e49d97276d37eb94831a8c0c346aaa54cb", byteCount: 2_248_764, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "ecc31323c1200c9c5081563b8b8d0d10d1322eef3b6767a58840adc1481e87e7",
                        streams: streamPins(.microphoneOwner7)),
        FirmwareRelease(name: "record-memory-001",
                        sha256: "5a6f8984773318a651f2703838672e9220615051fa36709ea591ed47e3b2e019", byteCount: 2_248_759, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "b8c9e9883a737f25676fad40ef9e1f4f61ca091a66fa1370201f90780cdb03e6",
                        streams: streamPins(.recordMemory6)),
        FirmwareRelease(name: "command-flags-001",
                        sha256: "b461c399c1361f5ac53f226a9d70896e1b2f039c0e70722a287737da3fab7851", byteCount: 2_248_692, modified: true,
                        profile: "H001Y-1.0.3.127-flash-canary-v1", headerSHA256: "fe56c3212e5c0597f8483adbf5b8e8f86662ba7162f37d0d858f41e618949c38",
                        streams: streamPins(.commandFlags5)),
        FirmwareRelease(name: "record-transport-001",
                        sha256: "424c0fe8574340199119cc5751bc6182d17e574adcd72a4a4e2d60f7a63675b8",
                        byteCount: 2_248_652, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "ddc29286261a7023cbf40fabb70a8e9726e3beba66a03db0b2910a4a9effc1b7",
                        streams: streamPins(.recordTransport4)),
        FirmwareRelease(name: "notifications-settings-002",
                        sha256: "771eb8242b3eea9b61d313cd061e3d007edee9a6a04614eaaeb55793ad450f66",
                        byteCount: 2_240_592, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "f047d289b98a66142aa1f857f547da31ea0e75efef21a5a21c4c37a8e9ce444b",
                        streams: streamPins(.notificationsSettings3)),
        FirmwareRelease(name: "notifications-settings-001",
                        sha256: "18959dcd3339667ffa82670843813349dbbc401b809e8c5fc12abcf56f39f719",
                        byteCount: 2_240_588, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "f68ae391716e4742561fbd0195f56ed2fd05b10c71624c7ed7b7f7a6cfbac73e",
                        streams: streamPins(.notificationsSettings)),
        FirmwareRelease(name: "wake-background-001",
                        sha256: "59abc5fa55be310c07886ab05fb713e6847a28632c75ead84cc76203d4d9a6d7",
                        byteCount: 2_235_644, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "d4cab46f823c0f8897fadfc6672f86d406e3d1a7f347afa17bb26527dd58f93c",
                        streams: streamPins(.wakeBackground)),
        FirmwareRelease(name: "wake-control-002",
                        sha256: "c4274e2eb92fa57d30a5d3f82779b6a36fcbbb25b113f5f7196f87e9e7f624c2",
                        byteCount: 2_236_085, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "e2a9582ab34372725d2293efafe9ac0448256f24ed1bf3498f38578158acf1e1",
                        streams: streamPins(.wakeControl)),
        FirmwareRelease(name: "minimal-owner-flash-004",
                        sha256: "66205f083f031576426b25d6b67f7596af949e68fd8186623e27fbdbe45a1677",
                        byteCount: 2_234_179, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "2fd98880faf869f5f3070ab7ac13b40b815d7c68118f1c2b9412c5c772386ab7",
                        streams: streamPins(.minimalOwnerFlash)),
    ]

    private enum StreamVariant { case latency27, bleLink26, bleLink25, bleFrames24, stereo23, stereo22, bleProbe21, bleProbe20, bleProbe19, bleProbe18, bleProbe17, bleProbe16, rawPresent15, activeAls14, textScale13, partialRender12, firstRunOwner11, sensorDrain10, sensorBuffer9, sensorCapture8, microphoneOwner7, recordMemory6, commandFlags5, recordTransport4, notificationsSettings3, notificationsSettings, stock, reader, canary, raster, rectCopy, bundle, text, diagnostic, dashboardRAM, resetUndoTrim, minimalOwnerFlash, wakeControl, wakeBackground }

    private static func streamPins(_ variant: StreamVariant) -> [FirmwareStreamPin] {
        let metadata: Int, appPacked: Int, appRaw: UInt32
        let metadataHash: String, appHash: String
        switch variant {
        case .latency27:
            metadata = 171; appPacked = 972_936; appRaw = 1_857_920
            metadataHash = "e49dfe8d7374c9e13878765366613acca87e0ae16aee21ad631ca18a05c06e31"
            appHash = "a06d90683fba3f687a94ac0da62536ce35c4317d4259dbf17902ed49dc3002a4"
        case .bleLink26:
            metadata = 171; appPacked = 972_825; appRaw = 1_857_568
            metadataHash = "88d8cb39499c4897ace971196799640e7a8994709fcfdbdd12094e72a59e49e9"
            appHash = "1cff227046edf76ba7b2441793d372807cf5762738949fcf5b250363e8a25311"
        case .bleLink25:
            metadata = 171; appPacked = 972_442; appRaw = 1_857_040
            metadataHash = "a55b172f54dfeeaed71306ba6e89738cc7869e98fd0772f8435d0485641f2eca"
            appHash = "4d1aa36ed1106c9002c900feab7c36fcef2d2e03d306764c6106a0770fbb7851"
        case .bleFrames24:
            metadata = 171; appPacked = 971_686; appRaw = 1_856_208
            metadataHash = "af8528cc3a1e8f472dcec32de244f242b06d434e124dcc8a3df9e7f292d44589"
            appHash = "d1d7b255e75f7e1548cb3432d9e867bdd34be526b7061869516a6865ed705e82"
        case .stereo23:
            metadata = 171; appPacked = 971_280; appRaw = 1_855_664
            metadataHash = "1a443f0f75e065cb69a5333815875dd0a3a3ecc8be7be5d31b340a476080098f"
            appHash = "7a2db74cf8c03b428902d6f53343efe177bf89daee0f2e8a0ad7b683d0ba5ca2"
        case .stereo22:
            metadata = 171; appPacked = 980_751; appRaw = 1_871_504
            metadataHash = "02de528f9512bc4cb672273c5c38d28dd3dfff3892bbf4a6056158c60dfa2dc6"
            appHash = "12ffa4a0dfc0edd45d0066ca9f4527b786a003a90cb0225e5a0c3ffe47bbbeef"
        case .bleProbe21:
            metadata = 171; appPacked = 980_324; appRaw = 1_871_088
            metadataHash = "a3119085c5951871cfbebd7bbae0ed566a7930a873a1c7fc76c321b10485929a"
            appHash = "960b1c66caa589cc7bda94a70c62f6cfa91bff08041160c462c20850ff04eb88"
        case .bleProbe20:
            metadata = 171; appPacked = 980_355; appRaw = 1_871_008
            metadataHash = "6a4bfa8f2f6077380048891274c130d9bc9e36f1af14bbdfa3ac8fe7fa5f1456"
            appHash = "9677adaf2d3e0e39ffb8ab7d40f9270a48913e9889965af3e993d7acc330d1c9"
        case .bleProbe19:
            metadata = 171; appPacked = 980_078; appRaw = 1_870_736
            metadataHash = "83a36158a987a2428af0dcd13a6e1fcb9a392e291c32e5ed59df6f86c0d6b136"
            appHash = "6757502ede9f7945753a533d93473c0df54aa1a6c6a151027f9bd4325dd54281"
        case .bleProbe18:
            metadata = 171; appPacked = 980_051; appRaw = 1_870_608
            metadataHash = "7c5534035b51256e2a4cc93cccd0eebd904c3f6de5896b8c7dcbfb5c296793dd"
            appHash = "49c6722c4796e3bcd3dae4f79401592d2d48cdf3ed1c141685c0e73baa12b43d"
        case .bleProbe17:
            metadata = 171; appPacked = 979_684; appRaw = 1_870_592
            metadataHash = "af2aa1ea16b816500ca6285a9116c6b053c10645639c33efbd99e20a71c3a39b"
            appHash = "1b132a9730ce244a2db8b8ae843b27faf62bb60b254b5f6c9e92c0dde7e8cc1e"
        case .bleProbe16:
            metadata = 171; appPacked = 980_052; appRaw = 1_870_496
            metadataHash = "df19e79bebcbce6c195f3f8c2bc0135ab4b94886079ee4673ce961f4151226a9"
            appHash = "0cbb5e97bd90374684bfaa7693aefd35a9d61192414837879bb70cafa06c3061"
        case .rawPresent15:
            metadata = 171; appPacked = 978_911; appRaw = 1_868_672
            metadataHash = "5488b7bb1815724ff2bbdcd290e13ad2614da8bfd9ec6a99db3efc1720e601a9"
            appHash = "14e082668474d2c79351bb793167765da31eae6226cb3957fe9432c2b160c6f5"
        case .activeAls14:
            metadata = 171; appPacked = 978_417; appRaw = 1_868_032
            metadataHash = "f01432efa94b3c8e71ea2c1cd22479a4e5fe174b6d1bdca18f08b27bfb502165"
            appHash = "7ad8b0bfc73d613ea6f3b10010191192188f779611b378806e3ce90b0a367e3a"
        case .textScale13:
            metadata = 171; appPacked = 978_050; appRaw = 1_867_504
            metadataHash = "66a0d5c4b944f74f9aa74d74210fd8f3b4ad66987f4eaa67bcf65b7954a09afa"
            appHash = "fffd1563b510e347d5d8bf134e6d7df54d3d9dd454abe85eb1a0ee47655ff9cc"
        case .partialRender12:
            metadata = 171; appPacked = 977_886; appRaw = 1_867_216
            metadataHash = "8a845205e06e5c68e15e11015918aba3265bbda22add7f8d39a581cf31f75ab4"
            appHash = "998f1321b5d76dd777e4df68f64d652fc39e85cd074f245d01de02f082e6d485"
        case .firstRunOwner11:
            metadata = 171; appPacked = 975_972; appRaw = 1_869_664
            metadataHash = "062213c02a8d64c4febaacdfed769d3616f333288bf5079aca7e5d34b8bdbcbc"
            appHash = "11e64d7861c73d2963fb7a4a38dadffbde49f16ce6532cf23f1258351c745258"
        case .sensorDrain10:
            metadata = 171; appPacked = 976_301; appRaw = 1_869_664
            metadataHash = "062213c02a8d64c4febaacdfed769d3616f333288bf5079aca7e5d34b8bdbcbc"
            appHash = "1ccd57116312f87be94bc4b39472dc7a54b2ec5dfc27f59b3e48e627a78b6f0a"
        case .sensorBuffer9:
            metadata = 171; appPacked = 976_143; appRaw = 1_869_424
            metadataHash = "830f7a2e1580632b10737fc8c505f5f8642be5d4ef6f0e4a0c9e262cc629aa82"
            appHash = "90d5eb015f684d70bc2d4cf2f4829fa349750272660dcbe27043e492e504e6ec"
        case .sensorCapture8:
            metadata = 171; appPacked = 975_109; appRaw = 1_867_824
            metadataHash = "1c66b3b0d03e0b7ad4a542b35a1d62c3768ced14ef6e5336eed7ff9ca976338d"
            appHash = "8d617160324d390b885b376d8c53039879b0094c6e9293e1e09fb3a2bf7db304"
        case .microphoneOwner7:
            metadata = 171; appPacked = 977_662; appRaw = 1_871_520
            metadataHash = "19d4b1e3ec8ddba05faf346926fd89cfee205296f3a0b2db504bfbf705ea552d"
            appHash = "6d346ec1432ad495a2cf2a71e1ba4903551c498f95e51144b0fcd4cc8f96d20a"
        case .recordMemory6:
            metadata = 171; appPacked = 977_657; appRaw = 1_869_344
            metadataHash = "5f643e689fcf0eb233c1f1468fb089b0b05bc0513d9080f2966b4c7732454dcf"
            appHash = "ad78e3f5591f86a96f4dccea4668a7011602efb269984da5a57295d9f2417fc6"
        case .commandFlags5:
            metadata = 171; appPacked = 977_590; appRaw = 1_869_344
            metadataHash = "5f643e689fcf0eb233c1f1468fb089b0b05bc0513d9080f2966b4c7732454dcf"
            appHash = "301a6eb94583c755fbd94d089620f5f1ef3e33f2278baf27aebbed3181519bd0"
        case .recordTransport4:
            metadata = 171; appPacked = 977_550; appRaw = 1_869_248
            metadataHash = "6b41306edf554583354f9a8027c56b04f8a713a6fcdc212c2aeae4f1409d0413"
            appHash = "2724c3928939464f15c9d28ca0c54013f25cb7e03ce3d8f2ce6918a55d1b92cb"
        case .notificationsSettings3:
            metadata = 171; appPacked = 969_490; appRaw = 1_855_504
            metadataHash = "40765600e05cc8bafc590d120ed8c24486617f105f9ca1463e76056148b31827"
            appHash = "5fd97e0169c669c97eb79322cb36981737c07b2e0d002cf00679a585fde2cca4"
        case .notificationsSettings:
            metadata = 171; appPacked = 969_486; appRaw = 1_855_504
            metadataHash = "40765600e05cc8bafc590d120ed8c24486617f105f9ca1463e76056148b31827"
            appHash = "6bd91f1185717eb8b437edfdccef8bc88d0dc2269fca4f0c5ae1b8b93caef22e"
        case .stock:
            metadata = 166; appPacked = 914_600; appRaw = 1_773_208
            metadataHash = "bf19868459ff0a657c781745d1efaa9f0352d296ecaae19ab301f1d1af9fdebe"
            appHash = "341de3742ff50cc25bc6c4cbea489d5f6c2cbebb085b56374e2c75f70be95694"
        case .reader:
            metadata = 171; appPacked = 952_651; appRaw = 1_827_232
            metadataHash = "1cde823a8502f402e158c6f5ed89c06ea0a9346f169164ebbaa5b6f3d0b0f73f"
            appHash = "4dd18a43b2e1612fdc5f342d31a684f4df7510ff97bc3d61ba5be71ed75be31f"
        case .canary:
            metadata = 171; appPacked = 955_686; appRaw = 1_832_800
            metadataHash = "e5a3cc0e3836694bb98e295d89620ec76550daa276491758f87beb58830a557b"
            appHash = "e4bbda6bea9c13e830b82e50bcc071385039ee9b06395ec8001dc38942509299"
        case .raster:
            metadata = 171; appPacked = 956_869; appRaw = 1_834_608
            metadataHash = "07c6f9bb617f88b29367641c0abdfbd669e62710449a0b8c0c88eba41d4c62c2"
            appHash = "750f7970025f86d4721ce3095139121254ca7969577f0fbbe5020eb22bb18cc3"
        case .rectCopy:
            metadata = 171; appPacked = 957_566; appRaw = 1_835_456
            metadataHash = "9eb32419f61f803cea53df4fa4e2f24c830c83d77d6a16dd79a741f0a6ad013f"
            appHash = "4d8a3c422831394a7dd0729d72f2233b260f34b0984d2448cab1f6828c47932d"
        case .bundle:
            metadata = 171; appPacked = 958_080; appRaw = 1_836_416
            metadataHash = "59a2cd5d0a5f69fb19b385c1199a1d128ea9b1414e77e38efe82a94fbca0fe57"
            appHash = "91ae2d698b408ea3cdd1ab0b04b5b39949dc68119a964161fcb2c27140aca4c8"
        case .text:
            metadata = 170; appPacked = 958_279; appRaw = 1_836_864
            metadataHash = "7d0800d151af9fb197e39454c6bbbadb5da363aa76c189886e9f14a65a93f792"
            appHash = "8a605b929d838cff05b709ebd37d1720b70c0706c0a0030bf844775bcfeb52c1"
        case .diagnostic:
            metadata = 171; appPacked = 959_165; appRaw = 1_838_672
            metadataHash = "a189ba5a175480d2500bd2a1df5730c34b1124503fa809c47738930d820b8d9a"
            appHash = "054f97d9e687ba2baf008f5dc118bff7dbc5c49ad462bb9f7188b1f6d9352ff9"
        case .resetUndoTrim:
            metadata = 171; appPacked = 955_302; appRaw = 1_833_472
            metadataHash = "fdeac5450e48ffc548b110450dc4b6117a8702bcf5bcd5bf197fb794c2d746e2"
            appHash = "1cf2a3d6a315d67764f4f43863f2d8ec802a5ef45eb82e1bc20a4b3b4fd833b6"
        case .wakeBackground:
            metadata = 171; appPacked = 964_542; appRaw = 1_848_160
            metadataHash = "9aaf54003c8b29364662268927f224d8e10311a8efe39165b55f1f0cc4be5ff2"
            appHash = "e29a270fea9b42fc3c596e5ce37f6205421ee5e1f5f29b96b66f4a235341149c"
        case .wakeControl:
            metadata = 171; appPacked = 964_983; appRaw = 1_848_112
            metadataHash = "59085caced14283f4b6cd4c3f553b9211904c883c11120f54ba398743c79892e"
            appHash = "e985d21d52ce088fd0ec7bb58cf7d9726b6f31243fb718e857f29d7bffb4f9ee"
        case .minimalOwnerFlash:
            metadata = 171; appPacked = 963_077; appRaw = 1_844_800
            metadataHash = "1a53d46f600064c708aabb7e8884ef1bb2edd1c57aeac9d1ea6203d251e1b4d6"
            appHash = "d1417475dd2e246fc4012f7d32b01791feba0b26cb6f364f8ab4bf0667f405aa"
        case .dashboardRAM:
            metadata = 171; appPacked = 959_569; appRaw = 1_838_672
            metadataHash = "a189ba5a175480d2500bd2a1df5730c34b1124503fa809c47738930d820b8d9a"
            appHash = "4ad7607ca742be20220eb1baae1c79ea2e01a94f2381ec190da14f698b9653d7"
        }
        let sizes: [Int] = [metadata, 481_265, 437_783, appPacked, 283_737, 986, 67006]
        let raw: [UInt32] = [344, 909_676, 695_512, appRaw, 284_300, 3616, 81594]
        let starts: [UInt32?] = [nil, 0x10000, 0x123000, 0x1EB000, 0x3EB000, 0x77A000, 0x6DF000]
        let ends: [UInt32?] = [nil, 0x123000, 0x1EB000, 0x3EB000, 0x481000, 0x77C000, 0x6F8000]
        let hashes = [
            metadataHash,
            "ba0207d664287ede74c2a51612220e2848bd00df362defd22bf5488c65a8f3e1",
            "939ee004a8185d84d643ee6cf992fad437a5e8ab356cdaaf29ce7a01acd1bba0",
            appHash,
            "8cd2c6c484d9ce80c7f21d7875b56cc4b9e61885ecda9d0e6a952541491b084c",
            "69c8e1e73137ab5c9c818d422ba256166b32c116d4116098f18907efbbfbd4ee",
            "b697fbbf3145b2c0ecdf110eeaf0ecaef2320c6c6ed6d8f89078832aa5cc3bca",
        ]
        var offset = 150
        return sizes.indices.map { index in
            defer { offset += sizes[index] }
            return FirmwareStreamPin(offset: offset, packedSize: sizes[index], unpackedSize: raw[index],
                                     flashStart: starts[index], flashEnd: ends[index], packedSHA256: hashes[index])
        }
    }
}
