/* GLASSLYCFW runtime for NIMO, first revision: proves appended code runs from
 * the stock command router. Command 0x7E (unused by stock firmware):
 *   key 0x01  identity/capabilities JSON
 *   key 0x02  echo the payload
 *   key 0x10  draw a test pattern on the panel from the UI task; [pattern]
 *             (0 gray bars, 1 border + diagonal, 2 black); replies when shown
 *             with [status][flush rc][left]
 * Replies are [status][data...] through the stock response path. */
#include <stdint.h>
#include "stock.h"

#ifndef GLASSLY_CFW_REVISION
#error "GLASSLY_CFW_REVISION is required"
#endif
#define STR2(x) #x
#define STR(x) STR2(x)

enum { GLASSLY_CMD = 0x7E, KEY_IDENTITY = 0x01, KEY_ECHO = 0x02, KEY_DRAW_TEST = 0x10 };
enum { STATUS_OK = 0, STATUS_FAILED = 1, STATUS_UNSUPPORTED = 5, STATUS_BUSY = 6, REPLY_MAX = 500 };
enum { FRAME_BYTES = NIMO_PANEL_STRIDE * NIMO_PANEL_H };

static void put(uint8_t *fb, uint32_t x, uint32_t y, uint32_t level)
{
    uint8_t *p = fb + y * NIMO_PANEL_STRIDE + (x >> 1);
    *p = (x & 1u) ? (uint8_t)((*p & 0xF0u) | (level & 0x0Fu)) : (uint8_t)((*p & 0x0Fu) | (level << 4));
}

static void fill_rect(uint8_t *fb, uint32_t x0, uint32_t y0, uint32_t w, uint32_t h, uint32_t level)
{
    for (uint32_t y = y0; y < y0 + h && y < NIMO_PANEL_H; y++)
        for (uint32_t x = x0; x < x0 + w && x < NIMO_PANEL_W; x++) put(fb, x, y, level);
}

static void draw_pattern(uint8_t *fb, uint32_t pattern, int left)
{
    for (uint32_t i = 0; i < FRAME_BYTES; i++) fb[i] = 0;
    if (pattern == 0) {
        for (uint32_t x = 0; x < NIMO_PANEL_W; x++)
            for (uint32_t y = 0; y < NIMO_PANEL_H; y++) put(fb, x, y, x * 16u / NIMO_PANEL_W);
    } else if (pattern == 1) {
        fill_rect(fb, 0, 0, NIMO_PANEL_W, 4, 15);
        fill_rect(fb, 0, NIMO_PANEL_H - 4, NIMO_PANEL_W, 4, 15);
        fill_rect(fb, 0, 0, 4, NIMO_PANEL_H, 15);
        fill_rect(fb, NIMO_PANEL_W - 4, 0, 4, NIMO_PANEL_H, 15);
        for (uint32_t y = 0; y < NIMO_PANEL_H; y++) fill_rect(fb, y * NIMO_PANEL_W / NIMO_PANEL_H, y, 3, 1, 10);
    }
    /* each arm marks its own outer side, so both eyes prove the code ran there */
    if (pattern != 2) fill_rect(fb, left ? 20u : NIMO_PANEL_W - 80u, 110, 60, 60, 15);
}

static void draw_test(void *arg)
{
    uint32_t pattern = (uint32_t)(uintptr_t)arg;
    uint8_t reply[3] = { STATUS_FAILED, 0xFF, NIMO_IS_LEFT };
    uint8_t *fb = nimo_malloc(FRAME_BYTES);
    if (fb != 0) {
        draw_pattern(fb, pattern, NIMO_IS_LEFT != 0);
        void *mutex = nimo_display_mutex();
        if (mutex != 0) nimo_os_lock(mutex);
        int rc = nimo_panel_flush(fb, 0, 0, NIMO_PANEL_W, NIMO_PANEL_H);
        if (mutex != 0) nimo_os_unlock(mutex);
        nimo_free(fb);
        reply[0] = rc == 0 ? STATUS_OK : STATUS_FAILED;
        reply[1] = (uint8_t)rc;
    }
    nimo_send_response(GLASSLY_CMD, KEY_DRAW_TEST, reply, sizeof reply);
}

static uint32_t append(uint8_t *out, uint32_t at, const char *text)
{
    while (*text != 0 && at < REPLY_MAX) out[at++] = (uint8_t)*text++;
    return at;
}

int glassly_command(uint32_t cmd, uint32_t key, const uint8_t *payload, uint32_t len)
{
    uint8_t reply[REPLY_MAX];
    uint32_t n = 0;

    if ((cmd & 0xFFu) != GLASSLY_CMD) return 0;
    switch (key & 0xFFu) {
    case KEY_IDENTITY:
        reply[n++] = STATUS_OK;
        n = append(reply, n, "{\"version\":\"GLASSLYCFW/" STR(GLASSLY_CFW_REVISION)
                             "\",\"platform\":\"nimo\",\"base\":\"1.1.5.1\",\"arm\":\"");
        n = append(reply, n, nimo_is_master() ? "master" : "slave");
        n = append(reply, n, "\"}");
        break;
    case KEY_DRAW_TEST:
        if (nimo_gui_post_async(draw_test, (void *)(uintptr_t)(len > 0 ? payload[0] : 0u))) return 1;
        reply[n++] = STATUS_BUSY;
        break;
    case KEY_ECHO:
        reply[n++] = STATUS_OK;
        for (uint32_t i = 0; i < len && n < REPLY_MAX; i++) reply[n++] = payload[i];
        break;
    default:
        reply[n++] = STATUS_UNSUPPORTED;
        break;
    }
    nimo_send_response(cmd, key, reply, n);
    return 1;
}
