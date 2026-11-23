import CryptoKit
import Foundation
import MemoMindCore

/// The original capture resumes a stock update. This reproduces its exact ordering,
/// including the two normal-service records before switching to the OTA channel.
final class CapturedTransport: MemoMindTransport {
    struct Row {
        let frame: Int
        let direction: Int
        let channel: Int
        let data: Data
    }

    let rows: [Row]
    var channel = 5
    private(set) var position = 0
    private(set) var writes = 0
    private(set) var reads = 0
    private var digest = SHA256()
    var outgoingSHA256: String {
        digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    init(rows: [Row]) {
        self.rows = rows
    }

    func take(_ direction: Int) throws -> Row {
        guard position < rows.count else { throw CLIError("Replay exhausted") }
        let row = rows[position]
        guard row.direction == direction, row.channel == channel else {
            throw CLIError("Replay ordering/service mismatch at frame \(row.frame)")
        }
        position += 1
        return row
    }

    func read(timeout _: TimeInterval) throws -> Data {
        reads += 1
        return try take(1).data
    }

    func write(_ data: Data) throws {
        let row = try take(0)
        guard data == row.data else { throw CLIError("Outgoing bytes differ at captured frame \(row.frame)") }
        writes += 1
        digest.update(data: data)
    }
}

func decodeHex(_ value: String) throws -> Data {
    let bytes = Array(value.utf8)
    guard bytes.count % 2 == 0 else { throw CLIError("Odd-length hex data") }
    var result = Data()
    func nibble(_ byte: UInt8) throws -> UInt8 {
        switch byte {
        case 48 ... 57: return byte - 48
        case 65 ... 70: return byte - 55
        case 97 ... 102: return byte - 87
        default: throw CLIError("Non-hex data")
        }
    }
    for index in stride(from: 0, to: bytes.count, by: 2) {
        try result.append(nibble(bytes[index]) << 4 | nibble(bytes[index + 1]))
    }
    return result
}

func replay(firmware: EligibleFirmware, path: String) throws -> [String: Any] {
    let transcript = try Data(contentsOf: URL(fileURLWithPath: path))
    guard let source = String(data: transcript, encoding: .utf8) else { throw CLIError("Transcript is not UTF8") }
    let parser = GMStream(legacyRepeatFA: true)
    var identity: DeviceIdentity?
    var rows = [CapturedTransport.Row]()
    for line in source.split(whereSeparator: \.isNewline) {
        let fields = line.split(separator: "\t", omittingEmptySubsequences: false)
        guard fields.count == 6, let number = Int(fields[0]), let channel = Int(fields[4]) else {
            throw CLIError("Malformed six-column RFCOMM transcript")
        }
        let directionText = String(fields[2])
        let direction = directionText.hasPrefix("0x") ? Int(directionText.dropFirst(2), radix: 16) : Int(directionText)
        guard let direction, [0, 1].contains(direction) else { throw CLIError("Unknown transcript direction") }
        let data = try decodeHex(String(fields[5]))
        if channel == 5, direction == 1, number < 1615 {
            for message in try parser.feed(data) where message.service == 1 && message.command == 2 {
                let strings = message.tlvs.filter { $0.kind == 2 }
                if strings.count == 1 {
                    identity = try DeviceIdentity.decode(strings[0].value)
                }
            }
        }
        if number == 1615 || number == 1617 || channel == 6 {
            rows.append(.init(frame: number, direction: direction, channel: channel, data: data))
        }
    }
    guard let identity, rows.first?.frame == 1615 else { throw CLIError("Captured identity or transaction start missing") }
    let transport = CapturedTransport(rows: rows)
    try GMSession(transport: transport).notifyOTA()
    transport.channel = 6
    let transaction = try OTATransaction(transport: transport, firmware: firmware,
                                         identity: identity, address: identity.mac, pace: 0)
    var result = try dictionary(transaction.run())
    guard transport.position == rows.count else { throw CLIError("Unconsumed transcript records") }
    result["mode"] = "offline captured replay"
    result["imageSHA256"] = firmware.sha256
    result["recordsConsumed"] = transport.position
    result["recordsTotal"] = rows.count
    result["outgoingPacketsIdentical"] = transport.writes
    result["incomingPacketsConsumed"] = transport.reads
    result["outgoingWireSHA256"] = transport.outgoingSHA256
    result["transcriptSHA256"] = SHA256.hash(data: transcript).map { String(format: "%02x", $0) }.joined()
    return result
}
