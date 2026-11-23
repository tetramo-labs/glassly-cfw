// SPDX-License-Identifier: MIT
// G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce: patches/zlib_glue.c mode8,
// scene.c immediate19/20 envelopes. License: LICENSE.
import Foundation

public enum BundleCommandError: Error, Equatable, LocalizedError {
    case tooManyCommands(Int)
    case emptyCommand(index: Int)
    case commandTooLarge(index: Int, length: Int)
    case unsupportedMode(index: Int, mode: UInt8)
    case invalidEnvelope(index: Int, mode: UInt8)
    case capacityExceeded(maximumCommandBytes: Int)
    public var errorDescription: String? {
        switch self {
        case let .tooManyCommands(count): "Bundle count \(count) exceeds255"
        case let .emptyCommand(index): "Bundle command \(index) is empty"
        case let .commandTooLarge(index, length): "Bundle command \(index) length \(length) exceedsLE16"
        case let .unsupportedMode(index, mode): "Bundle command \(index) has unsupported mode \(mode)"
        case let .invalidEnvelope(index, mode): "Bundle command \(index) has an invalid mode \(mode) envelope"
        case let .capacityExceeded(maximum): "Bundle exceeds current MemoMind \(maximum)-byte admission limit"
        }
    }
}

public extension RasterCommands {
    /// Canonical mode8: [08][count:u8][length:LE16][command]..., at most8192 bytes.
    /// Preserves order and every child byte, including permitted high mode bits.
    /// Count0 is legal and still requests the receiver's final presentation.
    ///
    /// Allowed base modes:3/6/9/19/20/36/37..41. Nested8, unsupported native15 and
    /// other control modes are rejected. Highbits are masked for admission, exactly
    /// as upstream;83/89 retain first/left mapping, while other child highbits are
    /// ignored by the native dispatcher. Output outer mode is always08, never88.
    ///
    /// Checks count, LE16 lengths, total capacity and known command envelopes only:
    /// 19 is exactly10 bytes;20's byte10 string length must match11+length. Other
    /// modes get their fixed minimum headers. This is NOT a RLE, rectangle, shape,
    /// scene-entry, asset, epoch, or receiver-state validator. Prefer typed encoders
    /// for supported child commands and check native capability before sending.
    ///
    /// Native execution is sequential with intermediate presentation deferred.
    /// Success schedules one final presentation, but this is not a transaction:
    /// a later failure can leave earlier pixel/cache mutations in place. Only the
    /// final cache-reply scratch survives; no per-child reply list is promised.
    static func bundle(_ commands: [Data]) throws -> Data {
        guard commands.count <= 255 else { throw BundleCommandError.tooManyCommands(commands.count) }
        var total = 2
        for (index, command) in commands.enumerated() {
            guard !command.isEmpty else { throw BundleCommandError.emptyCommand(index: index) }
            guard command.count <= 65535 else { throw BundleCommandError.commandTooLarge(index: index, length: command.count) }
            let rawMode = command[command.startIndex], mode = rawMode & 0x7F
            let minimum: Int
            switch mode {
            case 3: minimum = rawMode & 0x80 == 0 ? 8 : 12
            case 6: minimum = 3
            case 9: minimum = rawMode & 0x80 == 0 ? 17 : 33
            case 19: minimum = 10
            case 20: minimum = 11
            case 36: minimum = 2
            case 37: minimum = 5
            case 38: minimum = 10
            case 39: minimum = 7
            case 40: minimum = 9
            case 41: minimum = 6
            default: throw BundleCommandError.unsupportedMode(index: index, mode: rawMode)
            }
            guard command.count >= minimum,
                  mode != 19 || command.count == 10,
                  mode != 20 || command.count == 11 + Int(command[command.startIndex + 10])
            else {
                throw BundleCommandError.invalidEnvelope(index: index, mode: rawMode)
            }
            let remaining = maximumCommandBytes - total
            guard remaining >= 2, command.count <= remaining - 2 else {
                throw BundleCommandError.capacityExceeded(maximumCommandBytes: maximumCommandBytes)
            }
            total += 2 + command.count
        }
        var result = Data([8, UInt8(commands.count)])
        result.reserveCapacity(total)
        for command in commands {
            result += [UInt8(truncatingIfNeeded: command.count), UInt8(command.count >> 8)]
            result += command
        }
        return result
    }
}
