// SPDX-License-Identifier: MIT
import Foundation
@testable import MemoMindCore
import XCTest

final class SensorCommandsTests: XCTestCase {
    func testPinnedOriginalControlGoldenFixtures() throws {
        for f in SensorReferenceVectors.cases {
            let wire: Data
            switch f.kind {
            case "compassStop": wire = SensorCommands.compassStop()
            case "compassDefault": wire = SensorCommands.compassStart()
            case "compassConfig": wire = try SensorCommands.compassStart(intervalMilliseconds: f.values[0], minimumChange: f.values[1])
            case "alsQuery": wire = SensorCommands.alsQuery()
            case "alsStop": wire = SensorCommands.alsStop()
            case "alsStart": wire = try SensorCommands.alsStart(intervalMilliseconds: f.values[0], minimumDelta: f.values[1], heartbeatMilliseconds: f.values[2], bindToFramebufferLease: f.values[3] != 0)
            default: XCTFail("Unknown golden kind \(f.kind)"); continue
            }
            XCTAssertEqual(wire, hex(f.wire), f.name)
        }
    }

    func testExplicitDefaultsAndHeartbeatZero() throws {
        XCTAssertEqual(SensorCommands.compassStart(), Data([10, 1]))
        XCTAssertEqual(try SensorCommands.compassStart(intervalMilliseconds: 1000, minimumChange: 5), hex("0a02e8030500"))
        XCTAssertNotEqual(SensorCommands.compassStart(), try SensorCommands.compassStart(intervalMilliseconds: 1000, minimumChange: 5))
        XCTAssertEqual(try SensorCommands.alsStart(), hex("100100f40101008813"))
        XCTAssertEqual(try SensorCommands.alsStart(bindToFramebufferLease: true), hex("100101f40101008813"))
        XCTAssertEqual(try SensorCommands.alsStart(heartbeatMilliseconds: 0), hex("100100f40101000000"))
        XCTAssertEqual(SensorCommands.alsQuery(), Data([16, 0]))
        XCTAssertEqual(SensorCommands.alsStop(), Data([16, 2]))
    }

    func testUInt16PreservationInsteadOfHostClampingOrUnitConversion() throws {
        for value in [0, 1, 49, 50, 99, 100, 255, 256, 499, 500, 1000, 1999, 2000, 2001, 4999, 5000, 5001, 32768, 65535] {
            let little = Data([UInt8(truncatingIfNeeded: value), UInt8(value >> 8)])
            let compass = try SensorCommands.compassStart(intervalMilliseconds: value, minimumChange: value)
            XCTAssertEqual(compass, Data([10, 2]) + little + little)
            for lease in [false, true] {
                let als = try SensorCommands.alsStart(intervalMilliseconds: value, minimumDelta: value, heartbeatMilliseconds: value, bindToFramebufferLease: lease)
                XCTAssertEqual(als, Data([16, 1, lease ? 1 : 0]) + little + little + little)
                XCTAssertEqual(als.count, 9)
            }
            XCTAssertEqual(compass.count, 6)
        }
    }

    func testInvalidUnsignedFieldsRejectInsteadOfWrapping() {
        for value in [Int.min, -65536, -1, 65536, Int.max] {
            XCTAssertThrowsError(try SensorCommands.compassStart(intervalMilliseconds: value, minimumChange: 5)) {
                XCTAssertEqual($0 as? SensorCommandError, .unsigned16OutOfRange(field: "intervalMilliseconds"))
            }
            XCTAssertThrowsError(try SensorCommands.compassStart(intervalMilliseconds: 1000, minimumChange: value)) {
                XCTAssertEqual($0 as? SensorCommandError, .unsigned16OutOfRange(field: "minimumChange"))
            }
            XCTAssertThrowsError(try SensorCommands.alsStart(intervalMilliseconds: value)) {
                XCTAssertEqual($0 as? SensorCommandError, .unsigned16OutOfRange(field: "intervalMilliseconds"))
            }
            XCTAssertThrowsError(try SensorCommands.alsStart(minimumDelta: value)) {
                XCTAssertEqual($0 as? SensorCommandError, .unsigned16OutOfRange(field: "minimumDelta"))
            }
            XCTAssertThrowsError(try SensorCommands.alsStart(heartbeatMilliseconds: value)) {
                XCTAssertEqual($0 as? SensorCommandError, .unsigned16OutOfRange(field: "heartbeatMilliseconds"))
            }
        }
    }

    func testCanonicalModesAndContinuedBundleRejection() throws {
        let commands = try [SensorCommands.compassStop(), SensorCommands.compassStart(),
                            SensorCommands.compassStart(intervalMilliseconds: 50, minimumChange: 0),
                            SensorCommands.alsQuery(), SensorCommands.alsStop(), SensorCommands.alsStart()]
        for command in commands {
            XCTAssertTrue(command.first == 10 || command.first == 16)
            XCTAssertLessThan(command.count, RasterCommands.maximumCommandBytes)
            for high: UInt8 in [0, 128] {
                var raw = command; raw[0] |= high
                XCTAssertThrowsError(try RasterCommands.bundle([raw])) {
                    XCTAssertEqual($0 as? BundleCommandError, .unsupportedMode(index: 0, mode: raw[0]))
                }
            }
        }
    }
}
