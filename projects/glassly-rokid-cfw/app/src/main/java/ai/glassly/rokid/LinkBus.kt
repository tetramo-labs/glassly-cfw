package ai.glassly.rokid

import android.os.Handler
import android.os.Looper

object LinkBus {
    interface Screen {
        fun onText(text: String)
        fun onBrightness(level: Int)
        fun onStatus()
    }

    private val main = Handler(Looper.getMainLooper())

    @Volatile var screen: Screen? = null
    @Volatile var service: LinkService? = null

    @Volatile var linkState = "starting"
        private set
    @Volatile var batteryLevel = -1
        private set
    @Volatile var lastText = ""
        private set
    @Volatile var connected = false
        private set

    fun state(text: String, isConnected: Boolean) {
        linkState = text
        connected = isConnected
        main.post { screen?.onStatus() }
    }

    fun battery(level: Int) {
        batteryLevel = level
        main.post { screen?.onStatus() }
    }

    fun text(text: String) {
        lastText = text
        main.post { screen?.onText(text) }
    }

    fun brightness(level: Int) {
        main.post { screen?.onBrightness(level) }
    }

    fun sendKey(key: String) {
        service?.sendKey(key)
    }
}
