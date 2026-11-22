/* Host stand-ins for the stock entry points (see host_stock.h). Test-only. MIT. */
#include "host_stock.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

host_state host;
_Alignas(16) unsigned char nimo_host_ram[NIMO_RAM_BYTES];
_Alignas(16) unsigned char nimo_host_crumbs[NIMO_CRUMB_BYTES];
volatile uint8_t nimo_host_panel_up, nimo_host_left, nimo_host_display_on, nimo_host_lit;
volatile uint8_t nimo_host_light_powered, nimo_host_light_wanted, nimo_host_light_factory;
volatile uint16_t nimo_host_panel_brightness;
volatile uint32_t nimo_host_blank_ticks;
_Alignas(16) uint8_t nimo_host_fb[2][NIMO_PANEL_STRIDE * NIMO_PANEL_H];
volatile uint8_t nimo_host_fb_back, nimo_host_fb_front;
static int mutex_object, screen_object, timer_object, light_timer_object;

typedef struct block { struct block *next, *prev; size_t size; } block;
typedef union { max_align_t align; block b; } heap_header;
static block live = { &live, &live, 0 };

static void no_critical(void) { assert(host.critical == 0 && "stock call with interrupts masked"); }

void host_reset(int left)
{
    uint32_t x = 0x6e696d6fu;
    for (unsigned i = 0; i < sizeof nimo_host_crumbs; i++) {
        x = x * 1103515245u + 12345u;
        nimo_host_crumbs[i] = (uint8_t)(x >> 16);
    }
    host_reboot(left);
}

void host_reboot(int left)
{
    while (live.next != &live) {
        block *b = live.next;
        live.next = b->next;
        free(b);
    }
    live.prev = &live;
    memset(&host, 0, sizeof host);
    memset(nimo_host_ram, 0, sizeof nimo_host_ram);
    host.heap_capacity = 400u * 1024u;
    host.master = 1;
    host.now = 1000;
    nimo_host_panel_up = 1;
    nimo_host_left = (uint8_t)left;
    nimo_host_display_on = 1;
    nimo_host_lit = 0;
    nimo_host_blank_ticks = 7;
    nimo_host_panel_brightness = 20;
    nimo_host_light_powered = nimo_host_light_wanted = nimo_host_light_factory = 0;
    /* The stock frames after a flip: front 0 holds the last frame, back 1 the next. */
    memset(nimo_host_fb[0], 0x3C, sizeof nimo_host_fb[0]);
    memset(nimo_host_fb[1], 0x5A, sizeof nimo_host_fb[1]);
    nimo_host_fb_front = 0;
    nimo_host_fb_back = 1;
}

unsigned host_run_ui(void)
{
    unsigned ran = 0;
    while (host.queue_count != 0) {
        nimo_ui_fn fn = host.queue[0].fn;
        void *arg = host.queue[0].arg;
        memmove(host.queue, host.queue + 1, (host.queue_count - 1) * sizeof host.queue[0]);
        host.queue_count--;
        fn(arg);
        ran++;
    }
    return ran;
}

void host_timer_tick(void)
{
    assert(host.timer_live && host.timer_fn);
    host.timer_fn(&timer_object);
}

void host_light_tick(void)
{
    assert(host.light_timer_live && host.light_timer_fn);
    host.light_timer_fn(&light_timer_object);
}

void nimo_critical_enter(void)
{
    host.critical++;
    host.criticals++;
}

void nimo_critical_exit(void)
{
    assert(host.critical != 0);
    host.critical--;
}

int nimo_send_response(uint32_t cmd, uint32_t key, const void *data, uint32_t len)
{
    no_critical();
    assert(len <= sizeof host.replies[0].data && host.reply_count < 256);
    if (!host.master) return 0;
    host_reply *r = &host.replies[host.reply_count++];
    r->cmd = cmd;
    r->key = key;
    r->len = len;
    memcpy(r->data, data, len);
    return 0;
}

int nimo_peer_ui(uint32_t id, const void *data, uint32_t len)
{
    no_critical();
    if (host.peer_error) return host.peer_error;
    assert(len <= sizeof host.peer[0].data && host.peer_count < 256);
    host_reply *r = &host.peer[host.peer_count++];
    r->key = id;
    r->len = len;
    memcpy(r->data, data, len);
    return 0;
}

int nimo_is_master(void) { return host.master; }
void nimo_still_reset(void) { host.still_resets++; }

/* The stock driver: a read answers only while the sensor is powered, and the
 * arm without the sensor accepts a power request and does nothing. */
int nimo_light_read(uint16_t *lux)
{
    no_critical();
    assert(lux);
    host.light_reads++;
    if (!nimo_host_light_powered || host.light_read_rc) return 1;
    *lux = host.light_lux;
    return 0;
}

int nimo_light_power(uint32_t on)
{
    no_critical();
    if (!nimo_host_left) return 0;
    if (host.light_power_rc) return -1;
    if (on) host.light_power_on++;
    else host.light_power_off++;
    nimo_host_light_powered = on != 0;
    return 0;
}

int nimo_gui_post_async(nimo_ui_fn fn, void *arg)
{
    no_critical();
    if (host.queue_fail || host.queue_count == 48) return 0;
    host.queue[host.queue_count].fn = fn;
    host.queue[host.queue_count].arg = arg;
    host.queue_count++;
    return 1;
}

void *nimo_malloc(uint32_t size)
{
    no_critical();
    host.alloc_attempts++;
    if (host.alloc_attempts == host.alloc_fail_at || size > host.heap_capacity - host.heap_used) return 0;
    heap_header *h = malloc(sizeof *h + size);
    assert(h);
    h->b.size = size;
    h->b.next = live.next;
    h->b.prev = &live;
    live.next->prev = &h->b;
    live.next = &h->b;
    memset(h + 1, 0xA5, size);
    host.heap_used += size;
    if (host.heap_used > host.heap_peak) host.heap_peak = host.heap_used;
    host.allocations++;
    return h + 1;
}

void nimo_free(void *ptr)
{
    no_critical();
    assert(ptr);
    heap_header *h = (heap_header *)ptr - 1;
    assert(host.allocations && host.heap_used >= h->b.size);
    host.heap_used -= h->b.size;
    host.allocations--;
    h->b.prev->next = h->b.next;
    h->b.next->prev = h->b.prev;
    free(h);
}

uint32_t nimo_heap_free(void) { return (uint32_t)(host.heap_capacity - host.heap_used); }
uint32_t nimo_heap_largest(uint32_t caps) { (void)caps; return nimo_heap_free(); }
uint32_t nimo_now_ms(void) { return host.now; }
void *nimo_display_mutex(void) { return &mutex_object; }

void nimo_os_lock(void *mutex)
{
    assert(mutex == &mutex_object && host.lock_depth == 0);
    host.lock_depth++;
    host.locks++;
}

void nimo_os_unlock(void *mutex)
{
    assert(mutex == &mutex_object && host.lock_depth == 1);
    host.lock_depth--;
}

int nimo_panel_flush(const uint8_t *fb, uint32_t x, uint32_t row0, uint32_t w, uint32_t nrows)
{
    no_critical();
    if (host.reset_in_flush) longjmp(*host.reset_in_flush, 1);
    assert(host.lock_depth == 1 && x == 0 && w == NIMO_PANEL_W);
    assert(nrows != 0 && row0 + nrows <= NIMO_PANEL_H && host.flush_count < 512);
    host.flushes[host.flush_count].row0 = row0;
    host.flushes[host.flush_count].nrows = nrows;
    host.flush_count++;
    if (host.flush_rc == 0)
        memcpy(host.panel + row0 * NIMO_PANEL_STRIDE, fb + row0 * NIMO_PANEL_STRIDE, nrows * NIMO_PANEL_STRIDE);
    return host.flush_rc;
}

int nimo_set_brightness(uint32_t level)
{
    host.brightness_calls++;
    host.brightness = level;
    nimo_host_panel_brightness = (uint16_t)level;
    return 0;
}

void nimo_repaint_all(void) { host.repaints++; }
void nimo_cancel_auto_off(uint32_t reason) { assert(reason == 2); host.cancels++; }
void *nimo_lv_screen_active(void) { return &screen_object; }
void nimo_lv_obj_invalidate(void *obj) { assert(obj == &screen_object); host.invalidates++; }

void *nimo_lv_timer_create(nimo_timer_fn fn, uint32_t period_ms, void *user)
{
    assert(fn && !user);
    if (period_ms != NIMO_PUMP_MS) {
        assert(!host.light_timer_live);
        host.light_timer_fn = fn;
        host.light_timer_period = period_ms;
        host.light_timers_created++;
        host.light_timer_live = 1;
        return &light_timer_object;
    }
    assert(!host.timer_live);
    host.timer_fn = fn;
    host.timers_created++;
    host.timer_live = 1;
    return &timer_object;
}

void nimo_lv_timer_delete(void *timer)
{
    if (timer == &light_timer_object) {
        assert(host.light_timer_live);
        host.light_timer_live = 0;
        host.light_timers_deleted++;
        return;
    }
    assert(timer == &timer_object && host.timer_live);
    host.timer_live = 0;
    host.timers_deleted++;
}

/* Stand-in for the stock face: line 18, baseline 3 like Montserrat 16, made-up
 * 4 bpp glyphs for U+0020..U+007E and U+00B0 (gid = code - 0x1f, 96 for the
 * degree sign), packed the way lv_font_fmt_txt stores them. */
static uint8_t host_font_bitmap[8192];
static nimo_glyph_record host_font_glyphs[97];
static const nimo_font_dsc host_font_dsc = { host_font_bitmap, host_font_glyphs };
const nimo_font nimo_host_text_font = { 0, 0, 0, 18, 3, 0, -1, 1, &host_font_dsc };

static void host_font_build(void)
{
    if (host_font_glyphs[1].index_adv != 0) return;
    uint32_t at = 1;
    for (uint32_t gid = 1; gid <= 96; gid++) {
        uint32_t cp = gid == 96 ? 0xB0u : gid + 0x1Fu;
        nimo_glyph_record *g = &host_font_glyphs[gid];
        uint32_t w = cp == ' ' ? 0 : 4 + cp % 5, h = cp == ' ' ? 0 : 8 + cp % 6;
        g->box_w = (uint8_t)w;
        g->box_h = (uint8_t)h;
        g->ofs_x = (int8_t)(cp % 2);
        g->ofs_y = (int8_t)(cp < 0x80 && strchr("gjpqy", (int)cp) ? -3 : 0);
        g->index_adv = at | ((w ? (w + 2) * 16 - 3 : 64) << 20);
        for (uint32_t i = 0; i < w * h; i++) {
            uint32_t v = (i * 7 + cp) % 16;
            host_font_bitmap[at + i / 2] |= (uint8_t)(i & 1 ? v : v << 4);
        }
        at += (w * h + 1) / 2;
        assert(at < sizeof host_font_bitmap);
    }
}

int nimo_font_glyph(const nimo_font *font, nimo_glyph_dsc *dsc, uint32_t letter, uint32_t next)
{
    no_critical();
    assert(font == &nimo_host_text_font && next == 0);
    host_font_build();
    uint32_t gid = letter >= 0x20 && letter <= 0x7E ? letter - 0x1F : letter == 0xB0 ? 96 : 0;
    if (gid == 0) return 0;
    const nimo_glyph_record *g = &host_font_glyphs[gid];
    host.glyph_lookups++;
    dsc->adv_w = (uint16_t)(((g->index_adv >> 20) + 8) >> 4);
    dsc->box_w = g->box_w;
    dsc->box_h = g->box_h;
    dsc->ofs_x = g->ofs_x;
    dsc->ofs_y = g->ofs_y;
    dsc->format = 4;
    dsc->gid = gid;
    return 1;
}
