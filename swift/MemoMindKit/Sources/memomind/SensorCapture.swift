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
    var lastIMU: UInt32 = 0, lastLight: UInt32 = 0
    var imuSamples = 0, lightSamples = 0
    while ProcessInfo.processInfo.systemUptime < deadline {
        let now = ProcessInfo.processInfo.systemUptime
        let state = try session.sensorCapture(now - renewal >= 30 ? .renew : .status, event: &event)
        if now - renewal >= 30 {
            renewal = now
        }
        guard state.generation == start.generation, state.activeMask == 3 else { throw CLIError("Sensor capture ownership changed") }
        try capture.record(["event": "sensor-snapshot", "snapshot": dictionary(state)])
        if let imu = state.imu, imu.sequence != lastIMU {
            imuSamples += 1; lastIMU = imu.sequence
        }
        if let light = state.light, light.sequence != lastLight {
            lightSamples += 1; lastLight = light.sequence
        }
        Thread.sleep(forTimeInterval: 0.1)
    }
    let stopped = try session.sensorCapture(.stop, event: &event)
    started = false
    try capture.record(["event": "sensor-stopped", "snapshot": dictionary(stopped)])
    return ["complete": true, "passiveCapture": true, "imuSnapshotsSaved": imuSamples, "lightSnapshotsSaved": lightSamples,
            "subscriptionStopped": true, "physicalUnitsVerified": false, "flashMutations": 0]
}
