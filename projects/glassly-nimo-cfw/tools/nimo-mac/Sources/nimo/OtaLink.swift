import Foundation
import IOBluetooth

/// The WuQi OTA service (SDP UUID 0x7034, RFCOMM) as recorded on the MemoMind One:
/// `70 07 6e | flags | command | length16 BE | sequence + parameters | 33`.
/// Only the read-only attach (0x02) and file-identification (0xe1) queries are used here.
final class OtaLink: NSObject, IOBluetoothRFCOMMChannelDelegate {
    static let magic = Data([0x70, 0x07, 0x6E])
    let device: IOBluetoothDevice
    private var channel: IOBluetoothRFCOMMChannel?
    private var buffer = Data()
    private var pending: CheckedContinuation<Data, Error>?
    private var sequence: UInt8 = 0
    var onTraffic: ((String, Data) -> Void)?
    var log: (String) -> Void = { print($0) }

    enum Failure: Error, CustomStringConvertible {
        case open(IOReturn), closed, timeout, badFrame(String)
        var description: String {
            switch self {
            case let .open(s): "RFCOMM open failed \(String(format: "0x%08x", s))"
            case .closed: "RFCOMM channel closed"
            case .timeout: "OTA reply timed out"
            case let .badFrame(why): "bad OTA frame: \(why)"
            }
        }
    }

    init(device: IOBluetoothDevice) { self.device = device }

    /// The glasses accept the channel only on some fresh links; retry across link resets.
    func open(channelID: UInt8 = 6, attempts: Int = 5) throws {
        var last: IOReturn = kIOReturnError
        for attempt in 1 ... attempts {
            resetLink(device, log: log)
            var ch: IOBluetoothRFCOMMChannel?
            last = device.openRFCOMMChannelSync(&ch, withChannelID: channelID, delegate: self)
            if last == kIOReturnSuccess, let ch {
                channel = ch
                buffer = Data()
                log("OTA RFCOMM channel \(channelID) open on attempt \(attempt), MTU \(ch.getMTU())")
                return
            }
            log("attempt \(attempt): RFCOMM open failed \(String(format: "0x%08x", last))")
            Thread.sleep(forTimeInterval: 3)
        }
        throw Failure.open(last)
    }

    func close() { channel?.close(); channel = nil }

    static func encode(command: UInt8, sequence: UInt8, parameters: Data, flags: UInt8 = 0xC0) -> Data {
        let payload = Data([sequence]) + parameters
        return magic + Data([flags, command, UInt8(payload.count >> 8), UInt8(payload.count & 0xFF)]) + payload + Data([0x33])
    }

    func rfcommChannelData(_: IOBluetoothRFCOMMChannel!, data: UnsafeMutableRawPointer!, length: Int) {
        let chunk = Data(bytes: data, count: length)
        onTraffic?("ota-rx", chunk)
        buffer.append(chunk)
        while buffer.count >= 7 {
            // Rebase every pass: Data keeps absolute indices after a removal.
            let bytes = [UInt8](buffer)
            guard bytes[0] == 0x70, bytes[1] == 0x07, bytes[2] == 0x6E else {
                let bad = buffer; buffer = Data()
                pending?.resume(throwing: Failure.badFrame("prefix \(bad.hex)")); pending = nil; return
            }
            let length = Int(bytes[5]) << 8 | Int(bytes[6])
            guard bytes.count >= length + 8 else { return }
            let frame = Data(bytes[0 ..< length + 8])
            buffer = Data(bytes[(length + 8)...])
            guard frame.last == 0x33 else { pending?.resume(throwing: Failure.badFrame("footer")); pending = nil; return }
            if let cont = pending { pending = nil; cont.resume(returning: frame) } else { log("unsolicited OTA frame \(frame.hex)") }
        }
    }

    func rfcommChannelClosed(_: IOBluetoothRFCOMMChannel!) {
        log("OTA channel closed")
        channel = nil
        if let cont = pending { pending = nil; cont.resume(throwing: Failure.closed) }
    }

    /// Returns (flags, command, payload after the transport status and echoed sequence).
    func command(_ command: UInt8, _ parameters: Data = Data(), timeout: Double = 5) async throws -> (status: UInt8, payload: Data, raw: Data) {
        sequence = sequence &+ 1
        let seq = sequence
        let frame = Self.encode(command: command, sequence: seq, parameters: parameters)
        let reply: Data = try await withCheckedThrowingContinuation { cont in
            DispatchQueue.main.async {
                guard let channel = self.channel else { cont.resume(throwing: Failure.closed); return }
                self.pending = cont
                self.onTraffic?("ota-tx", frame)
                var bytes = [UInt8](frame)
                let s = bytes.withUnsafeMutableBufferPointer { channel.writeSync($0.baseAddress, length: UInt16($0.count)) }
                if s != kIOReturnSuccess { self.pending = nil; cont.resume(throwing: Failure.open(s)); return }
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    if let waiting = self.pending { self.pending = nil; waiting.resume(throwing: Failure.timeout) }
                }
            }
        }
        guard reply.count >= 9, reply[4] == command else { throw Failure.badFrame("command echo \(reply.hex)") }
        let payload = reply.subdata(in: 7 ..< reply.count - 1)
        guard payload.count >= 2, payload[1] == seq else { throw Failure.badFrame("sequence \(reply.hex)") }
        return (payload[0], payload.subdata(in: 2 ..< payload.count), reply)
    }

    /// `length | kind | value` records, as the MemoMind attach reply carries them.
    static func tlvs(_ data: Data) -> [(kind: UInt8, value: Data)] {
        var out: [(UInt8, Data)] = []
        var i = 0
        while i < data.count {
            let len = Int(data[i])
            guard len >= 1, i + 1 + len <= data.count else { break }
            out.append((data[i + 1], data.subdata(in: i + 2 ..< i + 1 + len)))
            i += 1 + len
        }
        return out
    }
}

/// The glasses keep channel state from the previous host session; a fresh ACL link is
/// the only reliable way to open a channel again.
func resetLink(_ device: IOBluetoothDevice, log: (String) -> Void) {
    if device.isConnected() { _ = device.closeConnection(); Thread.sleep(forTimeInterval: 2) }
    let s = device.openConnection()
    log("baseband link reopened \(String(format: "0x%08x", s)) connected \(device.isConnected())")
}
