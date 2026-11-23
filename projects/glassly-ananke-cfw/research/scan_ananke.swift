import Foundation
import CoreBluetooth

// Advertisement-only discovery: no connection, GATT access, or writes.
// Names are candidates, never sufficient identity for an automatic connection.
final class Scanner: NSObject, CBCentralManagerDelegate {
    var central: CBCentralManager!
    var seen = Set<UUID>()
    var candidates = 0
    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }
    func emit(_ record: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
           let line = String(data: data, encoding: .utf8) {
            print(line)
            fflush(stdout)
        }
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        emit(["event": "state", "state": central.state.rawValue,
              "authorization": CBManager.authorization.rawValue])
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        } else if central.state == .unauthorized || central.state == .unsupported {
            exit(2)
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard seen.insert(peripheral.identifier).inserted else { return }
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? peripheral.name ?? ""
        let services = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString }
        let words = ["ig05", "ananke", "iine", "controller", "joy-con", "xbox", "gamepad"]
        guard words.contains(where: { name.localizedCaseInsensitiveContains($0) }) ||
                services.contains(where: { ["AE40", "AE00"].contains($0.uppercased()) }) else { return }
        candidates += 1
        emit(["event": "candidate", "identifier": peripheral.identifier.uuidString,
              "name": name, "rssi": RSSI, "services": services,
              "connectable": advertisementData[CBAdvertisementDataIsConnectable] as? Bool ?? false])
    }
}
let scanner = Scanner()
DispatchQueue.main.asyncAfter(deadline: .now() + 40) {
    scanner.central.stopScan()
    scanner.emit(["event": "complete", "candidate_count": scanner.candidates,
                  "total_advertisers_seen": scanner.seen.count,
                  "scope": "BLE advertisements only; absence does not establish Bluetooth Classic or lack of GATT"])
    exit(0)
}
RunLoop.main.run()
