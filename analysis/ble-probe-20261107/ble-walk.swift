// CoreBluetooth central: connect to the MemoMind and either walk every service's
// characteristics and descriptors (BLE_MODE=walk) or sit idle (BLE_MODE=idle),
// logging when the peripheral drops the link. Usage: ble-walk [seconds] [name-substring]
import CoreBluetooth
import Foundation
final class Walker: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let mode = ProcessInfo.processInfo.environment["BLE_MODE"] ?? "walk"
    let nameHint: String, deadline: Date
    var manager: CBCentralManager!, peripheral: CBPeripheral?, connectedAt = Date(), pending = 0
    init(seconds: Double, nameHint: String) { self.nameHint = nameHint; deadline = Date().addingTimeInterval(seconds); super.init(); manager = CBCentralManager(delegate: self, queue: nil) }
    func log(_ s: String) { print(String(format: "[%+.3f] ", Date().timeIntervalSince(connectedAt)) + s); fflush(stdout) }
    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        guard c.state == .poweredOn else { return }
        c.scanForPeripherals(withServices: nil, options: nil); log("scanning (\(mode))")
    }
    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        let name = p.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? "?"
        guard name.localizedCaseInsensitiveContains(nameHint), peripheral == nil else { return }
        log("found \(name) rssi \(rssi) adv \(advertisementData)"); peripheral = p; p.delegate = self; c.stopScan(); c.connect(p, options: nil)
    }
    func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) {
        connectedAt = Date(); log("connected")
        if mode == "walk" { p.discoverServices(nil) }
    }
    func centralManager(_ c: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) { log("DISCONNECTED \(String(describing: error))"); exit(0) }
    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        log("services \((p.services ?? []).map { "\($0.uuid.uuidString)\($0.isPrimary ? "" : "(secondary)")" }) error \(String(describing: error))")
        for s in p.services ?? [] { pending += 2; p.discoverIncludedServices(nil, for: s); p.discoverCharacteristics(nil, for: s) }
    }
    func peripheral(_ p: CBPeripheral, didDiscoverIncludedServicesFor s: CBService, error: Error?) {
        log("\(s.uuid.uuidString) includes \((s.includedServices ?? []).map(\.uuid.uuidString)) error \(String(describing: error))"); pending -= 1
    }
    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error: Error?) {
        log("\(s.uuid.uuidString) characteristics \((s.characteristics ?? []).map { "\($0.uuid.uuidString) props 0x\(String($0.properties.rawValue, radix: 16))" }) error \(String(describing: error))")
        pending -= 1
        for ch in s.characteristics ?? [] { pending += 1; p.discoverDescriptors(for: ch) }
    }
    func peripheral(_ p: CBPeripheral, didDiscoverDescriptorsFor ch: CBCharacteristic, error: Error?) {
        log("  \(ch.uuid.uuidString) descriptors \((ch.descriptors ?? []).map(\.uuid.uuidString)) error \(String(describing: error))"); pending -= 1
        if pending == 0 { log("walk complete; idling until the peripheral drops") }
    }
}
let args = CommandLine.arguments
let seconds = args.count > 1 ? Double(args[1]) ?? 30 : 30
let walker = Walker(seconds: seconds, nameHint: args.count > 2 ? args[2] : "MemoMind")
DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { walker.log("timeout"); exit(1) }
RunLoop.main.run()
