import Foundation
import MemoMindCore

/// Sweep the glasses' font repertoire through mode-15 text drawn off the
/// panel, under a wake and frame lease, and save the measured runs. Only the
/// retained-scene firmware with text commands (GLASSLYCFW/10+) answers; the
/// result pins MemoMindOneRenderer's inline allowlist in glassly.
func captureFontProbe(session: GMSession, capture: Capture, from: UInt32 = 0, sampled: Bool = false, missBudget: Int = 0) throws -> [String: Any] {
    var event: UInt8 = 0x30
    var pendingNonce: UInt16?
    var eventError: Error?
    var cleanupAttempted = false
    func control(_ command: OwnershipCommand, nonce: UInt16 = 1) throws -> OwnershipSnapshot {
        let state = try session.ownership(command, nonce: nonce, event: &event)
        try capture.record(["event": "ownership-state", "operation": command.rawValue, "state": dictionary(state)])
        return state
    }
    func graphics(_ bytes: Data) throws -> String {
        event = event == 255 ? 1 : event + 1
        let reply = try session.request(event: event, service: 15, command: 0x7D, body: GMTLV(kind: 1, value: bytes).encoded())
        guard reply.tlvs.count == 1, reply.tlvs[0].kind == 5 else { throw CLIError("Expected graphics JSON") }
        struct Reply: Decodable { let result: String }
        var data = reply.tlvs[0].value
        while data.last == 0 {
            data.removeLast()
        }
        return try JSONDecoder().decode(Reply.self, from: data).result
    }
    struct Capabilities: Decodable {
        struct Ownership: Decodable {
            let command: Int
            let leaseTicks: Int
            let fallbackTicks: Int
            let claimedTicks: Int
        }

        let version: String
        let ownership: Ownership
    }
    let reply = try session.request(event: event, service: 15, command: 0x7E)
    guard reply.tlvs.count == 1, reply.tlvs[0].kind == 5 else { throw CLIError("Missing ownership capability") }
    var json = reply.tlvs[0].value
    while json.last == 0 {
        json.removeLast()
    }
    let capabilities = try JSONDecoder().decode(Capabilities.self, from: json)
    guard capabilities.version.range(of: "^GLASSLYCFW/[0-9]+$", options: .regularExpression) != nil else {
        throw CLIError("Unsupported firmware version")
    }
    let capability = capabilities.ownership
    guard capability.command == 121, capability.leaseTicks == 90000,
          capability.fallbackTicks == 400, capability.claimedTicks == 5000
    else {
        throw CLIError("Unsupported ownership contract")
    }
    session.unsolicited = { message in
        guard message.service == 15, message.command == 0x79 else { return }
        do {
            let state = try OwnershipSnapshot.decode(message)
            try capture.record(["event": "ownership-button", "state": dictionary(state)])
            if state.event == .wake {
                pendingNonce = state.nonce
            }
        } catch { eventError = error }
    }
    defer {
        session.unsolicited = nil
        if !cleanupAttempted {
            _ = try? control(.releaseFrame)
            _ = try? control(.releaseWake)
        }
    }
    guard try graphics(Data([11])) == "cleared" else { throw CLIError("Display command refused") }
    guard try control(.acquireWake).wakeLease else { throw CLIError("Wake lease refused") }
    guard try control(.acquireFrame).frameLease else { throw CLIError("Frame lease refused") }
    // A dark panel for the whole sweep: the probe strings are placed off it.
    guard try graphics(RasterCommands.fullFrame(pixels: Data(repeating: 0, count: 105_000))) == "ok" else {
        throw CLIError("Display command refused")
    }
    guard try control(.status).framePresented else { throw CLIError("Frame was not presented") }
    try capture.record(["event": "font-probe-display-ready", "version": capabilities.version])
    fputs("FONT PROBE: \(capabilities.version); sweeping \(FontProbe.blocks.count) blocks from U+\(String(from, radix: 16, uppercase: true))\n", stderr)
    var lastRenewal = ProcessInfo.processInfo.systemUptime
    let began = lastRenewal
    let report = try FontProbe.probe(from: from, sampled: sampled, missBudget: missBudget, draw: { bytes in
        if let error = eventError {
            throw error
        }
        if let nonce = pendingNonce {
            pendingNonce = nil
            let claimed = try control(.claim, nonce: nonce)
            if claimed.pending, claimed.nonce == nonce {
                guard try !control(.ready, nonce: nonce).pending else { throw CLIError("Wake READY did not complete") }
            }
        }
        if ProcessInfo.processInfo.systemUptime - lastRenewal >= 30 {
            guard try control(.acquireWake).wakeLease, try control(.acquireFrame).frameLease else {
                throw CLIError("Lease renewal refused")
            }
            lastRenewal = ProcessInfo.processInfo.systemUptime
        }
        let result = try graphics(RasterCommands.builtinText(bytes: bytes, x: -4000, y: -4000))
        try capture.record(["event": "font-probe-string", "hex": bytes.map { String(format: "%02x", $0) }.joined(), "result": result])
        switch result {
        case "ok": return true
        case "invalid": return false
        default: throw CLIError("Display command refused: \(result)")
        }
    }, progress: { block in
        try? capture.record(["event": "font-probe-block", "block": (try? dictionary(block)) ?? [:]])
        fputs("\(block.name): \(block.present) present, \(block.absent) absent, \(block.unresolved) unresolved (\(block.requests) requests)\n", stderr)
    })
    cleanupAttempted = true
    let frame = try control(.releaseFrame)
    let wake = try control(.releaseWake)
    guard !frame.frameLease, !wake.wakeLease else { throw CLIError("Ownership cleanup failed") }
    try capture.save(try dictionary(report), name: "font-repertoire.json")
    fputs("SWIFT: \(report.swiftRanges)\nKOTLIN: \(report.kotlinRanges)\n", stderr)
    if let next = report.nextScalar {
        fputs("MISS BUDGET REACHED (\(report.misses) misses); resume with --from U+\(String(next, radix: 16, uppercase: true))\n", stderr)
    }
    return ["complete": report.nextScalar == nil, "version": capabilities.version, "requests": report.requests, "from": from,
            "sampled": sampled, "missBudget": missBudget, "misses": report.misses,
            "nextScalar": report.nextScalar.map { String(format: "U+%04X", $0) } as Any,
            "elapsedSeconds": ProcessInfo.processInfo.systemUptime - began,
            "runs": report.runs.map { ["first": $0.first, "last": $0.last] },
            "blocks": try report.blocks.map { try dictionary($0) },
            "swiftRanges": report.swiftRanges, "kotlinRanges": report.kotlinRanges,
            "cleanupVerified": true, "physicalOutputConfirmed": false, "flashMutations": 0]
}
