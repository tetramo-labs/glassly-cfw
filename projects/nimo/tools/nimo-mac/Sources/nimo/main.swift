import CoreBluetooth
import Foundation
import IOBluetooth

/// `nimo scan [seconds]`   list NIMO peripherals advertising over LE (only the `_BLE` companion does).
/// `nimo sdp`              dump the paired NIMO's classic service records.
/// `nimo probe`            over the classic ATT bearer: handshake, version, battery, screen info.
/// `nimo layout [--seconds S]`  probe, then show the vendor's golden Dynamic Layout frame for S seconds.
/// Options: --name Nimo-XXXX, --output DIR (default captures/). Every frame is saved as JSON evidence.
/// The Mac must already be paired with `Nimo-XXXX` (System Settings > Bluetooth).

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
    print("\(ISO8601DateFormatter().string(from: Date())) \(s)")
    fflush(stdout)
}

// MARK: - LE scan (diagnostic only)

final class Scanner: NSObject, CBCentralManagerDelegate {
    var central: CBCentralManager!
    var seen: Set<UUID> = []
    override init() { super.init(); central = CBCentralManager(delegate: self, queue: nil) }
    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        guard c.state == .poweredOn else { log("bluetooth state \(c.state.rawValue)"); return }
        c.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        log("scanning")
    }
    func centralManager(_: CBCentralManager, didDiscover p: CBPeripheral, advertisementData ad: [String: Any], rssi: NSNumber) {
        let name = (ad[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        guard name.lowercased().hasPrefix("nimo"), !seen.contains(p.identifier) else { return }
        seen.insert(p.identifier)
        log("found \(name) rssi \(rssi) id \(p.identifier) services \((ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID])?.map(\.uuidString) ?? [])")
    }
}

// MARK: - classic device

func pairedNimo(named want: String?) -> IOBluetoothDevice? {
    let devices = (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []).filter {
        let n = ($0.name ?? "").lowercased()
        return n.hasPrefix("nimo") && !n.hasSuffix("_ble") && (want == nil || n == want!.lowercased())
    }
    return devices.first { $0.isConnected() } ?? devices.first
}

func dumpSDP(_ dev: IOBluetoothDevice) {
    final class D: NSObject { let s = DispatchSemaphore(value: 0)
        @objc func sdpQueryComplete(_: IOBluetoothDevice, status: IOReturn) { s.signal() } }
    let d = D()
    dev.performSDPQuery(d)
    _ = d.s.wait(timeout: .now() + 20)
    for rec in dev.services as? [IOBluetoothSDPServiceRecord] ?? [] {
        print("record:")
        for (k, v) in rec.attributes as? [NSNumber: IOBluetoothSDPDataElement] ?? [:] {
            print("  attr 0x\(String(k.intValue, radix: 16)): \(v)")
        }
    }
}

// MARK: - probe session over ATT

final class Probe {
    let options: Options
    let link: AttLink
    let assembler = Wire.Assembler()
    var trace: [[String: Any]] = []
    var results: [String: Any] = [:]
    var waiters: [UInt16: (Wire.Message) -> Void] = [:]
    var twsWaiter: (() -> Void)?
    var twsConnected = false
    var txHandle: UInt16 = 0
    var chunk = Wire.chunk

    init(options: Options, device: IOBluetoothDevice) {
        self.options = options
        link = AttLink(device: device)
        link.log = log
        link.onTraffic = { [weak self] dir, pdu in self?.trace.append(["t": Date().timeIntervalSince1970, "dir": dir, "hex": pdu.hex]) }
        link.onNotify = { [weak self] handle, value in self?.incoming(handle, value) }
    }

    func connect() async throws {
        try await link.exchangeMTU()
        chunk = min(Wire.chunk, link.mtu - 3 - 8)
        let services = try await link.services()
        for s in services { log("service \(s.uuid.hex) handles \(s.start)...\(s.end)") }
        guard let main = services.first(where: { $0.uuid.count == 2 && $0.uuid[0] == 0x33 && $0.uuid[1] == 0x70 }) else {
            throw AttLink.Failure.notFound("service 7033")
        }
        let chars = try await link.characteristics(start: main.start, end: main.end)
        for c in chars { log("characteristic \(c.uuid.hex) value \(c.value) props \(String(format: "0x%02X", c.properties))") }
        guard let tx = chars.first(where: { $0.uuid16 == 0x2021 }), let rx = chars.first(where: { $0.uuid16 == 0x2022 }) else {
            throw AttLink.Failure.notFound("2021/2022")
        }
        txHandle = tx.value
        let cccd = try await link.cccd(after: rx.value, end: main.end)
        try await link.write(handle: cccd, value: Data([1, 0]))
        log("rx notifications on (cccd \(cccd))")
    }

    func incoming(_: UInt16, _ packet: Data) {
        guard let m = assembler.ingest(packet) else { return }
        if m.isReport {
            describeReport(m)
        } else {
            let k = UInt16(m.cmd) << 8 | UInt16(m.key)
            if let w = waiters.removeValue(forKey: k) { w(m) } else { log("unsolicited reply \(m.cmd)/\(m.key) status \(m.status) \(m.data.hex)") }
        }
    }

    func describeReport(_ m: Wire.Message) {
        let d = m.data
        switch m.key {
        case 0x01: log("input event \(d.first.map { String(format: "0x%02X", $0) } ?? "")")
        case 0x02: log("app state appId \(d.count > 0 ? Int(d[0]) : -1) phase \(d.count > 1 ? Int(d[1]) : -1)")
        case 0x03:
            twsConnected = (d.first ?? 0) >= 1
            log("tws report \(twsConnected)")
            if twsConnected { twsWaiter?() }
        case 0x04:
            if d.first == 0x03, d.count >= 11 {
                twsConnected = d[9] >= 1
                log("heartbeat tws \(twsConnected) raw \(d.hex)")
                if twsConnected { twsWaiter?() }
            } else if d.first == 0x05, d.count >= 5 {
                log("battery L\(d[1]) R\(d[2]) charging \(d[3]) \(d[4])")
            } else { log("business report \(d.hex)") }
        default: log("report key \(m.key) \(d.hex)")
        }
    }

    func send(cmd: UInt8, key: UInt8, payload: Data = Data()) async throws {
        for f in Wire.frames(cmd: cmd, key: key, payload: payload, chunk: chunk) {
            try await link.write(handle: txHandle, value: f)
        }
    }

    func request(_ cmd: UInt8, _ key: UInt8, _ payload: Data = Data(), timeout: Double = 3) async -> Wire.Message? {
        let k = UInt16(cmd) << 8 | UInt16(key)
        return await withCheckedContinuation { cont in
            var done = false
            DispatchQueue.main.async {
                self.waiters[k] = { m in if !done { done = true; cont.resume(returning: m) } }
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    if !done { done = true; self.waiters[k] = nil; cont.resume(returning: nil) }
                }
                Task {
                    do { try await self.send(cmd: cmd, key: key, payload: payload) }
                    catch { log("send failed: \(error)"); if !done { done = true; self.waiters[k] = nil; cont.resume(returning: nil) } }
                }
            }
        }
    }

    func waitTws(timeout: Double) async -> Bool {
        if let r = await request(0x02, 0x16), r.status == 0, (r.data.first ?? 0) >= 1 { twsConnected = true }
        if twsConnected { return true }
        return await withCheckedContinuation { cont in
            var done = false
            DispatchQueue.main.async {
                self.twsWaiter = { if !done { done = true; cont.resume(returning: true) } }
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { if !done { done = true; cont.resume(returning: self.twsConnected) } }
            }
        }
    }

    func run() async -> Int32 {
        do { try await connect() } catch { log("connect failed: \(error)"); return 2 }
        log("waiting for the TWS link (glasses on, both arms)")
        let tws = await waitTws(timeout: 10)
        results["tws"] = tws
        log("tws \(tws)")
        let time = await request(0x03, 0x01, Wire.deviceTime())
        log("setTime status \(time.map { String($0.status) } ?? "timeout")")
        results["setTime"] = time.map { Int($0.status) } ?? -1
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
        if options.command == "layout" { await layoutTest() }
        return 0
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

    func save() {
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let dir = URL(fileURLWithPath: options.output).appendingPathComponent("nimo-\(options.command)-\(stamp)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let doc: [String: Any] = ["command": options.command, "device": link.device.name ?? "", "address": link.device.addressString ?? "",
                                  "attMtu": link.mtu, "results": results, "trace": trace]
        if let data = try? JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: dir.appendingPathComponent("session.json"))
            log("saved \(dir.path)/session.json (\(trace.count) ATT pdus)")
        }
    }
}

let options = parse()
switch options.command {
case "scan":
    let scanner = Scanner()
    DispatchQueue.main.asyncAfter(deadline: .now() + options.seconds) { _ = scanner; log("scan done"); exit(0) }
case "sdp":
    guard let dev = pairedNimo(named: options.name) else { log("no paired Nimo-* device"); exit(1) }
    log("device \(dev.name ?? "") \(dev.addressString ?? "") connected \(dev.isConnected())")
    dumpSDP(dev)
    exit(0)
case "ota-info":
    guard let dev = pairedNimo(named: options.name) else { log("no paired Nimo-* device; pair it in System Settings first"); exit(1) }
    log("device \(dev.name ?? "") \(dev.addressString ?? "") connected \(dev.isConnected())")
    let ota = OtaLink(device: dev)
    ota.log = log
    var trace: [[String: Any]] = []
    ota.onTraffic = { dir, d in trace.append(["t": Date().timeIntervalSince1970, "dir": dir, "hex": d.hex]) }
    var results: [String: Any] = [:]
    do { try ota.open() } catch { log("ota-info failed: \(error)"); exit(2) }
    DispatchQueue.main.asyncAfter(deadline: .now() + 60) { log("timed out"); exit(5) }
    Task {
        var code: Int32 = 0
        do {
            var attach: (status: UInt8, payload: Data, raw: Data)
            do {
                attach = try await ota.command(0x02, Data(repeating: 0xFF, count: 5))
            } catch OtaLink.Failure.timeout {
                // A half-open OTA session from an earlier host run answers nothing until the link drops.
                log("attach timed out; resetting the link once")
                ota.close()
                try await MainActor.run { try ota.open() }
                attach = try await ota.command(0x02, Data(repeating: 0xFF, count: 5))
            }
            log("attach status \(attach.status) payload \(attach.payload.hex)")
            var fields: [String: String] = [:]
            for (kind, value) in OtaLink.tlvs(attach.payload) {
                let text = String(data: value, encoding: .utf8).flatMap { $0.allSatisfy { $0.isASCII && !$0.isNewline && $0 != "\0" } ? $0 : nil }
                log("  field \(kind): \(value.hex)\(text.map { "  \"\($0)\"" } ?? "")")
                fields[String(kind)] = value.hex
            }
            results["attachStatus"] = Int(attach.status)
            results["attachFields"] = fields
            let ident = try await ota.command(0xE1)
            log("file identification status \(ident.status) payload \(ident.payload.hex)")
            results["fileIdentification"] = ident.payload.hex
        } catch {
            log("ota-info failed: \(error)")
            code = 2
        }
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let dir = URL(fileURLWithPath: options.output).appendingPathComponent("nimo-ota-info-\(stamp)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let doc: [String: Any] = ["command": "ota-info", "device": dev.name ?? "", "address": dev.addressString ?? "", "results": results, "trace": trace]
        if let data = try? JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: dir.appendingPathComponent("session.json"))
            log("saved \(dir.path)/session.json")
        }
        ota.close()
        exit(code)
    }
default:
    guard let dev = pairedNimo(named: options.name) else { log("no paired Nimo-* device; pair it in System Settings first"); exit(1) }
    log("device \(dev.name ?? "") \(dev.addressString ?? "") connected \(dev.isConnected())")
    let probe = Probe(options: options, device: dev)
    do { try probe.link.open() } catch { log("connect failed: \(error)"); exit(2) }
    DispatchQueue.main.asyncAfter(deadline: .now() + 120) { log("timed out"); probe.save(); exit(5) }
    Task {
        let code = await probe.run()
        DispatchQueue.main.async { probe.save(); probe.link.close(); exit(code) }
    }
}
RunLoop.main.run()
