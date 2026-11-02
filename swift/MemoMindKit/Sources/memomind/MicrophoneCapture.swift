import Foundation
import MemoMindBluetooth
import MemoMindCore

func captureMicrophone(session: GMSession, recording: MacRFCOMMTransport,
                       address: String, capture: Capture, seconds: Int) throws -> [String: Any]
{
    let parser = RecordingStream()
    var startSent = false
    var stopSubmitted = false
    defer {
        if startSent, !stopSubmitted {
            do {
                try recording.write(Data([0x52, 0, 0]))
                try capture.record(["event": "microphone-error-stop-submitted", "acknowledged": false])
            } catch { fputs("Microphone cleanup failed: \(error)\n", stderr) }
        }
        recording.close()
    }
    let configured = try session.request(event: 0x60, service: 1, command: 0x2F,
                                         body: GMTLV(kind: 8, value: Data([0])).encoded())
    guard configured.tlvs == [GMTLV(kind: 6, value: Data([0]))] else {
        throw CLIError("Microphone configuration refused")
    }
    try capture.record(["event": "microphone-configured", "noiseMode": 0, "pickupModeChanged": false])
    try recording.connect(address: address, service: .recording)
    try capture.record(["event": "recording-connected", "service": MemoMindBluetoothService.recording.rawValue,
                        "channel": recording.resolvedChannelID as Any? ?? NSNull()])
    try recording.write(Data([0x52, 0x12, 0]))
    var negotiated = false
    do {
        for event in try parser.feed(recording.read(timeout: 0.8)) {
            guard case .format(.legacy) = event else { throw CLIError("Recording already active or unexpected format") }
            negotiated = true
        }
    } catch RFCOMMError.timeout("read") {
        guard parser.pendingBytes == 0 else { throw CLIError("Incomplete recording negotiation") }
    }
    guard parser.pendingBytes == 0 else { throw CLIError("Incomplete recording negotiation") }
    try capture.record(["event": "recording-format", "format": "legacy", "acknowledged": negotiated])
    startSent = true
    try recording.write(Data([0x52, 1, 0]))
    fputs("MICROPHONE CAPTURE STARTED: \(seconds) seconds\n", stderr)
    let began = ProcessInfo.processInfo.systemUptime
    var started = false
    var frames = 0
    var tailFrames = 0
    func receive(_ timeout: Double, tail: Bool) throws {
        let events: [RecordingEvent]
        do { events = try parser.feed(recording.read(timeout: timeout)) }
        catch RFCOMMError.timeout("read") { return }
        for event in events {
            switch event {
            case let .format(format):
                guard format == .legacy else { throw CLIError("Recording format changed") }
                try capture.record(["event": "recording-format-confirmed", "mode": format.rawValue])
            case let .started(noise, timestamp):
                guard !started, !tail else { throw CLIError("Unexpected recording restart") }
                started = true
                try capture.record(["event": "microphone-start-notification", "noiseMode": noise,
                                    "producerTimestamp": timestamp,
                                    "latencySeconds": ProcessInfo.processInfo.systemUptime - began])
            case let .audio(command, metadata, packets):
                guard command == 0x92 else { throw CLIError("Another recording stream became active") }
                let hex = packets.map { $0.map { String(format: "%02x", $0) }.joined() }
                try capture.record(["event": "opus-frames", "packetsHex": hex,
                                    "metadataHex": metadata.map { String(format: "%02x", $0) }.joined(),
                                    "afterStop": tail])
                frames += packets.count
                if tail {
                    tailFrames += packets.count
                }
            }
        }
    }
    let deadline = began + Double(seconds)
    while ProcessInfo.processInfo.systemUptime < deadline {
        try receive(max(0.001, min(0.5, deadline - ProcessInfo.processInfo.systemUptime)), tail: false)
        if !started, ProcessInfo.processInfo.systemUptime - began >= 5 {
            throw CLIError("Microphone start notification timed out")
        }
    }
    try recording.write(Data([0x52, 0, 0]))
    stopSubmitted = true
    try capture.record(["event": "microphone-stop-submitted", "acknowledged": false])
    let drainDeadline = ProcessInfo.processInfo.systemUptime + 1
    while ProcessInfo.processInfo.systemUptime < drainDeadline {
        try receive(max(0.001, min(0.25, drainDeadline - ProcessInfo.processInfo.systemUptime)), tail: true)
    }
    guard started, frames > 0 else { throw CLIError("No confirmed microphone stream") }
    return ["complete": true, "startNotificationReceived": started, "framesSaved": frames,
            "formatNegotiated": negotiated, "recordBytes": 49, "opusBytesPerFrame": 40,
            "stopSubmitted": stopSubmitted, "stopAcknowledged": false, "stopTailFrames": tailFrames,
            "trailingBytes": parser.pendingBytes, "audioDecoded": false, "flashMutations": 0]
}
