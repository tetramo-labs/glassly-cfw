// SPDX-License-Identifier: MIT
// Wire contract: G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce,
// patches/zlib_glue.c mode9 image_dispatch branch. MIT: LICENSE.
import Foundation

/// Integer pixel coordinates; validation happens when constructing a command.
/// Unlike mode3, mode9 permits odd coordinates and dimensions.
public struct RasterRectangle: Equatable, Codable {
    public let x: Int
    public let y: Int
    public let width: Int
    public let height: Int
    public init(x: Int, y: Int, width: Int, height: Int) {
        self.x = x; self.y = y; self.width = width; self.height = height
    }

    fileprivate var fitsDisplay: Bool {
        width > 0 && width <= RasterCommands.width && height > 0 && height <= RasterCommands.height &&
            x >= 0 && x <= RasterCommands.width - width && y >= 0 && y <= RasterCommands.height - height
    }
}

public enum RectangleCopyCommandError: Error, Equatable, LocalizedError {
    case invalidSource
    case invalidDestination
    case mismatchedDimensions
    public var errorDescription: String? {
        switch self {
        case .invalidSource: "Rectangle-copy source must have positive dimensions and fit within600x350"
        case .invalidDestination: "Rectangle-copy destination must have positive dimensions and fit within600x350"
        case .mismatchedDimensions: "Rectangle-copy source and destination must have identical dimensions"
        }
    }
}

public extension RasterCommands {
    /// Mode9: [09][source x,y,width,height LE16][destination x,y,width,height LE16].
    /// Always17 bytes, with no RLE/zlib or transport envelope. Both rectangles must
    /// fit600x350; overlap and self-copy are allowed, with native memmove semantics.
    /// This is the ordinary shared-pair encoding for MemoMind's single display.
    /// Upstream89 instead contains first/left and second/right pairs; the MemoMind
    /// receiver selects first/left, but this API does not manufacture a second lens.
    /// Requires native mode9 capability; the function does not send/present pixels,
    /// acquire a display lease, establish the existing raster, or enforce sequencing.
    static func rectangleCopy(source: RasterRectangle, destination: RasterRectangle) throws -> Data {
        guard source.fitsDisplay else { throw RectangleCopyCommandError.invalidSource }
        guard destination.fitsDisplay else { throw RectangleCopyCommandError.invalidDestination }
        guard source.width == destination.width, source.height == destination.height else {
            throw RectangleCopyCommandError.mismatchedDimensions
        }
        var bytes: [UInt8] = [9]
        bytes.reserveCapacity(17)
        for rectangle in [source, destination] {
            for value in [rectangle.x, rectangle.y, rectangle.width, rectangle.height] {
                bytes += [UInt8(truncatingIfNeeded: value), UInt8(value >> 8)]
            }
        }
        return Data(bytes)
    }
}
