package ai.glassly.rokid.link

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class FramerTest {
    @Test
    fun framesWithABigEndianLength() {
        assertArrayEquals(byteArrayOf(0, 0, 0, 2, '{'.code.toByte(), '}'.code.toByte()), Framer.frame("{}"))
    }

    @Test
    fun reassemblesAcrossEveryChunkSize() {
        val message = """{"t":"text","text":"héllo wörld, a longer line to split"}"""
        val framed = Framer.frame(message)
        for (size in 1..framed.size + 3) {
            val reassembler = Reassembler()
            val out = Framer.chunks(framed, size).flatMap { reassembler.append(it) }
            assertEquals("chunk size $size", listOf(message), out)
            assertEquals(0, reassembler.pending)
        }
    }

    @Test
    fun cutsTwoMessagesInOneChunkAndHoldsAPartialTail() {
        val first = """{"t":"ping","id":1}"""
        val second = """{"t":"text","text":"x"}"""
        val third = Framer.frame("""{"t":"pong","id":2}""")
        val reassembler = Reassembler()
        val out = reassembler.append(Framer.frame(first) + Framer.frame(second) + third.copyOfRange(0, 6))
        assertEquals(listOf(first, second), out)
        assertEquals(6, reassembler.pending)
        assertEquals(listOf("""{"t":"pong","id":2}"""), reassembler.append(third.copyOfRange(6, third.size)))
    }

    @Test
    fun refusesAnOversizedLengthAndRecovers() {
        val reassembler = Reassembler()
        try {
            reassembler.append(byteArrayOf(0x7F, 0, 0, 0, 1))
            fail("expected FrameTooLarge")
        } catch (expected: FrameTooLarge) {
            assertTrue(expected.length > Framer.MAX_MESSAGE)
        }
        assertEquals(listOf("{}"), reassembler.append(Framer.frame("{}")))
    }

    @Test
    fun chunksCoverTheInputExactly() {
        val bytes = ByteArray(10) { it.toByte() }
        val parts = Framer.chunks(bytes, 4)
        assertEquals(listOf(4, 4, 2), parts.map { it.size })
        assertArrayEquals(bytes, parts.reduce { a, b -> a + b })
    }
}
