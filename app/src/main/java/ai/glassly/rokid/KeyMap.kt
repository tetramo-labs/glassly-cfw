package ai.glassly.rokid

import android.os.Handler
import android.os.Looper
import android.view.KeyEvent

enum class KeyRole { SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN, SELECT, BACK }

// The real touchpad and AI-key codes are unknown until the probe runs; every key the activity
// sees is logged, and this table is the one place to map them.
val KEY_TABLE: Map<Int, KeyRole> = mapOf(
    KeyEvent.KEYCODE_DPAD_LEFT to KeyRole.SWIPE_LEFT,
    KeyEvent.KEYCODE_DPAD_RIGHT to KeyRole.SWIPE_RIGHT,
    KeyEvent.KEYCODE_DPAD_UP to KeyRole.SWIPE_UP,
    KeyEvent.KEYCODE_DPAD_DOWN to KeyRole.SWIPE_DOWN,
    KeyEvent.KEYCODE_DPAD_CENTER to KeyRole.SELECT,
    KeyEvent.KEYCODE_ENTER to KeyRole.SELECT,
    KeyEvent.KEYCODE_BACK to KeyRole.BACK,
)

class GestureKeys(private val emit: (String) -> Unit) {
    private val handler = Handler(Looper.getMainLooper())
    private var downAt = 0L
    private var longFired = false
    private var tapPending = false

    private val longPress = Runnable {
        longFired = true
        tapPending = false
        handler.removeCallbacks(singleTap)
        emit("long_press")
    }
    private val singleTap = Runnable {
        tapPending = false
        emit("tap")
    }

    fun onDown(role: KeyRole, event: KeyEvent) {
        if (event.repeatCount > 0) return
        when (role) {
            KeyRole.SWIPE_LEFT -> emit("swipe_left")
            KeyRole.SWIPE_RIGHT -> emit("swipe_right")
            KeyRole.SWIPE_UP -> emit("swipe_up")
            KeyRole.SWIPE_DOWN -> emit("swipe_down")
            KeyRole.BACK -> emit("back")
            KeyRole.SELECT -> {
                downAt = event.eventTime
                longFired = false
                handler.postDelayed(longPress, LONG_PRESS_MS)
            }
        }
    }

    fun onUp(role: KeyRole, event: KeyEvent) {
        if (role != KeyRole.SELECT) return
        handler.removeCallbacks(longPress)
        if (longFired || event.eventTime - downAt >= LONG_PRESS_MS) {
            if (!longFired) emit("long_press")
            longFired = false
            return
        }
        if (tapPending) {
            tapPending = false
            handler.removeCallbacks(singleTap)
            emit("double_tap")
        } else {
            tapPending = true
            handler.postDelayed(singleTap, DOUBLE_TAP_MS)
        }
    }

    companion object {
        const val LONG_PRESS_MS = 600L
        const val DOUBLE_TAP_MS = 300L
    }
}
