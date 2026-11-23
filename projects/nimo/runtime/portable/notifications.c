/* MIT. G2 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce
 * patches/ancs_relay.c: queue, chunking, lease, framing and control semantics.
 * Adaptation: explicit context/platform, bounded record inputs, serialized queue.
 * Native ANCC hooks/struct offsets/absolute addresses intentionally excluded.
 * Exact upstream license is LICENSE in this directory. */
#include "notifications.h"
#define ANCS_PROTO_VERSION 1u
#define ANCS_RELAY_FIELD   125u

#define ANCS_OP_ENABLE   1u
#define ANCS_OP_DISABLE  2u
#define ANCS_OP_QUERY    3u
#define ANCS_OP_ACTION   4u
#define ANCS_OP_RENEW    5u

#define ANCS_KIND_SOURCE 1u
#define ANCS_KIND_ATTR   2u
#define ANCS_KIND_APP    3u
#define ANCS_KIND_STATUS 4u

#define ANCS_LEASE_MS    90000u
#define ANCS_RING_BYTES  4096u                 /* power of two; divides the 16-bit index space */
#define ANCS_RING_MASK   (ANCS_RING_BYTES - 1u)
#define ANCS_MSG_MAX     150u                  /* field-125 payload bytes, 'A','N' header included */
#define ANCS_HDR_LEN     4u                    /* 'A','N', version, kind */
#define ANCS_ATTR_FIXED  (ANCS_HDR_LEN + 9u)   /* uid, attr id, total, offset */
#define ANCS_APP_FIXED   (ANCS_HDR_LEN + 5u)   /* total, offset, id_len */
#define ANCS_APP_ID_MAX  64u                   /* stock keeps bundle ids in a 64-byte field */
#define ANCS_TICK_MS     20u
#define ANCS_RETRY_MS    100u
#define ANCS_BURST       2u

#define ANCS_NOW() ctx->platform.now_ms(ctx->platform.user)
#define ANCS_SIDE() ctx->platform.side(ctx->platform.user)
#define ANCS_SEND(b,n) ctx->platform.send(ctx->platform.user,b,n)
#define ANCS_ALLOC(n) ctx->platform.allocate(ctx->platform.user,n)
#define ANCS_TIMER_NEW(cb,a) ctx->platform.timer_new(ctx->platform.user,cb,a)
#define ANCS_TIMER_START(t,ms) ctx->platform.timer_start(ctx->platform.user,t,ms)
#define ANCS_TIMER_STOP(t) ctx->platform.timer_stop(ctx->platform.user,t)
#define ANCS_TIMER_DELETE(t) ctx->platform.timer_delete(ctx->platform.user,t)
static uint32_t rd16(const uint8_t *p) { return p[0]|((uint32_t)p[1]<<8); }
static uint32_t rd32(const uint8_t *p) { return rd16(p)|(rd16(p+2)<<16); }
static int ancs_lease_live(const mm_notifications *ctx) {
    return ctx->ancs_lease_deadline != 0 &&
           (int32_t)(ctx->ancs_lease_deadline - ANCS_NOW()) > 0;
}

/* Producer side: true when a hook may append. Read-only on purpose; the hooks
 * never clear an expired deadline, the consumer does. */
static int ancs_relay_armed(const mm_notifications *ctx) {
    return ctx->ancs_ring != 0 && ancs_lease_live(ctx);
}

static void ancs_kick(mm_notifications *ctx) {
    if (!ctx->ancs_idle || ctx->ancs_timer == 0) return;
    ctx->ancs_idle = 0;
    if (ANCS_TIMER_START(ctx->ancs_timer, ANCS_TICK_MS) != 0) ctx->ancs_idle = 1;
}

/* Append one record [len][epoch][payload...]: the field-125 payload is
 * hdr+body. Space is checked before any byte is written and the head index is
 * published last, so the consumer only ever sees complete records. */
static int ancs_push(mm_notifications *ctx, const uint8_t *hdr, uint32_t hdr_len,
                     const uint8_t *body, uint32_t body_len) {
    uint32_t len = hdr_len + body_len;
    uint32_t used = (uint16_t)(ctx->ancs_head - ctx->ancs_tail);
    if (len > ANCS_MSG_MAX || ANCS_RING_BYTES - used < len + 2u) {
        ctx->ancs_drops++;
        return 0;
    }
    uint8_t *ring = ctx->ancs_ring;
    uint32_t w = ctx->ancs_head;
    ring[w++ & ANCS_RING_MASK] = (uint8_t)len;
    ring[w++ & ANCS_RING_MASK] = ctx->ancs_epoch;
    for (uint32_t i = 0; i < hdr_len; i++) ring[w++ & ANCS_RING_MASK] = hdr[i];
    for (uint32_t i = 0; i < body_len; i++) ring[w++ & ANCS_RING_MASK] = body[i];
    ctx->ancs_head = (uint16_t)w;
    ancs_kick(ctx);
    return 1;
}

static void relay_source(mm_notifications *ctx,const uint8_t *notif) {
    if (!ancs_relay_armed(ctx)) return;
    uint8_t hdr[ANCS_HDR_LEN] = { 'A', 'N', ANCS_PROTO_VERSION, ANCS_KIND_SOURCE };
    ancs_push(ctx,hdr,sizeof hdr,notif,8);
}
static void relay_attribute(mm_notifications *ctx,uint32_t uid,uint8_t id,const uint8_t *data,uint32_t total) {
    if (!ancs_relay_armed(ctx)) return;
    uint8_t hdr[ANCS_ATTR_FIXED] = { 'A', 'N', ANCS_PROTO_VERSION, ANCS_KIND_ATTR };
    for (uint32_t i = 0; i < 4; i++) hdr[4 + i] = (uint8_t)(uid >> (8u*i));
    hdr[8] = id;
    hdr[9] = (uint8_t)total;
    hdr[10] = (uint8_t)(total >> 8);
    uint32_t off = 0;
    do {
        uint32_t chunk = total - off;
        if (chunk > ANCS_MSG_MAX - ANCS_ATTR_FIXED) chunk = ANCS_MSG_MAX - ANCS_ATTR_FIXED;
        hdr[11] = (uint8_t)off;
        hdr[12] = (uint8_t)(off >> 8);
        if (!ancs_push(ctx, hdr, sizeof hdr, data + off, chunk)) return;
        off += chunk;
    } while (off < total);
}

static void relay_app(mm_notifications *ctx,const uint8_t *buf,uint32_t n) {
    if (!ancs_relay_armed(ctx)) return;
    if (n < 5 || buf[0] != 1) return;
    uint32_t idx = 1;
    while (idx < n && buf[idx] != 0) idx++;
    uint32_t id_len = idx - 1;
    if (idx + 4 > n || buf[idx + 1] != 0 || id_len > ANCS_APP_ID_MAX) return;
    uint32_t total = rd16(buf + idx + 2);
    if (total > n - (idx + 4)) return;
    const uint8_t *data = buf + idx + 4;
    uint8_t hdr[ANCS_APP_FIXED + ANCS_APP_ID_MAX];
    hdr[0] = 'A'; hdr[1] = 'N'; hdr[2] = ANCS_PROTO_VERSION; hdr[3] = ANCS_KIND_APP;
    hdr[4] = (uint8_t)total;
    hdr[5] = (uint8_t)(total >> 8);
    hdr[8] = (uint8_t)id_len;
    for (uint32_t i = 0; i < id_len; i++) hdr[ANCS_APP_FIXED + i] = buf[1 + i];
    uint32_t hdr_len = ANCS_APP_FIXED + id_len;
    uint32_t off = 0;
    do {
        uint32_t chunk = total - off;
        if (chunk > ANCS_MSG_MAX - hdr_len) chunk = ANCS_MSG_MAX - hdr_len;
        hdr[6] = (uint8_t)off;
        hdr[7] = (uint8_t)(off >> 8);
        if (!ancs_push(ctx, hdr, hdr_len, data + off, chunk)) return;
        off += chunk;
    } while (off < total);
}

static uint32_t ancs_frame_len(uint32_t body_len) { return body_len >= 0x80u ? 8u : 7u; }

static void ancs_frame_notify(uint8_t *p, uint32_t body_len) {
    /* G2SettingPackage{commandId=3, magic=0, field 125}; tag 1002 = ea 07. */
    p[0] = 0x08; p[1] = 0x03;
    p[2] = 0x10; p[3] = 0x00;
    p[4] = 0xEA; p[5] = 0x07;
    if (body_len >= 0x80u) { p[6] = (uint8_t)(0x80u | (body_len & 0x7fu)); p[7] = (uint8_t)(body_len >> 7); }
    else p[6] = (uint8_t)body_len;
}

static void relay_tick(void *arg) {
    mm_notifications *ctx = (mm_notifications *)arg;
    if (!ctx || ctx->magic != MM_NOTIFICATIONS_MAGIC || !ctx->ancs_ring) return;
    uint8_t *ring = ctx->ancs_ring;
    if (!ancs_lease_live(ctx)) {
        /* Lease lapsed or DISABLE: discard everything queued and park. */
        ctx->ancs_lease_deadline = 0;
        ctx->ancs_tail = ctx->ancs_head;
        ctx->ancs_idle = 1;
        return;
    }
    uint32_t sent = 0;
    int failed = 0;
    while (sent < ANCS_BURST && !failed) {
        uint32_t r = ctx->ancs_tail;
        uint32_t used = (uint16_t)(ctx->ancs_head - r);
        if (used == 0) break;
        uint32_t len = ring[r & ANCS_RING_MASK];
        if (len == 0 || len > ANCS_MSG_MAX || used < len + 2u) {
            /* Not a record boundary: resynchronise on the producer's index. */
            ctx->ancs_tail = ctx->ancs_head;
            break;
        }
        uint8_t epoch = ring[(r + 1u) & ANCS_RING_MASK];
        uint8_t *p = ctx->ancs_notify_buf;
        uint32_t hdr = ancs_frame_len(len);
        for (uint32_t i = 0; i < len; i++) p[hdr + i] = ring[(r + 2u + i) & ANCS_RING_MASK];
        ctx->ancs_tail = (uint16_t)(r + 2u + len);
        if (epoch != ctx->ancs_epoch) continue;   /* queued before the current ENABLE */
        ancs_frame_notify(p, len);
        if (ANCS_SEND(p, hdr + len) != 0) {
            if (ctx->ancs_send_errs != 0xffu) ctx->ancs_send_errs++;
            failed = 1;
        } else {
            ctx->ancs_seq++;
        }
        sent++;
    }
    if ((uint16_t)(ctx->ancs_head - ctx->ancs_tail) != 0) {
        ANCS_TIMER_START(ctx->ancs_timer, failed ? ANCS_RETRY_MS : ANCS_TICK_MS);
        return;
    }
    /* Park, then re-check: a push that landed between the emptiness test and
     * the park would otherwise wait for the next push to restart the timer. */
    ctx->ancs_idle = 1;
    if ((uint16_t)(ctx->ancs_head - ctx->ancs_tail) != 0) ancs_kick(ctx);
}

/* ---- control plane (settings thread) --------------------------------------- */

static void ancs_send_status(mm_notifications *ctx) {
    uint8_t *p = ctx->ancs_status_buf;
    ancs_frame_notify(p, ANCS_HDR_LEN + 7u);
    p[7] = 'A'; p[8] = 'N'; p[9] = ANCS_PROTO_VERSION; p[10] = ANCS_KIND_STATUS;
    p[11] = ancs_lease_live(ctx) ? 1u : 0u;
    p[12] = (uint8_t)ANCS_SIDE();
    p[13] = (uint8_t)ctx->ancs_drops;
    p[14] = (uint8_t)(ctx->ancs_drops >> 8);
    p[15] = (uint8_t)ctx->ancs_seq;
    p[16] = (uint8_t)(ctx->ancs_seq >> 8);
    p[17] = ctx->ancs_send_errs;
    ANCS_SEND(p, 18);
}

/* Allocate the ring and the drain timer before the lease can arm, so a hook
 * never has to create anything. Returns 0 (and leaves the relay off) on OOM. */
static int ancs_arm(mm_notifications *ctx) {
    if (ctx->ancs_ring == 0) {
        ctx->ancs_ring = (uint8_t *)ANCS_ALLOC(ANCS_RING_BYTES);
        if (ctx->ancs_ring == 0) return 0;
        ctx->ancs_head = 0;
        ctx->ancs_tail = 0;
    }
    if (ctx->ancs_timer == 0) {
        ctx->ancs_timer = ANCS_TIMER_NEW(&mm_notifications_tick, ctx);
        if (ctx->ancs_timer == 0) return 0;
        ctx->ancs_idle = 1;
    }
    return 1;
}

static void apply_control(mm_notifications *ctx, const uint8_t *data, uint32_t len) {
    if (len < 4u || data[0] != 'A' || data[1] != 'N' ||
        data[2] != ANCS_PROTO_VERSION) return;
    if (ANCS_SIDE() != 1u) return;
    uint8_t op = data[3];
    if (op == ANCS_OP_ENABLE) {
        int fresh = !ancs_lease_live(ctx);
        if (ancs_arm(ctx)) {
            if (fresh) ctx->ancs_epoch++;
            ctx->ancs_lease_deadline = ANCS_NOW() + ANCS_LEASE_MS;
            ancs_kick(ctx);
        }
        ancs_send_status(ctx);
    } else if (op == ANCS_OP_DISABLE) {
        ctx->ancs_lease_deadline = 0;
        ancs_kick(ctx);            /* the tick discards whatever is queued */
        ancs_send_status(ctx);
    } else if (op == ANCS_OP_QUERY) {
        ancs_send_status(ctx);
    } else if (op == ANCS_OP_ACTION) {
        if (len >= 9u) { if (data[8] <= 1u) ctx->platform.action(ctx->platform.user, rd32(data + 4), data[8]); }
    } else if (op == ANCS_OP_RENEW) {
        if (ancs_lease_live(ctx)) ctx->ancs_lease_deadline = ANCS_NOW() + ANCS_LEASE_MS;
    }
}

static void cleanup_session(mm_notifications *ctx) {
    ctx->ancs_lease_deadline = 0;
    if (ctx->ancs_timer) {
        ANCS_TIMER_STOP(ctx->ancs_timer);
        if (ANCS_TIMER_DELETE(ctx->ancs_timer) == 0) ctx->ancs_timer = 0;
    }
    ctx->ancs_idle = 1;
}

static int valid(mm_notifications *ctx) { return ctx && ctx->magic==MM_NOTIFICATIONS_MAGIC; }
static void enter(mm_notifications *ctx) { ctx->platform.queue_enter(ctx->platform.user); }
static void leave(mm_notifications *ctx) { ctx->platform.queue_leave(ctx->platform.user); }
int mm_notifications_init(mm_notifications *ctx,const mm_notifications_platform *p) {
    if (!ctx || !p || !p->allocate || !p->deallocate || !p->now_ms || !p->side ||
        !p->timer_new || !p->timer_start || !p->timer_stop || !p->timer_delete ||
        !p->send || !p->action || !p->queue_enter || !p->queue_leave) return 0;
    /* Platform must not alias fresh context storage. */
    uintptr_t a=(uintptr_t)ctx,b=(uintptr_t)p;
    if (a<=b ? b-a<sizeof *ctx : a-b<sizeof *p) return 0;
    volatile uint8_t *v=(volatile uint8_t *)ctx;
    for(size_t i=0;i<sizeof *ctx;i++) v[i]=0;
    /* Individual assignments avoid freestanding memcpy imports. */
    ctx->platform.user=p->user;
#define COPY(name) ctx->platform.name=p->name
    COPY(allocate); COPY(deallocate); COPY(now_ms); COPY(side); COPY(timer_new);
    COPY(timer_start); COPY(timer_stop); COPY(timer_delete); COPY(send); COPY(action);
    COPY(queue_enter); COPY(queue_leave);
#undef COPY
    ctx->magic=MM_NOTIFICATIONS_MAGIC; return 1;
}
/* Caller-owned input must stay immutable and must not alias context/ring storage. */
static int input_ok(mm_notifications *ctx,const uint8_t *p,size_t n) {
    if (!p) return n==0;
    uintptr_t a=(uintptr_t)p,b=(uintptr_t)ctx;
    if (n>UINTPTR_MAX-a) return 0;
    if (a<=b ? b-a<n : a-b<sizeof *ctx) return 0;
    b=(uintptr_t)ctx->ancs_ring;
    return !b || !(a<=b ? b-a<n : a-b<ANCS_RING_BYTES);
}
void mm_notifications_control(mm_notifications *ctx,const uint8_t *p,size_t n) {
    if (!valid(ctx) || !p || n<4 || n>65535) return;
    enter(ctx); if(input_ok(ctx,p,n)) apply_control(ctx,p,(uint32_t)n); leave(ctx);
}
void mm_notifications_source(mm_notifications *ctx,const uint8_t *p,size_t n) {
    if (!valid(ctx) || !p || n!=8) return;
    enter(ctx); if(input_ok(ctx,p,n)) relay_source(ctx,p); leave(ctx);
}
void mm_notifications_attribute(mm_notifications *ctx,uint32_t uid,uint8_t id,const uint8_t *p,size_t n) {
    if (!valid(ctx) || (!p && n) || n>MM_NOTIFICATIONS_ATTRIBUTE_MAX) return;
    /* Empty null input uses a stable byte to avoid null+0 pointer arithmetic. */
    const uint8_t empty=0; if(!p) p=&empty;
    enter(ctx); if(input_ok(ctx,p,n)) relay_attribute(ctx,uid,id,p,(uint32_t)n); leave(ctx);
}
void mm_notifications_app_response(mm_notifications *ctx,const uint8_t *p,size_t n) {
    if (!valid(ctx) || !p || n>MM_NOTIFICATIONS_ATTRIBUTE_MAX) return;
    enter(ctx); if(input_ok(ctx,p,n)) relay_app(ctx,p,(uint32_t)n); leave(ctx);
}
void mm_notifications_tick(void *arg) {
    mm_notifications *ctx=arg; if(!valid(ctx)) return;
    enter(ctx); relay_tick(ctx); leave(ctx);
}
void mm_notifications_cleanup(mm_notifications *ctx) {
    if(!valid(ctx)) return;
    enter(ctx); cleanup_session(ctx); leave(ctx);
}
int mm_notifications_destroy(mm_notifications *ctx) {
    if(!valid(ctx)) return 0;
    enter(ctx); cleanup_session(ctx);
    if(ctx->ancs_timer) { leave(ctx); return 0; }
    if(ctx->ancs_ring) ctx->platform.deallocate(ctx->platform.user,ctx->ancs_ring);
    ctx->ancs_ring=0;ctx->magic=0;leave(ctx);return 1;
}
