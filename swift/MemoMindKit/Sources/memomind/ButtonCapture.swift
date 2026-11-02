import Foundation
import MemoMindCore

func captureButtons(session: GMSession, capture: Capture, seconds: Int) throws -> [String: Any] {
    let observer = ButtonObserverClient(session: session)
    let status = try observer.status()
    guard !status.active else { throw CLIError("A button observer is already active") }
    let nonce = UInt32.random(in: 1 ... UInt32.max)
    let subscription = try observer.subscribe(nonce: nonce)
    try capture.record(["event": "button-subscription", "snapshot": dictionary(subscription)])
    fputs("BUTTON CAPTURE READY: \(seconds) seconds\n", stderr)
    let deadline = ProcessInfo.processInfo.systemUptime + Double(seconds)
    var records = 0
    var drops: UInt32 = 0
    while ProcessInfo.processInfo.systemUptime < deadline {
        let snapshot = try observer.poll()
        try capture.record(["event": "button-poll", "snapshot": dictionary(snapshot)])
        if let last = snapshot.records.last {
            try observer.acknowledge(savedThrough: last.sequence)
            records += snapshot.records.count
            for record in snapshot.records {
                fputs("Button \(record.sequence): \(String(format: "%04x", record.identifier))\n", stderr)
            }
        }
        drops = snapshot.drops
        Thread.sleep(forTimeInterval: 0.25)
    }
    let stopped = try observer.stop()
    try capture.record(["event": "button-stopped", "snapshot": dictionary(stopped)])
    return ["complete": true, "recordsSaved": records, "drops": drops,
            "subscriptionStopped": true, "physicalActionsConfirmed": false, "flashMutations": 0]
}
