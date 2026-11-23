// SPDX-License-Identifier: MIT
// Wire contract: G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce,
// patches/zlib_glue.c image_dispatch modes7/11. License: LICENSE.
import Foundation

public enum DiagnosticControl: UInt8, CaseIterable, Sendable {
    /// Clear sticky diagnostic flags/counters and frame-order tracking.
    /// This changes diagnostic state; it is not a read-only status query.
    case clear = 0
    /// Hide the diagnostic overlay, preserving its history.
    case hide = 1
    /// Enable the diagnostic overlay; does not itself request a frame refresh.
    case show = 2
}

public extension RasterCommands {
    /// Canonical mode7 [07][sub], with no transport or zlib envelope.
    /// Requires native mode7 capability. This only constructs bytes; it does not
    /// query diagnostics, send a command or guarantee a visible overlay.
    ///
    /// Upstream also accepts87, missing/unknown subcommands as successful no-ops,
    /// and ignored trailing bytes. This typed API emits only the three defined
    /// actions and no trailing bytes. Mode7 cannot be a mode8 bundle child.
    static func diagnostics(_ action: DiagnosticControl) -> Data {
        Data([7, action.rawValue])
    }

    /// Canonical session cleanup [0b], with no transport or zlib envelope.
    /// Requests release of the receiver's implemented custom display/session
    /// resources. Exact cleanup coverage is firmware-specific; encoding this
    /// command does not establish completion, restore stock UI, close the host
    /// connection, or authorize a retry after an ambiguous transport failure.
    ///
    /// Upstream accepts8b and ignores trailing bytes; this API emits exactly0b.
    /// Mode11 cannot be a mode8 bundle child. Upstream cleanup preserves sticky
    /// diagnostic history and hides the overlay; mode7 clear is a separate action.
    static func cleanupSession() -> Data {
        Data([11])
    }
}

public enum DiagnosticReplyError: Error, Equatable, LocalizedError {
    case invalidReply(String)
    public var errorDescription: String? {
        if case let .invalidReply(reason) = self {
            return "Invalid native diagnostics reply: \(reason)"
        }
        return nil
    }
}

/// Native-v1 snapshot, distinct from G2's settings diagnostic wire/overlay.
/// Requires advertised diagnostics:"native-v1", snapshotBytes:20 and cleanup:
/// "graphics-input-current-screen". Native fonts, overlay layout and lifetime
/// differ from G2; snapshot decoding does not establish capability or visibility.
public struct DiagnosticSnapshot: Equatable, Codable, Sendable {
    public let flags: UInt8
    public let hidden: Bool
    public let seen: Bool
    public let resync: Bool
    public let lastFrameID: UInt16
    public let highFrameID: UInt16
    public let displayWorkerFailures: UInt32
    public let displayAllocationFailures: UInt32
    public let lastFailedMode: UInt8
    public let savedSceneEpoch: UInt16

    public var reordered: Bool {
        flags & 1 != 0
    }

    public var skipped: Bool {
        flags & 2 != 0
    }

    public var duplicated: Bool {
        flags & 4 != 0
    }

    /// Decode one correlated service15/cmd7d business response. Callers may supply
    /// expectedEvent when decoding saved wire messages outside GMSession.
    /// Requires exact five-key JSON with ABI integer1 (never Boolean), resultok,
    /// presentationunchanged and40 lowercase hex digits. Exactly one optional
    /// terminal JSON NUL is accepted, matching native response framing.
    /// No cross-field relationship or counter monotonicity is assumed.
    public static func decode(_ message: GMMessage, expectedEvent: UInt8? = nil) throws -> DiagnosticSnapshot {
        func invalid(_ reason: String) -> DiagnosticReplyError {
            .invalidReply(reason)
        }
        guard message.service == 15, message.command == 0x7D,
              expectedEvent == nil || message.event == expectedEvent else { throw invalid("correlation") }
        guard message.tlvs.count == 1, let tlv = message.tlvs.first, tlv.kind == 5,
              tlv.value.count <= 256, try message.body == (tlv.encoded()) else { throw invalid("JSON TLV/body") }
        let parsed: StrictDeviceJSON
        do { parsed = try StrictDeviceJSON.decode(tlv.value, maximumBytes: 256) }
        catch { throw invalid("JSON syntax") }
        guard let object = parsed.object,
              Set(object.keys) == ["glassly", "abi", "result", "presentation", "stateHex"],
              object["glassly"]?.string == "diagnostics", object["abi"]?.integer == 1,
              object["result"]?.string == "ok", object["presentation"]?.string == "unchanged",
              let stateHex = object["stateHex"]?.string else { throw invalid("schema") }
        let hex = Array(stateHex.utf8)
        guard hex.count == 40, hex.allSatisfy({ (48 ... 57).contains($0) || (97 ... 102).contains($0) }) else {
            throw invalid("stateHex")
        }
        func nibble(_ byte: UInt8) -> UInt8 {
            byte <= 57 ? byte - 48 : byte - 87
        }
        let bytes = stride(from: 0, to: 40, by: 2).map { nibble(hex[$0]) << 4 | nibble(hex[$0 + 1]) }
        guard bytes[0] & 0xF8 == 0, bytes[1] <= 1, bytes[2] <= 1, bytes[3] <= 1, bytes[17] == 0 else {
            throw invalid("snapshot flags/reserved")
        }
        func u16(_ at: Int) -> UInt16 {
            UInt16(bytes[at]) | UInt16(bytes[at + 1]) << 8
        }
        func u32(_ at: Int) -> UInt32 {
            UInt32(bytes[at]) | UInt32(bytes[at + 1]) << 8 | UInt32(bytes[at + 2]) << 16 | UInt32(bytes[at + 3]) << 24
        }
        return DiagnosticSnapshot(flags: bytes[0], hidden: bytes[1] != 0, seen: bytes[2] != 0, resync: bytes[3] != 0,
                                  lastFrameID: u16(4), highFrameID: u16(6), displayWorkerFailures: u32(8),
                                  displayAllocationFailures: u32(12), lastFailedMode: bytes[16], savedSceneEpoch: u16(18))
    }
}
