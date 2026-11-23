/* Own every scene allocation and adapt its one-shot timer to the serialized
 * UI task. No stock addresses, writable globals or locks. Ported from the
 * MemoMind runtime. MIT. */
#include "scene_session.h"
#include "raster_commands.h"
#include "rect_copy_commands.h"

/* The stock heap guarantees 4-byte alignment on RV32. Do not impose uint64_t
 * alignment: all retained core heap types use at most pointer alignment. */
typedef struct { size_t bytes; unsigned kind; } allocation_header;
_Static_assert(_Alignof(allocation_header)<=_Alignof(void *),"Native header alignment");

static void *allocate(void *user, unsigned kind, size_t size) {
    mm_scene_session *s=user;
    if (!size || size>SIZE_MAX-sizeof(allocation_header)) goto denied;
    size_t total=size+sizeof(allocation_header);
    if (s->live_bytes>s->budget || total>s->budget-s->live_bytes) goto denied;
    size_t available=s->hooks.free_bytes(s->hooks.user);
    if (available<s->headroom || total>available-s->headroom) goto denied;
    allocation_header *header=s->hooks.allocate(s->hooks.user,total);
    if (!header) goto denied;
    header->bytes=total;header->kind=kind;
    s->live_bytes+=total;
    if (s->live_bytes>s->peak_bytes) s->peak_bytes=s->live_bytes;
    return header+1;
denied:
    if (s->denied_allocations!=UINT32_MAX) s->denied_allocations++;
    return 0;
}
static void deallocate(void *user,unsigned kind,void *memory) {
    mm_scene_session *s=user;
    allocation_header *header=(allocation_header *)memory-1;
    (void)kind; /* Core returns only pointers obtained from its own callbacks. */
    s->live_bytes-=header->bytes;
    s->hooks.deallocate(s->hooks.user,header);
}
static uint32_t now(void *user) {
    mm_scene_session *s=user;return s->hooks.now_ms(s->hooks.user);
}
static int active(void *user) {
    mm_scene_session *s=user;return s->initialized && s->hooks.active(s->hooks.user);
}
static int shadow(void *user,mm_raster *raster) {
    mm_scene_session *s=user;*raster=s->raster;return 1;
}
static uintptr_t timer_new(void *user,void (*callback)(void *),void *arg) {
    mm_scene_session *s=user;
    /* No allocation or scheduler registration: the owner already pumps this
     * exact callback on the UI task, serially with dispatch. */
    return callback==mm_scene_tick && arg==&s->core ? 1u:0u;
}
static void timer_start(void *user,uintptr_t timer,uint32_t ms) {
    mm_scene_session *s=user;
    if (timer!=1u || !ms) return;
    s->timer_period=ms;s->timer_started=now(s);s->timer_armed=1;
}
static void timer_stop(void *user,uintptr_t timer) {
    mm_scene_session *s=user;(void)timer;s->timer_armed=0;
}
static void present(void *user,mm_scene_context *ctx,const mm_raster *raster,
                    mm_scene_dirty *dirty) {
    mm_scene_session *s=user;
    /* The original timer deferred rendering to a second display task. Here
     * we already own that task: finish the pending frame before presenting. */
    mm_scene_render_if_due_rects(ctx,raster->pixels,dirty);
    s->hooks.present(s->hooks.user,raster,dirty);
    dirty->direct_submitted=1;
}
static void settled(void *user,uint16_t tag) {
    mm_scene_session *s=user;
    if (s->hooks.settled) s->hooks.settled(s->hooks.user,tag);
}
static void mark(mm_scene_session *s,unsigned what) {
    if (s->hooks.mark) s->hooks.mark(s->hooks.user,what);
}
static int builtin_text(void *user,const mm_raster *raster,const uint8_t *text,size_t size,
                        mm_scene_dirty *dirty,uint32_t *tokens,size_t count) {
    mm_scene_session *s=user;(void)tokens;(void)count;
    return s->hooks.builtin_text(s->hooks.user,raster,text,size,dirty);
}
int mm_scene_session_init(mm_scene_session *s,const mm_scene_session_hooks *hooks,
                          const mm_raster *raster,size_t budget,size_t headroom,
                          uint32_t store_limit) {
    if (!s || !hooks || !hooks->allocate || !hooks->deallocate || !hooks->free_bytes ||
        !hooks->now_ms || !hooks->active || !hooks->present || mm_raster_validate(raster) ||
        raster->width>MM_VECTOR_MAX_DIMENSION || raster->height>MM_VECTOR_MAX_DIMENSION ||
        s->initialized || store_limit<MM_SCENE_MIN_STORE || store_limit>MM_SCENE_MAX_STORE)
        return -1;
    s->hooks=*hooks;s->raster=*raster;s->budget=budget;s->headroom=headroom;
    s->live_bytes=s->peak_bytes=0;s->denied_allocations=0;s->timer_armed=0;
    s->timer_started=s->timer_period=0;s->lens=0;
    mm_scene_platform p={s,allocate,deallocate,now,active,shadow,timer_new,timer_start,
        timer_stop,0,0,present,settled,0,hooks->builtin_text ? builtin_text:0};
    if (mm_scene_init(&s->core,&p,store_limit)) return -1;
    s->initialized=1;s->core.cache_reply_cap=250;
    return 0;
}
/* Mode 15 [15][x s16][y s16][options][len][text]: the hook checks the whole
 * string before it draws, so a refused one leaves the pixels and the animation
 * alone; a drawn one owns the canvas like a raster command. */
static int text_command(mm_scene_session *s,const uint8_t *data,size_t size,mm_scene_dirty *dirty) {
    if(size<7 || size!=7u+data[6] || !s->hooks.builtin_text)return -1;
    if(s->hooks.builtin_text(s->hooks.user,&s->raster,data+1,size-1,dirty))return -1;
    mm_scene_takeover(&s->core);
    s->core.shadow_stale=0;
    return 0;
}
/* Called only after full-batch prepare. Raster commands do not clear the final
 * cache reply scratch; each cache dispatch clears/replaces it internally. */
static int bundle_segment(mm_scene_session *s,const uint8_t *data,size_t size) {
    uint8_t mode=data[0]&127u;
    if(mode==3 || mode==6 || mode==9){
        s->bundle_full=1;
        if(mode==9 ? mm_rect_copy_validate(&s->raster,data,size):mm_raster_command_validate(&s->raster,data,size))return -1;
        mm_scene_takeover(&s->core);
        int rc=mode==9 ? mm_rect_copy_draw(&s->raster,data,size):mm_raster_command_draw(&s->raster,data,size);
        if(rc)return -1;
        s->core.shadow_stale=0;
        return 0;
    }
    if(mode>=37 && mode<=41)return mm_scene_dispatch(&s->core,mode,data+1,size-1,0,&s->bundle_dirty);
    if(mode==15)return text_command(s,data,size,&s->bundle_dirty);
    s->bundle_full=1;
    if(mode==19 || mode==20 || mode==36){
        mm_scene_dirty dirty;dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        int rc=mm_scene_immediate_mode(&s->core,&s->raster,data,size,mode,&dirty);
        if(!rc)mm_scene_takeover(&s->core);
        return rc;
    }
    /* Nested bundles and control commands are unsupported. Earlier segments
     * are intentionally kept. */
    return -1;
}
static int bundle(mm_scene_session *s,const uint8_t *data,size_t size) {
    if(size<2)return -1;
    mm_scene_prepare(&s->core,8,data+1,size-1);
    mark(s,MM_SCENE_MARK_RENDER);
    s->bundle_dirty.n=0;s->bundle_dirty.direct_submitted=0;s->bundle_dirty.direct_failed=0;s->bundle_full=0;
    size_t pos=2;
    for(unsigned i=0;i<data[1];i++){
        if(size-pos<2)return -1;
        size_t n=(size_t)data[pos]|((size_t)data[pos+1]<<8);pos+=2;
        if(!n || n>size-pos)return -1;
        if(bundle_segment(s,data+pos,n))return -1;
        pos+=n;
    }
    /* Even count 0 presents once. Trailing bytes are ignored as upstream. */
    mm_scene_render_if_due_rects(&s->core,s->raster.pixels,&s->bundle_dirty);
    s->hooks.present(s->hooks.user,&s->raster,
                     s->bundle_full || s->bundle_dirty.n>=MM_SCENE_RECT_MAX ? 0:&s->bundle_dirty);
    return 0;
}
static int overlaps_session(const mm_scene_session *s,const uint8_t *data,size_t size) {
    uintptr_t a=(uintptr_t)data,b=(uintptr_t)s;
    return size>UINTPTR_MAX-a || (a<=b?b-a<size:a-b<sizeof(*s));
}
int mm_scene_session_dispatch(mm_scene_session *s,const uint8_t *data,size_t size) {
    if (!s || !s->initialized || !data || !size || size>MM_SCENE_MAX_MESSAGE) return -1;
    if (overlaps_session(s,data,size) || !mm_scene_raster_input_valid(&s->core,data,size)) return -1;
    s->core.cache_reply_len=0;
    if (!active(s)) return -2;
    uint8_t mode=data[0]&127u;
    s->lens=mode==38 && size>5 ? (uint8_t)(data[5]>>4&3u):0;
    if (mode==8) return bundle(s,data,size);
    if (mode==15) {
        mm_scene_dirty dirty;
        dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        mark(s,MM_SCENE_MARK_RENDER);
        if (text_command(s,data,size,&dirty)) return -1;
        s->hooks.present(s->hooks.user,&s->raster,&dirty);
        return 0;
    }
    if (mode==9) {
        if (mm_rect_copy_validate(&s->raster,data,size)) return -1;
        mark(s,MM_SCENE_MARK_RENDER);
        mm_scene_takeover(&s->core);
        if (mm_rect_copy_draw(&s->raster,data,size)) return -1;
        s->core.shadow_stale=0;
        s->hooks.present(s->hooks.user,&s->raster,0);
        return 0;
    }
    if (mode==3 || mode==6) {
        /* Validate first: malformed raster input neither freezes the scene nor
         * alters pixels. Serial stable input means the following draw cannot
         * fail validation. Takeover stops animation before raster ownership. */
        if (mm_raster_command_validate(&s->raster,data,size)) return -1;
        mark(s,MM_SCENE_MARK_RENDER);
        mm_scene_takeover(&s->core);
        if (mm_raster_command_draw(&s->raster,data,size)) return -1;
        s->core.shadow_stale=0;
        s->hooks.present(s->hooks.user,&s->raster,0);
        return 0;
    }
    if (mode>=37 && mode<=41) {
        mm_scene_prepare(&s->core,mode,data+1,size-1);
        mark(s,MM_SCENE_MARK_RENDER);
        mm_scene_dirty dirty;
        dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        return mm_scene_dispatch(&s->core,mode,data+1,size-1,1,&dirty);
    }
    if (mode==19 || mode==20 || mode==36) {
        mm_scene_dirty dirty;
        dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        mark(s,MM_SCENE_MARK_RENDER);
        int result=mm_scene_immediate(&s->core,&s->raster,data,size,&dirty);
        if (!result) {
            mm_scene_takeover(&s->core);
            s->hooks.present(s->hooks.user,&s->raster,0);
        }
        return result;
    }
    return -1;
}
void mm_scene_session_pump(mm_scene_session *s) {
    if (!s || !s->initialized) return;
    if (!active(s)) {
        s->timer_armed=0;mm_scene_lose(&s->core);mm_scene_reap(&s->core);return;
    }
    if (s->timer_armed && (uint32_t)(now(s)-s->timer_started)>=s->timer_period) {
        s->timer_armed=0;mark(s,MM_SCENE_MARK_RENDER);mm_scene_tick(&s->core);
    }
}
void mm_scene_session_dispose(mm_scene_session *s) {
    if (!s || !s->initialized) return;
    s->timer_armed=0;mm_scene_release(&s->core);s->initialized=0;
}
