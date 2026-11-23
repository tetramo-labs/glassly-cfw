import Foundation

public enum RecordingFormat: UInt8, Sendable {
    case legacy = 0, compact = 1
    var recordBytes: Int {
        self == .legacy ? 49 : 40
    }
}

public enum RecordingEvent: Equatable, Sendable {
    case format(RecordingFormat)
    case started(noiseMode: UInt8, timestamp: UInt32)
    case audio(command: UInt8, metadata: Data, frames: [Data])
}

/// One recording connection. Invalid framing stops parsing until reset.
public final class RecordingStream {
    public private(set) var format: RecordingFormat
    public var pendingBytes: Int {
        buffer.count
    }

    private var buffer = Data()
    private var failed = false

    public init(format: RecordingFormat = .legacy) {
        self.format = format
    }

    public func reset(format: RecordingFormat = .legacy) {
        buffer.removeAll(keepingCapacity: false)
        failed = false
        self.format = format
    }

    public func feed(_ data: Data) throws -> [RecordingEvent] {
        try requireProtocol(!failed, "Recording parser stopped after invalid framing")
        do {
            try requireProtocol(data.count <= 65536 - buffer.count, "Recording buffer overflow")
            buffer.append(data)
            var events = [RecordingEvent]()
            while buffer.count >= 2 {
                try requireProtocol(buffer[0] == 0x52, "Invalid recording magic")
                let command = buffer[1]
                if command == 0x11 || command == 0x13 {
                    guard buffer.count >= 6 else { break }
                    if command == 0x13 {
                        guard let selected = RecordingFormat(rawValue: buffer[2]) else {
                            throw MemoMindProtocolError.invalid("Unknown recording format")
                        }
                        try requireProtocol(Array(buffer[3 ..< 6]) == [49, 40, 0], "Invalid recording format sizes")
                        format = selected
                        events.append(.format(selected))
                    } else {
                        try requireProtocol(buffer[2] <= 1, "Invalid recording noise mode")
                        let timestamp = UInt32(buffer[3]) << 16 | UInt32(buffer[4]) << 8 | UInt32(buffer[5])
                        events.append(.started(noiseMode: buffer[2], timestamp: timestamp))
                    }
                    buffer = Data(buffer.dropFirst(6))
                    continue
                }
                try requireProtocol((0x90 ... 0x94).contains(command), "Unknown recording command")
                guard buffer.count >= 12 else { break }
                let count = Int(buffer[6]), size = 12 + count * format.recordBytes
                try requireProtocol(buffer[2] == 0 && buffer[3] == 0 && buffer[11] == 255 && (1 ... 8).contains(count),
                                    "Invalid recording header")
                guard buffer.count >= size else { break }
                var frames = [Data]()
                for index in 0 ..< count {
                    let offset = 12 + index * format.recordBytes
                    if format == .legacy {
                        try requireProtocol(buffer[offset + 4] == 40, "Invalid legacy Opus length")
                    }
                    let start = offset + (format == .legacy ? 9 : 0)
                    frames.append(Data(buffer[start ..< start + 40]))
                }
                events.append(.audio(command: command, metadata: Data(buffer[4 ..< 11]), frames: frames))
                buffer = Data(buffer.dropFirst(size))
            }
            return events
        } catch {
            failed = true
            throw error
        }
    }
}
