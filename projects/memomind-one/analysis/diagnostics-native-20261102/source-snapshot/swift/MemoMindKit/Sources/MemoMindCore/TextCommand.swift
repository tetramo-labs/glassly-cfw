// SPDX-License-Identifier: MIT
// Wire/UTF-8 contract: G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce,
// patches/texture_cache.c cfw_builtin_draw_string_buf; zlib_glue.c mode15.
// License: LICENSE.
import Foundation

public enum TextCommandError: Error, Equatable, LocalizedError {
    case coordinateOutOfRange
    case textTooLong(byteCount: Int)
    case nulNotSupported
    case invalidUTF8

    public var errorDescription: String? {
        switch self {
        case .coordinateOutOfRange: "Text coordinates must fit signed16-bit integers"
        case let .textTooLong(count): "Text contains \(count) bytes; mode15 permits at most255"
        case .nulNotSupported: "Mode15 does not accept NUL"
        case .invalidUTF8: "Mode15 requires strict UTF-8 with optional control bytes1..31"
        }
    }
}

public extension RasterCommands {
    /// Canonical mode15 RLE-independent text command:
    /// [0f][x:s16LE][y:s16LE][options:u8][byteCount:u8][bytes]. No trailing bytes.
    /// Output is at most262 bytes, within the current8192-byte command limit.
    /// No transport or outer zlib envelope is added; native mode15 is required.
    ///
    /// Accepts strict UTF-8 (including DEL), plus bytes1..31, and rejects NUL.
    /// Each control byte moves x by byte-11 pixels; LF/CR are not line breaks.
    /// Coordinates may be negative/offscreen: the renderer clips glyph pixels.
    /// Options: low nibble scales intensity0..15;0x10 skips original zero glyph
    /// samples before inversion;0x20 inverts;0xc0 is preserved but ignored.
    /// Default0x0f gives full intensity with opaque glyph backgrounds.
    ///
    /// Validation covers wire syntax, not native font availability, kerning,
    /// glyph metrics, display ownership or pixels. A valid Unicode scalar may
    /// lack a MemoMind resource glyph and be rejected by the native renderer.
    static func builtinText(bytes: Data, x: Int, y: Int, options: UInt8 = 0x0F) throws -> Data {
        guard let sx = Int16(exactly: x), let sy = Int16(exactly: y) else {
            throw TextCommandError.coordinateOutOfRange
        }
        guard bytes.count <= 255 else { throw TextCommandError.textTooLong(byteCount: bytes.count) }
        guard !bytes.contains(0) else { throw TextCommandError.nulNotSupported }
        // The strict Foundation decoder rejects malformed, overlong, surrogate
        // and out-of-range sequences without repairing or normalizing bytes.
        guard String(data: bytes, encoding: .utf8) != nil else { throw TextCommandError.invalidUTF8 }
        let ux = UInt16(bitPattern: sx), uy = UInt16(bitPattern: sy)
        var result = Data([15, UInt8(truncatingIfNeeded: ux), UInt8(ux >> 8),
                           UInt8(truncatingIfNeeded: uy), UInt8(uy >> 8), options, UInt8(bytes.count)])
        result += bytes
        return result
    }

    /// Convenience overload counting UTF-8 bytes, not characters or glyphs.
    /// Never truncates, normalizes, replaces unsupported glyphs or changes LF/CR.
    static func builtinText(_ text: String, x: Int, y: Int, options: UInt8 = 0x0F) throws -> Data {
        try builtinText(bytes: Data(text.utf8), x: x, y: y, options: options)
    }
}
