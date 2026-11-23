package ai.glassly.rokid

import ai.glassly.rokid.link.FrameTooLarge
import ai.glassly.rokid.link.Framer
import ai.glassly.rokid.link.Incoming
import ai.glassly.rokid.link.Messages
import ai.glassly.rokid.link.Reassembler
import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.ParcelUuid
import android.util.Log
import android.view.Display
import java.util.UUID

@SuppressLint("MissingPermission")
class LinkService : Service() {
    private class Peer(val device: BluetoothDevice) {
        var chunkSize = DEFAULT_CHUNK
        var subscribed = false
        val reassembler = Reassembler()
        val outbox = ArrayDeque<ByteArray>()
        var inFlight = false
        var prepared: ByteArray? = null
    }

    private val worker = HandlerThread("GlasslyRokidLink").also { it.start() }
    private val handler = Handler(worker.looper)
    private val peers = mutableMapOf<String, Peer>()
    private var server: BluetoothGattServer? = null
    private var tx: BluetoothGattCharacteristic? = null
    private var advertising = false
    private var opened = false
    private var includeNameInScanResponse = true
    private var batteryLevel = -1
    private var batteryCharging = false
    private var batteryReceiver: BroadcastReceiver? = null

    private val adapter: BluetoothAdapter?
        get() = getSystemService(BluetoothManager::class.java)?.adapter

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        LinkBus.service = this
        if (!startInForeground()) stopSelf()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureRunning()
        return START_STICKY
    }

    // The activity starts the service again once it has been granted the permissions, so the
    // server opens on whichever start first finds them.
    private fun ensureRunning() {
        if (opened) return
        val missing = missingPermissions(this)
        if (missing.isNotEmpty()) {
            Log.e(TAG, "cannot advertise: missing permissions ${missing.joinToString()}")
            LinkBus.state("missing permissions", false)
            return
        }
        opened = true
        registerBattery()
        handler.post { openServer() }
    }

    override fun onDestroy() {
        Log.i(TAG, "link service stopping")
        batteryReceiver?.let { runCatching { unregisterReceiver(it) } }
        handler.post {
            stopAdvertising()
            runCatching { server?.close() }
            server = null
        }
        worker.quitSafely()
        if (LinkBus.service === this) LinkBus.service = null
        LinkBus.state("stopped", false)
        super.onDestroy()
    }

    fun sendKey(key: String) {
        handler.post {
            Log.i(TAG, "key -> phone: $key")
            broadcast(Messages.key(key))
        }
    }

    private fun startInForeground(): Boolean {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, getString(R.string.link_channel), NotificationManager.IMPORTANCE_LOW)
        )
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.link_notification))
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .build()
        return try {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
            true
        } catch (e: Exception) {
            Log.e(TAG, "cannot start the link service in the foreground: ${e.message}")
            LinkBus.state("cannot start: ${e.javaClass.simpleName}", false)
            false
        }
    }

    private fun openServer() {
        val manager = getSystemService(BluetoothManager::class.java)
        if (adapter?.isEnabled != true) {
            Log.e(TAG, "Bluetooth is off; retrying in 5 s")
            LinkBus.state("Bluetooth off", false)
            handler.postDelayed({ openServer() }, 5_000)
            return
        }
        val gatt = manager.openGattServer(this, callback)
        if (gatt == null) {
            Log.e(TAG, "openGattServer returned null; retrying in 5 s")
            LinkBus.state("GATT server unavailable", false)
            handler.postDelayed({ openServer() }, 5_000)
            return
        }
        server = gatt
        val service = BluetoothGattService(SERVICE_UUID, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val rx = BluetoothGattCharacteristic(
            RX_UUID,
            BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
            BluetoothGattCharacteristic.PERMISSION_WRITE,
        )
        val notify = BluetoothGattCharacteristic(
            TX_UUID,
            BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_READ,
        )
        notify.addDescriptor(
            BluetoothGattDescriptor(
                CCCD_UUID,
                BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE,
            )
        )
        service.addCharacteristic(rx)
        service.addCharacteristic(notify)
        tx = notify
        if (!gatt.addService(service)) {
            Log.e(TAG, "addService refused")
            LinkBus.state("addService refused", false)
        }
    }

    private fun startAdvertising() {
        if (advertising || peers.values.any { it.subscribed }) return
        val advertiser = adapter?.bluetoothLeAdvertiser ?: run {
            Log.e(TAG, "no BLE advertiser on this adapter")
            LinkBus.state("no BLE advertiser", false)
            return
        }
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_BALANCED)
            .setConnectable(true)
            .setTimeout(0)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .build()
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(SERVICE_UUID))
            .setIncludeDeviceName(false)
            .build()
        val name = linkName()
        val response = AdvertiseData.Builder()
            .setIncludeDeviceName(includeNameInScanResponse)
            .addManufacturerData(MANUFACTURER_ID, name.toByteArray(Charsets.UTF_8))
            .build()
        Log.i(TAG, "advertising $name (adapter name ${adapter?.name}, name in scan response: $includeNameInScanResponse)")
        advertiser.startAdvertising(settings, data, response, advertiseCallback)
        advertising = true
    }

    private fun stopAdvertising() {
        if (!advertising) return
        runCatching { adapter?.bluetoothLeAdvertiser?.stopAdvertising(advertiseCallback) }
        advertising = false
    }

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
            Log.i(TAG, "advertising started")
            LinkBus.state("advertising as ${linkName()}", false)
        }

        override fun onStartFailure(errorCode: Int) {
            handler.post {
                advertising = false
                if (errorCode == ADVERTISE_FAILED_DATA_TOO_LARGE && includeNameInScanResponse) {
                    Log.w(TAG, "scan response too large with the adapter name; advertising without it")
                    includeNameInScanResponse = false
                    startAdvertising()
                    return@post
                }
                Log.e(TAG, "advertising failed: $errorCode; retrying in 5 s")
                LinkBus.state("advertising failed ($errorCode)", false)
                handler.postDelayed({ startAdvertising() }, 5_000)
            }
        }
    }

    private val callback = object : BluetoothGattServerCallback() {
        override fun onServiceAdded(status: Int, service: BluetoothGattService) {
            handler.post {
                Log.i(TAG, "service added: status $status")
                if (status == BluetoothGatt.GATT_SUCCESS) startAdvertising()
            }
        }

        override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
            handler.post {
                Log.i(TAG, "connection ${device.address}: status $status state $newState")
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    if (peers.isNotEmpty()) Log.w(TAG, "another phone connected while ${peers.keys} is linked")
                    peers[device.address] = Peer(device)
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    peers.remove(device.address)
                    if (peers.values.none { it.subscribed }) {
                        LinkBus.state("disconnected", false)
                        startAdvertising()
                    }
                }
            }
        }

        override fun onMtuChanged(device: BluetoothDevice, mtu: Int) {
            handler.post {
                Log.i(TAG, "mtu ${device.address}: $mtu")
                peers[device.address]?.chunkSize = (mtu - 3).coerceAtLeast(DEFAULT_CHUNK)
            }
        }

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice, requestId: Int, descriptor: BluetoothGattDescriptor,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?,
        ) {
            if (responseNeeded) server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
            if (descriptor.uuid != CCCD_UUID || descriptor.characteristic.uuid != TX_UUID) return
            handler.post {
                val peer = peers.getOrPut(device.address) { Peer(device) }
                val enabled = value != null && value.isNotEmpty() && (value[0].toInt() and 0x01) != 0
                Log.i(TAG, "notifications ${if (enabled) "enabled" else "disabled"} by ${device.address}")
                peer.subscribed = enabled
                if (enabled) {
                    stopAdvertising()
                    LinkBus.state("connected to ${device.name ?: device.address}", true)
                    send(peer, hello())
                    if (batteryLevel >= 0) send(peer, Messages.battery(batteryLevel, batteryCharging))
                }
            }
        }

        override fun onDescriptorReadRequest(
            device: BluetoothDevice, requestId: Int, offset: Int, descriptor: BluetoothGattDescriptor,
        ) {
            val enabled = peers[device.address]?.subscribed == true
            val value = if (enabled) BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE else BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
            server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, 0, value)
        }

        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice, requestId: Int, characteristic: BluetoothGattCharacteristic,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?,
        ) {
            if (responseNeeded) server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
            if (characteristic.uuid != RX_UUID || value == null) return
            handler.post {
                val peer = peers.getOrPut(device.address) { Peer(device) }
                if (preparedWrite) {
                    peer.prepared = (peer.prepared ?: ByteArray(0)) + value
                } else {
                    receive(peer, value)
                }
            }
        }

        override fun onExecuteWrite(device: BluetoothDevice, requestId: Int, execute: Boolean) {
            server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, 0, null)
            handler.post {
                val peer = peers[device.address] ?: return@post
                val bytes = peer.prepared
                peer.prepared = null
                if (execute && bytes != null) receive(peer, bytes)
            }
        }

        override fun onNotificationSent(device: BluetoothDevice, status: Int) {
            handler.post {
                val peer = peers[device.address] ?: return@post
                if (status != BluetoothGatt.GATT_SUCCESS) Log.w(TAG, "notification to ${device.address} failed: $status")
                peer.inFlight = false
                pump(peer)
            }
        }
    }

    private fun receive(peer: Peer, bytes: ByteArray) {
        val messages = try {
            peer.reassembler.append(bytes)
        } catch (e: FrameTooLarge) {
            Log.e(TAG, "dropping the stream from ${peer.device.address}: ${e.message}")
            return
        }
        for (json in messages) {
            when (val message = Messages.decode(json)) {
                is Incoming.Text -> {
                    Log.i(TAG, "text (${message.text.length} chars)")
                    LinkBus.text(message.text)
                }
                is Incoming.Brightness -> {
                    Log.i(TAG, "brightness ${message.level}")
                    LinkBus.brightness(message.level)
                }
                is Incoming.Ping -> send(peer, Messages.pong(message.id))
                is Incoming.Pong -> Log.i(TAG, "pong ${message.id}")
                is Incoming.Unknown -> Log.i(TAG, "ignoring message type ${message.type}")
                null -> Log.w(TAG, "undecodable message: ${json.take(80)}")
            }
        }
    }

    private fun broadcast(json: String) {
        peers.values.filter { it.subscribed }.forEach { send(it, json) }
    }

    private fun send(peer: Peer, json: String) {
        if (!peer.subscribed) return
        Framer.chunks(Framer.frame(json), peer.chunkSize).forEach { peer.outbox.addLast(it) }
        pump(peer)
    }

    // The stack takes one notification per device at a time; the next goes out from
    // onNotificationSent, so chunks of one message never interleave or drop.
    private fun pump(peer: Peer) {
        if (peer.inFlight) return
        val chunk = peer.outbox.removeFirstOrNull() ?: return
        val characteristic = tx ?: return
        val gatt = server ?: return
        val accepted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            gatt.notifyCharacteristicChanged(peer.device, characteristic, false, chunk) == BluetoothStatusCodes.SUCCESS
        } else {
            @Suppress("DEPRECATION")
            characteristic.value = chunk
            @Suppress("DEPRECATION")
            gatt.notifyCharacteristicChanged(peer.device, characteristic, false)
        }
        if (accepted) {
            peer.inFlight = true
        } else {
            Log.w(TAG, "notify refused for ${peer.device.address}; retrying")
            peer.outbox.addFirst(chunk)
            handler.postDelayed({ pump(peer) }, 20)
        }
    }

    private fun hello(): String {
        val mode = getSystemService(DisplayManager::class.java)?.getDisplay(Display.DEFAULT_DISPLAY)?.mode
        val version = runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: ""
        return Messages.hello(serialSuffix(), version, Build.FINGERPRINT, mode?.physicalWidth ?: 480, mode?.physicalHeight ?: 640)
    }

    private fun linkName() = "Glassly-${serialSuffix()}"

    private fun serialSuffix(): String {
        val serial = runCatching { Build.getSerial() }.getOrNull()
        if (!serial.isNullOrBlank() && serial != Build.UNKNOWN && serial.length >= 4) return serial.takeLast(4)
        val name = runCatching { adapter?.name }.getOrNull()
        STOCK_NAME.matchEntire(name ?: "")?.let { return it.groupValues[1] }
        val address = runCatching { adapter?.address }.getOrNull()?.replace(":", "")
        if (!address.isNullOrBlank() && address != "020000000000") return address.takeLast(4)
        return "0000"
    }

    private fun registerBattery() {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100).coerceAtLeast(1)
                val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                val percent = if (level < 0) -1 else level * 100 / scale
                val charging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
                handler.post {
                    if (percent == batteryLevel && charging == batteryCharging) return@post
                    batteryLevel = percent
                    batteryCharging = charging
                    LinkBus.battery(percent)
                    if (percent >= 0) broadcast(Messages.battery(percent, charging))
                }
            }
        }
        batteryReceiver = receiver
        registerReceiver(receiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    }

    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("3968de60-3a92-46f5-b9d7-56e6bd29ecf5")
        val RX_UUID: UUID = UUID.fromString("e6d6ef96-b548-4811-bf63-02a4b65742ac")
        val TX_UUID: UUID = UUID.fromString("f76d2d6c-1755-4c9f-9132-3ccc8eaa6fb6")
        val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        const val MANUFACTURER_ID = 0xFFFF
        private const val DEFAULT_CHUNK = 20
        private const val CHANNEL_ID = "link"
        private const val NOTIFICATION_ID = 1
        private val STOCK_NAME = Regex("Glasses_(\\w{4})")

        val REQUIRED_PERMISSIONS = arrayOf(
            Manifest.permission.BLUETOOTH_ADVERTISE,
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.BLUETOOTH_SCAN,
        )

        fun missingPermissions(context: Context): List<String> =
            REQUIRED_PERMISSIONS.filter { context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }

        fun start(context: Context) {
            try {
                context.startForegroundService(Intent(context, LinkService::class.java))
            } catch (e: Exception) {
                Log.e(TAG, "cannot start the link service: ${e.message}")
            }
        }
    }
}
