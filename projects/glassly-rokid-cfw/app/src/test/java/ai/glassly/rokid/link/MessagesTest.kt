package ai.glassly.rokid.link

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MessagesTest {
    @Test
    fun helloCarriesTheProtocolFields() {
        val hello = JSONObject(Messages.hello("2996", "0.1.0-dev", "rokid/fp", 480, 640))
        assertEquals("hello", hello.getString("t"))
        assertEquals(1, hello.getInt("v"))
        assertEquals("Rokid Glasses", hello.getString("model"))
        assertEquals("2996", hello.getString("serial"))
        assertEquals("0.1.0-dev", hello.getString("app"))
        assertEquals("rokid/fp", hello.getString("build"))
        assertEquals(480, hello.getJSONObject("canvas").getInt("w"))
        assertEquals(640, hello.getJSONObject("canvas").getInt("h"))
    }

    @Test
    fun outgoingMessagesHaveTheirFields() {
        assertEquals("swipe_up", JSONObject(Messages.key("swipe_up")).getString("key"))
        val battery = JSONObject(Messages.battery(120, true))
        assertEquals("battery", battery.getString("t"))
        assertEquals(100, battery.getInt("level"))
        assertEquals(true, battery.getBoolean("charging"))
        assertEquals(7, JSONObject(Messages.pong(7)).getInt("id"))
    }

    @Test
    fun decodesIncomingMessages() {
        assertEquals(Incoming.Text("hi"), Messages.decode("""{"t":"text","text":"hi"}"""))
        assertEquals(Incoming.Text(""), Messages.decode("""{"t":"text","text":""}"""))
        assertEquals(Incoming.Brightness(100), Messages.decode("""{"t":"brightness","level":250}"""))
        assertEquals(Incoming.Ping(3), Messages.decode("""{"t":"ping","id":3}"""))
        assertEquals(Incoming.Ping("a"), Messages.decode("""{"t":"ping","id":"a"}"""))
        assertEquals(Incoming.Unknown("scene"), Messages.decode("""{"t":"scene"}"""))
    }

    @Test
    fun ignoresGarbage() {
        assertNull(Messages.decode("not json"))
        assertNull(Messages.decode("""{"text":"no type"}"""))
    }
}
