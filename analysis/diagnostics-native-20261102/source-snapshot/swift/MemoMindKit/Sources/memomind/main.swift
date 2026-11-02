import Foundation
import MemoMindBluetooth
import MemoMindCore

func loadFirmware(_ args: Arguments) throws -> EligibleFirmware {
    let path = try args.value("--firmware")
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    return try EligibleFirmware.load(data: data, expectedSHA256: args.value("--expected-sha256"))
}

func runLive(_ args: Arguments, firmware: EligibleFirmware?) throws {
    let capture = try Capture(path: args.value("--output"))
    let address = try args.value("--address").uppercased()
    func transport(_ name: String) -> MacRFCOMMTransport {
        MacRFCOMMTransport { event in
            var row: [String: Any] = ["event": event.kind.rawValue, "session": name,
                                      "hex": event.data.map { String(format: "%02x", $0) }.joined(),
                                      "bytes": event.data.count, "callbackUptime": event.uptime]
            if let status = event.status {
                row["status"] = status
            }
            try capture.record(row)
        }
    }
    let control = transport("control")
    let ota = transport("ota")
    defer { ota.close(); control.close() }
    do {
        try capture.record(["event": "attempt", "command": args.command, "address": address,
                            "imageSHA256": firmware?.sha256 ?? NSNull(), "confirmWrite": args.confirmWrite])
        try capture.record(["event": "connect-intent", "session": "control",
                            "service": MemoMindBluetoothService.normal.rawValue])
        try control.connect(address: address, service: .normal)
        try capture.record(["event": "connected", "session": "control",
                            "serviceDiscovery": control.serviceDiscoverySource as Any? ?? NSNull(),
                            "channel": control.resolvedChannelID as Any? ?? NSNull()])
        let session = GMSession(transport: control)
        let identity = try session.probe()
        try capture.record(["event": "identity", "device": dictionary(identity)])
        try identity.validate(address: address)
        var result: [String: Any]
        if let firmware {
            try capture.record(["event": "pre-ota-notification-intent"])
            try session.notifyOTA()
            try capture.record(["event": "pre-ota-notification-accepted"])
            try capture.record(["event": "connect-intent", "session": "ota",
                                "service": MemoMindBluetoothService.ota.rawValue])
            try ota.connect(address: address, service: .ota)
            try capture.record(["event": "connected", "session": "ota",
                                "serviceDiscovery": ota.serviceDiscoverySource as Any? ?? NSNull(),
                                "channel": ota.resolvedChannelID as Any? ?? NSNull()])
            let transaction = try OTATransaction(transport: ota, firmware: firmware,
                                                 identity: identity, address: address,
                                                 checkControlLink: {
                                                     try control.checkHealth()
                                                     // Every byte was durably recorded in the receive callback.
                                                     _ = try control.drainReceived()
                                                 })
            transaction.progress = { block in
                if block.offset % (4096 * 16) < 4096 {
                    fputs("Acknowledged through byte \(block.offset + block.length) / \(firmware.data.count)\n", stderr)
                }
            }
            result = try dictionary(transaction.run(checkOnly: args.command == "check"))
            result["imageSHA256"] = firmware.sha256
            result["releaseName"] = firmware.releaseName
            result["controlLinkPreserved"] = true
        } else {
            result = try ["device": dictionary(identity), "heartbeatStatus": 0,
                          "operationsSent": ["heartbeat", "device_information"], "flashMutations": 0]
        }
        result["mode"] = "native macOS IOBluetooth RFCOMM"
        result["command"] = args.command
        result["capture"] = capture.directory.path
        result["automaticRetries"] = 0
        try capture.record(["event": "operation-complete", "result": result])
        try capture.save(result, name: "result.json")
        try printJSON(result)
    } catch {
        let failure: [String: Any] = ["complete": false, "command": args.command,
                                      "error": String(describing: error), "automaticRetries": 0,
                                      "postRebootVersionVerified": false]
        // Preserve the original failure even if the log device has also failed.
        do {
            try capture.record(["event": "failed", "result": failure])
            try capture.save(failure, name: "failure.json")
        } catch { fputs("Could not save failure record: \(error)\n", stderr) }
        throw error
    }
}

do {
    let args = try Arguments(Array(CommandLine.arguments.dropFirst()))
    switch args.command {
    case "help", "--help", "-h": print(Arguments.usage)
    case "devices":
        let host = try MacRFCOMMTransport.hostStatus()
        let paired = try MacRFCOMMTransport.pairedDevices().map { device -> [String: Any] in
            ["address": device.address, "name": device.name ?? NSNull(), "connected": device.connected]
        }
        let hostRow: [String: Any] = ["available": host.available, "powerState": host.powerState as Any? ?? NSNull(),
                                      "address": host.address as Any? ?? NSNull(), "name": host.name as Any? ?? NSNull()]
        try printJSON(["host": hostRow,
                       "pairedDevices": paired, "scanned": false])
    case "inspect":
        let firmware = try loadFirmware(args)
        try printJSON(["eligible": true, "releaseName": firmware.releaseName, "profile": firmware.profile,
                       "sha256": firmware.sha256, "bytes": firmware.data.count, "modified": firmware.modified,
                       "bluetoothAccessed": false])
    case "replay":
        try printJSON(replay(firmware: loadFirmware(args), path: args.value("--transcript")))
    case "probe": try runLive(args, firmware: nil)
    case "check", "flash": try runLive(args, firmware: loadFirmware(args))
    default: throw CLIError(Arguments.usage)
    }
} catch {
    fputs("memomind: \(error)\n", stderr)
    exit(1)
}
