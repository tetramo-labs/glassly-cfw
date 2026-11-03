import Foundation
import MemoMindCore

func captureOwnership(session: GMSession, capture: Capture, seconds: Int) throws -> [String: Any] {
    var event: UInt8 = 0x20
    var cleanupAttempted = false
    var pendingNonce: UInt16?
    var eventError: Error?
    var buttonEvents = 0
    var handshakes = 0
    var lastDraw = 0.0
    var version = ""
    func control(_ command: OwnershipCommand, nonce: UInt16 = 1) throws -> OwnershipSnapshot {
        let state = try session.ownership(command, nonce: nonce, event: &event)
        try capture.record(["event": "ownership-state", "operation": command.rawValue, "state": dictionary(state)])
        return state
    }
    func graphics(_ bytes: Data, result: String = "ok") throws {
        event = event == 255 ? 1 : event + 1
        let reply = try session.request(event: event, service: 15, command: 0x7D, body: GMTLV(kind: 1, value: bytes).encoded())
        guard reply.tlvs.count == 1, reply.tlvs[0].kind == 5 else { throw CLIError("Expected graphics JSON") }
        struct Reply: Decodable { let result: String }
        var data = reply.tlvs[0].value
        while data.last == 0 {
            data.removeLast()
        }
        guard try JSONDecoder().decode(Reply.self, from: data).result == result else { throw CLIError("Display command refused") }
    }
    func draw() throws {
        try graphics(RasterCommands.fullFrame(pixels: Data(repeating: 0, count: 105_000)))
        try graphics(RasterCommands.builtinText(bytes: Data(version.utf8), x: 20, y: 30))
        try graphics(RasterCommands.builtinText(bytes: Data("WAKE / FRAME LEASE".utf8), x: 20, y: 80))
        lastDraw = ProcessInfo.processInfo.systemUptime
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
    version = capabilities.version
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
            buttonEvents += 1
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
    try graphics(Data([11]), result: "cleared")
    guard try control(.acquireWake).wakeLease else { throw CLIError("Wake lease refused") }
    guard try control(.acquireFrame).frameLease else { throw CLIError("Frame lease refused") }
    let began = ProcessInfo.processInfo.systemUptime
    try draw()
    guard try control(.status).framePresented else { throw CLIError("Frame was not presented") }
    try capture.record(["event": "ownership-display-ready"])
    fputs("OWNERSHIP DISPLAY READY: \(version); WAKE / FRAME LEASE\n", stderr)
    var preserved = false
    var expired = false
    while ProcessInfo.processInfo.systemUptime - began < Double(seconds) {
        if let error = eventError {
            throw error
        }
        if let nonce = pendingNonce {
            pendingNonce = nil
            let claimed = try control(.claim, nonce: nonce)
            if claimed.pending, claimed.nonce == nonce, claimed.frameLease {
                try draw()
                let ready = try control(.ready, nonce: nonce)
                guard !ready.pending else { throw CLIError("Wake READY did not complete") }
                handshakes += 1
                try capture.record(["event": "ownership-handshake-complete", "nonce": nonce])
            }
        }
        let state = try control(.status)
        let elapsed = ProcessInfo.processInfo.systemUptime - began
        if ProcessInfo.processInfo.systemUptime - lastDraw >= 35, elapsed < 85, state.framePresented, state.frameLease, !preserved {
            preserved = true
            try capture.record(["event": "ownership-frame-preserved", "elapsedSinceDrawSeconds": ProcessInfo.processInfo.systemUptime - lastDraw, "screenOn": state.screenOn])
            fputs("FRAME PRESERVED PAST 35 SECONDS\n", stderr)
        }
        if elapsed >= 91, !state.frameLease, !state.wakeLease, !state.framePresented {
            expired = true
        }
        Thread.sleep(forTimeInterval: 0.1)
    }
    cleanupAttempted = true
    let frame = try control(.releaseFrame)
    let wake = try control(.releaseWake)
    guard !frame.frameLease, !wake.wakeLease else { throw CLIError("Ownership cleanup failed") }
    return ["complete": true, "buttonEvents": buttonEvents, "wakeHandshakes": handshakes,
            "framePreservedPast35Seconds": preserved, "leasesExpired": expired,
            "cleanupVerified": true, "physicalOutputConfirmed": false, "flashMutations": 0]
}
