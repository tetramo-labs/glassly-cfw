import Foundation

public struct OTABlock: Codable, Equatable {
    public let offset: Int
    public let length: Int
    public let baseSequence: UInt8
    public let ackSequence: UInt8
}

public struct OTAResult: Codable {
    public let modifiedImage: Bool
    public let device: DeviceIdentity
    /// Unknown attach fields remain uninterpreted. Field 2 battery semantics are unproven.
    public let attachFields: [String: String]
    public let checkOnly: Bool
    public let state: String
    public let blocks: Int
    public let chunks: Int
    public let transferredRange: [Int]?
    public let postRebootVersionVerified: Bool
}

/// Single use, fail closed. Eligibility belongs to EligibleFirmware; the OTA connection
/// must already be open after GMSession.notifyOTA(). No connection changes or retries.
public final class OTATransaction {
    private let transport: MemoMindTransport
    private let image: Data
    private let modified: Bool
    private let identity: DeviceIdentity
    private let pace: TimeInterval
    private let timeout: TimeInterval
    private let waitForPacing: (TimeInterval) throws -> Void
    private let checkControlLink: (() throws -> Void)?
    private let parser = OTAStream()
    private var pending = [Data]()
    private var sequence: UInt8 = 0
    private var started = false
    public private(set) var phase = "validated"
    public private(set) var blocks = [OTABlock]()
    public private(set) var chunks = 0
    /// Reports acknowledged blocks only; callback must not reenter this transaction.
    public var progress: ((OTABlock) -> Void)?

    public convenience init(transport: MemoMindTransport, firmware: EligibleFirmware,
                            identity: DeviceIdentity, address: String,
                            pace: TimeInterval = 0.045, timeout: TimeInterval = 15,
                            checkControlLink: (() throws -> Void)? = nil) throws
    {
        try self.init(transport: transport, image: firmware.data, modified: firmware.modified,
                      identity: identity, address: address, pace: pace, timeout: timeout,
                      checkControlLink: checkControlLink)
    }

    /// Internal raw entry is for independent recorded/synthetic tests, never the CLI.
    init(transport: MemoMindTransport, image: Data, modified: Bool, identity: DeviceIdentity,
         address: String, pace: TimeInterval = 0.045, timeout: TimeInterval = 15,
         checkControlLink: (() throws -> Void)? = nil,
         waitForPacing: @escaping (TimeInterval) throws -> Void = { Thread.sleep(forTimeInterval: $0) }) throws
    {
        try identity.validate(address: address)
        try requireProtocol(image.count >= 18 && UInt64(image.count) <= UInt64(UInt32.max), "Invalid image length")
        try requireProtocol(pace.isFinite && pace >= 0 && timeout.isFinite && timeout > 0, "Invalid OTA timing")
        self.transport = transport; self.image = image; self.modified = modified; self.identity = identity
        self.pace = pace; self.timeout = timeout; self.checkControlLink = checkControlLink
        self.waitForPacing = waitForPacing
    }

    private func nextSequence() -> UInt8 {
        sequence &+= 1; return sequence
    }

    private func write(_ data: Data) throws {
        try checkControlLink?(); try transport.write(data)
    }

    private func response(command: UInt8, sequence: UInt8) throws -> [UInt8] {
        let deadline = monotonicNow() + timeout
        while pending.isEmpty {
            try checkControlLink?()
            let remaining = deadline - monotonicNow()
            guard remaining > 0 else { throw MemoMindProtocolError.timeout("OTA reply timeout") }
            pending += try parser.feed(transport.read(timeout: remaining))
        }
        let frame = Array(pending.removeFirst())
        try requireProtocol(frame[3] == 0 && frame[4] == command, "Unexpected OTA reply flags/command")
        let payload = Array(frame[7 ..< (frame.count - 1)])
        try requireProtocol(payload.count >= 2 && payload[0] == 0 && payload[1] == sequence,
                            "Unexpected OTA transport status/sequence")
        try requireProtocol(pending.isEmpty && parser.bufferedByteCount == 0, "Unexpected additional OTA reply bytes")
        return Array(payload.dropFirst(2))
    }

    private func command(_ command: UInt8, parameters: Data = Data()) throws -> [UInt8] {
        phase = String(format: "command 0x%02x", Int(command))
        let seq = nextSequence()
        try write(OTACodec.frame(command: command, sequence: seq, parameters: parameters))
        return try response(command: command, sequence: seq)
    }

    public func run(checkOnly: Bool = false) throws -> OTAResult {
        try requireProtocol(!started, "OTA transaction is single use; retries are forbidden")
        started = true
        do { return try execute(checkOnly: checkOnly) }
        catch { throw MemoMindProtocolError.stopped(phase: phase, reason: String(describing: error)) }
    }

    private func execute(checkOnly: Bool) throws -> OTAResult {
        var attached = try command(2, parameters: Data(repeating: 0xFF, count: 5))
        var fields = [UInt8: Data]()
        while !attached.isEmpty {
            let length = Int(attached[0])
            try requireProtocol(length >= 1 && attached.count >= length + 1, "Malformed attach TLV")
            let kind = attached[1]
            try requireProtocol(fields[kind] == nil, "Duplicate attach TLV")
            fields[kind] = Data(attached[2 ..< (length + 1)])
            attached.removeFirst(length + 1)
        }
        try requireProtocol(fields[1] == image.prefix(4), "OTA attach profile differs from image")
        try requireProtocol(command(0xE1) == [0, 0, 0, 0, 0, 0x12], "Unsupported OTA file-identification request")
        try requireProtocol(command(0xE2, parameters: Data(image.prefix(18))) == [3],
                            "Device did not return supported can-update result 3; entry not sent")
        func result(state: String, range: [Int]?) -> OTAResult {
            OTAResult(modifiedImage: modified, device: identity,
                      attachFields: Dictionary(uniqueKeysWithValues: fields.map { (String($0.key), $0.value.map { String(format: "%02x", $0) }.joined()) }),
                      checkOnly: checkOnly, state: state, blocks: blocks.count, chunks: chunks,
                      transferredRange: range, postRebootVersionVerified: false)
        }
        if checkOnly {
            return result(state: "eligible; stopped before OTA entry", range: nil)
        }
        let entry = try command(0xE3)
        try requireProtocol(entry.count == 8 && entry.first == 0 && entry.last == 1, "Unsupported OTA entry result/CRC mode")
        var offset = Int(readBE(entry[1 ..< 5])), size = Int(readBE(entry[5 ..< 7]))
        try requireProtocol(!modified || offset == 18, "Modified image requires fresh offset 18; refusing stale/partial resume before chunks")
        var previousEnd: Int?
        while true {
            phase = "block at offset \(offset), length \(size)"
            try requireProtocol(size > 0 && size <= 4096 && offset > 0 && offset < image.count && size <= image.count - offset,
                                "Requested block out of supported bounds")
            try requireProtocol(previousEnd == nil || offset == previousEnd, "Noncontiguous/repeated range requires unsupported recovery logic")
            let base = nextSequence()
            var seq = base
            for (index, relative) in stride(from: 0, to: size, by: 630).enumerated() {
                seq = base &+ UInt8(index)
                let fragment = image.subdata(in: (offset + relative) ..< (offset + min(relative + 630, size)))
                try write(OTACodec.chunk(sequence: seq, offset: UInt32(offset + relative), data: fragment))
                chunks += 1
                if relative + 630 < size, pace > 0 {
                    Thread.sleep(forTimeInterval: pace)
                }
            }
            let reply = try response(command: 0xE5, sequence: seq)
            try requireProtocol(reply.count == 9 && reply[0] == 0, "Unsupported OTA block result")
            let pacing = Int(readBE(reply[7 ..< 9]))
            try requireProtocol(pacing == 0 || pacing == 2000, "Unsupported OTA pacing field")
            let block = OTABlock(offset: offset, length: size, baseSequence: base, ackSequence: seq)
            blocks.append(block); progress?(block)
            previousEnd = offset + size
            offset = Int(readBE(reply[1 ..< 5])); size = Int(readBE(reply[5 ..< 7]))
            let terminal = offset == 0 && size == 0
            if terminal {
                try requireProtocol(previousEnd == image.count, "Premature terminal ACK before image EOF")
            } else {
                try requireProtocol(offset == previousEnd && size > 0 && size <= 4096 &&
                    offset < image.count && size <= image.count - offset, "Invalid next OTA block range")
            }
            if pacing != 0 {
                phase = "device pacing at offset \(offset)"
                for _ in 0 ..< 20 {
                    try checkControlLink?()
                    try waitForPacing(0.1)
                }
                try checkControlLink?()
            }
            if terminal {
                break
            }
        }
        try requireProtocol(command(0xE6) == [0], "Unsupported update-status result")
        try requireProtocol(command(3, parameters: Data([0])) == [0], "Unsupported reboot result")
        phase = "reboot acknowledged"
        return result(state: phase, range: [blocks[0].offset, previousEnd!])
    }
}
