import Foundation
import MemoMindBluetooth
import MemoMindCore

enum GlasslyInstall {
    static let version = "GLASSLYCFW/25"
    static let fileName = "memomind-one-glassly-cfw-25.bin"
    static let sha256 = "9cdd04786fceee283c30dafc20a01d680894d60026fdc78dbb7a8195fe54fae1"
    static let bootWait: TimeInterval = 300
    static let attemptSpacing: TimeInterval = 8
}

func runInstall(_ args: Arguments) throws {
    let path = (try? args.value("--firmware")) ?? bundledFirmwarePath()
    guard FileManager.default.fileExists(atPath: path) else {
        throw CLIError("Put \(GlasslyInstall.fileName) next to memomind, or pass --firmware FILE")
    }
    let firmware = try EligibleFirmware.load(data: Data(contentsOf: URL(fileURLWithPath: path)), expectedSHA256: GlasslyInstall.sha256)
    let glasses = try pairedGlasses(address: try? args.value("--address"))
    print("Glasses: \(glasses.name ?? "MemoMind One") (\(glasses.address))")
    if installedVersion(address: glasses.address, attempts: 1) == GlasslyInstall.version {
        print("\(GlasslyInstall.version) is already installed. Pair the glasses with your iPhone.")
        return
    }
    if !args.assumeYes {
        print("Install \(GlasslyInstall.version)? The glasses restart when it finishes. [y/N] ", terminator: "")
        guard readLine()?.lowercased().hasPrefix("y") == true else { throw CLIError("Cancelled") }
    }
    Thread.sleep(forTimeInterval: GlasslyInstall.attemptSpacing)
    let logs = try logDirectory()
    var flash = ["flash", "--address", glasses.address, "--firmware", path, "--expected-sha256", GlasslyInstall.sha256,
                 "--output", logs.path, "--confirm-write"]
    if args.resume {
        flash.append("--resume")
    }
    print("Installing. Keep the glasses close and charged; this takes a few minutes.")
    try runLive(Arguments(flash), firmware: firmware, printResult: false)
    print("Transferred. Waiting for the glasses to restart (wake them if the display stays dark)...")
    let attempts = Int(GlasslyInstall.bootWait / GlasslyInstall.attemptSpacing)
    guard let booted = installedVersion(address: glasses.address, attempts: attempts) else {
        throw CLIError("The firmware transferred, but the glasses did not answer within \(Int(GlasslyInstall.bootWait / 60)) minutes. Run memomind install again to check. Logs: \(logs.path)")
    }
    guard booted == GlasslyInstall.version else {
        throw CLIError("The glasses booted \(booted) instead of \(GlasslyInstall.version). Logs: \(logs.path)")
    }
    print("""
    Installed \(GlasslyInstall.version).
    Next: forget the glasses in this Mac's Bluetooth settings, pair them in your iPhone's Bluetooth settings, then add them in the Glassly App.
    """)
}

func bundledFirmwarePath() -> String {
    let executable = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
    return executable.deletingLastPathComponent().appendingPathComponent(GlasslyInstall.fileName).path
}

struct InstallTarget {
    let address: String
    let name: String?
}

func normalizedAddress(_ address: String) -> String {
    address.uppercased().replacingOccurrences(of: "-", with: ":")
}

func pairedGlasses(address: String?) throws -> InstallTarget {
    let paired = try MacRFCOMMTransport.pairedDevices().map { InstallTarget(address: normalizedAddress($0.address), name: $0.name) }
    if let address {
        guard let device = paired.first(where: { $0.address == normalizedAddress(address) }) else {
            throw CLIError("No paired device has address \(address)")
        }
        return device
    }
    let glasses = paired.filter { $0.name?.localizedCaseInsensitiveContains("memo") == true }
    guard let first = glasses.first else {
        throw CLIError("No MemoMind glasses are paired with this Mac. Pair them in System Settings > Bluetooth first.")
    }
    guard glasses.count == 1 else {
        throw CLIError("Several MemoMind glasses are paired; pass --address with one of: \(glasses.map(\.address).joined(separator: ", "))")
    }
    return first
}

func installedVersion(address: String, attempts: Int) -> String? {
    for attempt in 0 ..< max(1, attempts) {
        if attempt > 0 {
            Thread.sleep(forTimeInterval: GlasslyInstall.attemptSpacing)
        }
        let control = MacRFCOMMTransport()
        defer { control.close() }
        do {
            try control.connect(address: address, service: .normal)
            let session = GMSession(transport: control, timeout: 5)
            _ = try session.probe()
            let reply = try session.request(event: 3, service: 15, command: 0x7E)
            for tlv in reply.tlvs where tlv.kind == 5 {
                let json = tlv.value.prefix { $0 != 0 }
                if let object = try JSONSerialization.jsonObject(with: Data(json)) as? [String: Any],
                   let version = object["version"] as? String
                {
                    return version
                }
            }
            return "stock"
        } catch {
            if attempts == 1 {
                return nil
            }
        }
    }
    return nil
}

func logDirectory() throws -> URL {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    let base = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Glassly", isDirectory: true)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    return base.appendingPathComponent("memomind-install-" + formatter.string(from: Date()), isDirectory: true)
}
