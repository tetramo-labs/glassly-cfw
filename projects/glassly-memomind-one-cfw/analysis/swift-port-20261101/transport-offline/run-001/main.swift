#if os(macOS)
    import Foundation
    import IOBluetooth
    import MemoMindCore

    public enum MemoMindBluetoothService: String, Sendable {
        case normal = "00007033-0000-1000-8000-00805f9b34fb"
        case ota = "00007034-0000-1000-8000-00805f9b34fb"

        fileprivate var shortUUID: BluetoothSDPUUID16 {
            self == .normal ? 0x7033 : 0x7034
        }
    }

    public enum RFCOMMError: Error, CustomStringConvertible {
        case mainThreadRequired, reentrantOperation, connectionAlreadyAttempted, invalidAddress
        case invalidTimeout, notConnected, closed, receiveOverflow, invalidMTU, invalidCallback
        case timeout(String), io(String, IOReturn), serviceNotFound(String)

        public var description: String {
            switch self {
            case .mainThreadRequired: "IOBluetooth transport requires the main thread"
            case .reentrantOperation: "A transport operation is already running"
            case .connectionAlreadyAttempted: "Create a new transport for each connection attempt"
            case .invalidAddress: "Expected a six-byte Bluetooth address"
            case .invalidTimeout: "Timeout must be finite, positive, and at most 300 seconds"
            case .notConnected: "RFCOMM channel is not connected"
            case .closed: "RFCOMM channel closed"
            case .receiveOverflow: "RFCOMM receive queue exceeded its byte limit"
            case .invalidMTU: "RFCOMM channel reported a zero MTU"
            case .invalidCallback: "IOBluetooth delivered an invalid data callback"
            case let .timeout(operation): "RFCOMM \(operation) timed out"
            case let .io(operation, status): "RFCOMM \(operation) failed: \(String(format: "0x%08x", status))"
            case let .serviceNotFound(uuid): "SDP did not advertise RFCOMM service \(uuid)"
            }
        }
    }

    /// Submission is logged BEFORE calling IOBluetooth, not a claim of transmission.
    /// Completion means handed to Bluetooth hardware, not acknowledged by the glasses.
    /// RX contains a copy of one callback's bytes; boundaries are not GM frame boundaries.
    public struct RFCOMMTraffic {
        public enum Kind: String, Sendable { case receive, transmitSubmission, transmitCompletion }
        public let kind: Kind
        public let data: Data
        public let status: IOReturn?
        public let timestamp: Date
        public let uptime: TimeInterval
    }

    public struct PairedBluetoothDevice: Sendable {
        public let address: String
        public let name: String?
        public let connected: Bool
    }

    public struct BluetoothHostStatus: Sendable {
        public let available: Bool
        public let powerState: Int?
        public let address: String?
        public let name: String?
    }

    /// Main-thread synchronous facade over asynchronous IOBluetooth operations.
    /// Waits pump the default main run loop, including callbacks for other connections.
    /// Use a fresh instance for every connection attempt, and explicitly close it.
    /// Traffic callbacks must be bounded and must not reenter this transport. Throwing
    /// from a callback stops the connection, allowing durable-log failures to fail closed.
    /// This type is intentionally not Sendable; do not run it on a task pool thread.
    public final class MacRFCOMMTransport: MemoMindTransport {
        private let session: RFCOMMSession
        private let connectTimeout: TimeInterval
        private let writeTimeout: TimeInterval
        private var busy = false
        private var attempted = false

        /// Reads the local paired-device cache; does not scan, pair, or connect.
        public static func pairedDevices() throws -> [PairedBluetoothDevice] {
            guard Thread.isMainThread else { throw RFCOMMError.mainThreadRequired }
            return (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []).compactMap {
                guard let address = $0.addressString else { return nil }
                return PairedBluetoothDevice(address: address, name: $0.name, connected: $0.isConnected())
            }
        }

        /// Reads local controller status without changing power or opening a link.
        public static func hostStatus() throws -> BluetoothHostStatus {
            guard Thread.isMainThread else { throw RFCOMMError.mainThreadRequired }
            guard let host = IOBluetoothHostController.default() else {
                return BluetoothHostStatus(available: false, powerState: nil, address: nil, name: nil)
            }
            return BluetoothHostStatus(available: true, powerState: Int(host.powerState.rawValue),
                                       address: host.addressAsString(), name: host.nameAsString())
        }

        public init(connectTimeout: TimeInterval = 20, writeTimeout: TimeInterval = 10,
                    receiveLimit: Int = 1_048_576,
                    traffic: ((RFCOMMTraffic) throws -> Void)? = nil)
        {
            self.connectTimeout = connectTimeout
            self.writeTimeout = writeTimeout
            session = RFCOMMSession(receiveLimit: receiveLimit, traffic: traffic)
        }

        deinit {
            // Retain the delegate until main-thread cleanup if the caller drops its
            // last reference elsewhere. No IOBluetooth calls run on that thread.
            let retiring = session
            if Thread.isMainThread {
                retiring.fail(RFCOMMError.closed)
            } else {
                DispatchQueue.main.async { retiring.fail(RFCOMMError.closed) }
            }
        }

        public func connect(address: String, service: MemoMindBluetoothService) throws {
            try begin()
            defer { busy = false }
            try validateTimeout(connectTimeout)
            try checkHealth()
            guard !attempted else { throw RFCOMMError.connectionAlreadyAttempted }
            let parts = address.replacingOccurrences(of: "-", with: ":").split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count == 6, parts.allSatisfy({ part in
                part.utf8.count == 2 && part.utf8.allSatisfy {
                    (48 ... 57).contains($0) || (65 ... 70).contains($0) || (97 ... 102).contains($0)
                }
            }),
                let device = IOBluetoothDevice(addressString: parts.joined(separator: ":")),
                let uuid = IOBluetoothSDPUUID(uuid16: service.shortUUID)
            else {
                throw RFCOMMError.invalidAddress
            }
            attempted = true
            session.device = device
            let deadline = ProcessInfo.processInfo.systemUptime + connectTimeout
            do {
                session.sdpPending = true
                session.keepAlive = session
                let queryStatus = device.performSDPQuery(session, uuids: [uuid])
                if queryStatus != kIOReturnSuccess {
                    session.sdpPending = false
                    session.releaseIfQuiescent()
                    throw RFCOMMError.io("SDP submission", queryStatus)
                }
                try wait(until: deadline, operation: "SDP") { !self.session.sdpPending }
                guard let record = device.getServiceRecord(for: uuid) else {
                    throw RFCOMMError.serviceNotFound(service.rawValue)
                }
                var channelID: BluetoothRFCOMMChannelID = 0
                let status = record.getRFCOMMChannelID(&channelID)
                guard status == kIOReturnSuccess, (1 ... 30).contains(channelID) else {
                    throw RFCOMMError.serviceNotFound(service.rawValue)
                }
                session.openPending = true
                session.channelActive = true
                session.keepAlive = session
                let openStatus = device.openRFCOMMChannelAsync(&session.channel, withChannelID: channelID, delegate: session)
                if openStatus != kIOReturnSuccess {
                    session.openPending = false
                    session.channelActive = false
                    session.releaseIfQuiescent()
                    throw RFCOMMError.io("open submission", openStatus)
                }
                try wait(until: deadline, operation: "open") { !self.session.openPending }
                guard session.channel != nil, session.connected else { throw RFCOMMError.notConnected }
            } catch {
                session.fail(error)
                throw error
            }
        }

        public func read(timeout: TimeInterval) throws -> Data {
            try begin()
            defer { busy = false }
            try validateTimeout(timeout)
            try requireConnected()
            // A read timeout alone does not destroy a healthy connection.
            try wait(until: ProcessInfo.processInfo.systemUptime + timeout, operation: "read") {
                !self.session.received.isEmpty
            }
            let result = session.received.removeFirst()
            session.receivedBytes -= result.count
            return result
        }

        public func write(_ data: Data) throws {
            try begin()
            defer { busy = false }
            try validateTimeout(writeTimeout)
            try requireConnected()
            guard let channel = session.channel else { throw RFCOMMError.notConnected }
            let mtu = Int(channel.getMTU())
            guard mtu > 0 else { throw RFCOMMError.invalidMTU }
            let deadline = ProcessInfo.processInfo.systemUptime + writeTimeout
            do {
                var offset = 0
                while offset < data.count {
                    try checkHealth()
                    guard ProcessInfo.processInfo.systemUptime < deadline else { throw RFCOMMError.timeout("write") }
                    let length = min(mtu, Int(UInt16.max), data.count - offset)
                    let start = data.startIndex + offset
                    let chunk = Data(data[start ..< (start + length)])
                    try session.record(.transmitSubmission, data: chunk)
                    try requireConnected()
                    // Stable allocation retained until write completion or confirmed closure.
                    let buffer = NSMutableData(data: chunk)
                    session.writeBuffer = buffer
                    session.keepAlive = session
                    let status = channel.writeAsync(buffer.mutableBytes, length: UInt16(length), refcon: buffer.mutableBytes)
                    if status != kIOReturnSuccess {
                        session.writeBuffer = nil // Header contract: no bytes sent on submission failure.
                        session.releaseIfQuiescent()
                        throw RFCOMMError.io("write submission", status)
                    }
                    try wait(until: deadline, operation: "write") { self.session.writeBuffer == nil }
                    offset += length
                }
            } catch {
                // No retry: the peer may already have received some bytes.
                session.fail(error)
                throw error
            }
        }

        /// Checks a retained failure, including failures on an otherwise idle control channel.
        public func checkHealth() throws {
            guard Thread.isMainThread else { throw RFCOMMError.mainThreadRequired }
            if let error = session.failure {
                throw error
            }
        }

        /// Removes currently buffered unsolicited bytes, without waiting or decoding frames.
        public func drainReceived() throws -> [Data] {
            try begin()
            defer { busy = false }
            try checkHealth()
            let result = session.received
            session.received.removeAll(keepingCapacity: true)
            session.receivedBytes = 0
            return result
        }

        public var lastFailure: Error? {
            session.failure
        }

        public var lastCloseStatus: IOReturn? {
            session.lastCloseStatus
        }

        /// Closes only this RFCOMM channel, preserving another normal/OTA channel's ACL.
        public func close() {
            precondition(Thread.isMainThread, "IOBluetooth close requires the main thread")
            session.fail(RFCOMMError.closed)
        }

        private func begin() throws {
            guard Thread.isMainThread else { throw RFCOMMError.mainThreadRequired }
            guard !busy else { throw RFCOMMError.reentrantOperation }
            busy = true
            // Service other live channels even when this operation completes without
            // entering a wait (e.g. buffered reads or immediately completed writes).
            _ = RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.001))
        }

        private func validateTimeout(_ value: TimeInterval) throws {
            guard value.isFinite, value > 0, value <= 300 else { throw RFCOMMError.invalidTimeout }
        }

        private func requireConnected() throws {
            try checkHealth()
            guard session.connected else { throw RFCOMMError.notConnected }
        }

        private func wait(until deadline: TimeInterval, operation: String, done: () -> Bool) throws {
            while true {
                try checkHealth()
                if done() {
                    return
                }
                let remaining = deadline - ProcessInfo.processInfo.systemUptime
                guard remaining > 0 else { throw RFCOMMError.timeout(operation) }
                _ = RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: min(remaining, 0.01)))
            }
        }
    }

    private final class RFCOMMSession: NSObject, IOBluetoothRFCOMMChannelDelegate {
        var device: IOBluetoothDevice?
        var channel: IOBluetoothRFCOMMChannel?
        var sdpPending = false
        var openPending = false
        var connected = false
        var channelActive = false
        var failure: Error?
        var lastCloseStatus: IOReturn?
        var received: [Data] = []
        var receivedBytes = 0
        var writeBuffer: NSMutableData?
        // IOBluetooth delegate lifetime must cover late asynchronous completions.
        // If the OS never supplies a completion/close callback after timeout, this
        // one-shot session intentionally remains pinned rather than risking a UAF.
        var keepAlive: RFCOMMSession?
        let receiveLimit: Int
        let traffic: ((RFCOMMTraffic) throws -> Void)?

        init(receiveLimit: Int, traffic: ((RFCOMMTraffic) throws -> Void)?) {
            self.receiveLimit = max(0, min(receiveLimit, 16 * 1_048_576))
            self.traffic = traffic
        }

        func record(_ kind: RFCOMMTraffic.Kind, data: Data, status: IOReturn? = nil) throws {
            try traffic?(RFCOMMTraffic(kind: kind, data: data, status: status,
                                       timestamp: Date(), uptime: ProcessInfo.processInfo.systemUptime))
        }

        func releaseIfQuiescent() {
            if !sdpPending, !openPending, !channelActive, writeBuffer == nil {
                keepAlive = nil
            }
        }

        func fail(_ error: Error) {
            if failure == nil {
                failure = error
            }
            connected = false
            if let channel {
                lastCloseStatus = channel.close()
            }
            // No baseband close: another session may own the other service.
            releaseIfQuiescent()
        }

        @objc func sdpQueryComplete(_ device: IOBluetoothDevice!, status: IOReturn) {
            precondition(Thread.isMainThread)
            guard device === self.device, sdpPending else { return }
            sdpPending = false
            if status != kIOReturnSuccess {
                fail(RFCOMMError.io("SDP completion", status))
            }
            releaseIfQuiescent()
        }

        func rfcommChannelOpenComplete(_ channel: IOBluetoothRFCOMMChannel!, status: IOReturn) {
            precondition(Thread.isMainThread)
            guard openPending else { return }
            openPending = false
            if self.channel == nil {
                self.channel = channel
            }
            if status != kIOReturnSuccess {
                channelActive = false
                _ = channel?.setDelegate(nil)
                fail(RFCOMMError.io("open completion", status))
            } else if failure != nil {
                lastCloseStatus = channel?.close()
            } else {
                connected = true
            }
            releaseIfQuiescent()
        }

        func rfcommChannelClosed(_ channel: IOBluetoothRFCOMMChannel!) {
            precondition(Thread.isMainThread)
            guard channel === self.channel else { return }
            connected = false
            channelActive = false
            _ = channel?.setDelegate(nil)
            writeBuffer = nil
            if failure == nil {
                failure = RFCOMMError.closed
            }
            releaseIfQuiescent()
        }

        func rfcommChannelData(_ channel: IOBluetoothRFCOMMChannel!, data pointer: UnsafeMutableRawPointer!, length: Int) {
            precondition(Thread.isMainThread)
            guard channel === self.channel, failure == nil else { return }
            guard length >= 0, length == 0 || pointer != nil else { fail(RFCOMMError.invalidCallback); return }
            guard length > 0 else { return }
            guard received.count < 4096, length <= receiveLimit - receivedBytes else {
                fail(RFCOMMError.receiveOverflow); return
            }
            let data = Data(bytes: pointer, count: length)
            do { try record(.receive, data: data) }
            catch { fail(error); return }
            guard failure == nil else { return }
            received.append(data)
            receivedBytes += length
        }

        func rfcommChannelWriteComplete(_ channel: IOBluetoothRFCOMMChannel!, refcon: UnsafeMutableRawPointer!, status: IOReturn) {
            precondition(Thread.isMainThread)
            guard channel === self.channel, let buffer = writeBuffer, buffer.mutableBytes == refcon else { return }
            writeBuffer = nil
            do { try record(.transmitCompletion, data: buffer as Data, status: status) }
            catch { fail(error) }
            if status != kIOReturnSuccess {
                fail(RFCOMMError.io("write completion", status))
            }
            releaseIfQuiescent()
        }
    }
#endif
#if os(macOS)
var checks = 0
func check(_ value: @autoclosure () -> Bool) {
    precondition(value()); checks += 1
}
func mustThrow(_ body: () throws -> Void) {
    do { try body(); fatalError("expected failure") } catch { checks += 1 }
}
let transport = MacRFCOMMTransport()
mustThrow { _ = try transport.read(timeout: 0) }
mustThrow { _ = try transport.read(timeout: .nan) }
mustThrow { _ = try transport.read(timeout: .infinity) }
mustThrow { try transport.write(Data([1])) }
mustThrow { try transport.connect(address: "not-a-Bluetooth-address", service: .normal) }
let drained = try transport.drainReceived(); check(drained.isEmpty)
transport.close()
mustThrow { try transport.checkHealth() }
check(transport.lastFailure != nil)
let badTimeout = MacRFCOMMTransport(connectTimeout: 0)
mustThrow { try badTimeout.connect(address: "00:00:00:00:00:00", service: .normal) }
check(MemoMindBluetoothService.normal.rawValue == "00007033-0000-1000-8000-00805f9b34fb")
check(MemoMindBluetoothService.ota.rawValue == "00007034-0000-1000-8000-00805f9b34fb")
// Direct delegate-state injection. No IOBluetooth device/channel is constructed;
// nil identity supplies the callback source solely for these offline tests.
var events = [RFCOMMTraffic]()
private let receiver = RFCOMMSession(receiveLimit: 4, traffic: { events.append($0) })
var bytes: [UInt8] = [1,2,3]
bytes.withUnsafeMutableBytes { receiver.rfcommChannelData(nil, data: $0.baseAddress, length: 3) }
bytes[0] = 99
check(receiver.received == [Data([1,2,3])])
check(receiver.receivedBytes == 3)
check(events.count == 1 && events[0].kind == .receive)
bytes.withUnsafeMutableBytes { receiver.rfcommChannelData(nil, data: $0.baseAddress, length: 3) }
check(receiver.failure != nil && receiver.receivedBytes == 3)
private let loggerFailure = RFCOMMSession(receiveLimit: 10, traffic: { _ in throw RFCOMMError.closed })
bytes.withUnsafeMutableBytes { loggerFailure.rfcommChannelData(nil, data: $0.baseAddress, length: 3) }
check(loggerFailure.failure != nil && loggerFailure.received.isEmpty)
private let invalid = RFCOMMSession(receiveLimit: 10, traffic: nil)
invalid.rfcommChannelData(nil, data: nil, length: 1)
check(invalid.failure != nil)
private let writer = RFCOMMSession(receiveLimit: 10, traffic: { events.append($0) })
let pinned = NSMutableData(data: Data([4,5]))
writer.writeBuffer = pinned
writer.keepAlive = writer
writer.rfcommChannelWriteComplete(nil, refcon: pinned.mutableBytes.advanced(by: 1), status: 0)
check(writer.writeBuffer != nil)
writer.rfcommChannelWriteComplete(nil, refcon: pinned.mutableBytes, status: 0)
check(writer.writeBuffer == nil && writer.keepAlive == nil)
check(events.last?.kind == .transmitCompletion && events.last?.data == Data([4,5]))
writer.writeBuffer = pinned
writer.rfcommChannelWriteComplete(nil, refcon: pinned.mutableBytes, status: -1)
check(writer.failure != nil)
private let closed = RFCOMMSession(receiveLimit: 10, traffic: nil)
closed.keepAlive = closed
closed.channelActive = true
closed.releaseIfQuiescent()
check(closed.keepAlive != nil)
closed.rfcommChannelClosed(nil)
check(!closed.connected && closed.failure != nil && closed.keepAlive == nil)
print("PASS \(checks) offline transport checks; no device/controller calls")
#endif
