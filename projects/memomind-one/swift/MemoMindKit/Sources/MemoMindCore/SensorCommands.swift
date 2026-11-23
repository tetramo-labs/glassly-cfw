// SPDX-License-Identifier: MIT
// G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce: zlib_glue.c mode10,
// als_sensor.c als_control/als_passive_start. License: LICENSE.
import Foundation

public enum SensorCommandError: Error, Equatable, LocalizedError {
    case unsigned16OutOfRange(field: String)
    public var errorDescription: String? {
        switch self {
        case let .unsigned16OutOfRange(field): "\(field) must be an integer from0 through65535"
        }
    }
}

/// Encoding-only G2 sensor commands. Current MemoMind firmware does NOT support
/// modes10/16; these bytes do not establish a sensor capability or native binding.
/// No transport/zlib framing, physical-unit conversion, reports or raw-IMU wire
/// protocol is provided. Neither mode is admitted by RasterCommands.bundle.
public enum SensorCommands {
    private static func u16(_ value: Int, _ field: String) throws -> [UInt8] {
        guard let word = UInt16(exactly: value) else { throw SensorCommandError.unsigned16OutOfRange(field: field) }
        return [UInt8(truncatingIfNeeded: word), UInt8(word >> 8)]
    }

    /// [0x0a,0x00]. Upstream disables compass forwarding and stops on its master lens.
    /// This does not imply MemoMind ownership, stop completion or a usable sensor.
    public static func compassStop() -> Data {
        Data([10, 0])
    }

    /// [0x0a,0x01]. Upstream starts with stock defaults (documented1000ms/5 minimum
    /// change), without sending a configuration call. Not an explicit mode2 frame.
    public static func compassStart() -> Data {
        Data([10, 1])
    }

    /// [0x0a,0x02,intervalLE16,minimumChangeLE16]. Preserves every supplied UInt16;
    /// upstream clamps interval to50...2000ms after decoding. Minimum change is
    /// passed unchanged to stock; this API does not assign a physical unit/range.
    /// Upstream requires at least6 bytes, ignores trailing bytes and the mode high
    /// bit, and rejects unknown ops. Canonical output is exactly6 bytes/mode0x0a.
    public static func compassStart(intervalMilliseconds: Int, minimumChange: Int) throws -> Data {
        try Data([10, 2] + u16(intervalMilliseconds, "intervalMilliseconds") + u16(minimumChange, "minimumChange"))
    }

    /// [0x10,0x00]. G2 requests one snapshot of existing ALS driver globals; it does
    /// not necessarily open/read the sensor. No MemoMind report format is assumed.
    public static func alsQuery() -> Data {
        Data([16, 0])
    }

    /// [0x10,0x02]. Requests upstream passive-mode stop/restoration of stock ownership.
    public static func alsStop() -> Data {
        Data([16, 2])
    }

    /// [0x10,0x01,flags,intervalLE16,minDeltaLE16,heartbeatLE16], always9 bytes.
    /// Preserves supplied UInt16 values. Upstream clamps interval to100...5000ms;
    /// minDelta is an uninterpreted stock-value difference, not an assumed lux unit.
    /// Heartbeat0 disables time-only reporting; delta-based reporting still applies.
    /// The Boolean sets flags bit0 to request binding to G2's framebuffer lease;
    /// no equivalent MemoMind lease/brightness/sensor ownership is established.
    ///
    /// Upstream also permits partial start headers: omitted flags default0;
    /// incomplete interval/minDelta/heartbeat pairs default500/1/5000 respectively.
    /// It preserves unknown flag bits, using only bit0 for lease binding, ignores
    /// trailing bytes and the mode high bit. This typed API emits all fields,
    /// flags0/1 and mode0x10; it does not manufacture ignored or partial fields.
    public static func alsStart(intervalMilliseconds: Int = 500, minimumDelta: Int = 1,
                                heartbeatMilliseconds: Int = 5000, bindToFramebufferLease: Bool = false) throws -> Data
    {
        try Data([16, 1, bindToFramebufferLease ? 1 : 0] + u16(intervalMilliseconds, "intervalMilliseconds") +
            u16(minimumDelta, "minimumDelta") + u16(heartbeatMilliseconds, "heartbeatMilliseconds"))
    }
}
