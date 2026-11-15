/* Host check of the phone session (page.c, link.c, ident.c) on a fake clock,
 * link monitor and uplink: link loss ends the session while a dozing link
 * keeps it, the wake takeover and the slept-lease renewal need the link,
 * PAGE_OPEN renews an open page, and replies leave the tick that queued them.
 *
 *   clang -std=c11 -Ipatches -Ipatches/generated -o session_test tools/host/session_test.c
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cfw.h"

static customCfwContext ctx;
static uint32_t now = 1000;
static int link_up = 1, business_idle = 1, send_rc = 0, compass_stops, pushed_gesture;
static uint8_t sent[64][UPLINK_MAX];
static uint8_t sent_len[64];
static int sends;
static int lvgl_obj;

static void *t_memalign(uint32_t a, uint32_t n) { (void)a; return malloc(n); }
static void t_free(void *p) { free(p); }
static uint32_t t_tick(void) { return now; }
static int t_send(uint32_t biz, const void *b, uint32_t n, void *cb) {
    (void)biz; (void)cb;
    if (send_rc) return send_rc;
    assert(sends < 64 && n <= UPLINK_MAX);
    memcpy(sent[sends], b, n); sent_len[sends++] = (uint8_t)n;
    return 0;
}
static void *t_obj(void) { return &lvgl_obj; }
static void *t_obj1(void *p) { (void)p; return &lvgl_obj; }
static void t_noop1(void *p) { (void)p; }
static void t_flag(void *o, uint32_t f) { (void)o; (void)f; }
static void t_size(void *o, int32_t a, int32_t b) { (void)o; (void)a; (void)b; }
static void t_scroll(void *o, uint8_t m) { (void)o; (void)m; }
static int t_screen_cb(void *cb, const char *name, int prio, void *user) { (void)cb; (void)name; (void)prio; (void)user; return 0; }
static void *t_timer(void *cb, uint32_t period, void *user) { (void)cb; (void)period; (void)user; return &lvgl_obj; }
static int t_idle(void) { return business_idle; }
static void t_activity(void) {}
static int t_power(void) { return 1; }
static int t_zero(void) { return 0; }
static int t_inflate_init(cfw_zstream *z) { (void)z; return -1; }
static int t_inflate(cfw_zstream *z) { (void)z; return -1; }
static int t_inflate_end(cfw_zstream *z) { (void)z; return 0; }
static int t_msg_register(uint32_t m, void *h, void *u) { (void)m; (void)h; (void)u; return 0; }
static int t_msg_send(uint32_t m, const void *msg) { (void)m; (void)msg; return 0; }
static int t_rn_register(const void *c, uint32_t s, uint32_t b) { (void)c; (void)s; (void)b; return 0; }
static void t_mallinfo(cfw_mallinfo *m) { memset(m, 0, sizeof(*m)); }
#define fw_memalign t_memalign
#define fw_free t_free
#define fw_tick t_tick
#define fw_send t_send
#define fw_display_default t_obj
#define fw_screen_active t_obj1
#define fw_obj_create t_obj1
#define fw_obj_remove_style_all t_noop1
#define fw_obj_remove_flag t_flag
#define fw_obj_add_flag t_flag
#define fw_obj_set_scrollbar_mode t_scroll
#define fw_obj_set_size t_size
#define fw_obj_set_pos t_size
#define fw_obj_invalidate t_noop1
#define fw_screen_state_register t_screen_cb
#define fw_timer_create t_timer
#define fw_business_idle t_idle
#define fw_report_activity t_activity
#define fw_fb_get_power t_power
#define fw_inflate_init t_inflate_init
#define fw_inflate t_inflate
#define fw_inflate_end t_inflate_end
#define fw_msg_register t_msg_register
#define fw_msg_send t_msg_send
#define fw_rnlink_register t_rn_register
#define fw_mallinfo t_mallinfo

customCfwContext *cfw_ctx_peek(void) { return &ctx; }
customCfwContext *cfw_ctx(void) { return &ctx; }
uint8_t *cfw_rn_entry(void) { return NULL; }
void cfw_zero(void *p, uint32_t n) { memset(p, 0, n); }
uint8_t cfw_font_line_height(void) { return 25; }
int cfw_link_up(void) { return link_up; }
void cfw_input_wheel_listen(customCfwContext *c, int on) { (void)c; (void)on; }
void cfw_input_btn_listen(customCfwContext *c) { (void)c; }
void cfw_disp_pass(int on) { (void)on; }
void cfw_page_present(customCfwContext *c) { c->disp_dirty = 1; }
void cfw_compass_stop(customCfwContext *c) { (void)c; compass_stops++; }
void cfw_compass_tick(customCfwContext *c) { (void)c; }
void cfw_compass_control(customCfwContext *c, uint8_t arg) { (void)c; (void)arg; }
void cfw_anim_stop(customCfwContext *c) { (void)c; }
void cfw_anim_tick(customCfwContext *c) { (void)c; }
void cfw_scene_render(customCfwContext *c, cfw_lens *L) { (void)c; L->canvas_valid = 1; }
void cfw_head_angle(customCfwContext *c, uint8_t angle) { (void)c; (void)angle; }
void cfw_display_probe(customCfwContext *c, uint8_t mode) { (void)c; (void)mode; }
void cfw_input_poll(customCfwContext *c) {
    if (!pushed_gesture) return;
    pushed_gesture = 0;
    uint8_t g[7] = {RPL_GESTURE, GEST_SINGLE, 1, 0, 0, 0, 0};
    cfw_uplink_push(c, g, sizeof g);
}
int cfw_raster_mode(uint8_t mode) { (void)mode; return 0; }
int cfw_raster_message(customCfwContext *c, cfw_lens *L, const uint8_t *m, uint32_t n, int first,
                       uint8_t *reply_mode, uint8_t *status, uint16_t *request, uint8_t *extra, uint8_t *extra_len) {
    (void)c; (void)L; (void)m; (void)n; (void)first; (void)reply_mode; (void)status; (void)request; (void)extra; (void)extra_len; return 0;
}
int cfw_scene_message(customCfwContext *c, cfw_lens *L, const uint8_t *m, uint32_t n, uint8_t *status, uint16_t *request,
                      int first, uint8_t *extra, uint8_t *extra_len) {
    (void)c; (void)L; (void)m; (void)n; (void)status; (void)request; (void)first; (void)extra; (void)extra_len; return 0;
}

#include "ident.c"
#include "page.c"
#include "link.c"

static int queued(void) { return (ctx.uplink_tail + UPLINK_QUEUE - ctx.uplink_head) % UPLINK_QUEUE; }
static int last_page(uint8_t state, uint8_t reason) {
    for (int i = sends - 1; i >= 0; i--)
        if (sent[i][0] == RPL_PAGE) return sent[i][1] == state && sent[i][2] == reason;
    return 0;
}
static void query_and_open(void) {
    cfw_control(&ctx, CTRL_QUERY, 0);
    cfw_control(&ctx, CTRL_PAGE_OPEN, 0);
    assert(ctx.page_open);
    cfw_page_tick(&ctx);
    assert(last_page(1, PAGE_OK) && !queued());
}

int main(void) {
    puts("link loss ends the session");
    query_and_open();
    assert(ctx.queried && ctx.link_seen && ctx.disp_clear);
    ctx.lens[0].last_show_valid = 1;
    link_up = 0;
    int before = sends;
    cfw_page_tick(&ctx);
    assert(!ctx.page_open && !ctx.queried && !ctx.wake_takeover && compass_stops == 1);
    assert(sends == before && !queued());                    /* the close is not sent into a dead link */
    ctx.wake_pending = 1; link_up = 1;
    cfw_page_tick(&ctx);
    assert(!ctx.page_open);                                  /* no takeover of the lost session's scene */

    puts("a reconnect's QUERY before the launcher records the connect does not count as loss");
    link_up = 0;
    query_and_open();
    assert(ctx.queried && !ctx.link_seen);
    cfw_page_tick(&ctx);
    assert(ctx.page_open && ctx.queried);
    link_up = 1; cfw_page_tick(&ctx); assert(ctx.link_seen);
    link_up = 0; cfw_page_tick(&ctx); assert(!ctx.page_open && !ctx.queried);

    puts("a dozing link keeps the page past a slept lease, once");
    link_up = 1;
    query_and_open();
    ctx.lens[0].last_show_valid = 1;
    now += PAGE_LEASE_MS + 60000u;                           /* the timer did not run while it slept */
    cfw_page_tick(&ctx);
    assert(ctx.page_open && ctx.page_by_takeover && ctx.queried && last_page(1, PAGE_OK));
    now += PAGE_LEASE_MS + 60000u;
    cfw_page_tick(&ctx);
    assert(!ctx.page_open && last_page(0, PAGE_LEASE) && !ctx.wake_takeover);

    puts("PAGE_OPEN on an open page renews it without the idle gate");
    query_and_open();
    business_idle = 0;
    now += PAGE_LEASE_MS - 1000u;
    cfw_control(&ctx, CTRL_PAGE_OPEN, 0);
    cfw_uplink_flush(&ctx);
    assert(ctx.page_open && last_page(1, PAGE_OK) && ctx.lease_deadline == now + PAGE_LEASE_MS);
    now += 2000u; cfw_page_tick(&ctx); assert(ctx.page_open);
    business_idle = 1;

    puts("the wake takeover needs the link");
    now = ctx.lease_deadline;                                /* the lease ran out while awake */
    cfw_page_tick(&ctx);
    assert(!ctx.page_open && ctx.wake_takeover && last_page(0, PAGE_LEASE));
    ctx.link_seen = 0; link_up = 0;                          /* down, but not seen up since QUERY */
    ctx.wake_pending = 1; cfw_page_tick(&ctx);
    assert(!ctx.page_open && !ctx.wake_takeover);
    link_up = 1;
    query_and_open();
    ctx.lens[0].last_show_valid = 1;
    now = ctx.lease_deadline; cfw_page_tick(&ctx);
    assert(ctx.wake_takeover);
    ctx.wake_pending = 1; cfw_page_tick(&ctx);
    assert(ctx.page_open && ctx.page_by_takeover && last_page(1, PAGE_OK));
    puts("a slept lease is not renewed without the link either");
    ctx.page_by_takeover = 0; ctx.link_seen = 0; link_up = 0;
    now = ctx.lease_deadline + LEASE_SLEPT_MS + 1u;
    cfw_page_tick(&ctx);
    assert(!ctx.page_open);
    link_up = 1;

    puts("replies queued during a tick leave in that tick");
    query_and_open();
    pushed_gesture = 1;
    before = sends;
    cfw_page_tick(&ctx);
    assert(sends == before + 1 && sent[sends - 1][0] == RPL_GESTURE && !queued());

    puts("a full uplink ring drains before it drops");
    send_rc = -1;
    for (int i = 0; i < (int)UPLINK_QUEUE - 1; i++) cfw_send_page_state(&ctx, 1, (uint8_t)i);
    assert(queued() == UPLINK_QUEUE - 1);
    uint8_t extra[3] = {RPL_PAGE, 1, 99};
    assert(!cfw_uplink_push(&ctx, extra, 3));                /* the link is busy: dropped */
    send_rc = 0; before = sends;
    assert(cfw_uplink_push(&ctx, extra, 3));
    assert(sends == before + (int)UPLINK_QUEUE - 1 && queued() == 1);
    for (int i = 0; i < (int)UPLINK_QUEUE - 1; i++) assert(sent[before + i][2] == i);
    cfw_uplink_flush(&ctx);
    assert(sent[sends - 1][2] == 99);
    puts("session: link loss, dozing link, takeover gating, PAGE_OPEN renewal, tick flush and full ring passed");
    for (unsigned e = 0; e < 2; e++) { free(ctx.lens[e].canvas); free(ctx.lens[e].base); }
    return 0;
}
