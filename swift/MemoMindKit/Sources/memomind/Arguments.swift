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

      memomind devices
      memomind inspect --firmware FILE --expected-sha256 HASH
      memomind replay --firmware FILE --expected-sha256 HASH --transcript TSV
      memomind probe --address MAC --output NEW_DIRECTORY
      memomind buttons --address MAC --seconds 180 --output NEW_DIRECTORY
      memomind microphone --address MAC --seconds 10 --output NEW_DIRECTORY
      memomind check --address MAC --firmware FILE --expected-sha256 HASH --output NEW_DIRECTORY
      memomind flash --address MAC --firmware FILE --expected-sha256 HASH --output NEW_DIRECTORY --confirm-write

    check stops before OTA entry; flash transfers and requests reboot.
    Every live operation records a new durable JSONL trace. No retry or resume.
    Firmware must match the compiled release catalog and explicit hash.
    """

    let command: String
    let values: [String: String]
    let confirmWrite: Bool

    init(_ arguments: [String]) throws {
        guard let command = arguments.first else { throw CLIError(Self.usage) }
        guard ["devices", "inspect", "replay", "probe", "buttons", "microphone", "check", "flash", "help", "--help", "-h"].contains(command) else {
            throw CLIError("Unknown command: \(command)\n\(Self.usage)")
        }
        self.command = command
        var values: [String: String] = [:]
        var confirm = false
        var index = 1
        while index < arguments.count {
            let flag = arguments[index]
            if flag == "--confirm-write" {
                guard !confirm else { throw CLIError("Duplicate --confirm-write") }
                confirm = true
                index += 1
                continue
            }
            guard ["--address", "--firmware", "--expected-sha256", "--output", "--transcript", "--seconds"].contains(flag),
                  values[flag] == nil, index + 1 < arguments.count,
                  !arguments[index + 1].hasPrefix("--")
            else {
                throw CLIError("Unknown, duplicate or missing-value option: \(flag)")
            }
            values[flag] = arguments[index + 1]
            index += 2
        }
        let allowed: Set<String> = switch command {
        case "probe": ["--address", "--output"]
        case "buttons", "microphone": ["--address", "--output", "--seconds"]
        case "check", "flash": ["--address", "--output", "--firmware", "--expected-sha256"]
        case "inspect": ["--firmware", "--expected-sha256"]
        case "replay": ["--firmware", "--expected-sha256", "--transcript"]
        default: []
        }
        guard Set(values.keys) == allowed else {
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
        if let address = values["--address"] {
            guard address.range(of: "^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$", options: .regularExpression) != nil else {
                throw CLIError("Address must have six colon-separated hexadecimal bytes")
            }
        }
        self.values = values
        confirmWrite = confirm
    }

    func value(_ key: String) throws -> String {
        guard let value = values[key] else { throw CLIError("Missing \(key)") }
        return value
    }
}
