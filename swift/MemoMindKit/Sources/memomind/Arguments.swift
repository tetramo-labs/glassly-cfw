import Foundation

struct CLIError: Error, LocalizedError {
    let message: String
    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? {
        message
    }
}

struct Arguments {
    static let usage = """
    Native MemoMind One RFCOMM flasher

      memomind install [--address MAC] [--firmware FILE] [--yes] [--resume]
      memomind devices
      memomind inspect --firmware FILE --expected-sha256 HASH
      memomind replay --firmware FILE --expected-sha256 HASH --transcript TSV
      memomind probe --address MAC --output NEW_DIRECTORY
      memomind buttons --address MAC --seconds 180 --output NEW_DIRECTORY
      memomind sensors --address MAC --seconds 30 [--interval MS] --output NEW_DIRECTORY
      memomind microphone --address MAC --seconds 10 --output NEW_DIRECTORY
      memomind ownership --address MAC --seconds 120 --output NEW_DIRECTORY
      memomind fontprobe --address MAC [--from U+XXXX] [--to U+XXXX] [--scalars FILE] [--sampled] [--miss-budget N] --output NEW_DIRECTORY
      memomind check --address MAC --firmware FILE --expected-sha256 HASH --output NEW_DIRECTORY
      memomind flash --address MAC --firmware FILE --expected-sha256 HASH --output NEW_DIRECTORY --confirm-write [--resume]

    check stops before OTA entry; flash transfers and requests reboot.
    Every live operation records a new durable JSONL trace. No retry; --resume only
    continues a device-side stage of the same image from the offset the device offers.
    Firmware must match the compiled release catalog and explicit hash.
    """

    let command: String
    let values: [String: String]
    let confirmWrite: Bool
    let resume: Bool
    let sampled: Bool
    let assumeYes: Bool

    init(_ arguments: [String]) throws {
        guard let command = arguments.first else { throw CLIError(Self.usage) }
        guard ["install", "devices", "inspect", "replay", "probe", "buttons", "microphone", "sensors", "ownership", "fontprobe", "check", "flash", "help", "--help", "-h"].contains(command) else {
            throw CLIError("Unknown command: \(command)\n\(Self.usage)")
        }
        self.command = command
        var values: [String: String] = [:]
        var confirm = false, sampled = false, resume = false, assumeYes = false
        var index = 1
        while index < arguments.count {
            let flag = arguments[index]
            if flag == "--sampled" {
                guard command == "fontprobe", !sampled else { throw CLIError("--sampled is a fontprobe option, once") }
                sampled = true
                index += 1
                continue
            }
            if flag == "--yes" {
                guard command == "install", !assumeYes else { throw CLIError("--yes is an install option, once") }
                assumeYes = true
                index += 1
                continue
            }
            if flag == "--resume" {
                guard command == "flash" || command == "install", !resume else { throw CLIError("--resume is a flash or install option, once") }
                resume = true
                index += 1
                continue
            }
            if flag == "--confirm-write" {
                guard !confirm else { throw CLIError("Duplicate --confirm-write") }
                confirm = true
                index += 1
                continue
            }
            guard ["--address", "--firmware", "--expected-sha256", "--output", "--transcript", "--seconds", "--interval", "--from", "--to", "--miss-budget", "--scalars"].contains(flag),
                  values[flag] == nil, index + 1 < arguments.count,
                  !arguments[index + 1].hasPrefix("--")
            else {
                throw CLIError("Unknown, duplicate or missing-value option: \(flag)")
            }
            values[flag] = arguments[index + 1]
            index += 2
        }
        let optional: Set<String> = switch command {
        case "sensors": ["--interval"]
        case "fontprobe": ["--from", "--to", "--miss-budget", "--scalars"]
        case "install": ["--address", "--firmware"]
        default: []
        }
        let allowed: Set<String> = switch command {
        case "probe", "fontprobe": ["--address", "--output"]
        case "buttons", "microphone", "sensors", "ownership": ["--address", "--output", "--seconds"]
        case "check", "flash": ["--address", "--output", "--firmware", "--expected-sha256"]
        case "inspect": ["--firmware", "--expected-sha256"]
        case "replay": ["--firmware", "--expected-sha256", "--transcript"]
        default: []
        }
        guard Set(values.keys).subtracting(optional) == allowed else {
            throw CLIError("\(command) requires exactly: \(allowed.sorted().joined(separator: " "))")
        }
        guard confirm == (command == "flash") else {
            throw CLIError("Only flash requires --confirm-write")
        }
        if let seconds = values["--seconds"] {
            let maximum = command == "microphone" ? 15 : 600
            guard let duration = Int(seconds), (1...maximum).contains(duration) else {
                throw CLIError("Duration must be 1...\(maximum) seconds")
            }
        }
        if let budget = values["--miss-budget"] {
            guard let n = Int(budget), (1...1000).contains(n) else { throw CLIError("--miss-budget must be 1...1000") }
        }
        for key in ["--from", "--to"] {
            if let text = values[key] {
                guard Self.scalar(text) != nil else { throw CLIError("\(key) must be U+XXXX inside the Unicode range") }
            }
        }
        if let interval = values["--interval"] {
            guard let ms = Int(interval), (100...5000).contains(ms) else {
                throw CLIError("Interval must be 100...5000 ms")
            }
        }
        if let address = values["--address"] {
            guard address.range(of: "^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$", options: .regularExpression) != nil else {
                throw CLIError("Address must have six colon-separated hexadecimal bytes")
            }
        }
        self.values = values
        confirmWrite = confirm
        self.resume = resume
        self.sampled = sampled
        self.assumeYes = assumeYes
    }

    /// "U+01F7" or bare hex → scalar value.
    static func scalar(_ text: String) -> UInt32? {
        let hex = text.hasPrefix("U+") || text.hasPrefix("u+") ? String(text.dropFirst(2)) : text
        guard let value = UInt32(hex, radix: 16), value <= 0x10FFFF else { return nil }
        return value
    }

    func value(_ key: String) throws -> String {
        guard let value = values[key] else { throw CLIError("Missing \(key)") }
        return value
    }
}
