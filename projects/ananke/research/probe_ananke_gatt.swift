import Foundation
import CoreBluetooth

// Exact discovered peripheral only. GATT discovery and vendor notification
// subscription; no characteristic writes, firmware updates, or protocol probes.
guard (2...3).contains(CommandLine.arguments.count), let targetID = UUID(uuidString: CommandLine.arguments[1]) else {
    fputs("Usage: probe-ananke-gatt <observed peripheral UUID> [seconds: 10...180]\n", stderr)
    exit(64)
}
let duration = CommandLine.arguments.count == 3 ? Double(CommandLine.arguments[2]) ?? 0 : 90
guard (10...180).contains(duration) else { exit(64) }
// Keep command-line capture latency from being distorted by App Nap. This is
// a Mac measurement aid, not evidence of iOS background delivery.
let activity = ProcessInfo.processInfo.beginActivity(options: [.userInitiatedAllowingIdleSystemSleep, .latencyCritical],
                                                    reason: "Measure controller notification timing")
final class Probe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let targetID: UUID
    var central: CBCentralManager!
    var target: CBPeripheral?
    var notificationCount = 0
    var subscribed = Set<String>()
    var finished = false
    init(targetID: UUID) {
        self.targetID = targetID
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }
    func emit(_ value: [String: Any]) {
        var record = value
        record["time"] = ISO8601DateFormatter().string(from: Date())
        record["uptime_seconds"] = ProcessInfo.processInfo.systemUptime
        if let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
           let line = String(data: data, encoding: .utf8) {
            print(line); fflush(stdout)
        }
    }
    func finish(_ code: Int32, _ reason: String) {
        guard !finished else { return }
        finished = true
        central.stopScan()
        if let peripheral = target { central.cancelPeripheralConnection(peripheral) }
        emit(["event": "complete", "reason": reason, "notifications": notificationCount,
              "subscribed": Array(subscribed).sorted()])
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { exit(code) }
    }
    func check(_ error: Error?) -> Bool {
        if let error = error { finish(1, error.localizedDescription); return false }
        return !finished
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        emit(["event": "state", "state": central.state.rawValue,
              "authorization": CBManager.authorization.rawValue])
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: nil, options: nil)
        } else if central.state == .unauthorized || central.state == .unsupported || central.state == .poweredOff {
            finish(2, "Bluetooth unavailable")
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard target == nil, peripheral.identifier == targetID else { return }
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? peripheral.name ?? ""
        guard name == "IG05 Gamepad(BLE)" else { finish(1, "Target name mismatch"); return }
        target = peripheral
        peripheral.delegate = self
        central.stopScan()
        emit(["event": "connecting", "name": name, "identifier": peripheral.identifier.uuidString])
        central.connect(peripheral)
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        emit(["event": "connected"])
        peripheral.discoverServices(nil)
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        finish(1, error?.localizedDescription ?? "Connection failed")
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        if !finished { finish(1, error?.localizedDescription ?? "Disconnected") }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard check(error) else { return }
        for service in peripheral.services ?? [] {
            emit(["event": "service", "uuid": service.uuid.uuidString])
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard check(error) else { return }
        for characteristic in service.characteristics ?? [] {
            let serviceID = service.uuid.uuidString.uppercased()
            let charID = characteristic.uuid.uuidString.uppercased()
            emit(["event": "characteristic", "service": serviceID, "uuid": charID,
                  "properties": characteristic.properties.rawValue])
            if ((serviceID == "AE40" && charID == "AE42") ||
                (serviceID == "AE00" && charID == "AE02")) && characteristic.properties.contains(.notify) {
                peripheral.setNotifyValue(true, for: characteristic)
            }
        }
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        if characteristic.isNotifying { subscribed.insert(characteristic.uuid.uuidString) }
        emit(["event": "subscription", "uuid": characteristic.uuid.uuidString,
              "enabled": characteristic.isNotifying])
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        notificationCount += 1
        emit(["event": "notification", "uuid": characteristic.uuid.uuidString,
              "hex": (characteristic.value ?? Data()).map { String(format: "%02x", $0) }.joined()])
        if notificationCount >= 512 { finish(0, "Notification limit reached") }
    }
}
let probe = Probe(targetID: targetID)
DispatchQueue.main.asyncAfter(deadline: .now() + duration) { probe.finish(0, "\(duration)-second limit") }
RunLoop.main.run()
