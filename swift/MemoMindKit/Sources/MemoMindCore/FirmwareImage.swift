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
                        byteCount: 2228668, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "873f44726e712b0b3a2f234397db184b12073a55e23c3bc01a33aca488f8b55f",
                        streams: streamPins(.rectCopy)),
        // Exact reconstructed mode8 release; admission alone is not boot proof.
        FirmwareRelease(name: "bundle-commands-001",
                        sha256: "0f54b4569ef2960e2916abfcff4a434c0f1164f05d059a8418100f3da3f8fce5",
                        byteCount: 2229182, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "aa42bd320c3aa574c9c4b04592698e699a57ee036f04ca49a356d01002917ffc",
                        streams: streamPins(.bundle)),
        // Exact reconstructed mode15 release; admission alone is not boot proof.
        FirmwareRelease(name: "text-commands-001",
                        sha256: "e5409e0d42da0009b759852289915e92517a185c1255ad8de28a56c49c070d31",
                        byteCount: 2229380, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "f70265e4218854cd2abb66e3be39f6c128a47625f939388659a957afb8718feb",
                        streams: streamPins(.text)),
        // Exact reconstructed diagnostics/cleanup release; admission alone is not boot proof.
        FirmwareRelease(name: "diagnostic-commands-001",
                        sha256: "a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917",
                        byteCount: 2230267, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "7787494fdb8d50c1a0d578c2494cd0127a1cbcb954dc8aa2541faaa766baf016",
                        streams: streamPins(.diagnostic)),
        // Six reviewed cold-boot UI gates; existing diagnostic runtime unchanged.
        // Exact-byte admission is separate from successful hardware boot.
        FirmwareRelease(name: "dashboard-ram-002",
                        sha256: "f56376fde20515c0ad2a421eb352f774b4c21f274cda2d38f012a0d008c6d14a",
                        byteCount: 2230671, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "3e0ed487f355806dafd975fb2849c2e146ab8d7b8fc0e5431420c332434bc13c",
                        streams: streamPins(.dashboardRAM)),
        // Standalone RESET scratch trimming; native mutation rollback required.
        FirmwareRelease(name: "reset-undo-trim-001",
                        sha256: "3bf52f5a2a6137759ddc3546c47b1ceed42a401953e75379712044d32e2206a9",
                        byteCount: 2226404, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "ebe404e8435d9a0fb469e43a0784ca4547cccf130fd6921530b43315749d99b8",
                        streams: streamPins(.resetUndoTrim)),
        // Minimal launcher + 256KiB COW assets and 65535-byte raw carrier.
        // Exact reviewed 96KiB RX allocation; catalog admission is not boot proof.
        FirmwareRelease(name: "wake-control-002",
                        sha256: "c4274e2eb92fa57d30a5d3f82779b6a36fcbbb25b113f5f7196f87e9e7f624c2",
                        byteCount: 2236085, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "e2a9582ab34372725d2293efafe9ac0448256f24ed1bf3498f38578158acf1e1",
                        streams: streamPins(.wakeControl)),
        FirmwareRelease(name: "minimal-owner-flash-004",
                        sha256: "66205f083f031576426b25d6b67f7596af949e68fd8186623e27fbdbe45a1677",
                        byteCount: 2234179, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "2fd98880faf869f5f3070ab7ac13b40b815d7c68118f1c2b9412c5c772386ab7",
                        streams: streamPins(.minimalOwnerFlash)),
    ]

    private enum StreamVariant { case stock, reader, canary, raster, rectCopy, bundle, text, diagnostic, dashboardRAM, resetUndoTrim, minimalOwnerFlash, wakeControl }

    private static func streamPins(_ variant: StreamVariant) -> [FirmwareStreamPin] {
        let metadata: Int, appPacked: Int, appRaw: UInt32
        let metadataHash: String, appHash: String
        switch variant {
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
            metadata = 171; appPacked = 957566; appRaw = 1835456
            metadataHash = "9eb32419f61f803cea53df4fa4e2f24c830c83d77d6a16dd79a741f0a6ad013f"
            appHash = "4d8a3c422831394a7dd0729d72f2233b260f34b0984d2448cab1f6828c47932d"
        case .bundle:
            metadata = 171; appPacked = 958080; appRaw = 1836416
            metadataHash = "59a2cd5d0a5f69fb19b385c1199a1d128ea9b1414e77e38efe82a94fbca0fe57"
            appHash = "91ae2d698b408ea3cdd1ab0b04b5b39949dc68119a964161fcb2c27140aca4c8"
        case .text:
            metadata = 170; appPacked = 958279; appRaw = 1836864
            metadataHash = "7d0800d151af9fb197e39454c6bbbadb5da363aa76c189886e9f14a65a93f792"
            appHash = "8a605b929d838cff05b709ebd37d1720b70c0706c0a0030bf844775bcfeb52c1"
        case .diagnostic:
            metadata = 171; appPacked = 959165; appRaw = 1838672
            metadataHash = "a189ba5a175480d2500bd2a1df5730c34b1124503fa809c47738930d820b8d9a"
            appHash = "054f97d9e687ba2baf008f5dc118bff7dbc5c49ad462bb9f7188b1f6d9352ff9"
        case .resetUndoTrim:
            metadata = 171; appPacked = 955302; appRaw = 1833472
            metadataHash = "fdeac5450e48ffc548b110450dc4b6117a8702bcf5bcd5bf197fb794c2d746e2"
            appHash = "1cf2a3d6a315d67764f4f43863f2d8ec802a5ef45eb82e1bc20a4b3b4fd833b6"
        case .wakeControl:
            metadata = 171; appPacked = 964983; appRaw = 1848112
            metadataHash = "59085caced14283f4b6cd4c3f553b9211904c883c11120f54ba398743c79892e"
            appHash = "e985d21d52ce088fd0ec7bb58cf7d9726b6f31243fb718e857f29d7bffb4f9ee"
        case .minimalOwnerFlash:
            metadata = 171; appPacked = 963077; appRaw = 1844800
            metadataHash = "1a53d46f600064c708aabb7e8884ef1bb2edd1c57aeac9d1ea6203d251e1b4d6"
            appHash = "d1417475dd2e246fc4012f7d32b01791feba0b26cb6f364f8ab4bf0667f405aa"
        case .dashboardRAM:
            metadata = 171; appPacked = 959569; appRaw = 1838672
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
