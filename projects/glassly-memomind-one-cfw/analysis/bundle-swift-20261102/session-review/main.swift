import Foundation

struct ReviewFailure: Error { let text: String }
func need(_ condition: Bool, _ text: String) throws { if !condition { throw ReviewFailure(text: text) } }
func rejects(_ body: () throws -> Void) throws {
    do { try body() } catch { return }
    throw ReviewFailure(text: "Expected failure")
}
final class ReviewIO: MemoMindTransport {
    var reads: [Data], writes = [Data]()
    init(_ reads: [Data]) { self.reads = reads }
    func read(timeout: TimeInterval) throws -> Data {
        guard !reads.isEmpty else { throw ReviewFailure(text: "No synthetic reply") }
        return reads.removeFirst()
    }
    func write(_ data: Data) throws { writes.append(data) }
}
func packet(_ text: String, event: UInt8 = 37) throws -> Data {
    try GMCodec.frames(event: event, service: 15, command: 125,
                       body: GMTLV(kind: 5, value: Data(text.utf8)).encoded()).reduce(Data(), +)
}
func ack(_ head: UInt8) -> Data {
    var bytes: [UInt8] = [head, 0, 0, 9, 37, 15, 125]
    let sum = bytes.reduce(0) { $0 + Int($1) }
    bytes += [UInt8(sum >> 8), UInt8(sum & 255)]
    return Data(bytes)
}
func value(_ message: GMMessage) -> String { String(decoding: message.tlvs[0].value, as: UTF8.self) }
func select(_ message: GMMessage) throws -> Bool {
    guard message.tlvs.count == 1 && message.tlvs[0].kind == 5 else { throw ReviewFailure(text: "Invalid business schema") }
    switch value(message) {
    case "ok", "invalid": return true
    case "settled": return false
    default: throw ReviewFailure(text: "Unknown business value")
    }
}
var passed = [String]()
func check(_ name: String, _ body: () throws -> Void) throws { try body(); passed.append(name) }
try check("nil final filter preserves historical last-match behavior") {
    let io = try ReviewIO([packet("ok") + packet("settled")])
    let reply = try GMSession(transport: io).request(event: 37, service: 15, command: 125)
    try need(value(reply) == "settled" && io.writes.count == 1, "Default final behavior changed")
}
try check("nil fragment filter preserves historical first-business stop") {
    let io = try ReviewIO([packet("invalid") + packet("settled")])
    let reply = try GMSession(transport: io).request(event: 37, service: 15, command: 125, body: Data(count: 1500))
    try need(value(reply) == "invalid" && io.writes.count == 1, "Default fragment behavior changed")
}
try check("final ACK never calls business filter") {
    let io = try ReviewIO([ack(0xfa) + packet("ok")]); var calls = 0
    let reply = try GMSession(transport: io).request(event: 37, service: 15, command: 125, responseFilter: { calls += 1; return try select($0) })
    try need(value(reply) == "ok" && calls == 1, "ACK reached filter")
}
try check("all continuation ACK heads preserve fragment sequencing") {
    let io = try ReviewIO([packet("settled") + ack(0xfa), ack(1), packet("ok")])
    let session = GMSession(transport: io); var notifications = 0
    session.unsolicited = { _ in notifications += 1 }
    let reply = try session.request(event: 37, service: 15, command: 125, body: Data(count: 1500), responseFilter: select)
    try need(value(reply) == "ok" && io.writes.count == 3 && notifications == 1, "Fragment ACK behavior changed")
}
try check("wrong fragment ACK after a notification stops before next write") {
    let io = try ReviewIO([packet("settled") + ack(1)])
    try rejects { _ = try GMSession(transport: io).request(event: 37, service: 15, command: 125, body: Data(count: 1500), responseFilter: select) }
    try need(io.writes.count == 1, "Retried wrong ACK")
}
try check("coalesced early rejection ACK and notification stop remaining writes") {
    let io = try ReviewIO([packet("invalid") + ack(0xfa) + packet("settled")])
    let session = GMSession(transport: io); var notifications = 0
    session.unsolicited = { _ in notifications += 1 }
    let reply = try session.request(event: 37, service: 15, command: 125, body: Data(count: 1500), responseFilter: select)
    try need(value(reply) == "invalid" && io.writes.count == 1 && notifications == 1, "Early rejection did not stop")
}
try check("filter throw after candidate reply rejects complete read") {
    let io = try ReviewIO([packet("ok") + packet("malformed")])
    try rejects { _ = try GMSession(transport: io).request(event: 37, service: 15, command: 125, responseFilter: select) }
    try need(io.writes.count == 1, "Unexpected retry")
}
try check("notification alone cannot acknowledge request fragment") {
    let io = try ReviewIO([packet("settled")])
    try rejects { _ = try GMSession(transport: io).request(event: 37, service: 15, command: 125, body: Data(count: 1500), responseFilter: select) }
    try need(io.writes.count == 1, "Notification acknowledged a fragment")
}
try check("notifications do not hide duplicate accepted replies") {
    let io = try ReviewIO([packet("ok") + packet("settled") + packet("ok")])
    try rejects { _ = try GMSession(transport: io).request(event: 37, service: 15, command: 125, responseFilter: select) }
}
try check("different-event business message is routed without passing response filter") {
    let io = try ReviewIO([packet("malformed", event: 36) + packet("ok")])
    let session = GMSession(transport: io); var unsolicited = [String](), calls = 0
    session.unsolicited = { unsolicited.append(value($0)) }
    let reply = try session.request(event: 37, service: 15, command: 125, responseFilter: { calls += 1; return try select($0) })
    try need(value(reply) == "ok" && calls == 1 && unsolicited == ["malformed"], "Scope changed")
}
try check("late duplicated prior reply routes to unsolicited on next event") {
    let io = try ReviewIO([packet("ok"), packet("ok") + packet("ok", event: 38)])
    let session = GMSession(transport: io); var events = [UInt8]()
    session.unsolicited = { events.append($0.event) }
    _ = try session.request(event: 37, service: 15, command: 125, responseFilter: select)
    _ = try session.request(event: 38, service: 15, command: 125, responseFilter: select)
    try need(events == [37], "Late duplicate scope changed")
}
let output: [String: Any] = ["checks": passed, "passed": true, "count": passed.count, "device_operations": false]
print(String(decoding: try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys]), as: UTF8.self))
