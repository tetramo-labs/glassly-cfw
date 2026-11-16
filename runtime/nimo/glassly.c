/* GLASSLYCFW runtime for NIMO: the display lease, the retained scene and the
 * breadcrumbs. Command 0x7E (unused by stock firmware); docs/runtime.md has
 * the key table. Replies are [status][data...] through the stock response
 * path. The router runs this on its own task: anything that touches LVGL or
 * the panel is copied and posted to the UI task, which sends the reply when it
 * has run. */
#include "glassly.h"

#ifndef GLASSLY_CFW_REVISION
#error "GLASSLY_CFW_REVISION is required"
#endif
#define STR2(x) #x
#define STR(x) STR2(x)

/* build_response frames a reply in a 608-byte buffer. The status JSON with a
 * last_crash record stays under this with every field at its widest (537
 * bytes; the host and emulator tests build that case). */
enum { REPLY_MAX = 560 };

static uint32_t append(uint8_t *out, uint32_t at, const char *text)
{
    while (*text != 0 && at < REPLY_MAX) out[at++] = (uint8_t)*text++;
    return at;
}

static uint32_t append_u32(uint8_t *out, uint32_t at, uint32_t value)
{
    char digits[10];
    uint32_t n = 0;
    do {
        digits[n++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value != 0);
    while (n != 0 && at < REPLY_MAX) out[at++] = (uint8_t)digits[--n];
    return at;
}

static void put32(uint8_t *out, uint32_t value)
{
    for (uint32_t i = 0; i < 4; i++) out[i] = (uint8_t)(value >> (8u * i));
}

/* Reflected 0xEDB88320, bitwise to stay small. */
uint32_t nimo_crc32(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint32_t k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void nimo_crumb_start(uint32_t lane, uint32_t stage, uint32_t seq, uint32_t key, uint32_t mode, uint32_t len)
{
    volatile nimo_crumb *c = &NIMO_CRUMBS->lane[lane];
    c->stage = NIMO_STAGE_IDLE;
    c->seq = seq;
    c->len = len;
    c->key = (uint8_t)key;
    c->mode = (uint8_t)mode;
    c->stage = (uint8_t)stage;
}

void nimo_crumb_stage(uint32_t lane, uint32_t stage)
{
    ((volatile nimo_crumb *)&NIMO_CRUMBS->lane[lane])->stage = (uint8_t)stage;
}

/* First command since a reset (the zeroed block has no magic yet): keep the
 * previous boot's lanes if the record is intact, else start a fresh one. */
static void crumbs_boot(nimo_ram *ram)
{
    nimo_crumbs *c = NIMO_CRUMBS;
    if (c->magic == NIMO_CRUMB_MAGIC && c->check == ~NIMO_CRUMB_MAGIC && c->boot != 0 && c->boot < 0xFFFFFFFFu) {
        for (uint32_t i = 0; i < NIMO_LANES; i++) ram->last[i] = c->lane[i];
        c->boot++;
        ram->crumbs = 2;
    } else {
        c->magic = NIMO_CRUMB_MAGIC;
        c->check = ~NIMO_CRUMB_MAGIC;
        c->boot = 1;
        c->reserved = 0;
        ram->crumbs = 1;
    }
    for (uint32_t i = 0; i < NIMO_LANES; i++) nimo_crumb_start(i, NIMO_STAGE_IDLE, 0, 0, 0, 0);
    ram->boot = c->boot;
}

/* At most NIMO_MAX_JOBS scene messages wait for the UI task. No AMOs on this
 * core: the count changes inside the stock critical section. */
static int job_reserve(nimo_ram *ram)
{
    nimo_critical_enter();
    int ok = ram->jobs < NIMO_MAX_JOBS;
    if (ok) ram->jobs = ram->jobs + 1u;
    nimo_critical_exit();
    return ok;
}

void nimo_job_finished(void)
{
    nimo_ram *ram = NIMO_RAM;
    nimo_critical_enter();
    if (ram->jobs != 0) ram->jobs = ram->jobs - 1u;
    nimo_critical_exit();
}

static uint32_t identity(uint8_t *out)
{
    nimo_ram *ram = NIMO_RAM;
    uint32_t n = 0;
    out[n++] = STATUS_OK;
    n = append(out, n, "{\"version\":\"GLASSLYCFW/" STR(GLASSLY_CFW_REVISION)
                       "\",\"revision\":" STR(GLASSLY_CFW_REVISION)
                       ",\"platform\":\"nimo\",\"base\":\"1.1.5.1\",\"arm\":\"");
    n = append(out, n, nimo_is_master() ? "master" : "slave");
    n = append(out, n, "\",\"eye\":\"");
    n = append(out, n, NIMO_IS_LEFT ? "left" : "right");
    n = append(out, n, "\",\"canvas\":{\"width\":540,\"height\":280,\"stride\":270,\"format\":\"gray4\"},"
                       "\"eyes\":[\"left\",\"right\"],\"scene\":{\"modes\":[3,6,8,9,15,19,20,36,37,38,39,40,41],"
                       "\"store\":65536,\"objects\":128,\"assets\":128,\"show_eye_bits\":true,"
                       "\"eye_objects\":true,\"text\":true},"
                       "\"max_message\":");
    n = append_u32(out, n, NIMO_MAX_PAYLOAD);
    n = append(out, n, ",\"owned\":");
    n = append_u32(out, n, ram->owned);
    n = append(out, n, "}");
    return n;
}

static uint32_t field(uint8_t *out, uint32_t at, const char *name, uint32_t value)
{
    at = append(out, at, name);
    return append_u32(out, at, value);
}

static const char *const lane_names[NIMO_LANES] = { "router", "ui", "pump" };
static const char *const stage_names[NIMO_STAGES] = {
    "idle", "router", "posted", "dispatch", "render", "present", "reply", "done", "tick",
};

static int crumb_open(const nimo_crumb *c)
{
    return c->stage != NIMO_STAGE_IDLE && c->stage != NIMO_STAGE_POSTED && c->stage != NIMO_STAGE_DONE;
}

/* The previous boot's breadcrumbs: the lane that stopped mid-way (UI first,
 * then the pump, then the router), with "open" naming every such lane (bit per
 * lane), or null when the previous boot ended at rest or left no record. */
static uint32_t last_crash(uint8_t *out, uint32_t n, const nimo_ram *ram)
{
    static const uint8_t order[NIMO_LANES] = { NIMO_LANE_UI, NIMO_LANE_PUMP, NIMO_LANE_ROUTER };
    uint32_t open = 0, pick = NIMO_LANES;
    for (uint32_t i = 0; i < NIMO_LANES && ram->crumbs == 2; i++) {
        uint32_t lane = order[i];
        if (!crumb_open(&ram->last[lane])) continue;
        open |= 1u << lane;
        if (pick == NIMO_LANES) pick = lane;
    }
    n = append(out, n, ",\"last_crash\":");
    if (pick == NIMO_LANES) return append(out, n, "null");
    const nimo_crumb *c = &ram->last[pick];
    n = append(out, n, "{\"lane\":\"");
    n = append(out, n, lane_names[pick]);
    n = append(out, n, "\",\"stage\":\"");
    n = append(out, n, c->stage < NIMO_STAGES ? stage_names[c->stage] : "?");
    n = field(out, n, "\",\"seq\":", c->seq);
    n = field(out, n, ",\"key\":", c->key);
    n = field(out, n, ",\"mode\":", c->mode);
    n = field(out, n, ",\"len\":", c->len);
    n = field(out, n, ",\"open\":", open);
    return append(out, n, "}");
}

/* Live counters from the RAM block plus the stock heap totals; the
 * breadcrumbs come first so a truncated print still shows them. */
static uint32_t status_json(uint8_t *out)
{
    nimo_ram *ram = NIMO_RAM;
    uint32_t n = 0;
    out[n++] = STATUS_OK;
    n = field(out, n, "{\"owned\":", ram->owned);
    n = field(out, n, ",\"session\":", ram->session != 0);
    n = field(out, n, ",\"boot\":", ram->boot);
    n = last_crash(out, n, ram);
    n = field(out, n, ",\"heap_free\":", nimo_heap_free());
    n = field(out, n, ",\"heap_largest\":", nimo_heap_largest(0));
    n = field(out, n, ",\"display_on\":", NIMO_DISPLAY_ON);
    n = field(out, n, ",\"panel_brightness\":", NIMO_PANEL_BRIGHTNESS);
    n = field(out, n, ",\"brightness\":", ram->brightness_set ? ram->brightness : 0xFFu);
    n = field(out, n, ",\"gate_skips\":", ram->gate_skips);
    n = field(out, n, ",\"repins\":", ram->repins);
    n = field(out, n, ",\"inputs\":", ram->inputs);
    n = field(out, n, ",\"presents\":", ram->presents);
    n = field(out, n, ",\"deferred\":", ram->presents_deferred);
    n = field(out, n, ",\"flush_errors\":", ram->flush_errors);
    n = field(out, n, ",\"scenes\":", ram->scene_messages);
    n = field(out, n, ",\"rejected\":", ram->scene_failures);
    n = field(out, n, ",\"settled\":", ram->settled_sent);
    n = field(out, n, ",\"busy\":", ram->busy);
    n = field(out, n, ",\"alloc_failures\":", ram->alloc_failures);
    n = field(out, n, ",\"pump_ticks\":", ram->pump_ticks);
    n = field(out, n, ",\"commands\":", ram->commands);
    n = append(out, n, "}");
    return n;
}

/* Copies the payload and queues it for the UI task; 0 when queued. */
static uint32_t post_scene(const uint8_t *payload, uint32_t len, uint32_t seq)
{
    nimo_ram *ram = NIMO_RAM;
    if (len == 0) return STATUS_INVALID;
    if (len > NIMO_MAX_PAYLOAD) return STATUS_TOO_LARGE;
    if (!job_reserve(ram)) {
        ram->busy++;
        return STATUS_BUSY;
    }
    nimo_job *job = 0;
    if (nimo_heap_free() >= sizeof(nimo_job) + len + NIMO_JOB_HEADROOM) job = nimo_malloc(sizeof(nimo_job) + len);
    if (job == 0) {
        nimo_job_finished();
        ram->alloc_failures++;
        return STATUS_NO_MEMORY;
    }
    job->len = len;
    job->seq = seq;
    for (uint32_t i = 0; i < len; i++) job->data[i] = payload[i];
    if (nimo_gui_post_async(nimo_ui_scene, job)) return STATUS_OK;
    nimo_free(job);
    nimo_job_finished();
    ram->busy++;
    return STATUS_BUSY;
}

static uint32_t post(nimo_ui_fn fn, uint32_t arg, uint32_t seq)
{
    if (nimo_gui_post_async(fn, (void *)(uintptr_t)((seq << 8) | (arg & 0xFFu)))) return STATUS_OK;
    NIMO_RAM->busy++;
    return STATUS_BUSY;
}

int glassly_command(uint32_t cmd, uint32_t key, const uint8_t *payload, uint32_t len)
{
    uint8_t reply[REPLY_MAX];
    uint32_t n = 0;
    uint32_t status;
    nimo_ram *ram = NIMO_RAM;

    if ((cmd & 0xFFu) != GLASSLY_CMD) return 0;
    if (ram->magic != NIMO_RAM_MAGIC) crumbs_boot(ram);
    ram->magic = NIMO_RAM_MAGIC;
    uint32_t seq = ++ram->commands;
    nimo_crumb_start(NIMO_LANE_ROUTER, NIMO_STAGE_ROUTER, seq, key, (key & 0xFFu) == KEY_SCENE && len ? payload[0] : 0u,
                     len);
    switch (key & 0xFFu) {
    case KEY_IDENTITY:
        n = identity(reply);
        break;
    case KEY_STATUS:
        n = status_json(reply);
        break;
    case KEY_ECHO:
        reply[n++] = STATUS_OK;
        for (uint32_t i = 0; i < len && n < REPLY_MAX; i++) reply[n++] = payload[i];
        break;
    case KEY_CHECKSUM:
        reply[n++] = STATUS_OK;
        put32(reply + n, len);
        put32(reply + n + 4, nimo_crc32(payload, len));
        n += 8;
        break;
    case KEY_DRAW_TEST:
        status = post(nimo_ui_draw_test, len > 0 ? payload[0] : 0u, seq);
        if (status == STATUS_OK) goto posted;
        reply[n++] = (uint8_t)status;
        break;
    case KEY_SCENE:
        status = post_scene(payload, len, seq);
        if (status == STATUS_OK) goto posted;
        reply[n++] = (uint8_t)status;
        break;
    case KEY_CANVAS:
        status = post(nimo_ui_canvas, 0, seq);
        if (status == STATUS_OK) goto posted;
        reply[n++] = (uint8_t)status;
        break;
    case KEY_ACQUIRE:
    case KEY_RELEASE:
        status = post((key & 0xFFu) == KEY_ACQUIRE ? nimo_ui_acquire : nimo_ui_release, 0, seq);
        if (status == STATUS_OK) goto posted;
        reply[n++] = (uint8_t)status;
        break;
    case KEY_ANCS_CONTROL:
        n = glassly_ancs_control(payload, len, reply);
        break;
    case KEY_INPUT_CONTROL:
        if (len != 1 || payload[0] > 1u) {
            reply[n++] = STATUS_INVALID;
            break;
        }
        ram->input_lease_until = payload[0] ? nimo_now_ms() + NIMO_INPUT_LEASE_MS : 0;
        if (payload[0] && ram->input_lease_until == 0) ram->input_lease_until = 1;
        reply[n++] = STATUS_OK;
        break;
    case KEY_BRIGHTNESS:
        if (len != 1 || (payload[0] > 32u && payload[0] != 255u)) {
            reply[n++] = STATUS_INVALID;
            break;
        }
        status = post(nimo_ui_brightness, payload[0], seq);
        if (status == STATUS_OK) goto posted;
        reply[n++] = (uint8_t)status;
        break;
    default:
        reply[n++] = STATUS_UNSUPPORTED;
        break;
    }
    nimo_crumb_stage(NIMO_LANE_ROUTER, NIMO_STAGE_REPLY);
    nimo_send_response(cmd, key, reply, n);
    nimo_crumb_stage(NIMO_LANE_ROUTER, NIMO_STAGE_DONE);
    return 1;
posted:
    /* The UI task owns the job now and sends its reply. */
    nimo_crumb_stage(NIMO_LANE_ROUTER, NIMO_STAGE_POSTED);
    return 1;
}
