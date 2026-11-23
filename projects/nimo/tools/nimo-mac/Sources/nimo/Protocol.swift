import Foundation

/// The NIMO 0xBF transport: 8-byte header, CRC16-CCITT over the app payload, 501-byte chunks.
enum Wire {
    static let magic: UInt8 = 0xBF
    static let chunk = 501

    static func crc16(_ data: Data) -> UInt16 {
        var crc: UInt16 = 0xFFFF
        for b in data {
            crc ^= UInt16(b) << 8
            for _ in 0 ..< 8 {
                crc = crc & 0x8000 != 0 ? (crc << 1) ^ 0x1021 : crc << 1
            }
        }
        return crc
    }

    static func header(_ payload: Data, index: Int, ack: Bool) -> Data {
        let crc = crc16(payload)
        return Data([magic, ack ? 2 : 0, UInt8(payload.count & 0xFF), UInt8(payload.count >> 8),
                     UInt8(crc & 0xFF), UInt8(crc >> 8), UInt8(index & 0xFF), UInt8(index >> 8)])
    }

    /// Request frames for one command; several when the app payload exceeds a chunk.
    static func frames(cmd: UInt8, key: UInt8, payload: Data = Data(), ack: Bool = true, chunk: Int = Wire.chunk) -> [Data] {
        var full = Data([cmd, key, UInt8(payload.count & 0xFF), UInt8(payload.count >> 8)])
        full.append(payload)
        let count = max(1, (full.count + chunk - 1) / chunk)
        return (0 ..< count).map { i in
            let piece = full.subdata(in: i * chunk ..< min(full.count, (i + 1) * chunk))
            return header(piece, index: i == count - 1 ? 0 : i + 1, ack: ack) + piece
        }
    }

    struct Message {
        let cmd: UInt8
        let key: UInt8
        let status: UInt8
        let data: Data
        var isReport: Bool { cmd == 0x06 }
    }

    /// Reassembles chunked replies; single packets pass straight through.
    final class Assembler {
        private var pending: [UInt16: (first: Data, parts: [Int: Data])] = [:]

        func ingest(_ packet: Data) -> Message? {
            guard packet.count >= 8, packet[0] == magic else { return nil }
            let len = Int(packet[2]) | Int(packet[3]) << 8
            let index = Int(packet[6]) | Int(packet[7]) << 8
            guard packet.count >= 8 + len, len >= 5 else { return nil }
            let app = packet.subdata(in: 8 ..< 8 + len)
            guard crc16(app) == (UInt16(packet[4]) | UInt16(packet[5]) << 8) else { return nil }
            let group = UInt16(app[0]) << 8 | UInt16(app[1])
            if index == 0, pending[group] == nil {
                return Message(cmd: app[0], key: app[1], status: app[4], data: app.subdata(in: 5 ..< app.count))
            }
            var entry = pending[group] ?? (first: app, parts: [:])
            if index == 1 { entry.first = app }
            entry.parts[index == 0 ? Int.max : index] = index == 1 ? app.subdata(in: 5 ..< app.count) : app.subdata(in: 5 ..< app.count)
            if index != 0 {
                pending[group] = entry
                return nil
            }
            pending[group] = nil
            var data = Data()
            for k in entry.parts.keys.sorted() { data.append(entry.parts[k]!) }
            return Message(cmd: entry.first[0], key: entry.first[1], status: entry.first[4], data: data)
        }
    }

    static func deviceTime(_ date: Date = Date()) -> Data {
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second, .weekday], from: date)
        let year = c.year ?? 2000
        let zone = max(-48, min(48, TimeZone.current.secondsFromGMT(for: date) / 900))
        return Data([UInt8(year & 0xFF), UInt8(year >> 8), UInt8(c.month ?? 1), UInt8(c.day ?? 1), UInt8(c.hour ?? 0),
                     UInt8(c.minute ?? 0), UInt8(c.second ?? 0), UInt8((c.weekday ?? 1) - 1), UInt8(bitPattern: Int8(zone))])
    }
}

extension Data {
    var hex: String { map { String(format: "%02X", $0) }.joined(separator: " ") }
}

enum Decode {
    static func version(_ d: Data) -> String? {
        guard d.count >= 4 else { return nil }
        let v = UInt32(d[0]) | UInt32(d[1]) << 8 | UInt32(d[2]) << 16 | UInt32(d[3]) << 24
        return "\(v >> 28 & 0xF).\(v >> 21 & 0x7F).\(v >> 12 & 0x1FF).\(v & 0xFFF)"
    }

    static func text(_ d: Data) -> String {
        var end = d.count
        while end > 0, d[end - 1] == 0 { end -= 1 }
        return String(decoding: d.prefix(end), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func screenInfo(_ d: Data) -> [String: Int]? {
        guard d.count >= 20 else { return nil }
        func u16(_ o: Int) -> Int { Int(d[o]) | Int(d[o + 1]) << 8 }
        return ["leftPhysicalWidth": u16(0), "leftPhysicalHeight": u16(2), "leftValidWidth": u16(4), "leftValidHeight": u16(6),
                "leftOffsetX": Int(d[8]), "leftOffsetY": Int(d[9]), "rightPhysicalWidth": u16(10), "rightPhysicalHeight": u16(12),
                "rightValidWidth": u16(14), "rightValidHeight": u16(16), "rightOffsetX": Int(d[18]), "rightOffsetY": Int(d[19])]
    }
}

/// The vendor guide's golden Dynamic Layout frame: a rounded rectangle and "Hello Glass".
enum Golden {
    static let appId: UInt8 = 0xFD
    static let frame: Data = {
        var d = Data([0x02, 0x00, 0x01,
                      0x01, 0x0C, 0x00, 0x14, 0x00, 0x14, 0x00, 0x78, 0x00, 0x32, 0x00, 0x02, 0x08, 0xFF, 0x00,
                      0x03, 0x19, 0x00, 0xA0, 0x00, 0x1E, 0x00, 0x2C, 0x01, 0x28, 0x00, 0x00, 0x00, 0x02, 0xFF, 0x0B, 0x00])
        d.append(contentsOf: Array("Hello Glass".utf8))
        return d
    }()
}
