// SPDX-License-Identifier: MIT
// RLE token algorithm adapted from G2 commit 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce:
// demos/video-bench.ts rleEncode/packBox; patches/zlib_glue.c post-inflate modes3/6.
// See runtime/portable/PROVENANCE.md and LICENSE for upstream license.
import Foundation

public enum RasterCommandError: Error, LocalizedError, Equatable {
    case invalidBounds
    case invalidStride
    case incorrectByteCount(expected: Int, actual: Int)
    case capacityExceeded(maximumCommandBytes: Int)
    public var errorDescription: String? {
        switch self {
        case .invalidBounds: "Raster box must fit 600x350, with x/width multiples of4 and y/height multiples of2"
        case .invalidStride: "GRAY4 row stride must cover the visible row and have a representable total length"
        case let .incorrectByteCount(expected, actual): "Expected exactly \(expected) packed GRAY4 bytes, received \(actual)"
        case let .capacityExceeded(maximum): "RLE command exceeds the current MemoMind \(maximum)-byte admission limit"
        }
    }
}

/// Pure RLE command construction: no transport, zlib, lease or display side effects.
/// Pixels are packed GRAY4, high nibble left, rows top-to-bottom. Caller supplies
/// exactly rowStride*height bytes, including final-row padding; padding is ignored.
/// These commands require the optional native raster-command firmware capability.
public enum RasterCommands {
    public static let width = 600
    public static let height = 350
    public static let tightFrameBytes = 105_000
    /// Current MemoMind command admission, not the full G2 protocol capacity.
    public static let maximumCommandBytes = 8192

    /// Mode6: [6][RLE], seeds/replaces the complete persistent600x350 raster.
    /// Default input is exactly105000 bytes; hardware-stride320 input is112000.
    public static func fullFrame(pixels: Data, rowStride: Int = 300, maximumCommandBytes: Int = Self.maximumCommandBytes) throws -> Data {
        try encode(pixels: pixels, width: width, height: height, rowStride: rowStride, header: [6], maximumCommandBytes: maximumCommandBytes)
    }

    /// Mode3: [3][x/4][y/2][width/4][height/2][fidLE16][RLE]. Input contains only
    /// the local box pixels. No clipping, crop, grayscale conversion or fid tracking
    /// occurs. Send a mode6 keyframe first to establish the intended base; fid is diagnostic only.
    public static func boundingBox(pixels: Data, x: Int, y: Int, width: Int, height: Int,
                                   frameID: UInt16, rowStride: Int? = nil, maximumCommandBytes: Int = Self.maximumCommandBytes) throws -> Data
    {
        guard width > 0, width <= Self.width, height > 0, height <= Self.height,
              x >= 0, x <= Self.width - width, y >= 0, y <= Self.height - height,
              x % 4 == 0, width % 4 == 0, y % 2 == 0, height % 2 == 0
        else {
            throw RasterCommandError.invalidBounds
        }
        let header: [UInt8] = [3, UInt8(x / 4), UInt8(y / 2), UInt8(width / 4), UInt8(height / 2),
                               UInt8(truncatingIfNeeded: frameID), UInt8(frameID >> 8)]
        return try encode(pixels: pixels, width: width, height: height,
                          rowStride: rowStride ?? width / 2, header: header, maximumCommandBytes: maximumCommandBytes)
    }

    private static func encode(pixels: Data, width: Int, height: Int, rowStride: Int, header: [UInt8], maximumCommandBytes: Int) throws -> Data {
        guard (1...65535).contains(maximumCommandBytes) else { throw RasterCommandError.capacityExceeded(maximumCommandBytes: maximumCommandBytes) }
        let rowBytes = width / 2
        guard rowStride >= rowBytes, rowStride <= Int.max / height else { throw RasterCommandError.invalidStride }
        let expectedBytes = rowStride * height
        guard pixels.count == expectedBytes else {
            throw RasterCommandError.incorrectByteCount(expected: expectedBytes, actual: pixels.count)
        }
        // Bound output by the explicitly admitted firmware command capacity.
        var output = header
        output.reserveCapacity(maximumCommandBytes)
        return try pixels.withUnsafeBytes { (source: UnsafeRawBufferPointer) in
            func nibble(_ index: Int) -> UInt8 {
                let byteIndex = index / 2
                let value = source[byteIndex / rowBytes * rowStride + byteIndex % rowBytes]
                return index & 1 == 0 ? value >> 4 : value & 15
            }
            let count = width * height
            var position = 0
            while position < count {
                let color = nibble(position)
                var end = position + 1
                while end < count, nibble(end) == color {
                    end += 1
                }
                var run = end - position
                while run > 0 {
                    let part = min(run, 65535)
                    let tokenBytes = part <= 15 ? 1 : part <= 255 ? 2 : 4
                    guard tokenBytes <= maximumCommandBytes - output.count else {
                        throw RasterCommandError.capacityExceeded(maximumCommandBytes: maximumCommandBytes)
                    }
                    if part <= 15 {
                        output.append(UInt8(part << 4) | color)
                    } else if part <= 255 {
                        output += [color, UInt8(part)]
                    } else {
                        output += [color, 0, UInt8(truncatingIfNeeded: part), UInt8(part >> 8)]
                    }
                    run -= part
                }
                position = end
            }
            return Data(output)
        }
    }
}
