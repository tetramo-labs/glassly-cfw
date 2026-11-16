package ai.glassly.rokid.link

import org.json.JSONObject

sealed class Incoming {
    data class Text(val text: String) : Incoming()
    data class Brightness(val level: Int) : Incoming()
    data class Ping(val id: Any?) : Incoming()
    data class Pong(val id: Any?) : Incoming()
    data class Unknown(val type: String) : Incoming()
}

object Messages {
    const val VERSION = 1
    const val MODEL = "Rokid Glasses"

    fun hello(serial: String, app: String, build: String, canvasWidth: Int, canvasHeight: Int): String =
        JSONObject()
            .put("t", "hello")
            .put("v", VERSION)
            .put("model", MODEL)
            .put("serial", serial)
            .put("app", app)
            .put("build", build)
            .put("canvas", JSONObject().put("w", canvasWidth).put("h", canvasHeight))
            .toString()

    fun key(key: String): String = JSONObject().put("t", "key").put("key", key).toString()

    fun battery(level: Int, charging: Boolean): String =
        JSONObject().put("t", "battery").put("level", level.coerceIn(0, 100)).put("charging", charging).toString()

    fun ping(id: Any?): String = JSONObject().put("t", "ping").put("id", id ?: JSONObject.NULL).toString()

    fun pong(id: Any?): String = JSONObject().put("t", "pong").put("id", id ?: JSONObject.NULL).toString()

    fun decode(json: String): Incoming? {
        val obj = runCatching { JSONObject(json) }.getOrNull() ?: return null
        val type = obj.optString("t").ifEmpty { return null }
        return when (type) {
            "text" -> Incoming.Text(obj.optString("text"))
            "brightness" -> Incoming.Brightness(obj.optInt("level", -1).coerceIn(0, 100))
            "ping" -> Incoming.Ping(obj.opt("id").takeUnless { it == JSONObject.NULL })
            "pong" -> Incoming.Pong(obj.opt("id").takeUnless { it == JSONObject.NULL })
            else -> Incoming.Unknown(type)
        }
    }
}
