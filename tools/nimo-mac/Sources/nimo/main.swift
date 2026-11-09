import CoreBluetooth
import Foundation

/// `nimo scan [seconds]` lists NIMO peripherals.
/// `nimo probe [--name N] [--output DIR]` connects, runs the stock handshake and reads
/// version, battery and screen info.
/// `nimo layout [--name N] [--seconds S] [--output DIR]` also launches the Dynamic Layout
/// page, shows the vendor's golden frame for S seconds and exits it.
/// Every frame in and out is saved as JSON evidence under --output (default captures/).

let service = CBUUID(string: "7033")
let txUUID = CBUUID(string: "2021")
let rxUUID = CBUUID(string: "2022")

struct Options {
    var command = "probe"
    var name: String?
    var seconds = 15.0
    var output = "captures"
}

func parse() -> Options {
    var o = Options()
    var args = Array(CommandLine.arguments.dropFirst())
    if let first = args.first, !first.hasPrefix("--") { o.command = first; args.removeFirst() }
    var i = 0
    while i < args.count {
        switch args[i] {
        case "--name": o.name = args[i + 1]; i += 2
        case "--seconds": o.seconds = Double(args[i + 1]) ?? o.seconds; i += 2
        case "--output": o.output = args[i + 1]; i += 2
        default:
            if o.command == "scan", let s = Double(args[i]) { o.seconds = s }
            i += 1
        }
    }
    return o
}

func log(_ s: String) {
    let t = ISO8601DateFormatter().string(from: Date())
    print("\(t) \(s)")
    fflush(stdout)
}

final class Session: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let options: Options
    let queue = DispatchQueue(label: "nimo.ble")
    var central: CBCentralManager!
    var peripheral: CBPeripheral?
    var tx: CBCharacteristic?
    let assembler = Wire.Assembler()
    var trace: [[String: Any]] = []
    var seen: Set<UUID> = []
    var waiters: [UInt16: (Wire.Message) -> Void] = [:]
    var reportWaiters: [UInt8: (Wire.Message) -> Void] = [:]
    var twsConnected = false
    var writes: [Data] = []
    var writing = false

    init(options: Options) {
        self.options = options
        super.init()
        central = CBCentralManager(delegate: self, queue: queue)
    }

    func record(_ dir: String, _ bytes: Data) {
        trace.append(["t": Date().timeIntervalSince1970, "dir": dir, "hex": bytes.hex])
    }

    // MARK: scanning

    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        log("bluetooth state \(c.state.rawValue)")
        guard c.state == .poweredOn else { return }
        // A classic-paired, system-connected NIMO exposes its GATT over BR/EDR without advertising.
        for p in c.retrieveConnectedPeripherals(withServices: [service]) {
            log("system-connected peripheral \(p.name ?? "?") id \(p.identifier)")
            if options.command != "scan", peripheral == nil {
                peripheral = p
                p.delegate = self
                c.connect(p, options: nil)
                return
            }
        }
        c.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        log("scanning for nimo* (not *_ble unless named with --name)")
    }

    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData ad: [String: Any], rssi: NSNumber) {
        let name = (ad[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        guard name.lowercased().hasPrefix("nimo"), !seen.contains(p.identifier) else { return }
        seen.insert(p.identifier)
        let services = (ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID])?.map(\.uuidString) ?? []
        log("found \(name) rssi \(rssi) id \(p.identifier) services \(services)")
        guard options.command != "scan", peripheral == nil else { return }
        if let want = options.name {
            if want.lowercased() != name.lowercased() { return }
        } else if name.lowercased().hasSuffix("_ble") {
            return
        }
        c.stopScan()
        peripheral = p
        p.delegate = self
        log("connecting \(name)")
        c.connect(p, options: nil)
    }

    func centralManager(_: CBCentralManager, didConnect p: CBPeripheral) {
        log("connected; discovering 7033")
        p.discoverServices(nil)
    }

    func centralManager(_: CBCentralManager, didFailToConnect _: CBPeripheral, error: Error?) {
        log("connect failed: \(error?.localizedDescription ?? "?")"); finish(1)
    }

    func centralManager(_: CBCentralManager, didDisconnectPeripheral _: CBPeripheral, error: Error?) {
        log("disconnected: \(error?.localizedDescription ?? "clean")"); finish(error == nil ? 0 : 2)
    }

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        log("services \(p.services?.map(\.uuid.uuidString) ?? [])")
        guard let s = p.services?.first(where: { $0.uuid == service }) else {
            log("no 7033 service \(error?.localizedDescription ?? "")"); finish(3); return
        }
        p.discoverCharacteristics(nil, for: s)
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error _: Error?) {
        for c in s.characteristics ?? [] {
            log("characteristic \(c.uuid) props \(c.properties.rawValue)")
            if c.uuid == txUUID { tx = c }
            if c.uuid == rxUUID { p.setNotifyValue(true, for: c) }
        }
        log("mtu withResponse \(p.maximumWriteValueLength(for: .withResponse)) withoutResponse \(p.maximumWriteValueLength(for: .withoutResponse))")
    }

    func peripheral(_: CBPeripheral, didUpdateNotificationStateFor c: CBCharacteristic, error: Error?) {
        if let error { log("notify failed: \(error.localizedDescription)"); finish(4); return }
        guard c.uuid == rxUUID else { return }
        log("rx notifications on")
        Task { await self.run() }
    }

    func peripheral(_: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error _: Error?) {
        guard let v = c.value else { return }
        record("rx", v)
        guard let m = assembler.ingest(v) else { return }
        if m.isReport {
            describeReport(m)
            reportWaiters[m.key]?(m)
        } else {
            let k = UInt16(m.cmd) << 8 | UInt16(m.key)
            if let w = waiters.removeValue(forKey: k) { w(m) } else { log("unsolicited reply \(m.cmd)/\(m.key) status \(m.status) \(m.data.hex)") }
        }
    }

    func peripheral(_: CBPeripheral, didWriteValueFor _: CBCharacteristic, error: Error?) {
        if let error { log("write error \(error.localizedDescription)") }
        queue.asyncAfter(deadline: .now() + .milliseconds(5)) { self.writing = false; self.drain() }
    }

    func describeReport(_ m: Wire.Message) {
        let d = m.data
        switch m.key {
        case 0x01: log("input event \(d.first.map { String(format: "0x%02X", $0) } ?? "")")
        case 0x02: log("app state appId \(d.count > 0 ? Int(d[0]) : -1) phase \(d.count > 1 ? Int(d[1]) : -1)")
        case 0x03:
            twsConnected = (d.first ?? 0) >= 1
            log("tws report \(twsConnected)")
        case 0x04:
            if d.first == 0x03, d.count >= 11 { twsConnected = d[9] >= 1; log("heartbeat tws \(twsConnected) raw \(d.hex)") }
            else if d.first == 0x05, d.count >= 5 { log("battery L\(d[1]) R\(d[2]) charging \(d[3]) \(d[4])") }
            else { log("business report \(d.hex)") }
        default: log("report key \(m.key) \(d.hex)")
        }
    }

    // MARK: writing

    func send(_ frames: [Data]) {
        queue.async { self.writes.append(contentsOf: frames); self.drain() }
    }

    func drain() {
        guard !writing, let p = peripheral, let tx, !writes.isEmpty else { return }
        writing = true
        let f = writes.removeFirst()
        record("tx", f)
        p.writeValue(f, for: tx, type: .withResponse)
    }

    func request(_ cmd: UInt8, _ key: UInt8, _ payload: Data = Data(), timeout: Double = 3) async -> Wire.Message? {
        await withCheckedContinuation { cont in
            queue.async {
                var done = false
                let k = UInt16(cmd) << 8 | UInt16(key)
                self.waiters[k] = { m in if !done { done = true; cont.resume(returning: m) } }
                self.queue.asyncAfter(deadline: .now() + timeout) {
                    if !done { done = true; self.waiters[k] = nil; cont.resume(returning: nil) }
                }
                self.send(Wire.frames(cmd: cmd, key: key, payload: payload))
            }
        }
    }

    func waitTws(timeout: Double) async -> Bool {
        if twsConnected { return true }
        if let r = await request(0x02, 0x16), r.status == 0, (r.data.first ?? 0) >= 1 { twsConnected = true; return true }
        return await withCheckedContinuation { cont in
            queue.async {
                var done = false
                self.reportWaiters[0x03] = { _ in if !done, self.twsConnected { done = true; cont.resume(returning: true) } }
                self.queue.asyncAfter(deadline: .now() + timeout) { if !done { done = true; cont.resume(returning: self.twsConnected) } }
            }
        }
    }

    // MARK: the probe

    var results: [String: Any] = [:]

    func run() async {
        log("waiting for the TWS link (glasses on, both arms)")
        let tws = await waitTws(timeout: 10)
        results["tws"] = tws
        log("tws \(tws)")
        let time = await request(0x03, 0x01, Wire.deviceTime())
        log("setTime status \(time.map { String($0.status) } ?? "timeout")")
        results["setTime"] = time?.status ?? -1
        let queries: [(String, UInt8, (Data) -> Any)] = [
            ("version", 0x0A, { Decode.version($0) ?? $0.hex }),
            ("versionDetail", 0x0B, { Decode.text($0) }),
            ("battery", 0x06, { $0.hex }),
            ("screenInfo", 0x07, { Decode.screenInfo($0) ?? $0.hex }),
            ("brightness", 0x02, { $0.hex }),
            ("heightLevel", 0x17, { $0.hex }),
            ("currentAppId", 0x14, { $0.hex }),
            ("tws", 0x16, { $0.hex }),
        ]
        for (name, key, decode) in queries {
            if let r = await request(0x02, key) {
                let value: Any = r.status == 0 ? decode(r.data) : "status \(r.status)"
                results[name] = value
                log("\(name): \(value)")
            } else {
                results[name] = "timeout"
                log("\(name): timeout")
            }
        }
        if options.command == "layout" {
            await layoutTest()
        }
        finish(0)
    }

    func layoutTest() async {
        let launch = await request(0x07, 0x01, Data([Golden.appId, 0]), timeout: 5)
        log("launch 0xFD: \(launch.map { "status \($0.status) \($0.data.hex)" } ?? "timeout")")
        results["layoutLaunch"] = launch.map { Int($0.status) } ?? -1
        guard launch?.status == 0 else { return }
        try? await Task.sleep(nanoseconds: 500_000_000)
        var payload = Data([Golden.appId, 0, 0, 0])
        payload.append(Golden.frame)
        let update = await request(0x07, 0x04, payload, timeout: 5)
        log("update: \(update.map { "status \($0.status) \($0.data.hex)" } ?? "timeout")")
        results["layoutUpdate"] = update.map { Int($0.status) } ?? -1
        log("holding the frame for \(options.seconds)s; tap the arms to see input events")
        try? await Task.sleep(nanoseconds: UInt64(options.seconds * 1_000_000_000))
        let exit = await request(0x07, 0x03, Data([Golden.appId]), timeout: 5)
        log("exit: \(exit.map { "status \($0.status) \($0.data.hex)" } ?? "timeout")")
        results["layoutExit"] = exit.map { Int($0.status) } ?? -1
    }

    func finish(_ code: Int32) {
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let dir = URL(fileURLWithPath: options.output).appendingPathComponent("nimo-\(options.command)-\(stamp)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let doc: [String: Any] = ["command": options.command, "peripheral": peripheral?.name ?? "", "results": results, "trace": trace]
        if let data = try? JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: dir.appendingPathComponent("session.json"))
            log("saved \(dir.path)/session.json (\(trace.count) frames)")
        }
        if let p = peripheral, p.state == .connected, code == 0, central.delegate != nil {
            central.delegate = nil
            central.cancelPeripheralConnection(p)
        }
        exit(code)
    }
}

let options = parse()
let session = Session(options: options)
if options.command == "scan" {
    DispatchQueue.main.asyncAfter(deadline: .now() + options.seconds) { log("scan done"); exit(0) }
} else {
    DispatchQueue.main.asyncAfter(deadline: .now() + 90) { log("timed out"); session.finish(5) }
}
RunLoop.main.run()
