import Foundation
struct Failure: Error { let reason: String }
func need(_ value: Bool, _ reason: String) throws { if !value { throw Failure(reason: reason) } }
func rejected(_ body: () throws -> Void) throws {
    do { try body() } catch { return }
    throw Failure(reason: "Expected rejection")
}
var currentReply = Data()
func jsonRequest(_ command: UInt8, _ body: Data) throws -> Data { currentReply }
func save(_ name: String, _ body: Data) throws {}
func message(_ raw: String, event: UInt8 = 37) throws -> GMMessage {
    let wire = try GMCodec.frames(event: event, service: 15, command: 125, body: GMTLV(kind: 5, value: Data(raw.utf8)).encoded()).reduce(Data(), +)
    return try GMStream().feed(wire)[0]
}
func wrap(_ bytes: [UInt8]) -> Data {
    Data(("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"" + bytes.map { String(format: "%02x", $0) }.joined() + "\"}").utf8)
}
var checks = 0
for number in ["0", "11", "65535"] {
    let m = try message("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"settled\",\"tag\":\(number)}")
    try need(try settledTag(m) == UInt16(number), "Valid tag rejected"); checks += 1
}
for number in ["00", "011", "00011", "65536", "-1", "1.0", "1e1", "true", "1,\"extra\":0"] {
    try rejected { _ = try settledTag(message("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"settled\",\"tag\":\(number)}")) }; checks += 1
}
let reset: [UInt8] = [41, 1, 0, 0, 0x34, 0x12, 1, 0, 0, 0, 0, 64, 0]
currentReply = wrap(reset)
try need(try sceneReply(Data(), 41, 1) == 0x1234, "Reset epoch parse"); checks += 1
let hide: [UInt8] = [39, 16, 0, 0, 0x34, 0x12, 1, 0, 0, 0, 0]
currentReply = wrap(hide)
try need(try sceneReply(Data(), 39, 16, 0x1234) == 0x1234, "Hide parse"); checks += 1
for n in 0..<reset.count {
    currentReply = wrap(Array(reset.prefix(n)))
    try rejected { _ = try sceneReply(Data(), 41, 1) }; checks += 1
}
for n in 0..<hide.count {
    currentReply = wrap(Array(hide.prefix(n)))
    try rejected { _ = try sceneReply(Data(), 39, 16, 0x1234) }; checks += 1
}
for index in [0, 1, 3, 4, 10, 11, 12] {
    var bad = reset; bad[index] &+= 1; currentReply = wrap(bad)
    try rejected { _ = try sceneReply(Data(), 41, 1, 0x1234) }; checks += 1
}
final class IO: MemoMindTransport {
    var writes = 0, reads = 0, packets: [Data]
    init(_ packets: [Data]) { self.packets = packets }
    func write(_ data: Data) throws { writes += 1 }
    func read(timeout: TimeInterval) throws -> Data {
        reads += 1
        guard !packets.isEmpty else { throw Failure(reason: "No synthetic reply") }
        return packets.removeFirst()
    }
}
let unsolicited = try GMCodec.frames(event: 36, service: 15, command: 125, body: GMTLV(kind: 5, value: Data("malformed".utf8)).encoded())[0]
let ack = try GMCodec.frames(event: 37, service: 15, command: 125)[0]
for withACK in [false, true] {
    let io = IO([unsolicited + (withACK ? ack : Data())]); var error: String?
    let checked = CheckedIO(io) { try need(error == nil, "Observed notification failure") }
    let session = GMSession(transport: checked)
    session.unsolicited = { _ in error = "Bad notification" }
    try rejected { _ = try session.request(event: 37, service: 15, command: 125, body: Data(count: 1500), responseFilter: { _ in true }) }
    try need(io.writes == 1 && io.reads == 1, "Guard allowed another write/read after observed notification failure"); checks += 1
}
let io = IO([])
let stopped = CheckedIO(io) { throw Failure(reason: "already poisoned") }
try rejected { try stopped.write(Data([1])) }
try need(io.writes == 0, "Preexisting failure allowed write"); checks += 1
print("{\"passed\":true,\"checks\":\(checks),\"device_operations\":false}")
