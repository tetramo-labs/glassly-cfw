import Darwin
import Foundation

/// One new private capture directory per attempt. A failed attempt remains intact.
final class Capture {
    let directory: URL
    private var descriptor: Int32 = -1
    private let clock = ISO8601DateFormatter()

    init(path: String) throws {
        directory = URL(fileURLWithPath: path, isDirectory: true)
        guard mkdir(directory.path, 0o700) == 0 else {
            throw CLIError("Cannot create new capture directory: \(String(cString: strerror(errno)))")
        }
        descriptor = Darwin.open(directory.appendingPathComponent("trace.jsonl").path,
                                 O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard descriptor >= 0 else { throw CLIError("Cannot create trace: \(String(cString: strerror(errno)))") }
        clock.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try record(["event": "capture-start", "format": "memomind-native-mac-v1",
                    "automaticRetries": 0, "process": ProcessInfo.processInfo.processIdentifier])
    }

    deinit {
        if descriptor >= 0 {
            Darwin.close(descriptor)
        }
    }

    func record(_ row: [String: Any]) throws {
        var stamped = row
        stamped["utc"] = clock.string(from: Date())
        stamped["uptimeSeconds"] = ProcessInfo.processInfo.systemUptime
        var data = try JSONSerialization.data(withJSONObject: stamped, options: [.sortedKeys])
        data.append(0x0A)
        try Self.write(data, to: descriptor)
    }

    func save(_ value: [String: Any], name: String) throws {
        let fd = Darwin.open(directory.appendingPathComponent(name).path,
                             O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw CLIError("Cannot create \(name): \(String(cString: strerror(errno)))") }
        defer { Darwin.close(fd) }
        var data = try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
        data.append(0x0A)
        try Self.write(data, to: fd)
    }

    private static func write(_ data: Data, to fd: Int32) throws {
        try data.withUnsafeBytes { raw in
            var offset = 0
            while offset < raw.count {
                let count = Darwin.write(fd, raw.baseAddress!.advanced(by: offset), raw.count - offset)
                if count < 0, errno == EINTR {
                    continue
                }
                guard count > 0 else { throw CLIError("Capture write failed: \(String(cString: strerror(errno)))") }
                offset += count
            }
        }
        guard fsync(fd) == 0 else { throw CLIError("Capture fsync failed: \(String(cString: strerror(errno)))") }
    }
}

func dictionary(_ value: some Encodable) throws -> [String: Any] {
    guard let result = try JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any] else {
        throw CLIError("Expected an encoded object")
    }
    return result
}

func printJSON(_ value: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
    print(String(decoding: data, as: UTF8.self))
}
