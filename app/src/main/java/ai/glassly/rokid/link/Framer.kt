package ai.glassly.rokid.link

object Framer {
    const val MAX_MESSAGE = 65536

    fun frame(json: String): ByteArray {
        val body = json.toByteArray(Charsets.UTF_8)
        require(body.size <= MAX_MESSAGE) { "message of ${body.size} bytes exceeds $MAX_MESSAGE" }
        val out = ByteArray(4 + body.size)
        out[0] = (body.size ushr 24).toByte()
        out[1] = (body.size ushr 16).toByte()
        out[2] = (body.size ushr 8).toByte()
        out[3] = body.size.toByte()
        body.copyInto(out, 4)
        return out
    }

    fun chunks(bytes: ByteArray, size: Int): List<ByteArray> {
        require(size > 0) { "chunk size must be positive" }
        return (bytes.indices step size).map { start -> bytes.copyOfRange(start, minOf(start + size, bytes.size)) }
    }
}

class FrameTooLarge(val length: Int) : Exception("framed message claims $length bytes")

class Reassembler {
    private var buffer = ByteArray(0)

    val pending: Int get() = buffer.size

    fun append(bytes: ByteArray): List<String> {
        buffer += bytes
        val messages = mutableListOf<String>()
        while (buffer.size >= 4) {
            val length = ((buffer[0].toInt() and 0xFF) shl 24) or ((buffer[1].toInt() and 0xFF) shl 16) or
                ((buffer[2].toInt() and 0xFF) shl 8) or (buffer[3].toInt() and 0xFF)
            if (length < 0 || length > Framer.MAX_MESSAGE) {
                buffer = ByteArray(0)
                throw FrameTooLarge(length)
            }
            if (buffer.size < 4 + length) break
            messages += String(buffer, 4, length, Charsets.UTF_8)
            buffer = buffer.copyOfRange(4 + length, buffer.size)
        }
        return messages
    }

    fun reset() {
        buffer = ByteArray(0)
    }
}
