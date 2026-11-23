import CoreBluetooth
import Foundation

let started = Date()
func log(_ text: String) { print(String(format: "%7.3f ", Date().timeIntervalSince(started)) + text); fflush(stdout) }
func hex(_ d: Data) -> String { d.map { String(format: "%02x", $0) }.joined() }

func gmFrame(event: UInt8, service: UInt8, command: UInt8, body: [UInt8] = []) -> Data {
    let logical = body.count + 9
    var packet: [UInt8] = [0xFA, UInt8(logical >> 16 & 0xFF), UInt8(logical >> 8 & 0xFF), UInt8(logical & 0xFF), event, service, command] + body
    let sum = packet.reduce(0) { $0 + Int($1) } & 0xFFFF
    packet += [UInt8(sum >> 8), UInt8(sum & 0xFF)]
    return Data(packet)
}

func fragments(_ frame: Data, limit: Int) -> [Data] {
    let bytes = [UInt8](frame); var out: [Data] = []; var offset = 0
    repeat {
        let first = offset == 0, room = max(1, limit - (first ? 3 : 1)), end = min(bytes.count, offset + room)
        var header: [UInt8] = [(first ? 1 : 0) | (end >= bytes.count ? 2 : 0)]
        if first { header += [UInt8(bytes.count & 0xFF), UInt8(bytes.count >> 8)] }
        out.append(Data(header + bytes[offset ..< end])); offset = end
    } while offset < bytes.count
    return out
}

final class Check: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var central: CBCentralManager!
    var peripheral: CBPeripheral?
    var gm: CBCharacteristic?
    var ota: CBCharacteristic?
    var timer: Timer?
    var accepted = false
    var sentHeartbeat = false
    var stream = Data()

    func start() { central = CBCentralManager(delegate: self, queue: .main) }

    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        log("central state \(c.state.rawValue)")
        if c.state == .poweredOn { c.scanForPeripherals(withServices: [CBUUID(string: "9200")]) }
    }

    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData a: [String: Any], rssi: NSNumber) {
        let name = p.name ?? (a[CBAdvertisementDataLocalNameKey] as? String) ?? "?"
        guard peripheral == nil, name.localizedCaseInsensitiveContains("memo") else { return }
        log("advert \(name) rssi \(rssi) services \(a[CBAdvertisementDataServiceUUIDsKey] ?? "-")")
        peripheral = p; p.delegate = self; c.stopScan(); c.connect(p)
    }

    func centralManager(_: CBCentralManager, didConnect p: CBPeripheral) { log("connected"); p.discoverServices(nil) }
    func centralManager(_: CBCentralManager, didDisconnectPeripheral _: CBPeripheral, error: Error?) {
        log("disconnected: \(error?.localizedDescription ?? "requested") accepted=\(accepted)"); exit(accepted && sentHeartbeat ? 0 : 2)
    }

    func peripheral(_ p: CBPeripheral, didDiscoverServices _: Error?) {
        log("services \(p.services?.map(\.uuid.uuidString) ?? [])")
        guard let s = p.services?.first(where: { $0.uuid == CBUUID(string: "9400") }) else { log("no 9400"); exit(3) }
        p.discoverCharacteristics(nil, for: s)
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error _: Error?) {
        log("characteristics \(s.characteristics?.map { "\($0.uuid.uuidString) props \($0.properties.rawValue)" } ?? [])")
        gm = s.characteristics?.first { $0.uuid == CBUUID(string: "9401") }
        ota = s.characteristics?.first { $0.uuid == CBUUID(string: "9402") }
        guard let gm else { exit(4) }
        p.setNotifyValue(true, for: gm)
    }

    func peripheral(_ p: CBPeripheral, didUpdateNotificationStateFor c: CBCharacteristic, error: Error?) {
        log("notify \(c.uuid.uuidString) \(c.isNotifying) \(error?.localizedDescription ?? "")")
        if c.uuid == CBUUID(string: "9401") {
            timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.hello() }
            hello()
        }
    }

    func hello() {
        guard !accepted, let p = peripheral, let gm else { return }
        let limit = p.maximumWriteValueLength(for: .withoutResponse)
        p.writeValue(Data([0x80, 1, UInt8(limit & 0xFF), UInt8(limit >> 8)]), for: gm, type: .withoutResponse)
    }

    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error _: Error?) {
        guard let v = c.value else { return }
        if !accepted, v.count >= 4, v[0] == 0x80, v[1] == 1 {
            log("hello reply \(hex(v))")
            if v[2] == 0 {
                accepted = true; timer?.invalidate()
                let limit = p.maximumWriteValueLength(for: .withoutResponse)
                log("accepted; mtu write limit \(limit); sending GM heartbeat (service 1 command 1)")
                for piece in fragments(gmFrame(event: 1, service: 1, command: 1), limit: limit) {
                    p.writeValue(piece, for: c, type: .withoutResponse)
                }
                sentHeartbeat = true
            }
            return
        }
        stream.append(v)
        log("gm notify \(v.count) B: \(hex(v.prefix(48)))")
        if stream.count >= 4, stream[0] == 0xFA {
            log("GM reply frame over BLE: \(hex(stream))")
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.central.cancelPeripheralConnection(p) }
        }
    }
}

let check = Check()
check.start()
DispatchQueue.main.asyncAfter(deadline: .now() + 45) { log("timeout accepted=\(check.accepted)"); exit(5) }
RunLoop.main.run()
