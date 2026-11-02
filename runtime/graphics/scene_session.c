/* Own every scene allocation and adapt its one-shot timer to the serialized
 * MemoMind display worker. No stock addresses, writable globals or locks. */
#include "scene_session.h"
#ifdef MM_RASTER_COMMANDS
#include "raster_commands.h"
#ifdef MM_RECT_COPY
#include "rect_copy_commands.h"
#endif
#endif

/* Native TLSF guarantees4-byte alignment on RV32. Do not impose uint64_t
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
    /* No allocation or scheduler registration: the native owner already pumps
     * this exact callback on the display worker, serially with dispatch. */
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
     * we already own that task: finish the pending frame before LVGL borrows it. */
    mm_scene_render_if_due(ctx,raster->pixels);
    s->hooks.present(s->hooks.user,raster);
    dirty->direct_submitted=1;
}
static void settled(void *user,uint16_t tag) {
    mm_scene_session *s=user;
    if (s->hooks.settled) s->hooks.settled(s->hooks.user,tag);
}
static int builtin_text(void *user,const mm_raster *raster,const uint8_t *text,
                        size_t size,mm_scene_dirty *dirty,uint32_t *tokens,size_t count) {
    mm_scene_session *s=user;
    return s->hooks.builtin_text ?
        s->hooks.builtin_text(s->hooks.user,raster,text,size,dirty,tokens,count):-1;
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
    s->timer_started=s->timer_period=0;
    mm_scene_platform p={s,allocate,deallocate,now,active,shadow,timer_new,timer_start,
        timer_stop,0,0,present,settled,0,hooks->builtin_text ? builtin_text:0};
    if (mm_scene_init(&s->core,&p,store_limit)) return -1;
    s->initialized=1;s->core.cache_reply_cap=250;
    return 0;
}
#ifdef MM_TEXT_COMMANDS
/* Mode15 owns temporary token scratch; native callbacks preflight the entire
 * string before pixels change. Serialized display execution makes takeover
 * after successful drawing safe, while failures preserve animation and pixels. */
static int text_command(mm_scene_session *s,const uint8_t *data,size_t size) {
    if(size<7 || size!=7u+data[6] || !s->hooks.builtin_text)return -1;
    size_t count=data[6]?data[6]:1u;
    uint32_t *tokens=allocate(s,MM_SCENE_WORKSPACE,count*sizeof(*tokens));
    if(!tokens)return -3;
    mm_scene_dirty dirty;dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
    int rc=s->hooks.builtin_text(s->hooks.user,&s->raster,data+1,size-1,&dirty,tokens,count);
    deallocate(s,MM_SCENE_WORKSPACE,tokens);
    if(rc)return -1;
    mm_scene_takeover(&s->core);s->core.shadow_stale=0;
    return 0;
}
#endif
#ifdef MM_COMMAND_BUNDLES
/* Called only after full-batch prepare. Raster commands do not clear the final
 * cache reply scratch; each cache dispatch clears/replaces it internally. */
static int bundle_segment(mm_scene_session *s,const uint8_t *data,size_t size) {
    uint8_t mode=data[0]&127u;
#ifdef MM_TEXT_COMMANDS
    if(mode==15)return text_command(s,data,size);
#endif
    if(mode==3 || mode==6 || mode==9){
#ifdef MM_DIAGNOSTIC_COMMANDS
        if(s->hooks.frame)s->hooks.frame(s->hooks.user,data,size);
#endif
        if(mode==9 ? mm_rect_copy_validate(&s->raster,data,size):mm_raster_command_validate(&s->raster,data,size))return -1;
        mm_scene_takeover(&s->core);
        int rc=mode==9 ? mm_rect_copy_draw(&s->raster,data,size):mm_raster_command_draw(&s->raster,data,size);
        if(rc)return -1;
        s->core.shadow_stale=0;
        return 0;
    }
    mm_scene_dirty dirty;dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
    if(mode>=37 && mode<=41)return mm_scene_dispatch(&s->core,mode,data+1,size-1,0,&dirty);
    if(mode==19 || mode==20 || mode==36){
        int rc=mm_scene_immediate_mode(&s->core,&s->raster,data,size,mode,&dirty);
        if(!rc)mm_scene_takeover(&s->core);
        return rc;
    }
    /* Without MM_TEXT_COMMANDS, mode15 is unsupported. No nested bundle or
     * control command is accepted. Earlier segments are intentionally kept. */
    return -1;
}
static int bundle(mm_scene_session *s,const uint8_t *data,size_t size) {
    if(size<2)return -1;
    mm_scene_prepare(&s->core,8,data+1,size-1);
    size_t pos=2;
    for(unsigned i=0;i<data[1];i++){
        if(size-pos<2)return -1;
        size_t n=(size_t)data[pos]|((size_t)data[pos+1]<<8);pos+=2;
        if(!n || n>size-pos)return -1;
#ifdef MM_TEXT_COMMANDS
        int rc=bundle_segment(s,data+pos,n);if(rc)return rc;
#else
        if(bundle_segment(s,data+pos,n))return -1;
#endif
        pos+=n;
    }
    /* Even count0 presents once. Trailing bytes are ignored as upstream. */
    s->hooks.present(s->hooks.user,&s->raster);
    return 0;
}
#endif
int mm_scene_session_dispatch(mm_scene_session *s,const uint8_t *data,size_t size) {
    if (!s || !s->initialized || !data || !size || size>MM_SCENE_MAX_MESSAGE) return -1;
#ifdef MM_RASTER_COMMANDS
    uintptr_t input=(uintptr_t)data,owner=(uintptr_t)s;
    if (size>UINTPTR_MAX-input || (input<=owner?owner-input<size:input-owner<sizeof(*s)) ||
        !mm_scene_raster_input_valid(&s->core,data,size)) return -1;
#endif
    s->core.cache_reply_len=0;
    if (!active(s)) return -2;
    uint8_t mode=data[0];
#ifdef MM_TEXT_COMMANDS
    if((mode&127u)==15){
        int rc=text_command(s,data,size);
        if(!rc)s->hooks.present(s->hooks.user,&s->raster);
        return rc;
    }
#endif
#ifdef MM_COMMAND_BUNDLES
    if ((mode&127u)==8) return bundle(s,data,size);
#endif
#ifdef MM_RASTER_COMMANDS
#ifdef MM_RECT_COPY
    if ((mode&127u)==9) {
        if (mm_rect_copy_validate(&s->raster,data,size)) return -1;
        mm_scene_takeover(&s->core);
        if (mm_rect_copy_draw(&s->raster,data,size)) return -1;
        s->core.shadow_stale=0;
        s->hooks.present(s->hooks.user,&s->raster);
        return 0;
    }
#endif
    if ((mode&127u)==3 || (mode&127u)==6) {
#ifdef MM_DIAGNOSTIC_COMMANDS
        if(s->hooks.frame)s->hooks.frame(s->hooks.user,data,size);
#endif
        uintptr_t a=(uintptr_t)data,b=(uintptr_t)s;
        if (size>UINTPTR_MAX-a || (a<=b?b-a<size:a-b<sizeof(*s)) ||
            mm_raster_command_validate(&s->raster,data,size)) return -1;
        /* Validate first: malformed raster input neither freezes the scene nor
         * alters pixels. Serial stable input means the following draw cannot
         * fail validation. Takeover stops animation before raster ownership. */
        mm_scene_takeover(&s->core);
        if (mm_raster_command_draw(&s->raster,data,size)) return -1;
        s->core.shadow_stale=0;
        s->hooks.present(s->hooks.user,&s->raster);
        return 0;
    }
#endif
    if (mode>=37 && mode<=41) {
        mm_scene_prepare(&s->core,mode,data+1,size-1);
        mm_scene_dirty dirty;
        dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        int rc=mm_scene_dispatch(&s->core,mode,data+1,size-1,1,&dirty);
#ifdef MM_SCENE_RESET_UNDO_TRIM
        /* Never trim from bundle_segment: later children use scratch already
         * promised by whole-bundle prepare. rc==0 alone also includes rejects. */
        if (!rc && mode==41 && size>=6 && data[5]==0)
            (void)mm_scene_trim_reset_undo(&s->core);
#endif
        return rc;
    }
    if (mode==19 || mode==20 || mode==36) {
        mm_scene_dirty dirty;
        dirty.n=0;dirty.direct_submitted=0;dirty.direct_failed=0;
        int result=mm_scene_immediate(&s->core,&s->raster,data,size,&dirty);
        if (!result) {
            mm_scene_takeover(&s->core);
            s->hooks.present(s->hooks.user,&s->raster);
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
        s->timer_armed=0;mm_scene_tick(&s->core);
    }
}
void mm_scene_session_dispose(mm_scene_session *s) {
    if (!s || !s->initialized) return;
    s->timer_armed=0;mm_scene_release(&s->core);s->initialized=0;
}
