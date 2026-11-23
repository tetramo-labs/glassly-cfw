import Foundation
import IOBluetooth

/// A minimal GATT client over the classic ATT bearer (L2CAP PSM 0x1F), which is how the
/// NIMO exposes service 0x7033 to a paired host. IOBluetooth delivers on the main run loop.
final class AttLink: NSObject, IOBluetoothL2CAPChannelDelegate {
    enum Failure: Error, CustomStringConvertible {
        case open(IOReturn), closed, timeout(String), att(UInt8, UInt8), notFound(String)
        var description: String {
            switch self {
            case let .open(s): "L2CAP open failed \(String(format: "0x%08x", s))"
            case .closed: "ATT channel closed"
            case let .timeout(op): "ATT \(op) timed out"
            case let .att(req, code): "ATT request \(String(format: "0x%02X", req)) failed with error \(String(format: "0x%02X", code))"
            case let .notFound(what): "\(what) not found"
            }
        }
    }

    let device: IOBluetoothDevice
    private var channel: IOBluetoothL2CAPChannel?
    private var pending: CheckedContinuation<Data, Error>?
    private var pendingOpcode: UInt8 = 0
    private(set) var mtu = 23
    var onNotify: ((UInt16, Data) -> Void)?
    var onTraffic: ((String, Data) -> Void)?
    var log: (String) -> Void = { print($0) }

    init(device: IOBluetoothDevice) {
        self.device = device
    }

    func open() throws {
        resetLink(device, log: log)
        var ch: IOBluetoothL2CAPChannel?
        let s = device.openL2CAPChannelSync(&ch, withPSM: 0x1F, delegate: self)
        guard s == kIOReturnSuccess, let ch else { throw Failure.open(s) }
        channel = ch
        mtu = max(23, Int(ch.outgoingMTU))
        log("ATT channel open, L2CAP MTU \(ch.outgoingMTU)")
    }

    func close() {
        channel?.close()
        channel = nil
    }

    // MARK: delegate (main thread)

    func l2capChannelData(_: IOBluetoothL2CAPChannel!, data: UnsafeMutableRawPointer!, length: Int) {
        let pdu = Data(bytes: data, count: length)
        onTraffic?("att-rx", pdu)
        guard let op = pdu.first else { return }
        if op == 0x1B, pdu.count >= 3 {
            onNotify?(UInt16(pdu[1]) | UInt16(pdu[2]) << 8, pdu.subdata(in: 3 ..< pdu.count))
            return
        }
        if op == 0x1D, pdu.count >= 3 { // indication: confirm, then treat like a notification
            send(Data([0x1E]))
            onNotify?(UInt16(pdu[1]) | UInt16(pdu[2]) << 8, pdu.subdata(in: 3 ..< pdu.count))
            return
        }
        guard let cont = pending else { log("unexpected ATT pdu \(pdu.hex)"); return }
        pending = nil
        if op == 0x01, pdu.count >= 5 {
            cont.resume(throwing: Failure.att(pdu[1], pdu[4]))
        } else {
            cont.resume(returning: pdu)
        }
    }

    func l2capChannelClosed(_: IOBluetoothL2CAPChannel!) {
        log("ATT channel closed")
        channel = nil
        if let cont = pending { pending = nil; cont.resume(throwing: Failure.closed) }
    }

    private func send(_ pdu: Data) {
        guard let channel else { return }
        onTraffic?("att-tx", pdu)
        var bytes = [UInt8](pdu)
        bytes.withUnsafeMutableBufferPointer { buf in
            let s = channel.writeSync(buf.baseAddress, length: UInt16(buf.count))
            if s != kIOReturnSuccess { log("ATT write failed \(String(format: "0x%08x", s))") }
        }
    }

    /// One ATT request; the bearer allows a single outstanding request.
    func request(_ pdu: Data, timeout: Double = 5) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.main.async {
                guard self.channel != nil else { cont.resume(throwing: Failure.closed); return }
                self.pending = cont
                self.pendingOpcode = pdu[0]
                self.send(pdu)
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    if let waiting = self.pending, self.pendingOpcode == pdu[0] {
                        // Only our own request can still be pending with this opcode.
                        self.pending = nil
                        _ = waiting
                        cont.resume(throwing: Failure.timeout(String(format: "0x%02X", pdu[0])))
                    }
                }
            }
        }
    }

    private static func u16(_ v: Int) -> [UInt8] { [UInt8(v & 0xFF), UInt8(v >> 8 & 0xFF)] }

    func exchangeMTU(_ want: Int = 517) async throws {
        let r = try await request(Data([0x02] + Self.u16(want)))
        guard r.count >= 3, r[0] == 0x03 else { return }
        mtu = min(want, Int(r[1]) | Int(r[2]) << 8)
        log("ATT MTU \(mtu)")
    }

    struct Characteristic {
        let declaration: UInt16
        let properties: UInt8
        let value: UInt16
        let uuid: Data
        var uuid16: UInt16? { uuid.count == 2 ? UInt16(uuid[0]) | UInt16(uuid[1]) << 8 : nil }
    }

    /// Primary services as (uuid, start, end) via Read By Group Type.
    func services() async throws -> [(uuid: Data, start: UInt16, end: UInt16)] {
        var out: [(Data, UInt16, UInt16)] = []
        var start = 1
        while start <= 0xFFFF {
            let r: Data
            do { r = try await request(Data([0x10] + Self.u16(start) + Self.u16(0xFFFF) + Self.u16(0x2800))) }
            catch Failure.att(_, 0x0A) { break }
            guard r.count >= 2, r[0] == 0x11 else { break }
            let len = Int(r[1])
            var i = 2
            var last = start
            while i + len <= r.count {
                let s = UInt16(r[i]) | UInt16(r[i + 1]) << 8
                let e = UInt16(r[i + 2]) | UInt16(r[i + 3]) << 8
                out.append((r.subdata(in: i + 4 ..< i + len), s, e))
                last = Int(e)
                i += len
            }
            if last >= 0xFFFF { break }
            start = last + 1
        }
        return out
    }

    func characteristics(start: UInt16, end: UInt16) async throws -> [Characteristic] {
        var out: [Characteristic] = []
        var from = Int(start)
        while from <= Int(end) {
            let r: Data
            do { r = try await request(Data([0x08] + Self.u16(from) + Self.u16(Int(end)) + Self.u16(0x2803))) }
            catch Failure.att(_, 0x0A) { break }
            guard r.count >= 2, r[0] == 0x09 else { break }
            let len = Int(r[1])
            var i = 2
            while i + len <= r.count {
                let decl = UInt16(r[i]) | UInt16(r[i + 1]) << 8
                let value = UInt16(r[i + 3]) | UInt16(r[i + 4]) << 8
                out.append(Characteristic(declaration: decl, properties: r[i + 2], value: value, uuid: r.subdata(in: i + 5 ..< i + len)))
                from = Int(decl) + 1
                i += len
            }
        }
        return out
    }

    /// The Client Characteristic Configuration descriptor after `valueHandle`, up to `end`.
    func cccd(after valueHandle: UInt16, end: UInt16) async throws -> UInt16 {
        var from = Int(valueHandle) + 1
        while from <= Int(end) {
            let r: Data
            do { r = try await request(Data([0x04] + Self.u16(from) + Self.u16(Int(end)))) }
            catch Failure.att(_, 0x0A) { break }
            guard r.count >= 2, r[0] == 0x05 else { break }
            let step = r[1] == 1 ? 4 : 18
            var i = 2
            while i + step <= r.count {
                let h = UInt16(r[i]) | UInt16(r[i + 1]) << 8
                if r[1] == 1, r[i + 2] == 0x02, r[i + 3] == 0x29 { return h }
                if r[1] == 1, r[i + 2] == 0x03, r[i + 3] == 0x28 { throw Failure.notFound("CCCD before the next characteristic") }
                from = Int(h) + 1
                i += step
            }
        }
        throw Failure.notFound("CCCD")
    }

    func write(handle: UInt16, value: Data) async throws {
        let r = try await request(Data([0x12] + Self.u16(Int(handle))) + value)
        guard r.first == 0x13 else { throw Failure.notFound("write response") }
    }

    func read(handle: UInt16) async throws -> Data {
        let r = try await request(Data([0x0A] + Self.u16(Int(handle))))
        guard r.first == 0x0B else { throw Failure.notFound("read response") }
        return r.subdata(in: 1 ..< r.count)
    }
}
