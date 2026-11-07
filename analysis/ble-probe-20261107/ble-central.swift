// CoreBluetooth central: find the MemoMind, discover service 0x9400, subscribe to
// 0x9401, write a payload and time the echo. Usage: ble-central [seconds] [name-substring]
import CoreBluetooth
import Foundation
final class Central: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let service = CBUUID(string: "9400"), chara = CBUUID(string: "9401")
    let nameHint: String, deadline: Date
    var manager: CBCentralManager!, peripheral: CBPeripheral?, characteristic: CBCharacteristic?
    var seen: [String: (Int, [String: Any])] = [:], sentAt = Date(), round = 0, rtts: [Double] = []
    init(seconds: Double, nameHint: String) { self.nameHint = nameHint; deadline = Date().addingTimeInterval(seconds); super.init(); manager = CBCentralManager(delegate: self, queue: nil) }
    func log(_ s: String) { print(String(format: "[%.3f] ", Date().timeIntervalSince(deadline) + 0) + s); fflush(stdout) }
    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        log("central state \(c.state.rawValue)")
        guard c.state == .poweredOn else { return }
        c.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        log("scanning for '\(nameHint)' or service 9400")
    }
    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        let name = p.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? "?"
        let uuids = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID])?.map(\.uuidString) ?? []
        if seen[p.identifier.uuidString] == nil { seen[p.identifier.uuidString] = (rssi.intValue, advertisementData); log("found \(name) rssi \(rssi) services \(uuids)") }
        if name.localizedCaseInsensitiveContains(nameHint) || uuids.contains("9400") {
            log("connecting to \(name)"); peripheral = p; p.delegate = self; c.stopScan(); c.connect(p, options: nil)
        }
    }
    func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) { log("connected; discovering services"); p.discoverServices(nil) }
    func centralManager(_ c: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) { log("connect failed: \(String(describing: error))") }
    func centralManager(_ c: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) { log("disconnected: \(String(describing: error))") }
    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        log("services: \((p.services ?? []).map(\.uuid.uuidString))")
        for s in p.services ?? [] where s.uuid == service { p.discoverCharacteristics(nil, for: s) }
        if !(p.services ?? []).contains(where: { $0.uuid == service }) { log("service 9400 absent") }
    }
    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error: Error?) {
        for ch in s.characteristics ?? [] {
            log("chara \(ch.uuid.uuidString) props \(ch.properties.rawValue)")
            if ch.uuid == chara { characteristic = ch; p.setNotifyValue(true, for: ch) }
        }
    }
    func peripheral(_ p: CBPeripheral, didUpdateNotificationStateFor ch: CBCharacteristic, error: Error?) {
        log("notify state \(ch.isNotifying) error \(String(describing: error)); mtu \(p.maximumWriteValueLength(for: .withoutResponse))")
        if ch.isNotifying { send(p) }
    }
    func send(_ p: CBPeripheral) {
        guard let ch = characteristic, round < 20 else { finish(); return }
        round += 1; sentAt = Date()
        let payload = Data("glassly-\(round)".utf8)
        p.writeValue(payload, for: ch, type: ch.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse)
    }
    func peripheral(_ p: CBPeripheral, didUpdateValueFor ch: CBCharacteristic, error: Error?) {
        let rtt = Date().timeIntervalSince(sentAt) * 1000; rtts.append(rtt)
        log(String(format: "echo %@ after %.1f ms", String(decoding: ch.value ?? Data(), as: UTF8.self), rtt))
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { self.send(p) }
    }
    func peripheral(_ p: CBPeripheral, didWriteValueFor ch: CBCharacteristic, error: Error?) { if let e = error { log("write error \(e)") } }
    func finish() {
        if !rtts.isEmpty { let s = rtts.sorted(); log(String(format: "echo RTT median %.1f ms, min %.1f, max %.1f over %d rounds", s[s.count/2], s[0], s[s.count-1], s.count)) }
        exit(rtts.isEmpty ? 1 : 0)
    }
}
let seconds = Double(CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "40") ?? 40
let hint = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "MemoMind"
let central = Central(seconds: seconds, nameHint: hint)
DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { central.log("timeout"); central.finish() }
RunLoop.main.run()
