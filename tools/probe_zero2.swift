import Foundation
import CoreBluetooth

// Local, bounded GATT diagnostic. Only an explicitly selected peripheral can
// be connected. Modes that write FF13 values are explicit: keepalive, echo,
// buttons (A1 start after subscription; A0 stop before disconnect).
struct ButtonDecoder {
    // YC3121 Zero 2 user-confirmed ordered tap capture, 2026-11-05.
    // docs/evidence/buttons-probe-mapping.json; never import other devices' masks.
    static let mapping: [(UInt32, String)] = [
        (0x2000, "A"), (0x1000, "B"), (0x0010, "X"), (0x0020, "Y"),
        (0x0200, "Up"), (0x0100, "Down"), (0x0080, "Left"), (0x0040, "Right"),
        (0x0400, "L"), (0x0800, "R"), (0x0008, "Select"), (0x0001, "Start")]
    static func labels(_ mask: UInt32) -> [String] {
        mapping.filter { mask & $0.0 != 0 }.map { $0.1 }
    }
    var sequence: UInt8?
    var held: UInt32 = 0
    var snapshots = 0
    mutating func decode(_ data: Data) throws -> [String: Any] {
        let b = Array(data)
        func invalid() -> NSError {
            NSError(domain: "Zero2ButtonPacket", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Invalid v4 button packet or missing initial baseline"])
        }
        guard b.count == 8, b[0] == 0x47, b[1] == 4, b[3] & ~3 == 0 else { throw invalid() }
        let mask = UInt32(b[4]) | UInt32(b[5]) << 8 | UInt32(b[6]) << 16 | UInt32(b[7]) << 24
        let baseline = b[3] & 2 != 0
        guard mask & ~0x3ff9 == 0, !baseline || b[2] == 0,
              sequence != nil || baseline else { throw invalid() }
        let gap = sequence.map { b[2] != ($0 &+ 1) } ?? false
        let resync = baseline || gap || b[3] & 1 != 0
        let pressed = resync ? 0 : mask & ~held
        let released = resync ? 0 : held & ~mask
        sequence = b[2]; held = mask; snapshots += 1
        return ["sequence": Int(b[2]), "flags": Int(b[3]), "mask": mask,
                "mask_hex": String(format: "%04x", mask), "resync": resync,
                "sequence_gap": gap && !baseline, "pressed_mask": pressed, "released_mask": released,
                "held_buttons": Self.labels(mask), "pressed_buttons": Self.labels(pressed),
                "released_buttons": Self.labels(released)]
    }
}

func packetSelftest() {
    var decoder = ButtonDecoder()
    func packet(_ seq: UInt8, _ flags: UInt8, _ mask: UInt16) -> Data {
        Data([0x47, 4, seq, flags, UInt8(truncatingIfNeeded: mask), UInt8(mask >> 8), 0, 0])
    }
    let baseline = try! decoder.decode(packet(0, 2, 1))
    precondition(baseline["resync"] as! Bool && baseline["pressed_mask"] as! UInt32 == 0)
    let press = try! decoder.decode(packet(1, 0, 9))
    precondition(press["pressed_mask"] as! UInt32 == 8)
    precondition(press["pressed_buttons"] as! [String] == ["Select"])
    precondition(ButtonDecoder.labels(0x3000) == ["A", "B"])
    precondition(ButtonDecoder.mapping.reduce(UInt32(0)) { $0 | $1.0 } == 0x3ff9)
    precondition(ButtonDecoder.labels(1) == ["Start"])
    let release = try! decoder.decode(packet(2, 0, 0))
    precondition(release["released_mask"] as! UInt32 == 9)
    let overflow = try! decoder.decode(packet(3, 1, 1))
    precondition(overflow["resync"] as! Bool && overflow["pressed_mask"] as! UInt32 == 0)
    let gap = try! decoder.decode(packet(8, 0, 9))
    precondition(gap["sequence_gap"] as! Bool && gap["pressed_mask"] as! UInt32 == 0)
    decoder.sequence = 255
    let wrap = try! decoder.decode(packet(0, 0, 0))
    precondition(!(wrap["resync"] as! Bool))
    for bad in [Data(), Data([0x47,4]), packet(0,4,0), packet(0,0,2), packet(1,2,0)] {
        do { _ = try decoder.decode(bad); preconditionFailure("Malformed packet accepted") } catch {}
    }
    var fresh = ButtonDecoder()
    do { _ = try fresh.decode(packet(1,0,1)); preconditionFailure("Missing baseline accepted") } catch {}
    print("Button decoder baseline/press/release/overflow/gap/wrap/malformed checks passed (no Bluetooth)")
}
if Array(CommandLine.arguments.dropFirst()) == ["--packet-selftest"] { packetSelftest(); exit(0) }

let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 3, ["scan", "inspect", "subscribe", "cycle", "keepalive", "echo", "buttons"].contains(args[0]),
      let duration = Double(args[2]), duration.isFinite, (5...300).contains(duration),
      (args[0] == "scan" ? args[1] == "-" : UUID(uuidString: args[1]) != nil) else {
    fputs("Usage: probe_zero2 scan - SECONDS | inspect|subscribe|cycle|keepalive|echo|buttons UUID SECONDS\n", stderr)
    exit(64)
}

final class Probe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let mode: String
    let identifier: UUID?
    var central: CBCentralManager!
    var target: CBPeripheral?
    var seen = Set<UUID>()
    var servicesPending = 0
    var descriptorsPending = 0
    var discoveryComplete = false
    var subscribed = false
    var subscriptionTransitions = 0
    var keepaliveWrites = 0
    let echoValues: [UInt8] = [0x31, 0xa5, 0x00, 0xff]
    var echoIndex = 0
    var echoAck = false
    var echoSeen = false
    var echoOutstanding = false
    var buttonDecoder = ButtonDecoder()
    var buttonCharacteristic: CBCharacteristic?
    var buttonStartAcknowledged = false
    var buttonWrites: [UInt8] = []
    var buttonStopping = false
    var buttonStopResult: (Int32, String)?
    var notifications = 0
    var finished = false
    var connectedAt: Double?
    let started = ProcessInfo.processInfo.systemUptime

    init(mode: String, identifier: UUID?) {
        self.mode = mode
        self.identifier = identifier
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }
    func emit(_ event: String, _ fields: [String: Any] = [:]) {
        var record = fields
        record["event"] = event
        record["time"] = ISO8601DateFormatter().string(from: Date())
        record["elapsed_seconds"] = ProcessInfo.processInfo.systemUptime - started
        if let connectedAt = connectedAt {
            record["connected_seconds"] = ProcessInfo.processInfo.systemUptime - connectedAt
        }
        let data = try! JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        print(String(decoding: data, as: UTF8.self)); fflush(stdout)
    }
    func finish(_ code: Int32, _ reason: String) {
        guard !finished else { return }
        if mode == "buttons", !buttonStopping, let target = target,
           target.state == .connected, let characteristic = buttonCharacteristic {
            buttonStopping = true
            buttonStopResult = (code, reason)
            emit("button_stop_requested", ["hex": "a0"])
            buttonWrites.append(0xa0)
            target.writeValue(Data([0xa0]), for: characteristic, type: .withResponse)
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                if !self.finished { self.finish(1, "Button stop acknowledgement timed out") }
            }
            return
        }
        finished = true
        central.stopScan()
        emit("complete", ["exit_code": code, "reason": reason, "candidates": seen.count,
                          "discovery_complete": discoveryComplete, "subscribed": subscribed,
                          "notifications": notifications, "subscription_transitions": subscriptionTransitions,
                          "keepalive_writes_acknowledged": keepaliveWrites, "echoes_verified": echoIndex, "button_snapshots": buttonDecoder.snapshots,
                          "button_start_acknowledged": buttonStartAcknowledged])
        if let target = target { central.cancelPeripheralConnection(target) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { exit(code) }
    }
    func deadline() {
        let success = mode == "buttons" ? subscribed && discoveryComplete && buttonStartAcknowledged && buttonDecoder.snapshots > 0 :
            mode == "echo" ? false : mode == "keepalive" ? subscribed && discoveryComplete && keepaliveWrites > 0 :
            mode == "cycle" ? false : mode == "scan" ? !seen.isEmpty :
            (mode == "inspect" ? discoveryComplete : subscribed && discoveryComplete)
        finish(success ? 0 : 3, "Time limit; notification count is separate from subscription success")
    }
    func check(_ error: Error?) -> Bool {
        guard !finished else { return false }
        if let error = error { finish(1, error.localizedDescription); return false }
        return true
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard !finished else { return }
        emit("bluetooth_state", ["state": central.state.rawValue,
                                 "authorization": CBManager.authorization.rawValue])
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: nil, options: nil)
        } else if [.unauthorized, .unsupported, .poweredOff].contains(central.state) {
            finish(2, "Bluetooth unavailable")
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData ad: [String: Any], rssi RSSI: NSNumber) {
        guard !finished, target == nil else { return }
        let localName = ad[CBAdvertisementDataLocalNameKey] as? String ?? ""
        let cachedName = peripheral.name ?? ""
        // Startup passes "80EL" plus NUL padding to command 04, independently
        // of the USB/classic model-name pointer. This is a candidate, not ID proof.
        let names = [localName, cachedName].map { $0.trimmingCharacters(in: .controlCharacters) }
        let candidate = names.contains {
            $0 == "80EL" || $0.lowercased().replacingOccurrences(of: " ", with: "").contains("zero2")
        } || (ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).contains(CBUUID(string: "FF10"))
        guard identifier.map({ $0 == peripheral.identifier }) ?? candidate else { return }
        if seen.insert(peripheral.identifier).inserted {
            emit("advertisement", ["identifier": peripheral.identifier.uuidString,
                "local_name": localName, "cached_name": cachedName, "rssi": RSSI,
                "connectable": ad[CBAdvertisementDataIsConnectable] as? NSNumber ?? false,
                "services": (ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString },
                "manufacturer_hex": (ad[CBAdvertisementDataManufacturerDataKey] as? Data ?? Data()).hex])
        }
        guard mode != "scan" else { return }
        target = peripheral
        peripheral.delegate = self
        central.stopScan()
        emit("connecting", ["identifier": peripheral.identifier.uuidString])
        central.connect(peripheral)
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        guard !finished else { return }
        connectedAt = ProcessInfo.processInfo.systemUptime
        emit("connected")
        peripheral.discoverServices(nil)
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        finish(1, error?.localizedDescription ?? "Connection failed")
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        guard !finished else { return }
        emit("disconnected", ["error": error?.localizedDescription ?? "none"])
        finish(1, "Peripheral disconnected before capture ended")
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard check(error) else { return }
        let services = peripheral.services ?? []
        servicesPending = services.count
        for service in services {
            emit("service", ["uuid": service.uuid.uuidString, "primary": service.isPrimary])
            peripheral.discoverCharacteristics(nil, for: service)
        }
        if services.isEmpty { finish(1, "No services returned") }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard check(error) else { return }
        for characteristic in service.characteristics ?? [] {
            emit("characteristic", ["service": service.uuid.uuidString, "uuid": characteristic.uuid.uuidString,
                                    "properties": characteristic.properties.rawValue])
            descriptorsPending += 1
            peripheral.discoverDescriptors(for: characteristic)
            if ["subscribe", "cycle", "keepalive", "echo", "buttons"].contains(mode), service.uuid == CBUUID(string: "FF10"),
               characteristic.uuid == CBUUID(string: "FF13"), characteristic.properties.contains(.notify) {
                emit("subscription_requested", ["service": "FF10", "uuid": "FF13"])
                peripheral.setNotifyValue(true, for: characteristic)
            }
        }
        servicesPending -= 1
        completeDiscovery()
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverDescriptorsFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        emit("descriptors", ["service": characteristic.service?.uuid.uuidString ?? "",
             "characteristic": characteristic.uuid.uuidString,
             "uuids": (characteristic.descriptors ?? []).map { $0.uuid.uuidString }])
        descriptorsPending -= 1
        completeDiscovery()
    }
    func completeDiscovery() {
        if servicesPending == 0 && descriptorsPending == 0 && !discoveryComplete {
            discoveryComplete = true
            emit("discovery_complete")
            if mode == "inspect" { finish(0, "GATT discovery finished") }
        }
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        subscribed = characteristic.isNotifying
        subscriptionTransitions += 1
        emit("subscription", ["uuid": characteristic.uuid.uuidString, "enabled": subscribed])
        if mode == "keepalive" && subscriptionTransitions == 1 && subscribed {
            keepalive(peripheral, characteristic)
        }
        if mode == "echo" && subscriptionTransitions == 1 && subscribed {
            sendEcho(peripheral, characteristic)
        }
        if mode == "buttons" && subscriptionTransitions == 1 && subscribed {
            guard characteristic.properties.contains(.write) else { finish(1, "FF13 is not writable"); return }
            buttonCharacteristic = characteristic
            emit("button_start_requested", ["hex": "a1"])
            buttonWrites.append(0xa1)
            peripheral.writeValue(Data([0xa1]), for: characteristic, type: .withResponse)
        }
        if mode == "cycle" {
            let expected = subscriptionTransitions != 2
            guard subscriptionTransitions <= 3 && subscribed == expected else {
                finish(1, "Unexpected subscription transition"); return
            }
            let phase = subscriptionTransitions
            DispatchQueue.main.asyncAfter(deadline: .now() + (phase == 3 ? 5 : 3)) {
                guard !self.finished else { return }
                if phase == 3 {
                    self.finish(self.discoveryComplete ? 0 : 3, "Subscribed, unsubscribed, resubscribed; final hold complete")
                } else {
                    let enable = phase == 2
                    self.emit("subscription_requested", ["uuid": characteristic.uuid.uuidString, "enabled": enable])
                    peripheral.setNotifyValue(enable, for: characteristic)
                }
            }
        }
    }
    func keepalive(_ peripheral: CBPeripheral, _ characteristic: CBCharacteristic) {
        guard !finished else { return }
        guard characteristic.service?.uuid == CBUUID(string: "FF10"),
              characteristic.uuid == CBUUID(string: "FF13"), characteristic.properties.contains(.write),
              characteristic.isNotifying, peripheral.state == .connected else {
            finish(1, "Keepalive target/state mismatch"); return
        }
        emit("keepalive_write_requested", ["uuid": characteristic.uuid.uuidString, "hex": "00"])
        peripheral.writeValue(Data([0]), for: characteristic, type: .withResponse)
    }
    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        if mode == "buttons" {
            guard characteristic === buttonCharacteristic, !buttonWrites.isEmpty else {
                finish(1, "Unexpected button control acknowledgement"); return
            }
            let command = buttonWrites.removeFirst()
            if command == 0xa0, let result = buttonStopResult {
                emit("button_stop_acknowledged")
                finish(result.0, result.1)
            } else {
                buttonStartAcknowledged = true
                emit("button_start_acknowledged")
            }
            return
        }
        if mode == "echo" {
            echoAck = true
            emit("echo_write_acknowledged", ["index": echoIndex])
            advanceEcho(peripheral, characteristic)
            return
        }
        guard mode == "keepalive" else { finish(1, "Unexpected value-write callback"); return }
        keepaliveWrites += 1
        emit("keepalive_write_acknowledged", ["uuid": characteristic.uuid.uuidString, "count": keepaliveWrites])
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { self.keepalive(peripheral, characteristic) }
    }
    func sendEcho(_ peripheral: CBPeripheral, _ characteristic: CBCharacteristic) {
        guard !finished, !echoOutstanding, echoIndex < echoValues.count else { return }
        guard characteristic.service?.uuid == CBUUID(string: "FF10"),
              characteristic.uuid == CBUUID(string: "FF13"), characteristic.properties.contains(.write),
              characteristic.isNotifying else { finish(1, "Echo target/state mismatch"); return }
        echoAck = false; echoSeen = false; echoOutstanding = true
        let value = Data([echoValues[echoIndex]])
        emit("echo_write_requested", ["index": echoIndex, "hex": value.hex])
        peripheral.writeValue(value, for: characteristic, type: .withResponse)
    }
    func advanceEcho(_ peripheral: CBPeripheral, _ characteristic: CBCharacteristic) {
        guard echoOutstanding && echoAck && echoSeen else { return }
        echoOutstanding = false
        emit("echo_verified", ["index": echoIndex, "hex": Data([echoValues[echoIndex]]).hex])
        echoIndex += 1
        if echoIndex == echoValues.count {
            finish(0, "All four notification echoes and write acknowledgements verified")
        } else {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.sendEcho(peripheral, characteristic) }
        }
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard check(error) else { return }
        notifications += 1
        emit("notification", ["service": characteristic.service?.uuid.uuidString ?? "",
                              "uuid": characteristic.uuid.uuidString, "hex": (characteristic.value ?? Data()).hex])
        if mode == "echo" {
            guard echoOutstanding, echoIndex < echoValues.count,
                  characteristic.uuid == CBUUID(string: "FF13"),
                  characteristic.value == Data([echoValues[echoIndex]]) else {
                finish(1, "Unexpected notification during echo test"); return
            }
            echoSeen = true
            advanceEcho(peripheral, characteristic)
        }
        if mode == "buttons" {
            guard characteristic.service?.uuid == CBUUID(string: "FF10"), characteristic.uuid == CBUUID(string: "FF13") else {
                finish(1, "Unexpected button notification characteristic"); return
            }
            do { emit("button_snapshot", try buttonDecoder.decode(characteristic.value ?? Data())) }
            catch { finish(1, error.localizedDescription); return }
        }
        if notifications >= 512 { finish(0, "512-notification capture limit") }
    }
}
extension Data {
    var hex: String { map { String(format: "%02x", $0) }.joined() }
}
let probe = Probe(mode: args[0], identifier: UUID(uuidString: args[1]))
DispatchQueue.main.asyncAfter(deadline: .now() + duration) { probe.deadline() }
RunLoop.main.run()
