/* The real router handler, UI-task jobs, scene session and portable scene
 * core against host stand-ins for the stock functions: acquire, scene
 * messages and the rows each present flushes, per-eye filtering, the pump
 * timer, release and the transfer checksum. Prints the identity JSON and the
 * checksum reply for the runner to check independently. MIT. */
#include "host_stock.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>

static uint16_t request_id;

static void w16(uint8_t *p, unsigned v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void w32(uint8_t *p, uint32_t v) { w16(p, v & 0xFFFFu); w16(p + 2, v >> 16); }

static host_reply *last(void) { assert(host.reply_count); return &host.replies[host.reply_count - 1]; }

static host_reply *command(uint32_t key, const uint8_t *payload, uint32_t len)
{
    unsigned before = host.reply_count;
    assert(glassly_command(GLASSLY_CMD, key, payload, len) == 1);
    host_run_ui();
    assert(host.reply_count > before);
    return &host.replies[before];
}

static nimo_session *session(void) { return NIMO_RAM->session; }

/* Scene message with the session's epoch and a fresh request id (modes 37..41). */
static host_reply *scene(uint8_t *msg, uint32_t len)
{
    if (msg[0] >= 37 && msg[0] <= 41 && len >= 5 && session()) {
        w16(msg + 1, session()->scene.core.cache_epoch);
        w16(msg + 3, ++request_id);
    }
    host_reply *r = command(KEY_SCENE, msg, len);
    assert(r->key == KEY_SCENE);
    return r;
}

static unsigned cache_status(const host_reply *r)
{
    assert(r->data[0] == STATUS_OK && r->len >= 11);
    return r->data[4];
}

static unsigned pixel(const uint8_t *fb, unsigned x, unsigned y)
{
    uint8_t b = fb[y * NIMO_PANEL_STRIDE + x / 2];
    return x & 1u ? b & 15u : b >> 4;
}

static void acquire(void)
{
    host_reply *r = command(KEY_ACQUIRE, 0, 0);
    assert(r->key == KEY_ACQUIRE && r->len == 4 && r->data[0] == STATUS_OK && r->data[1] == 0);
    assert(NIMO_RAM->owned == 1 && session() && host.timer_live);
    /* the canvas is the stock buffer the indices no longer name */
    assert(NIMO_RAM->pinned && nimo_host_fb_front == nimo_host_fb_back && nimo_host_fb_back == NIMO_RAM->back);
    assert(session()->shadow == nimo_host_fb[NIMO_RAM->back ^ 1u]);
}

static void release(void)
{
    host_reply *r = command(KEY_RELEASE, 0, 0);
    assert(r->key == KEY_RELEASE && r->len == 1 && r->data[0] == STATUS_OK);
    assert(!NIMO_RAM->owned && !session() && !host.timer_live && host.allocations == 0 && host.heap_used == 0);
    assert(!NIMO_RAM->pinned && nimo_host_fb_front == NIMO_RAM->front && host.lock_depth == 0);
}

static void reset_scene(void)
{
    uint8_t m[6] = { 41, 0, 0, 0, 0, 0 };
    assert(cache_status(scene(m, sizeof m)) == 0);
}

/* PUT one filled rectangle object. */
static void put_rect(uint32_t id, int x, int y, int w, int h, unsigned color)
{
    uint8_t m[34] = { 37 };
    m[5] = 1;
    w32(m + 6, id);
    w32(m + 10, 1);
    m[14] = 3; m[15] = 1; m[16] = (uint8_t)color; m[17] = 0;
    w16(m + 18, (unsigned)x); w16(m + 20, (unsigned)y); w16(m + 22, (unsigned)w); w16(m + 24, (unsigned)h);
    assert(cache_status(scene(m, sizeof m)) == 0);
}

/* SHOW the listed objects (version 1) with PRESENT|TAG and lens bits. */
static host_reply *show(const uint32_t *ids, unsigned count, uint8_t lens_bits)
{
    uint8_t m[64] = { 38 };
    m[5] = (uint8_t)(0x05u | lens_bits);
    m[6] = 0; m[7] = 0;
    w16(m + 8, count);
    for (unsigned i = 0; i < count; i++) { w32(m + 10 + 8 * i, ids[i]); w32(m + 14 + 8 * i, 1); }
    host_reply *r = scene(m, 10 + 8 * count);
    assert(cache_status(r) == 0);
    return r;
}

static void expect_flush(unsigned index, uint32_t row0, uint32_t nrows)
{
    assert(index < host.flush_count);
    if (host.flushes[index].row0 != row0 || host.flushes[index].nrows != nrows) {
        fprintf(stderr, "flush %u: rows %u+%u, expected %u+%u\n", index, host.flushes[index].row0,
                host.flushes[index].nrows, row0, nrows);
        assert(0);
    }
}

/* A present's rows cover [lo, hi) with at most the renderer's few rows of
 * bounding margin on either side. */
static void expect_rows(unsigned index, uint32_t lo, uint32_t hi)
{
    assert(index < host.flush_count);
    uint32_t a = host.flushes[index].row0, b = a + host.flushes[index].nrows;
    if (a > lo || b < hi || a + 4 < lo || b > hi + 4) {
        fprintf(stderr, "flush %u: rows %u..%u, expected about %u..%u\n", index, a, b, lo, hi);
        assert(0);
    }
}

static int panel_matches_shadow(void)
{
    return memcmp(host.panel, session()->shadow, NIMO_FRAME_BYTES) == 0;
}

static uint32_t reference_crc(const uint8_t *p, size_t n)
{
    uint32_t table[256];
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        table[i] = c;
    }
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) c = table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return ~c;
}

static void test_plain_commands(void)
{
    host_reset(1);
    host_reply *r = command(KEY_IDENTITY, 0, 0);
    assert(r->data[0] == STATUS_OK && r->len < 500);
    printf("IDENTITY %.*s\n", (int)r->len - 1, (const char *)r->data + 1);
    r = command(KEY_STATUS, 0, 0);
    assert(r->data[0] == STATUS_OK && r->len < 500);
    printf("STATUS %.*s\n", (int)r->len - 1, (const char *)r->data + 1);
    uint8_t echo[3] = { 1, 2, 3 };
    r = command(KEY_ECHO, echo, 3);
    assert(r->len == 4 && r->data[0] == 0 && !memcmp(r->data + 1, echo, 3));
    static uint8_t chunk[1200];
    for (unsigned i = 0; i < sizeof chunk; i++) chunk[i] = (uint8_t)(i * 7u + 3u);
    r = command(KEY_CHECKSUM, chunk, sizeof chunk);
    assert(r->len == 9 && r->data[0] == 0);
    uint32_t len = r->data[1] | r->data[2] << 8 | r->data[3] << 16 | (uint32_t)r->data[4] << 24;
    uint32_t crc = r->data[5] | r->data[6] << 8 | r->data[7] << 16 | (uint32_t)r->data[8] << 24;
    assert(len == sizeof chunk && crc == reference_crc(chunk, sizeof chunk));
    printf("CHECKSUM 1200 %08x\n", crc);
    r = command(0x7F, 0, 0);
    assert(r->len == 1 && r->data[0] == STATUS_UNSUPPORTED);
    assert(glassly_command(0x05, 1, 0, 0) == 0);
    uint8_t level[1] = { 33 };
    r = command(KEY_BRIGHTNESS, level, 1);
    assert(r->len == 1 && r->data[0] == STATUS_INVALID && host.brightness_calls == 0);
    level[0] = 16;
    r = command(KEY_BRIGHTNESS, level, 1);
    assert(r->len == 2 && r->data[0] == STATUS_OK && host.brightness == 16);
    assert(NIMO_RAM->brightness == 16 && NIMO_RAM->brightness_set);
    uint8_t bad[2] = { 1, 2 };
    assert(command(KEY_BRIGHTNESS, bad, 2)->data[0] == STATUS_INVALID);
    assert(host.allocations == 0 && NIMO_RAM->magic == NIMO_RAM_MAGIC);
    printf("plain commands: identity, echo, 1200-byte checksum, brightness, unsupported passed\n");
}

static void test_not_owned(void)
{
    host_reset(1);
    uint8_t m[6] = { 41, 0, 0, 0, 0, 0 };
    host_reply *r = scene(m, sizeof m);
    assert(r->len == 1 && r->data[0] == STATUS_NOT_OWNED && host.allocations == 0 && NIMO_RAM->jobs == 0);
    r = command(KEY_RELEASE, 0, 0); /* release without a lease is harmless */
    assert(r->data[0] == STATUS_OK && host.repaints == 1 && host.invalidates == 1);
    static uint8_t big[NIMO_MAX_PAYLOAD + 1];
    big[0] = 41;
    r = command(KEY_SCENE, big, sizeof big);
    assert(r->len == 1 && r->data[0] == STATUS_TOO_LARGE && host.allocations == 0);
    assert(command(KEY_SCENE, big, 0)->data[0] == STATUS_INVALID);
    printf("not owned: scene refused, release harmless, oversize and empty refused\n");
}

static void test_lifecycle(int left)
{
    host_reset(left);
    request_id = 0;
    acquire();
    expect_flush(0, 0, NIMO_PANEL_H);
    for (unsigned i = 0; i < NIMO_FRAME_BYTES; i++) assert(host.panel[i] == 0);
    assert(nimo_host_lit == 1 && nimo_host_blank_ticks == 0 && host.cancels == 1);
    assert(session()->eye == (left ? 1 : 2) && session()->scene.core.eye == session()->eye);
    host_reply *r = command(KEY_IDENTITY, 0, 0);
    assert(strstr((const char *)r->data + 1, "\"owned\":1") && strstr((const char *)r->data + 1, left ? "\"eye\":\"left\"" : "\"eye\":\"right\""));

    reset_scene();
    put_rect(1, 5, 5, 10, 5, 7);
    assert(host.flush_count == 1);
    uint32_t one[1] = { 1 };
    unsigned replies = host.reply_count;
    show(one, 1, 0);
    expect_flush(1, 0, NIMO_PANEL_H); /* a new cache's first render redraws everything */
    assert(pixel(host.panel, 6, 6) == 7 && pixel(host.panel, 4, 6) == 0 && panel_matches_shadow());
    /* the settled notice follows the scene reply */
    assert(host.reply_count == replies + 2 && last()->key == KEY_SETTLED && last()->len == 3);
    assert((last()->data[1] | last()->data[2] << 8) == request_id);

    /* GLIDE 100 px over 10 frames: the pump timer renders, presents and settles */
    uint8_t g[24] = { 38 };
    g[5] = 7;
    g[10] = 4; w32(g + 11, 1); w16(g + 15, 100); w16(g + 17, 0); g[19] = 10;
    g[20] = 0; g[21] = 0; g[22] = 255; g[23] = 255;
    assert(cache_status(scene(g, sizeof g)) == 0 && session()->scene.timer_armed);
    unsigned flushes = host.flush_count;
    for (int i = 0; i < 40 && session()->scene.timer_armed; i++) {
        host.now += NIMO_PUMP_MS;
        nimo_host_lit = 0;
        host_timer_tick();
        assert(nimo_host_lit == 1);
    }
    assert(!session()->scene.timer_armed && host.flush_count > flushes);
    for (unsigned i = flushes; i < host.flush_count; i++) expect_rows(i, 5, 10);
    assert(pixel(host.panel, 106, 6) == 7 && pixel(host.panel, 6, 6) == 0 && panel_matches_shadow());
    assert(last()->key == KEY_SETTLED);

    /* immediate geometry (mode 36) presents the whole canvas */
    uint8_t raw[22] = { 36, 1, 3, 1, 15, 0 };
    w16(raw + 6, 300); w16(raw + 8, 200); w16(raw + 10, 4); w16(raw + 12, 4);
    flushes = host.flush_count;
    r = scene(raw, sizeof raw);
    assert(r->len == 1 && r->data[0] == STATUS_OK);
    expect_flush(flushes, 0, NIMO_PANEL_H);
    assert(pixel(host.panel, 301, 201) == 15);

    /* a malformed message is refused without touching the panel */
    uint8_t junk[3] = { 99, 1, 2 };
    flushes = host.flush_count;
    r = scene(junk, sizeof junk);
    assert(r->len == 1 && r->data[0] == STATUS_INVALID && host.flush_count == flushes);

    uint16_t epoch = session()->scene.core.cache_epoch;
    release();
    assert(host.repaints == 1 && host.invalidates == 1 && NIMO_RAM->epoch == epoch);
    acquire();
    assert(session()->scene.core.cache_epoch == (uint16_t)(epoch + 1u));
    release();
    printf("lifecycle (%s arm): acquire, reset, put, show, glide via pump, settled, mode 36, release, epoch advance passed\n",
           left ? "left" : "right");
}

/* A SHOW naming the other eye renders but waits; this eye's next present
 * sends the union, so the panel ends exactly on this eye's scene. */
static void test_show_eye(int left)
{
    host_reset(left);
    request_id = 0;
    acquire();
    reset_scene();
    put_rect(1, 10, 5, 20, 5, 9);
    put_rect(2, 10, 50, 20, 10, 12);
    uint32_t one[1] = { 1 }, two[1] = { 2 };
    uint8_t mine = left ? 0x10 : 0x20, other = left ? 0x20 : 0x10;
    show(one, 1, mine);
    expect_flush(1, 0, NIMO_PANEL_H);
    unsigned flushes = host.flush_count, deferred = NIMO_RAM->presents_deferred;
    show(two, 1, other);
    assert(host.flush_count == flushes && NIMO_RAM->presents_deferred == deferred + 1);
    assert(pixel(host.panel, 12, 6) == 9 && pixel(host.panel, 12, 52) == 0);
    show(one, 1, mine);
    expect_rows(flushes, 5, 60);
    assert(pixel(host.panel, 12, 6) == 9 && pixel(host.panel, 12, 52) == 0 && panel_matches_shadow());
    /* both-eye SHOW reaches this panel directly */
    show(two, 1, 0);
    expect_rows(flushes + 1, 5, 60);
    assert(pixel(host.panel, 12, 6) == 0 && pixel(host.panel, 12, 52) == 12 && panel_matches_shadow());
    /* a refused flush leaves its rows pending for the next present */
    host.flush_rc = 1;
    show(one, 1, mine);
    assert(NIMO_RAM->flush_errors == 1);
    host.flush_rc = 0;
    put_rect(3, 200, 100, 4, 4, 3);
    uint32_t both[2] = { 1, 3 };
    flushes = host.flush_count;
    show(both, 2, 0);
    expect_rows(flushes, 5, 104);
    assert(panel_matches_shadow());
    release();
    printf("show eye bits (%s arm): other-eye SHOW deferred, union sent on this eye, refused flush retried passed\n",
           left ? "left" : "right");
}

/* Objects whose id has bit 31 belong to one eye (bit 30 right): each arm draws
 * only its own, with no second render pass. */
static void test_eye_objects(int left)
{
    host_reset(left);
    request_id = 0;
    acquire();
    reset_scene();
    put_rect(0x80000001u, 40, 100, 10, 10, 5);
    put_rect(0xC0000002u, 60, 120, 10, 10, 6);
    put_rect(7, 80, 140, 10, 10, 4);
    uint32_t ids[3] = { 0x80000001u, 0xC0000002u, 7 };
    show(ids, 3, 0);
    expect_flush(1, 0, NIMO_PANEL_H);
    assert(pixel(host.panel, 42, 102) == (left ? 5u : 0u));
    assert(pixel(host.panel, 62, 122) == (left ? 0u : 6u));
    assert(pixel(host.panel, 82, 142) == 4 && panel_matches_shadow());
    /* dropping the shared object redraws only its rows; tagged ones stay filtered */
    uint32_t tagged[2] = { 0x80000001u, 0xC0000002u };
    unsigned flushes = host.flush_count;
    show(tagged, 2, 0);
    expect_rows(flushes, 140, 150);
    assert(pixel(host.panel, 82, 142) == 0 && pixel(host.panel, 42, 102) == (left ? 5u : 0u) && panel_matches_shadow());
    release();
    printf("eye objects (%s arm): only this eye's tagged objects drawn passed\n", left ? "left" : "right");
}

static void test_queue_and_memory(void)
{
    host_reset(1);
    request_id = 0;
    host.queue_fail = 1;
    host_reply *r = command(KEY_ACQUIRE, 0, 0);
    assert(r->data[0] == STATUS_BUSY && !NIMO_RAM->owned);
    host.queue_fail = 0;
    acquire();
    reset_scene();
    host.queue_fail = 1;
    uint8_t m[6] = { 41, 0, 0, 0, 0, 0 };
    unsigned live = host.allocations;
    r = command(KEY_SCENE, m, sizeof m);
    assert(r->data[0] == STATUS_BUSY && host.allocations == live && NIMO_RAM->jobs == 0);
    host.queue_fail = 0;
    /* at most NIMO_MAX_JOBS scene messages wait for the UI task */
    unsigned before = host.reply_count;
    for (unsigned i = 0; i < NIMO_MAX_JOBS; i++) assert(glassly_command(GLASSLY_CMD, KEY_SCENE, m, sizeof m) == 1);
    assert(host.reply_count == before && NIMO_RAM->jobs == NIMO_MAX_JOBS);
    assert(glassly_command(GLASSLY_CMD, KEY_SCENE, m, sizeof m) == 1);
    assert(host.reply_count == before + 1 && last()->data[0] == STATUS_BUSY);
    assert(host_run_ui() == NIMO_MAX_JOBS && NIMO_RAM->jobs == 0 && host.reply_count == before + 1 + NIMO_MAX_JOBS);
    /* scene allocations keep the reserved headroom: a tiny heap refuses the store */
    release();
    host.heap_capacity = sizeof(nimo_session) + NIMO_JOB_HEADROOM + 4096;
    acquire();
    uint8_t reset[6] = { 41, 0, 0, 0, 0, 0 };
    r = scene(reset, sizeof reset);
    assert(cache_status(r) == 3 && session()->scene.denied_allocations);
    release();
    /* every allocation failure point during acquire is clean */
    host.heap_capacity = 400u * 1024u;
    for (unsigned fail = 1; fail <= 1; fail++) {
        host.alloc_attempts = 0;
        host.alloc_fail_at = fail;
        r = command(KEY_ACQUIRE, 0, 0);
        assert(r->data[0] == STATUS_NO_MEMORY && !NIMO_RAM->owned && !session() && host.allocations == 0);
        assert(!NIMO_RAM->pinned && nimo_host_fb_front == NIMO_RAM->front);
    }
    host.alloc_fail_at = 0;
    host.heap_capacity = sizeof(nimo_session) + NIMO_JOB_HEADROOM - 1;
    assert(command(KEY_ACQUIRE, 0, 0)->data[0] == STATUS_NO_MEMORY && host.allocations == 0);
    assert(!NIMO_RAM->owned && !NIMO_RAM->pinned && nimo_host_fb_front == NIMO_RAM->front);
    /* indices the stock code never keeps: refuse without touching them */
    host.heap_capacity = 400u * 1024u;
    nimo_host_fb_back = 2;
    assert(command(KEY_ACQUIRE, 0, 0)->data[0] == STATUS_INVALID && !NIMO_RAM->owned && host.allocations == 0);
    assert(nimo_host_fb_back == 2 && nimo_host_fb_front == 0 && !NIMO_RAM->pinned);
    nimo_host_fb_back = 1;
    printf("queue and memory: busy queue, job limit, store headroom, acquire allocation failures passed\n");
}

/* The lease borrows the stock buffer the indices do not name: stock writes to
 * the back buffer leave the canvas alone, release gives the stock image back,
 * and indices moved by anything are pinned again on the next pump tick. */
static void test_borrowed_canvas(int flipped)
{
    host_reset(1);
    nimo_host_fb_front = flipped ? 0 : 1;
    nimo_host_fb_back = 1;
    acquire();
    uint8_t back = NIMO_RAM->back;
    assert(back == 1 && NIMO_RAM->front == (flipped ? 0 : 1) && session()->shadow == nimo_host_fb[0]);
    for (unsigned i = 0; i < NIMO_FRAME_BYTES; i++) assert(nimo_host_fb[0][i] == 0 && host.panel[i] == 0);
    reset_scene();
    put_rect(1, 10, 10, 40, 30, 9);
    uint32_t ids[1] = { 1 };
    show(ids, 1, 0);
    assert(pixel(nimo_host_fb[0], 12, 12) == 9 && panel_matches_shadow());
    memset(nimo_host_fb[1], 0x77, NIMO_FRAME_BYTES); /* LVGL drawing into the back buffer */
    host.now += 10;
    host_timer_tick();
    assert(pixel(nimo_host_fb[0], 12, 12) == 9 && pixel(nimo_host_fb[0], 100, 100) == 0 && NIMO_RAM->repins == 0);
    /* canvas checksum: this arm's canvas, as zlib computes it */
    host_reply *r = command(KEY_CANVAS, 0, 0);
    uint32_t crc = reference_crc(nimo_host_fb[0], NIMO_FRAME_BYTES);
    assert(r->key == KEY_CANVAS && r->len == 6 && r->data[0] == STATUS_OK && r->data[5] == 1);
    assert(((uint32_t)r->data[1] | (uint32_t)r->data[2] << 8 | (uint32_t)r->data[3] << 16 |
            (uint32_t)r->data[4] << 24) == crc);
    /* a stray flip: the next tick pins the indices again and resends the canvas */
    unsigned flushes = host.flush_count;
    nimo_host_fb_front = 1;
    nimo_host_fb_back = 0;
    host.now += 10;
    host_timer_tick();
    assert(nimo_host_fb_front == back && nimo_host_fb_back == back && NIMO_RAM->repins == 1);
    assert(host.flush_count == flushes + 1);
    expect_flush(flushes, 0, NIMO_PANEL_H);
    release();
    assert(memcmp(nimo_host_fb[0], nimo_host_fb[1], NIMO_FRAME_BYTES) == 0 && nimo_host_fb[0][0] == 0x77);
    assert(nimo_host_fb_back == 1 && nimo_host_fb_front == (flipped ? 0 : 1));
    r = command(KEY_CANVAS, 0, 0);
    assert(r->len == 6 && r->data[0] == STATUS_NOT_OWNED);
    printf("borrowed canvas (%s): pin, stock writes elsewhere, checksum, repin, unpin passed\n",
           flipped ? "flipped" : "unflipped");
}

static void test_slave_and_draw(void)
{
    host_reset(0);
    host.master = 0;
    assert(glassly_command(GLASSLY_CMD, KEY_ACQUIRE, 0, 0) == 1);
    host_run_ui();
    assert(host.reply_count == 0 && NIMO_RAM->owned && session());
    assert(glassly_command(GLASSLY_CMD, KEY_RELEASE, 0, 0) == 1);
    host_run_ui();
    assert(!NIMO_RAM->owned && host.allocations == 0);
    host.master = 1;
    uint8_t pattern[1] = { 1 };
    host_reply *r = command(KEY_DRAW_TEST, pattern, 1);
    assert(r->key == KEY_DRAW_TEST && r->len == 3 && r->data[0] == STATUS_OK && r->data[2] == 0);
    expect_flush(host.flush_count - 1, 0, NIMO_PANEL_H);
    assert(pixel(host.panel, 100, 1) == 15 && pixel(host.panel, 500, 140) == 15 && host.allocations == 0);
    printf("slave arm runs silently; draw test passed\n");
}

static const char *status_text(void)
{
    static char text[640];
    host_reply *r = command(KEY_STATUS, 0, 0);
    assert(r->data[0] == STATUS_OK && r->len < 560 && r->len < sizeof text);
    memcpy(text, r->data + 1, r->len - 1);
    text[r->len - 1] = 0;
    return text;
}

static void expect_text(const char *text, const char *part)
{
    if (!strstr(text, part)) {
        fprintf(stderr, "missing %s in %s\n", part, text);
        assert(0);
    }
}

/* Breadcrumbs survive a reset (host_reboot keeps them, power-on fills them
 * with noise); the first command of a boot reports the previous boot's open
 * lane. The job count goes through the critical section, never an AMO. */
static void test_breadcrumbs(void)
{
    host_reset(1);
    const char *text = status_text();
    expect_text(text, "\"boot\":1,\"last_crash\":null");
    acquire();
    uint8_t raw[22] = { 36, 1, 3, 1, 15, 0 };
    w16(raw + 6, 300); w16(raw + 8, 200); w16(raw + 10, 4); w16(raw + 12, 4);
    unsigned criticals = host.criticals;
    assert(command(KEY_SCENE, raw, sizeof raw)->data[0] == STATUS_OK && host.criticals == criticals + 2);
    assert(host.critical == 0 && NIMO_RAM->jobs == 0);
    uint32_t seq = NIMO_RAM->commands + 1;
    jmp_buf reset;
    host.reset_in_flush = &reset;
    if (!setjmp(reset)) {
        glassly_command(GLASSLY_CMD, KEY_SCENE, raw, sizeof raw);
        host_run_ui();
        assert(0 && "no present");
    }
    host_reboot(1);
    text = status_text();
    char want[200];
    snprintf(want, sizeof want, "\"boot\":2,\"last_crash\":{\"lane\":\"ui\",\"stage\":\"present\",\"seq\":%u,"
             "\"key\":32,\"mode\":36,\"len\":22,\"open\":2}", seq);
    expect_text(text, want);
    printf("BREADCRUMBS %s\n", text);
    /* that boot ended at rest */
    host_reboot(1);
    expect_text(status_text(), "\"boot\":3,\"last_crash\":null");
    /* a reset in the draw test's present */
    host.reset_in_flush = &reset;
    if (!setjmp(reset)) {
        uint8_t pattern[1] = { 2 };
        glassly_command(GLASSLY_CMD, KEY_DRAW_TEST, pattern, 1);
        host_run_ui();
        assert(0);
    }
    host_reboot(1);
    text = status_text();
    expect_text(text, "\"last_crash\":{\"lane\":\"ui\",\"stage\":\"present\"");
    expect_text(text, "\"key\":16,\"mode\":0,\"len\":1,\"open\":2}");
    /* widest status JSON (every number at 10 digits, the router lane open at
     * its longest stage name) still fits the reply buffer */
    for (uint32_t *p = &NIMO_RAM->commands; p <= &NIMO_RAM->pump_ticks; p++) *p = 0xFFFFFFFFu;
    NIMO_RAM->commands = 0xFFFFFFFEu;
    NIMO_RAM->gate_skips = 0xFFFFFFFFu;
    NIMO_RAM->crumbs = 2;
    NIMO_RAM->boot = 0xFFFFFFFFu;
    NIMO_RAM->last[NIMO_LANE_UI].stage = NIMO_STAGE_DONE;
    NIMO_RAM->last[NIMO_LANE_PUMP].stage = NIMO_STAGE_DONE;
    NIMO_RAM->last[NIMO_LANE_ROUTER] = (nimo_crumb){ 0xFFFFFFFFu, 0xFFFFFFFFu, NIMO_STAGE_DISPATCH, 255, 255, 0 };
    host.heap_capacity = 0xFFFFFFFFu;
    nimo_host_panel_brightness = 0xFFFFu;
    text = status_text();
    expect_text(text, "\"lane\":\"router\",\"stage\":\"dispatch\",\"seq\":4294967295");
    assert(strlen(text) + 1 < 560 && text[strlen(text) - 1] == '}');
    printf("breadcrumbs: power-on noise ignored, reset mid-present reported, clean boot null, widest status %zu B passed\n",
           strlen(text) + 1);
}

static size_t load(const char *dir, const char *name, uint8_t *out, size_t cap)
{
    char path[1024];
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *f = fopen(path, "rb");
    assert(f);
    size_t n = fread(out, 1, cap, f);
    assert(n > 0 && n < cap && feof(f));
    fclose(f);
    return n;
}

/* The scripts/scene_packets.py files replay as the hardware steps send them:
 * raw files, fixed epoch, no reply-driven rewriting. */
static host_reply *replay(const char *dir, const char *name)
{
    static uint8_t data[NIMO_MAX_PAYLOAD];
    size_t n = load(dir, name, data, sizeof data);
    host_reply *r = command(KEY_SCENE, data, (uint32_t)n);
    assert(r->key == KEY_SCENE && r->data[0] == STATUS_OK);
    if (r->len > 1) assert(r->len >= 11 && r->data[4] == 0);
    printf("REPLY %s %s ", NIMO_IS_LEFT ? "left" : "right", name);
    for (unsigned i = 0; i < r->len; i++) printf("%02x", r->data[i]);
    printf("\n");
    return r;
}

static void pump_until_settled(void)
{
    for (int i = 0; i < 1000 && session()->scene.timer_armed; i++) {
        host.now += NIMO_PUMP_MS;
        host_timer_tick();
    }
    assert(!session()->scene.timer_armed);
}

static void test_demo_scenes(const char *dir, int left)
{
    host_reset(left);
    acquire();
    /* the mode-36 demo frame: border, diagonals and circles over the whole canvas */
    unsigned before = host.flush_count;
    replay(dir, "demo-geometry.bin");
    expect_flush(before, 0, NIMO_PANEL_H);
    assert(pixel(host.panel, 3, 140) == 15 && pixel(host.panel, 70, 140) == 2 && pixel(host.panel, 270, 30) == 15);
    assert(panel_matches_shadow());
    replay(dir, "scene-retained.bin");
    assert(pixel(host.panel, 270, 100) == 11 && pixel(host.panel, 9, 140) == 15);
    unsigned settled = NIMO_RAM->settled_sent;
    pump_until_settled();
    assert(NIMO_RAM->settled_sent == settled + 1 && last()->key == KEY_SETTLED && (last()->data[1] | last()->data[2] << 8) == 3);
    assert(pixel(host.panel, 460, 60) == 15 && pixel(host.panel, 60, 60) == 0 && panel_matches_shadow());
    replay(dir, "scene-eyes.bin");
    assert(pixel(host.panel, 80, 210) == (left ? 15u : 0u) && pixel(host.panel, NIMO_PANEL_W - 85, 210) == (left ? 0u : 15u));
    assert(panel_matches_shadow());
    unsigned flushes = host.flush_count;
    replay(dir, "scene-show-right.bin");
    if (left) assert(host.flush_count == flushes && pixel(host.panel, 9, 140) == 15);
    else assert(pixel(host.panel, 9, 140) == 0 && pixel(host.panel, 270, 100) == 11 && panel_matches_shadow());
    flushes = host.flush_count;
    replay(dir, "scene-show-left.bin");
    if (left) assert(pixel(host.panel, 9, 140) == 15 && pixel(host.panel, 270, 100) == 0 && panel_matches_shadow());
    else assert(host.flush_count == flushes && pixel(host.panel, 270, 100) == 11 && pixel(host.panel, 9, 140) == 0);
    replay(dir, "scene-show-both.bin");
    assert(pixel(host.panel, 9, 140) == 15 && pixel(host.panel, 270, 100) == 11 && panel_matches_shadow());
    release();
    printf("demo scenes (%s arm): mode-36 demo, retained scene + glide + settled, eye objects, right/left/both SHOW passed\n",
           left ? "left" : "right");
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "--scenes")) {
        test_demo_scenes(argv[2], 1);
        test_demo_scenes(argv[2], 0);
        printf("PASS: demo scene replay\n");
        return 0;
    }
    test_plain_commands();
    test_not_owned();
    test_lifecycle(1);
    test_lifecycle(0);
    test_show_eye(1);
    test_show_eye(0);
    test_eye_objects(1);
    test_eye_objects(0);
    test_queue_and_memory();
    test_borrowed_canvas(1);
    test_borrowed_canvas(0);
    test_slave_and_draw();
    test_breadcrumbs();
    printf("PASS: NIMO session host tests\n");
    return 0;
}
