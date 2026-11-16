/* UI-task side of the display lease: the session, its canvas, the pump timer
 * and every panel write the runtime makes. Runs only on the LVGL task, so it
 * needs no lock of its own; the display mutex serializes the panel against
 * the stock frame task. All state lives in the RAM block or the heap. MIT. */
#include "glassly.h"
#include "text.h"

static void zero(void *to, uint32_t n)
{
    volatile uint8_t *d = to;
    while (n--) *d++ = 0;
}

/* Whole stock framebuffers: both 4-aligned, 75,600 bytes (a word multiple). */
static void copy_frame(uint8_t *to, const uint8_t *from)
{
    volatile uint32_t *d = (volatile uint32_t *)(void *)to;
    const volatile uint32_t *s = (const volatile uint32_t *)(const void *)from;
    for (uint32_t i = 0; i < NIMO_FRAME_BYTES / 4u; i++) d[i] = s[i];
}

/* Replies from the UI task: the running lane (job or pump) marks the send. */
static void reply(uint32_t key, const uint8_t *data, uint32_t n)
{
    uint32_t lane = NIMO_RAM->lane;
    nimo_crumb_stage(lane, NIMO_STAGE_REPLY);
    nimo_send_response(GLASSLY_CMD, key, data, n);
    nimo_crumb_stage(lane, NIMO_STAGE_DONE);
}

/* A UI job starts: it owns the UI lane until it has replied. */
static void job_start(uint32_t key, uint32_t seq, uint32_t mode, uint32_t len)
{
    NIMO_RAM->lane = NIMO_LANE_UI;
    nimo_crumb_start(NIMO_LANE_UI, NIMO_STAGE_DISPATCH, seq, key, mode, len);
}

/* The stock auto-off turns the display off after a few ticks of a black
 * stock canvas; while owned the panel is ours, so keep it marked lit. */
static void keep_lit(void)
{
    NIMO_LIT = 1;
    NIMO_BLANK = 0;
}

static int flush_rows(const uint8_t *fb, uint32_t top, uint32_t bottom)
{
    nimo_ram *ram = NIMO_RAM;
    nimo_crumb_stage(ram->lane, NIMO_STAGE_PRESENT);
    void *mutex = nimo_display_mutex();
    if (mutex != 0) nimo_os_lock(mutex);
    int rc = nimo_panel_flush(fb, 0, top, NIMO_PANEL_W, bottom - top);
    if (mutex != 0) nimo_os_unlock(mutex);
    keep_lit();
    if (rc == 0) {
        ram->presents++;
        ram->present_rows += bottom - top;
    } else {
        ram->flush_errors++;
    }
    return rc;
}

static void join_rows(uint16_t *top, uint16_t *bottom, uint32_t t, uint32_t b)
{
    if (b <= t) return;
    if (*bottom <= *top) {
        *top = (uint16_t)t;
        *bottom = (uint16_t)b;
        return;
    }
    if (t < *top) *top = (uint16_t)t;
    if (b > *bottom) *bottom = (uint16_t)b;
}

/* Rows a present changed: NULL or a full list means the whole raster; an
 * empty list means the render found nothing to redraw. */
static void dirty_rows(const mm_scene_dirty *dirty, uint32_t *top, uint32_t *bottom)
{
    if (dirty == 0 || dirty->n >= MM_SCENE_RECT_MAX) {
        *top = 0;
        *bottom = NIMO_PANEL_H;
        return;
    }
    uint32_t t = NIMO_PANEL_H, b = 0;
    for (uint32_t i = 0; i < dirty->n; i++) {
        const mm_scene_rect *r = &dirty->r[i];
        if (r->w == 0 || r->h == 0) continue;
        if (r->t < t) t = r->t;
        if ((uint32_t)r->t + r->h > b) b = (uint32_t)r->t + r->h;
    }
    if (b > NIMO_PANEL_H) b = NIMO_PANEL_H;
    if (b <= t) t = b = 0;
    *top = t;
    *bottom = b;
}

/* A SHOW that names the other eye still renders here (both arms keep the same
 * scene), but its rows wait until this eye's next present; every present then
 * sends at least what changed since this panel's last one. */
static void present(void *user, const mm_raster *raster, const mm_scene_dirty *dirty)
{
    nimo_session *s = user;
    uint32_t top, bottom;
    dirty_rows(dirty, &top, &bottom);
    uint8_t lens = s->scene.lens;
    if (lens != 0 && lens != s->eye) {
        join_rows(&s->pend_top, &s->pend_bottom, top, bottom);
        NIMO_RAM->presents_deferred++;
        return;
    }
    join_rows(&s->pend_top, &s->pend_bottom, top, bottom);
    top = s->pend_top;
    bottom = s->pend_bottom;
    if (bottom <= top) return;
    s->pend_top = s->pend_bottom = 0;
    if (flush_rows(raster->pixels, top, bottom) != 0) join_rows(&s->pend_top, &s->pend_bottom, top, bottom);
}

static void send_settled(uint16_t tag)
{
    uint8_t out[3] = { STATUS_OK, (uint8_t)tag, (uint8_t)(tag >> 8) };
    reply(KEY_SETTLED, out, sizeof out);
    NIMO_RAM->settled_sent++;
}

/* Settled tags wait for the reply of the dispatch that produced them. */
static void settled(void *user, uint16_t tag)
{
    nimo_session *s = user;
    if (s->settled_count < NIMO_SETTLED_QUEUE) s->settled[s->settled_count++] = tag;
    else send_settled(tag);
}

static void flush_settled(nimo_session *s)
{
    for (uint32_t i = 0; i < s->settled_count; i++) send_settled(s->settled[i]);
    s->settled_count = 0;
}

static void *allocate(void *user, size_t n)
{
    (void)user;
    void *p = nimo_malloc((uint32_t)n);
    if (p == 0) NIMO_RAM->alloc_failures++;
    return p;
}

static void deallocate(void *user, void *p)
{
    (void)user;
    nimo_free(p);
}

static uint32_t free_bytes(void *user)
{
    (void)user;
    return nimo_heap_free();
}

static uint32_t now_ms(void *user)
{
    (void)user;
    return nimo_now_ms();
}

static int active(void *user)
{
    nimo_ram *ram = NIMO_RAM;
    return ram->owned && ram->session == user;
}

static void mark(void *user, unsigned what)
{
    (void)user;
    if (what == MM_SCENE_MARK_RENDER) nimo_crumb_stage(NIMO_RAM->lane, NIMO_STAGE_RENDER);
}

/* The lease borrows one stock framebuffer as its canvas. Under the display
 * mutex (the frame task's) and with interrupts masked, the stock front index
 * moves onto the back buffer, so every stock writer uses that one; the kick
 * gate then holds off the commit, the only code that copies into the other
 * buffer or moves either index. Returns the canvas, or 0 when the indices are
 * not the two the stock code keeps. */
static uint8_t *pin_canvas(void)
{
    nimo_ram *ram = NIMO_RAM;
    void *mutex = nimo_display_mutex();
    if (mutex != 0) nimo_os_lock(mutex);
    nimo_critical_enter();
    uint8_t back = NIMO_FB_BACK, front = NIMO_FB_FRONT;
    int ok = back <= 1u && front <= 1u;
    if (ok) {
        ram->front = front;
        ram->back = back;
        NIMO_FB_FRONT = back;
        ram->pinned = 1;
        ram->owned = 1;
    }
    nimo_critical_exit();
    if (mutex != 0) nimo_os_unlock(mutex);
    return ok ? NIMO_FB(back ^ 1u) : 0;
}

/* Gives the canvas back: it gets the stock image again, the front index the
 * lease found returns, and only then do the stock kick and flush run again. */
static void unpin_canvas(void)
{
    nimo_ram *ram = NIMO_RAM;
    void *mutex = nimo_display_mutex();
    if (mutex != 0) nimo_os_lock(mutex);
    if (ram->pinned) copy_frame(NIMO_FB(ram->back ^ 1u), NIMO_FB(ram->back));
    nimo_critical_enter();
    if (ram->pinned) NIMO_FB_FRONT = ram->front;
    ram->pinned = 0;
    ram->owned = 0;
    nimo_critical_exit();
    if (mutex != 0) nimo_os_unlock(mutex);
}

/* Nothing stock should move the indices while pinned. If something did, the
 * stock writers now share the canvas: pin them back and resend everything. */
static void check_pin(nimo_session *s)
{
    nimo_ram *ram = NIMO_RAM;
    if (!ram->pinned || (NIMO_FB_BACK == ram->back && NIMO_FB_FRONT == ram->back)) return;
    nimo_critical_enter();
    NIMO_FB_BACK = ram->back;
    NIMO_FB_FRONT = ram->back;
    nimo_critical_exit();
    ram->repins++;
    s->pend_top = 0;
    s->pend_bottom = NIMO_PANEL_H;
    if (flush_rows(s->shadow, 0, NIMO_PANEL_H) == 0) s->pend_top = s->pend_bottom = 0;
}

static nimo_session *session_create(uint8_t *canvas)
{
    nimo_ram *ram = NIMO_RAM;
    if (nimo_heap_free() < sizeof(nimo_session) + NIMO_JOB_HEADROOM) {
        ram->alloc_failures++;
        return 0;
    }
    nimo_session *s = nimo_malloc(sizeof *s);
    if (s == 0) {
        ram->alloc_failures++;
        return 0;
    }
    zero(s, sizeof *s);
    s->shadow = canvas;
    zero(s->shadow, NIMO_FRAME_BYTES);
    mm_raster raster = { s->shadow, NIMO_FRAME_BYTES, NIMO_PANEL_W, NIMO_PANEL_H, NIMO_PANEL_STRIDE };
    mm_scene_session_hooks hooks = { s, allocate, deallocate, free_bytes, now_ms, active, present, settled, mark,
                                      nimo_builtin_text };
    if (mm_scene_session_init(&s->scene, &hooks, &raster, MM_SCENE_SESSION_BUDGET,
                              MM_SCENE_SESSION_HEADROOM, MM_SCENE_MIN_STORE) != 0) {
        nimo_free(s);
        return 0;
    }
    /* A new session never reuses the epoch a phone may still hold. */
    if (ram->epoch != 0) {
        uint16_t epoch = (uint16_t)(ram->epoch + 1u);
        s->scene.core.cache_epoch = epoch != 0 ? epoch : 1u;
    }
    s->eye = NIMO_IS_LEFT ? 1u : 2u;
    /* Eye-tagged objects (id bit 31, bit 30 right) render only for this arm. */
    s->scene.core.eye = s->eye;
    s->magic = NIMO_SESSION_MAGIC;
    return s;
}

static void session_destroy(nimo_session *s)
{
    nimo_ram *ram = NIMO_RAM;
    if (s->scene.core.cache_epoch != 0) ram->epoch = s->scene.core.cache_epoch;
    mm_scene_session_dispose(&s->scene);
    s->magic = 0;
    nimo_free(s);
}

static void pump(void *timer)
{
    (void)timer;
    nimo_ram *ram = NIMO_RAM;
    nimo_session *s = ram->session;
    uint32_t tick = ++ram->pump_ticks;
    if (!ram->owned || s == 0 || s->magic != NIMO_SESSION_MAGIC) return;
    ram->lane = NIMO_LANE_PUMP;
    nimo_crumb_start(NIMO_LANE_PUMP, NIMO_STAGE_TICK, tick, 0, 0, 0);
    keep_lit();
    check_pin(s);
    mm_scene_session_pump(&s->scene);
    flush_settled(s);
    nimo_crumb_stage(NIMO_LANE_PUMP, NIMO_STAGE_DONE);
}

/* [status][flush rc][display on][eye] */
void nimo_ui_acquire(void *arg)
{
    job_start(KEY_ACQUIRE, NIMO_JOB_SEQ(arg), 0, 0);
    nimo_ram *ram = NIMO_RAM;
    uint8_t out[4] = { STATUS_OK, 0xFF, NIMO_DISPLAY_ON, NIMO_IS_LEFT ? 1u : 2u };
    nimo_session *s = ram->session;
    if (s == 0) {
        uint8_t *canvas = pin_canvas();
        if (canvas == 0) {
            out[0] = STATUS_INVALID;
            reply(KEY_ACQUIRE, out, sizeof out);
            return;
        }
        s = session_create(canvas);
        if (s == 0) {
            unpin_canvas();
            out[0] = STATUS_NO_MEMORY;
            reply(KEY_ACQUIRE, out, sizeof out);
            return;
        }
        ram->session = s;
    }
    if (!ram->acquired) {
        ram->lease_brightness = (uint8_t)NIMO_PANEL_BRIGHTNESS;
        ram->brightness_changed = 0;
        ram->acquired = 1;
    }
    if (ram->timer == 0) ram->timer = nimo_lv_timer_create(pump, NIMO_PUMP_MS, 0);
    ram->eye = s->eye;
    ram->owned = 1;
    ram->acquires++;
    nimo_cancel_auto_off(2);
    /* The whole canvas reaches the panel: black on a new session, the retained
     * scene on a repeated acquire. */
    s->pend_top = 0;
    s->pend_bottom = NIMO_PANEL_H;
    int rc = flush_rows(s->shadow, 0, NIMO_PANEL_H);
    if (rc == 0) s->pend_top = s->pend_bottom = 0;
    out[1] = (uint8_t)rc;
    reply(KEY_ACQUIRE, out, sizeof out);
}

void nimo_ui_release(void *arg)
{
    job_start(KEY_RELEASE, NIMO_JOB_SEQ(arg), 0, 0);
    nimo_ram *ram = NIMO_RAM;
    uint8_t out[1] = { STATUS_OK };
    nimo_session *s = ram->session;
    ram->session = 0;
    if (ram->timer != 0) {
        nimo_lv_timer_delete(ram->timer);
        ram->timer = 0;
    }
    if (s != 0) session_destroy(s);
    unpin_canvas();
    /* A level set during the lease was the phone's; the wearer's comes back. */
    if (ram->acquired && ram->brightness_changed) nimo_set_brightness(ram->lease_brightness);
    ram->acquired = 0;
    ram->brightness_changed = 0;
    ram->releases++;
    /* Stock repaint: every framebuffer row dirty, then a full LVGL redraw. */
    nimo_repaint_all();
    nimo_lv_obj_invalidate(nimo_lv_screen_active());
    reply(KEY_RELEASE, out, sizeof out);
}

/* [status][cache reply...] */
void nimo_ui_scene(void *arg)
{
    nimo_job *job = arg;
    job_start(KEY_SCENE, job->seq, job->data[0], job->len);
    nimo_ram *ram = NIMO_RAM;
    uint8_t out[1 + sizeof(((mm_scene_context *)0)->cache_reply)];
    uint32_t n = 1;
    nimo_session *s = ram->session;
    if (!ram->owned || s == 0 || s->magic != NIMO_SESSION_MAGIC) {
        out[0] = STATUS_NOT_OWNED;
        s = 0;
    } else {
        int rc = mm_scene_session_dispatch(&s->scene, job->data, job->len);
        if (rc == 0) {
            out[0] = STATUS_OK;
            ram->scene_messages++;
            uint32_t len = s->scene.core.cache_reply_len;
            for (uint32_t i = 0; i < len && n < sizeof out; i++) out[n++] = s->scene.core.cache_reply[i];
        } else {
            out[0] = rc == -2 ? STATUS_NOT_OWNED : STATUS_INVALID;
            ram->scene_failures++;
        }
    }
    nimo_free(job);
    nimo_job_finished();
    reply(KEY_SCENE, out, n);
    if (s != 0) flush_settled(s);
}

/* [status][stock rc] */
void nimo_ui_brightness(void *arg)
{
    uint32_t level = NIMO_JOB_ARG(arg);
    job_start(KEY_BRIGHTNESS, NIMO_JOB_SEQ(arg), 0, 1);
    nimo_ram *ram = NIMO_RAM;
    if (level == 255u) {
        ram->brightness_changed = 0;
        ram->brightness_set = 0;
        uint8_t out[2] = { STATUS_OK, 0 };
        reply(KEY_BRIGHTNESS, out, sizeof out);
        return;
    }
    int rc = nimo_set_brightness(level);
    uint8_t out[2] = { rc == 0 ? STATUS_OK : STATUS_INVALID, (uint8_t)rc };
    if (rc == 0) {
        ram->brightness = (uint8_t)level;
        ram->brightness_set = 1;
        if (ram->acquired) ram->brightness_changed = 1;
    }
    reply(KEY_BRIGHTNESS, out, sizeof out);
}

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
    zero(fb, NIMO_FRAME_BYTES);
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

/* GLASSLYCFW/4 test pattern, kept for bring-up: [status][flush rc][left]. While
 * owned it replaces the canvas, as a raster message would. */
void nimo_ui_draw_test(void *arg)
{
    uint32_t pattern = NIMO_JOB_ARG(arg);
    job_start(KEY_DRAW_TEST, NIMO_JOB_SEQ(arg), 0, 1);
    uint8_t out[3] = { STATUS_NO_MEMORY, 0xFF, NIMO_IS_LEFT };
    nimo_session *s = NIMO_RAM->session;
    uint8_t *fb = s != 0 ? s->shadow : nimo_malloc(NIMO_FRAME_BYTES);
    if (fb != 0) {
        nimo_crumb_stage(NIMO_LANE_UI, NIMO_STAGE_RENDER);
        if (s != 0) mm_scene_takeover(&s->scene.core);
        draw_pattern(fb, pattern, NIMO_IS_LEFT != 0);
        int rc = flush_rows(fb, 0, NIMO_PANEL_H);
        if (s == 0) nimo_free(fb);
        else if (rc == 0) s->pend_top = s->pend_bottom = 0;
        else {
            s->pend_top = 0;
            s->pend_bottom = NIMO_PANEL_H;
        }
        out[0] = rc == 0 ? STATUS_OK : STATUS_INVALID;
        out[1] = (uint8_t)rc;
    }
    reply(KEY_DRAW_TEST, out, sizeof out);
}

/* [status][CRC-32 of this arm's canvas LE][eye 1 left / 2 right] */
void nimo_ui_canvas(void *arg)
{
    job_start(KEY_CANVAS, NIMO_JOB_SEQ(arg), 0, 0);
    nimo_session *s = NIMO_RAM->session;
    uint8_t out[6] = { STATUS_NOT_OWNED, 0, 0, 0, 0, NIMO_IS_LEFT ? 1u : 2u };
    if (NIMO_RAM->owned && s != 0 && s->magic == NIMO_SESSION_MAGIC) {
        uint32_t crc = nimo_crc32(s->shadow, NIMO_FRAME_BYTES);
        out[0] = STATUS_OK;
        for (uint32_t i = 0; i < 4; i++) out[1 + i] = (uint8_t)(crc >> (8u * i));
    }
    reply(KEY_CANVAS, out, sizeof out);
}

/* Touch messages while owned: [status][message id][stock length][first bytes
 * of the stock parameter, at most NIMO_INPUT_BYTES] as key 0x26 (the master
 * answers). Tap gestures carry 8 bytes: side (1 left), 1, source u16, gesture
 * sequence u32. The master keeps them from the stock screens; the slave hands
 * them on, as the stock code may forward them to the master from there. */
int glassly_input(uint32_t id, const uint8_t *param, uint32_t len)
{
    nimo_ram *ram = NIMO_RAM;
    if (id == NIMO_MSG_ANCS_RELAY) return glassly_ancs_forwarded(param, len);
    if (id == NIMO_MSG_AUTO_BRIGHTNESS && !ram->owned) return 0;
    uint32_t now = nimo_now_ms();
    int input_leased = ram->input_lease_until != 0 && (int32_t)(ram->input_lease_until - now) > 0;
    if (!ram->owned && !input_leased) return 0;
    /* Head messages reach the phone from the detector (glassly_head_event),
     * so the copies the stock screens produce are only kept from them. */
    if (id == NIMO_MSG_HEAD_UP || id == NIMO_MSG_HEAD_DOWN) return nimo_is_master();
    /* Once the phone has set a level, the stock ALS steps (both arms get
     * them) wait for the release. */
    if (id == NIMO_MSG_AUTO_BRIGHTNESS) {
        if (!ram->brightness_changed) return 0;
        ram->gate_skips++;
        return 1;
    }
    uint32_t seq = ++ram->inputs;
    job_start(KEY_INPUT, seq, id, len);
    uint8_t out[3 + NIMO_INPUT_BYTES];
    uint32_t n = param == 0 ? 0 : len < NIMO_INPUT_BYTES ? len : NIMO_INPUT_BYTES;
    out[0] = STATUS_OK;
    out[1] = (uint8_t)id;
    out[2] = (uint8_t)(len > 255u ? 255u : len);
    for (uint32_t i = 0; i < n; i++) out[3 + i] = param[i];
    reply(KEY_INPUT, out, 3 + n);
    return nimo_is_master();
}

static int lease_live(uint32_t until, uint32_t now)
{
    return until != 0 && (int32_t)(until - now) > 0;
}

static void head_job(void *arg)
{
    uint32_t packed = (uint32_t)(uintptr_t)arg;
    uint8_t out[3] = {STATUS_OK, (uint8_t)packed, 0};
    job_start(KEY_INPUT, packed >> 8, packed & 0xFFu, 0);
    reply(KEY_INPUT, out, sizeof out);
}

/* Sensor task, once per detector result (up nonzero for head-up, else
 * head-down), ahead of the stock HUD flag and screen filters that decide
 * whether a stock 0x86/0x87 is made at all. */
void glassly_head_event(uint32_t up)
{
    nimo_ram *ram = NIMO_RAM;
    if (!ram->owned && !lease_live(ram->input_lease_until, nimo_now_ms())) return;
    uint32_t seq = ++ram->heads;
    uint32_t id = up ? NIMO_MSG_HEAD_UP : NIMO_MSG_HEAD_DOWN;
    if (!nimo_gui_post_async(head_job, (void *)(uintptr_t)((seq << 8) | id))) ram->busy++;
}

#define IMU_HEAD 9u

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

/* UI task: [status][batch u16][overruns][count][ms tick u32][count x (x, y, z
 * int16 LE)], oldest sample first, 8196 counts per g. */
static void imu_job(void *arg)
{
    (void)arg;
    nimo_ram *ram = NIMO_RAM;
    ram->imu_posted = 0;
    for (;;) {
        uint16_t read = ram->imu_read;
        uint32_t n = (uint16_t)(ram->imu_write - read);
        if (n == 0) return;
        if (n > NIMO_IMU_RING) n = NIMO_IMU_RING;
        uint8_t out[IMU_HEAD + NIMO_IMU_RING * 6u];
        uint32_t seq = ++ram->imu_batches;
        job_start(KEY_IMU, seq, 0, n);
        out[0] = STATUS_OK;
        out[1] = (uint8_t)seq;
        out[2] = (uint8_t)(seq >> 8);
        out[3] = ram->imu_overruns;
        out[4] = (uint8_t)n;
        put_u32(out + 5, ram->imu_time);
        for (uint32_t i = 0; i < n; i++) {
            const int16_t *sample = ram->imu_ring[(uint16_t)(read + i) % NIMO_IMU_RING];
            for (uint32_t axis = 0; axis < 3; axis++) {
                uint16_t v = (uint16_t)sample[axis];
                out[IMU_HEAD + i * 6u + axis * 2u] = (uint8_t)v;
                out[IMU_HEAD + i * 6u + axis * 2u + 1u] = (uint8_t)(v >> 8);
            }
        }
        ram->imu_read = (uint16_t)(read + n);
        reply(KEY_IMU, out, IMU_HEAD + n * 6u);
    }
}

/* Sensor task, after every FIFO drain: records are the stock 7 x int16
 * layout whose first three are the accelerometer. While leased the head
 * task's stillness time stays at zero, so the FIFO never stops for
 * wake-on-motion. */
void glassly_imu_batch(const int16_t *records, uint32_t count)
{
    nimo_ram *ram = NIMO_RAM;
    uint32_t now = nimo_now_ms();
    if (!lease_live(ram->imu_lease_until, now)) return;
    nimo_still_reset();
    uint16_t write = ram->imu_write;
    for (uint32_t i = 0; i < count; i++, records += 7) {
        if ((uint16_t)(write - ram->imu_read) >= NIMO_IMU_RING) {
            ram->imu_overruns++;
            continue;
        }
        int16_t *slot = ram->imu_ring[write % NIMO_IMU_RING];
        slot[0] = records[0];
        slot[1] = records[1];
        slot[2] = records[2];
        write++;
    }
    ram->imu_time = now;
    ram->imu_write = write;
    if (ram->imu_posted) return;
    ram->imu_posted = 1;
    if (!nimo_gui_post_async(imu_job, 0)) {
        ram->imu_posted = 0;
        ram->busy++;
    }
}

/* [1] arms or renews a 90 s lease, [0] drops it. Reply [status][leased]
 * [overruns][batches u16][head events u16]. */
uint32_t glassly_imu_control(const uint8_t *payload, uint32_t len, uint8_t *out)
{
    nimo_ram *ram = NIMO_RAM;
    if (len != 1 || payload[0] > 1u) {
        out[0] = STATUS_INVALID;
        return 1;
    }
    uint32_t now = nimo_now_ms();
    ram->imu_lease_until = payload[0] ? now + NIMO_IMU_LEASE_MS : 0;
    if (payload[0] && ram->imu_lease_until == 0) ram->imu_lease_until = 1;
    out[0] = STATUS_OK;
    out[1] = (uint8_t)lease_live(ram->imu_lease_until, now);
    out[2] = ram->imu_overruns;
    out[3] = (uint8_t)ram->imu_batches;
    out[4] = (uint8_t)(ram->imu_batches >> 8);
    out[5] = (uint8_t)ram->heads;
    out[6] = (uint8_t)(ram->heads >> 8);
    return 7;
}
