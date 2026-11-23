@testable import MemoMindCore
import XCTest

func hex(_ string: String) -> Data {
    precondition(string.count % 2 == 0)
    var data = Data(), cursor = string.startIndex
    while cursor < string.endIndex {
        let end = string.index(cursor, offsetBy: 2)
        data.append(UInt8(string[cursor ..< end], radix: 16)!)
        cursor = end
    }
    return data
}

func tlv(_ kind: UInt8, _ value: Data) throws -> Data {
    try GMTLV(kind: kind, value: value).encoded()
}

final class QueueTransport: MemoMindTransport {
    var reads: [Data]
    var writes = [Data]()
    var onWrite: ((Data) throws -> Void)?
    var onRead: (() -> Void)?
    init(_ reads: [Data] = []) {
        self.reads = reads
    }

    func write(_ data: Data) throws {
        writes.append(data); try onWrite?(data)
    }

    func read(timeout _: TimeInterval) throws -> Data {
        onRead?()
        guard !reads.isEmpty else { throw MemoMindProtocolError.timeout("injected timeout") }
        return reads.removeFirst()
    }
}

final class ProtocolTests: XCTestCase {
    func testIndependentPythonVectors() throws {
        XCTAssertEqual(try GMCodec.frames(event: 1, service: 1, command: 1), [hex("fa0000090101010106")])
        for (size, frames) in [(503, PythonProtocolVectors.gm503), (642, PythonProtocolVectors.gm642)] {
            XCTAssertEqual(try GMCodec.frames(event: 37, service: 15, command: 125,
                                              body: hex(PythonProtocolVectors.gmBody), fragmentPayload: size), frames.map(hex))
        }
        XCTAssertEqual(try OTACodec.frame(command: 2, sequence: 1, parameters: Data(repeating: 255, count: 5)), hex(PythonProtocolVectors.attach))
        let bytes = Data((0 ..< 512).map { UInt8($0 % 256) }) + Data("end".utf8)
        XCTAssertEqual(try OTACodec.chunk(sequence: 255, offset: 0x1234_5678, data: bytes), hex(PythonProtocolVectors.chunk))
        XCTAssertEqual(OTACodec.crc32(Data("123456789".utf8)), 0xCBF4_3926)
    }

    func testAllByteSplitsAndTLVCrossing() throws {
        let body = try tlv(2, Data(repeating: 120, count: 496)) + tlv(1, Data(repeating: 65, count: 500))
        let frames = try GMCodec.frames(event: 7, service: 1, command: 2, body: body)
        let parser = GMStream()
        var messages = [GMMessage]()
        for byte in frames.reduce(Data(), +) {
            messages += try parser.feed(Data([byte]))
        }
        XCTAssertEqual(messages.count, 1)
        XCTAssertEqual(messages.first?.body, body)
        XCTAssertEqual(messages.first?.tlvs, try GMCodec.parseTLVs(body))
        let ota = OTAStream()
        var packets = [Data]()
        for byte in hex(PythonProtocolVectors.chunk) {
            packets += try ota.feed(Data([byte]))
        }
        XCTAssertEqual(packets, [hex(PythonProtocolVectors.chunk)])
    }

    func testChecksumResetAndMalformedTLVs() throws {
        let valid = try GMCodec.frames(event: 1, service: 1, command: 1, body: tlv(6, Data([0])))[0]
        var bad = valid; bad[bad.count - 1] ^= 1
        let parser = GMStream()
        XCTAssertThrowsError(try parser.feed(bad))
        XCTAssertEqual(try parser.feed(valid).count, 1)
        for badBody in [hex("060000020000"), hex("0200000261"), hex("010000")] {
            XCTAssertThrowsError(try GMCodec.parseTLVs(badBody))
        }
        XCTAssertEqual(try GMCodec.parseTLVs(hex("99000003616263")), [GMTLV(kind: 0x99, value: Data("abc".utf8))])
    }

    func testLegacyContinuationAndInterleavedFragmentACK() throws {
        let packets = PythonProtocolVectors.gm503.map(hex)
        let parser = GMStream(fragmentACKs: true)
        XCTAssertTrue(try parser.feed(packets[0]).isEmpty)
        let raw = hex("01000009250f7d")
        let ack = raw + Data(beBytes(raw.reduce(0) { $0 + UInt32($1) }, 2))
        XCTAssertEqual(try parser.feed(ack).first?.head, 1)
        XCTAssertEqual(try parser.feed(packets[1]).first?.body, hex(PythonProtocolVectors.gmBody))
        XCTAssertThrowsError(try GMStream().feed(ack))
        var second = Array(packets[1].dropLast(2)); second[0] = 0xFA
        second += beBytes(second.reduce(0) { $0 + UInt32($1) } & 65535, 2)
        XCTAssertEqual(try GMStream(legacyRepeatFA: true).feed(packets[0] + Data(second)).count, 1)
        XCTAssertThrowsError(try GMStream().feed(packets[1]))
    }

    func testFragmentACKOrderingAndEarlyRejection() throws {
        let body = hex(PythonProtocolVectors.gmBody)
        let rejection = try GMCodec.frames(event: 37, service: 15, command: 125, body: tlv(6, Data([8])))[0]
        let rejected = QueueTransport([rejection])
        let message = try GMSession(transport: rejected).request(event: 37, service: 15, command: 125, body: body)
        XCTAssertEqual(message.tlvs[0].value, Data([8])); XCTAssertEqual(rejected.writes.count, 1)
        let badACK = hex("02000009250f7d00bc") // valid sum, wrong head
        let wrong = QueueTransport([badACK])
        XCTAssertThrowsError(try GMSession(transport: wrong).request(event: 37, service: 15, command: 125, body: body))
        XCTAssertEqual(wrong.writes.count, 1)
        let ack = hex("fa000009250f7d01b4")
        let success = try GMCodec.frames(event: 37, service: 15, command: 125, body: tlv(6, Data([0])))[0]
        let accepted = QueueTransport([ack, success])
        XCTAssertEqual(try GMSession(transport: accepted).request(event: 37, service: 15, command: 125, body: body).tlvs[0].value, Data([0]))
        XCTAssertEqual(accepted.writes, PythonProtocolVectors.gm642.map(hex))
    }

    func testMalformedOTAAndCodecLimits() throws {
        XCTAssertThrowsError(try OTAStream().feed(hex("00076e0002000033")))
        XCTAssertThrowsError(try OTAStream().feed(hex("70076e0002000034")))
        XCTAssertThrowsError(try OTACodec.chunk(sequence: 1, offset: 0, data: Data(count: 631)))
        XCTAssertThrowsError(try OTACodec.frame(command: 1, sequence: 1, parameters: Data(count: 65535)))
        XCTAssertThrowsError(try GMCodec.frames(event: 1, service: 1, command: 1, body: Data(count: 81912)))
        XCTAssertThrowsError(try GMCodec.frames(event: 1, service: 1, command: 1, fragmentPayload: 640))
    }

    func testProbeAndPrivateNotifyStatus() throws {
        let heartbeat = try GMCodec.frames(event: 1, service: 1, command: 1, body: tlv(6, Data([0])))[0]
        let identity = Data("{\"model\":\"H001Y\",\"hver\":\"2.1.2\",\"fver\":\"1.3\",\"ver\":\"1.0.3.127\",\"mac\":\"AA\"}\0".utf8)
        let info = try GMCodec.frames(event: 2, service: 1, command: 2, body: tlv(2, identity))[0]
        let io = QueueTransport([heartbeat, info])
        XCTAssertEqual(try GMSession(transport: io).probe().mac, "AA")
        XCTAssertEqual(io.writes.count, 2)
        for status: UInt8 in [0, 1] {
            let reply = try GMCodec.frames(event: 0x15, service: 1, command: 0x1C, body: tlv(6, Data([status])))[0]
            let session = GMSession(transport: QueueTransport([reply]))
            if status == 1 {
                XCTAssertNoThrow(try session.notifyOTA())
            } else {
                XCTAssertThrowsError(try session.notifyOTA())
            }
        }
    }
}
