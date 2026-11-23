package ai.glassly.rokid

import android.app.Activity
import android.app.role.RoleManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView

class HomeActivity : Activity(), LinkBus.Screen {
    private lateinit var status: TextView
    private lateinit var message: TextView
    private val gestures = GestureKeys { LinkBus.sendKey(it) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        status = TextView(this).apply {
            setTextColor(STATUS_GREEN)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            typeface = Typeface.SANS_SERIF
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(16, 12, 16, 0)
        }
        message = TextView(this).apply {
            setTextColor(GREEN)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            typeface = Typeface.SANS_SERIF
            gravity = Gravity.CENTER
            setPadding(24, 48, 24, 24)
        }
        root.addView(message, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addView(
            status,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP),
        )
        setContentView(root)
        hideSystemBars()
        LinkService.start(this)
    }

    override fun onResume() {
        super.onResume()
        LinkBus.screen = this
        onText(LinkBus.lastText)
        onStatus()
        val missing = LinkService.missingPermissions(this)
        if (missing.isNotEmpty()) {
            Log.w(TAG, "requesting ${missing.joinToString()}")
            requestPermissions(missing.toTypedArray(), PERMISSION_REQUEST)
        }
    }

    override fun onPause() {
        if (LinkBus.screen === this) LinkBus.screen = null
        super.onPause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST) return
        Log.i(TAG, "permissions: ${permissions.zip(grantResults.toList()).joinToString()}")
        LinkService.start(this)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    override fun onText(text: String) {
        message.text = text
    }

    override fun onBrightness(level: Int) {
        window.attributes = window.attributes.apply { screenBrightness = (level / 100f).coerceIn(0.01f, 1f) }
    }

    override fun onStatus() {
        val battery = LinkBus.batteryLevel.takeIf { it >= 0 }?.let { "  ·  $it%" } ?: ""
        status.text = "${LinkBus.linkState}$battery"
        if (LinkBus.connected) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        logKey("down", keyCode, event)
        val role = KEY_TABLE[keyCode] ?: return super.onKeyDown(keyCode, event)
        gestures.onDown(role, event)
        if (role == KeyRole.BACK && !isHome()) return super.onKeyDown(keyCode, event)
        return true
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        logKey("up", keyCode, event)
        val role = KEY_TABLE[keyCode] ?: return super.onKeyUp(keyCode, event)
        gestures.onUp(role, event)
        if (role == KeyRole.BACK && !isHome()) return super.onKeyUp(keyCode, event)
        return true
    }

    @Deprecated("Back is handled in onKeyDown so the home screen never closes")
    override fun onBackPressed() {
        if (!isHome()) super.onBackPressed()
    }

    private fun isHome(): Boolean =
        runCatching { getSystemService(RoleManager::class.java).isRoleHeld(RoleManager.ROLE_HOME) }.getOrDefault(false)

    private fun logKey(phase: String, keyCode: Int, event: KeyEvent) {
        val mapped = KEY_TABLE[keyCode]?.name ?: "unmapped"
        Log.i(
            TAG,
            "key $phase code=$keyCode ${KeyEvent.keyCodeToString(keyCode)} scan=${event.scanCode} " +
                "repeat=${event.repeatCount} source=0x${Integer.toHexString(event.source)} " +
                "device=${event.device?.name} -> $mapped",
        )
    }

    private fun hideSystemBars() {
        window.insetsController?.let {
            it.hide(WindowInsets.Type.systemBars())
            it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN
    }

    companion object {
        private const val PERMISSION_REQUEST = 1
        private val GREEN = Color.rgb(0, 255, 0)
        private val STATUS_GREEN = Color.rgb(0, 160, 0)
    }
}
