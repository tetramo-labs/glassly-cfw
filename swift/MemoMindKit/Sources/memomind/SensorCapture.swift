import Foundation
import MemoMindCore

func captureSensors(session: GMSession, capture: Capture, seconds: Int) throws -> [String: Any] {
    var event: UInt8 = 0x40
    try SensorCaptureSnapshot.validateCapability(session.request(event: event, service: 15, command: 0x7E))
    let initial = try session.sensorCapture(.status, event: &event)
    guard initial.activeMask == 0 else { throw CLIError("A sensor capture is already active") }
    var started = false
    defer {
        if started {
            _ = try? session.sensorCapture(.stop, event: &event)
        }
    }
    let start = try session.sensorCapture(.start, event: &event)
    started = true
    try capture.record(["event": "sensor-start", "snapshot": dictionary(start)])
    let deadline = ProcessInfo.processInfo.systemUptime + Double(seconds)
    var renewal = ProcessInfo.processInfo.systemUptime
    var acknowledged: UInt32 = 0, sequence: UInt32 = 0, drops: UInt32 = 0
    var imuSamples = 0, lightSamples = 0, missed: UInt64 = 0
    while ProcessInfo.processInfo.systemUptime < deadline {
        let now = ProcessInfo.processInfo.systemUptime
        if now - renewal >= 30 {
            let state = try session.sensorCapture(.renew, event: &event)
            guard state.generation == start.generation else { throw CLIError("Sensor capture ownership changed") }
            renewal = now
        }
        let batch = try session.sensorBatch(generation: start.generation, acknowledged: acknowledged, event: &event)
        guard batch.sequence >= sequence, batch.drops >= drops else { throw CLIError("Sensor counters moved backwards") }
        try capture.record(["event": "sensor-batch", "batch": dictionary(batch)])
        if let first = batch.samples.first {
            missed += UInt64(first.sequence - acknowledged - 1)
        }
        for sample in batch.samples {
            if sample.imu != nil {
                imuSamples += 1
            }
            if sample.light != nil {
                lightSamples += 1
            }
        }
        if let last = batch.samples.last {
            acknowledged = last.sequence
        }
        sequence = batch.sequence; drops = batch.drops
        if batch.pending <= batch.samples.count {
            Thread.sleep(forTimeInterval: 0.1)
        }
    }
    let stopped = try session.sensorCapture(.stop, event: &event)
    started = false
    try capture.record(["event": "sensor-stopped", "snapshot": dictionary(stopped)])
    return ["complete": true, "passiveCapture": true, "imuSnapshotsSaved": imuSamples, "lightSnapshotsSaved": lightSamples,
            "subscriptionStopped": true, "physicalUnitsVerified": false, "flashMutations": 0,
            "missingSequences": missed, "reportedOverwrites": drops, "lastSavedSequence": acknowledged,
            "stopDiscardsUnread": true, "losslessCapture": false]
}
