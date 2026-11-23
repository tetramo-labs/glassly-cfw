#ifdef MM_SENSOR_CAPTURE
#include "sensor_capture.h"
#endif
#ifndef MM_CFW_REVISION
#define MM_CFW_REVISION 1
#endif
#define MM_STRING_VALUE(x) #x
#define MM_STRING(x) MM_STRING_VALUE(x)
#ifdef MM_NOTIFICATION_RELAY
#include "notification_native.h"
#endif
#ifdef MM_WAKE_CONTROL
#include "wake_control.h"
#endif
/* MemoMind display-worker adapter. Native APIs are isolated in native.c.
 * No writable globals; separate owned context and palette/pixel allocations.
 * Native allocator OOM/assert behavior is a separate admission requirement; the
 * NULL paths tested here do not establish that the firmware can safely exhaust.
 */
#include "graphics.h"
#ifdef MM_MICROPHONE_CONTROL
#include "microphone_native.h"
#endif
#ifdef MM_DIAGNOSTIC_COMMANDS
#include "diagnostics.h"
#endif
#ifdef MM_GRAPHICS_INPUT
#include "input.h"
#endif
#ifdef MM_GRAPHICS_SCENE
#include "scene_session.h"
#include "native_text.h"
#endif

#ifdef MM_FLASH_SCENE
#include "large_message.h"
#endif
#ifdef MM_RECORD_TRANSPORT
#include "record_session.h"
#endif
#define P mm_graphics_native
#define OWNER_MAGIC 0x474c4931u
typedef struct {
    uint32_t magic, started;
    void *parent, *image, *timer;
    mm_native_image descriptor;
#ifdef MM_FLASH_SCENE
    mm_large_message assembly;
#ifdef MM_RECORD_TRANSPORT
    mm_record_session *records;
    uint32_t records_started;
#endif
#endif
#ifdef MM_GRAPHICS_SCENE
    mm_scene_session scene;
    uint16_t settled_tags[4];
    uint8_t settled_count, event;
#ifdef MM_RAW_PRESENT
    /* lvgl_stale: the image object is hidden or unsourced and must be restored
     * (one stock redraw) before raw copies can rely on it as the fallback. */
    uint8_t lvgl_stale;
    uint32_t raw_presents, raw_fallbacks;
    /* Box (l,t,r,b; empty when r<=l) each eye's panel still lacks: a SHOW for
     * one eye leaves the other panel's box pending. [0] left, [1] right. */
    uint16_t eye_box[2][4];
#endif
#ifdef MM_COMMAND_BUNDLES
    /* Display-call owned scratch, borrowed here solely by settled callbacks. */
    uint16_t *bundle_tags;
    uint16_t bundle_count,bundle_capacity;
    uint8_t bundle_active,bundle_overflow;
#endif
#endif
} owner;

static const char ok[] = "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"ok\",\"presentation\":\"scheduled\"}";
static const char cleared[] = "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"cleared\"}";
static const char invalid[] = "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"invalid\"}";
static const char busy[] = "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"stock-ui-active\"}";
static const char no_memory[] = "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"allocation-failed\"}";

static void *reply(const char *text) {
    void *value=P.json(text);
    return value ? value : P.status(4, 0);
}
static int valid_message(const uint8_t *data, size_t length) {
#ifdef MM_GRAPHICS_SCENE
#ifdef MM_FLASH_SCENE
    if (!data || !length || length>MM_SCENE_MAX_MESSAGE) return 0;
#ifdef MM_RECORD_TRANSPORT
    if(data[0]==MM_RECORD_MODE)return mm_record_valid(data,length);
#endif
    if(data[0]==MM_LARGE_WIRE_MODE)return length>=6 && length<=MM_LARGE_CHUNK+8;
#else
    if (!data || !length || length>MM_GRAPHICS_MAX_MESSAGE) return 0;
#endif
#ifdef MM_RASTER_COMMANDS
    if ((data[0]&127u)==3 || (data[0]&127u)==6) return length>=3;
#ifdef MM_RECT_COPY
    if ((data[0]&127u)==9) return length>=((data[0]&128u)?33u:17u);
#endif
#endif
#ifdef MM_COMMAND_BUNDLES
    if ((data[0]&127u)==8) return length>=2;
#endif
#ifdef MM_TEXT_COMMANDS
    if ((data[0]&127u)==15) return length>=7 && length==7u+data[6];
#endif
#ifdef MM_DIAGNOSTIC_COMMANDS
    if ((data[0]&127u)==7 || (data[0]&127u)==11) return 1;
#endif
    if (data[0]==11) return length==1;
    if ((data[0]&127u)>=37 && (data[0]&127u)<=41) return length>=5;
    return length>=2 && ((data[0]&127u)==19 || (data[0]&127u)==20 || (data[0]&127u)==36);
#else
    return data && ((length==1 && data[0]==11) ||
                    mm_geometry_validate_message(data,length)==MM_GEOMETRY_OK);
#endif
}
static void deleted(void *event) {
    owner *o=P.event_userdata(event);
    if (!o || o->magic!=OWNER_MAGIC) return;
    o->magic=0;
#ifdef MM_FLASH_SCENE
    mm_large_clear(&o->assembly,P.free);
#ifdef MM_RECORD_TRANSPORT
    mm_record_close(o->records);o->records=0;
#endif
#endif
    void *timer=o->timer;
    o->timer=0;
    if (timer) P.timer_delete(timer);
#ifdef MM_GRAPHICS_SCENE
    mm_scene_session_dispose(&o->scene);
#endif
    P.cache_invalidate(&o->descriptor);
    if (o->descriptor.data) P.free((void *)o->descriptor.data);
    P.free(o);
}
#ifdef MM_WAKE_CONTROL
void glassly_graphics_drop_frame(void *parent) {
    owner *o=parent?P.find_owner(parent,deleted):0;
    if(o && o->magic==OWNER_MAGIC)P.image_delete(o->image);
}
#endif
#ifdef MM_MINIMAL_LAUNCHER
/* Display-task lifecycle only. Never deletes the shared active screen. */
void glassly_graphics_cleanup(void) {
#ifdef MM_MICROPHONE_CONTROL
    glassly_microphone_cleanup();
#ifdef MM_SENSOR_CAPTURE
    glassly_sensor_cleanup();
#endif
#endif
#ifdef MM_NOTIFICATION_RELAY
    glassly_notification_cleanup();
#endif
    void *parent=P.screen();
    if(!parent)return;
    owner *o=P.find_owner(parent,deleted);
    if(o && o->magic==OWNER_MAGIC){
        if(o->scene.initialized)mm_scene_session_dispose(&o->scene);
        P.image_delete(o->image);
    }
#ifdef MM_DIAGNOSTIC_COMMANDS
    mm_diagnostics_dispose(parent);
    glassly_input_cleanup(parent);
#ifdef MM_WAKE_CONTROL
    glassly_wake_cleanup(parent);
#endif
#endif
}
#endif
#ifdef MM_GRAPHICS_SCENE
static void flush_settled(owner *o);
#ifdef MM_FLASH_SCENE
static void scene_present(void *,const mm_raster *,const mm_scene_dirty *);
#endif
#endif
static void tick(void *timer) {
    owner *o=P.timer_userdata(timer);
    if (!o || o->magic!=OWNER_MAGIC) return;
#ifdef MM_WAKE_CONTROL
#ifdef MM_RECORD_TRANSPORT
    if(o->records && (uint32_t)(P.now()-o->records_started)>=MM_GRAPHICS_LEASE_TICKS){
        mm_record_close(o->records);o->records=0;
    }
#endif
    if(o->assembly.data && (uint32_t)(P.now()-o->started)>=MM_GRAPHICS_LEASE_TICKS)
        mm_large_clear(&o->assembly,P.free);
#endif
    if (!P.launcher_active() || P.screen()!=o->parent ||
        ((uint32_t)(P.now()-o->started)>=MM_GRAPHICS_LEASE_TICKS
#ifdef MM_WAKE_CONTROL
         && !glassly_wake_frame_active(o->parent)
#endif
        )) {
        P.image_delete(o->image);
        /* DELETE callback frees both owner and current timer. */
        return;
    }
#ifdef MM_GRAPHICS_SCENE
#if defined(MM_FLASH_SCENE) && !defined(MM_RAW_PRESENT)
    /* The stock refresh could paint a half-rendered raster: hide the image
     * around the tick and re-present afterwards. Raw presents copy only
     * finished boxes, so they skip both invalidations. */
    int detached=o->scene.timer_armed && (uint32_t)(P.now()-o->scene.timer_started)>=o->scene.timer_period;
    if(detached)glassly_graphics_detach(o->image);
#endif
    mm_scene_session_pump(&o->scene);
#if defined(MM_FLASH_SCENE) && !defined(MM_RAW_PRESENT)
    if(detached)scene_present(o,&o->scene.raster,0);
#endif
    flush_settled(o);
#endif
}
static owner *create(void *parent) {
    /* Policy headroom, not a largest-block or concurrency guarantee. Keep large
     * owned data allocation last; its native allocator returns NULL on no fit. */
    if (P.free_bytes()<MM_GRAPHICS_METADATA_MARGIN+sizeof(owner)) return 0;
    owner *o=P.alloc(sizeof(*o));
    if (!o) return 0;
#ifdef MM_GRAPHICS_SCENE
    for (size_t i=0;i<sizeof(*o);i++) ((uint8_t *)o)[i]=0;
#endif
    o->magic=OWNER_MAGIC; o->parent=parent; o->image=0; o->timer=0;
    o->started=P.now();
#ifdef MM_RAW_PRESENT
    o->lvgl_stale=1;
#endif
    o->descriptor.header=(MM_GRAPHICS_HEIGHT<<21)|(MM_GRAPHICS_WIDTH<<10)|9u;
    o->descriptor.data_size=64u+MM_GRAPHICS_PIXELS;
    o->descriptor.data=0;
    o->image=P.image_create(parent);
    if (!o->image) { P.free(o); return 0; }
    if (!P.on_delete(o->image,deleted,o)) {
        P.image_delete(o->image); P.free(o); return 0;
    }
    /* Once attached, only the DELETE callback owns final free. */
    o->timer=P.timer_create(tick,MM_GRAPHICS_TIMER_TICKS,o);
    if (!o->timer) { P.image_delete(o->image); return 0; }
    if (P.free_bytes()<64u+MM_GRAPHICS_PIXELS+MM_GRAPHICS_METADATA_MARGIN) {
        P.image_delete(o->image); return 0;
    }
    uint32_t *palette=P.alloc(64u+MM_GRAPHICS_PIXELS);
    if (!palette) { P.image_delete(o->image); return 0; }
    o->descriptor.data=(const uint8_t *)palette;
    for (uint32_t i=0;i<16;i++) palette[i]=0xff000000u|(i*17u)*0x010101u;
    uint8_t *pixels=(uint8_t *)palette+64;
    for (size_t i=0;i<MM_GRAPHICS_PIXELS;i++) pixels[i]=0;
    return o;
}
#ifdef MM_GRAPHICS_SCENE
static void *scene_allocate(void *user,size_t n) {(void)user;return P.alloc(n);}
static void scene_free(void *user,void *p) {(void)user;P.free(p);}
static uint32_t scene_free_bytes(void *user) {(void)user;return P.free_bytes();}
static uint32_t scene_now(void *user) {(void)user;return P.now();}
static int scene_active(void *user) {
    owner *o=user;
    return o->magic==OWNER_MAGIC && P.launcher_active() && P.screen()==o->parent &&
        ((uint32_t)(P.now()-o->started)<MM_GRAPHICS_LEASE_TICKS
#ifdef MM_WAKE_CONTROL
         || glassly_wake_frame_active(o->parent)
#endif
        );
}
#ifdef MM_RAW_PRESENT
/* The stock JBD013 driver feeds both eyes' panels from one framebuffer: bit
 * 4 of this byte enables panel 1 (right eye, calibration "right"), bit 5
 * panel 2 (left). With one bit clear the synchronous submit queues the box
 * for the other panel only; the bits are put back right after. */
#define PANEL_ENABLE ((volatile uint8_t *)0x02010318u)
static const uint16_t whole_panel[4]={0,0,MM_GRAPHICS_WIDTH,MM_GRAPHICS_HEIGHT};
static __attribute__((noinline)) void box_join(uint16_t *a,const uint16_t *b) {
    if(b[2]<=b[0])return;
    unsigned empty=a[2]<=a[0];
    for(unsigned i=0;i<4;i++)if(empty || (i<2 ? b[i]<a[i]:b[i]>a[i]))a[i]=b[i];
}
/* Copy box l,t,r,b of the owned raster straight into the locked panel slices
 * and submit it to `panels` (0x30 both), bypassing the LVGL redraw. Returns 0
 * when the stock lock refuses (display inactive, another app current). The
 * raster and the panel share GRAY4 packing; only the stride differs (300 vs
 * 320 bytes). */
static __attribute__((noinline)) int raw_submit(const mm_raster *raster,const uint16_t *box,uint8_t panels) {
    uint32_t l=box[0],t=box[1],r=box[2],b=box[3];
    if(r<=l)return 1;
    uint8_t mask=0;
    if(!(P.slice_lock(t,b-1u,0,&mask)&0xffu) || !mask)return 0;
    uint32_t x0=l>>1,bytes=(r-l)>>1;
    for(uint32_t y=t;y<b;y++){
        uint8_t *dst=P.slice_pixels(0,(int32_t)y,0);
        if(!dst){P.slice_submit(mask,0,0);return 0;}
        const uint8_t *src=raster->pixels+(size_t)y*raster->stride+x0;
        for(uint32_t i=0;i<bytes;i++)dst[x0+i]=src[i];
    }
    uint16_t rect[4]={(uint16_t)l,(uint16_t)t,(uint16_t)(r-1u),(uint16_t)(b-1u)};
    volatile uint8_t *enable=PANEL_ENABLE;
    uint8_t on=*enable&0x30u;
    if(on==0x30u)*enable=(uint8_t)((*enable&~0x30u)|panels);
    int submitted=(P.slice_submit(mask,rect,1)&0xffu)!=0;
    if(on==0x30u)*enable=(uint8_t)((*enable&~0x30u)|on);
    return submitted;
}
/* Present the changed box. A SHOW that names one eye reaches only that eye's
 * panel; every present sends a panel at least what changed since its last
 * one, so the eyes stay exact through any order of one-eye and both-eye frames. */
static int raw_present(owner *o,const mm_raster *raster,const mm_scene_dirty *dirty) {
    if(!P.slice_lock || !P.slice_pixels || !P.slice_submit || !raster || !raster->pixels ||
       raster->width!=MM_GRAPHICS_WIDTH || raster->height!=MM_GRAPHICS_HEIGHT || raster->stride!=MM_GRAPHICS_STRIDE ||
       !P.launcher_active() || P.screen()!=o->parent)return 0;
    uint32_t l=0,t=0,r=MM_GRAPHICS_WIDTH,b=MM_GRAPHICS_HEIGHT;
    /* direct_failed is not initialized by every producer (the generated tick
     * sets only n/direct_submitted) and the session already drops presents of
     * an invalid shadow, so only the box list is consulted here. A whole-panel
     * present passes no list; an empty one adds nothing to either eye. */
    if(dirty && dirty->n<MM_SCENE_RECT_MAX){
        l=MM_GRAPHICS_WIDTH;t=MM_GRAPHICS_HEIGHT;r=0;b=0;
        for(uint32_t i=0;i<dirty->n;i++){
            const mm_scene_rect *q=&dirty->r[i];
            if(!q->w || !q->h)continue;
            if(q->l<l)l=q->l;
            if(q->t<t)t=q->t;
            if((uint32_t)q->l+q->w>r)r=(uint32_t)q->l+q->w;
            if((uint32_t)q->t+q->h>b)b=(uint32_t)q->t+q->h;
        }
        if(r>MM_GRAPHICS_WIDTH)r=MM_GRAPHICS_WIDTH;
        if(b>MM_GRAPHICS_HEIGHT)b=MM_GRAPHICS_HEIGHT;
        if(r<=l || b<=t)r=l=0; /* nothing changed */
    }
    l&=~1u;r=(r+1u)&~1u;
    if(r>MM_GRAPHICS_WIDTH)r=MM_GRAPHICS_WIDTH;
    uint16_t box[4]={(uint16_t)l,(uint16_t)t,(uint16_t)r,(uint16_t)b};
    uint16_t (*eye)[4]=o->eye_box;
    unsigned lens=o->scene.lens;
#ifdef MM_SCENE_STEREO_EYES
    /* A stereo pair redraws this box for the other eye next. */
    if(o->scene.core.eye)box_join(eye[lens-1u],box);
    else
#endif
    {box_join(eye[0],box);box_join(eye[1],box);}
    if(lens==1u || lens==2u){
#ifdef MM_SCENE_STEREO_EYES
        if(!o->scene.core.eye)o->scene.core.eye_synced=0;
#endif
        uint16_t *pending=eye[lens-1u];
        if(!raw_submit(raster,pending,lens==1u ? 0x20u:0x10u))return 0;
        pending[0]=pending[2]=0;
        return 1;
    }
    /* Both eyes show this raster: one broadcast of everything either lacks. */
    box_join(eye[0],eye[1]);
    if(!raw_submit(raster,eye[0],0x30u))return 0;
    eye[0][0]=eye[0][2]=eye[1][0]=eye[1][2]=0;
    return 1;
}
#endif
static void scene_present(void *user,const mm_raster *raster,const mm_scene_dirty *dirty) {
    owner *o=user;
#ifdef MM_FLASH_SCENE
    if(o->scene.core.shadow_invalid){glassly_graphics_detach(o->image);
#ifdef MM_RAW_PRESENT
        o->lvgl_stale=1;
#endif
#ifdef MM_SCENE_STEREO_EYES
        o->scene.core.eye_synced=0;
#endif
        return;}
#endif
#ifdef MM_COMMAND_BUNDLES
    if(o->bundle_active && o->bundle_overflow)return;
#endif
#ifdef MM_RAW_PRESENT
    if(o->lvgl_stale){
        /* One stock redraw restores the fallback object; the raw copy below
         * still reaches the panel first. */
        P.cache_invalidate(&o->descriptor);P.image_source(o->image,&o->descriptor);
#ifdef MM_FLASH_SCENE
        glassly_diagnostics_hidden(o->image,0);
#endif
        o->lvgl_stale=0;
        /* The redraw puts this raster on both panels: each eye is resent whole. */
        box_join(o->eye_box[0],whole_panel);box_join(o->eye_box[1],whole_panel);
    }
    if(raw_present(o,raster,dirty))o->raw_presents++;
    else {
        o->raw_fallbacks++;P.cache_invalidate(&o->descriptor);P.image_source(o->image,&o->descriptor);
        /* LVGL draws this raster to both panels. */
        o->eye_box[0][0]=o->eye_box[0][2]=o->eye_box[1][0]=o->eye_box[1][2]=0;
#ifdef MM_SCENE_STEREO_EYES
        o->scene.core.eye_synced=0;
#endif
    }
#else
    (void)dirty;(void)raster;
    P.cache_invalidate(&o->descriptor);P.image_source(o->image,&o->descriptor);
#endif
#ifdef MM_WAKE_CONTROL
    glassly_wake_presented(o->parent);
#endif
#if defined(MM_FLASH_SCENE) && !defined(MM_RAW_PRESENT)
    glassly_diagnostics_hidden(o->image,0);
#endif
#ifdef MM_DIAGNOSTIC_COMMANDS
    mm_diagnostics_present(o->parent,o->image);
#endif
}
static void scene_settled(void *user,uint16_t tag) {
    owner *o=user;
#ifdef MM_COMMAND_BUNDLES
    if(o->bundle_active){
        if(o->bundle_count<o->bundle_capacity)o->bundle_tags[o->bundle_count++]=tag;
        else o->bundle_overflow=1; /* Explicit internal error, never silent loss. */
        return;
    }
#endif
    /* One unbundled scene dispatch can settle at most the superseded tag plus
     * its new tag; a timer settles one. Flush after every dispatch/tick. */
    if (o->settled_count<4) o->settled_tags[o->settled_count++]=tag;
}
static int scene_builtin_text(void *user,const mm_raster *raster,const uint8_t *data,
                              size_t size,mm_scene_dirty *dirty,uint32_t *tokens,size_t count) {
    (void)user;
    return mm_native_builtin_text(0,raster,data,size,dirty,tokens,count);
}
#ifdef MM_DIAGNOSTIC_COMMANDS
static void scene_frame(void *user,const uint8_t *data,size_t size) {owner *o=user;mm_diagnostics_frame(o->parent,data,size);}
#endif
static int initialize_scene(owner *o) {
    if (o->scene.initialized) return 0;
    mm_raster target={(uint8_t *)o->descriptor.data+64,MM_GRAPHICS_PIXELS,
        MM_GRAPHICS_WIDTH,MM_GRAPHICS_HEIGHT,MM_GRAPHICS_STRIDE};
    mm_scene_session_hooks hooks={o,scene_allocate,scene_free,scene_free_bytes,
        scene_now,scene_active,scene_present,scene_settled,scene_builtin_text
#ifdef MM_DIAGNOSTIC_COMMANDS
        ,scene_frame
#endif
    };
#ifdef MM_DIAGNOSTIC_COMMANDS
    int rc=mm_scene_session_init(&o->scene,&hooks,&target,MM_SCENE_SESSION_BUDGET,
        MM_SCENE_SESSION_HEADROOM,MM_SCENE_MIN_STORE);
    if(!rc)o->scene.core.cache_epoch=mm_diagnostics_epoch(o->parent);
    return rc;
#else
    return mm_scene_session_init(&o->scene,&hooks,&target,MM_SCENE_SESSION_BUDGET,
        MM_SCENE_SESSION_HEADROOM,MM_SCENE_MIN_STORE);
#endif
}
static void *cache_response(owner *o) {
    static const char prefix[]="{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"";
    static const char hex[]="0123456789abcdef";
    size_t n=o->scene.core.cache_reply_len;
    char *text=P.alloc(sizeof(prefix)+2*n+2);
    if (!text) return reply(no_memory);
    size_t at=0;
    for (;at<sizeof(prefix)-1;at++) text[at]=prefix[at];
    for (size_t i=0;i<n;i++) {
        uint8_t b=o->scene.core.cache_reply[i];text[at++]=hex[b>>4];text[at++]=hex[b&15];
    }
    text[at++]='"';text[at++]='}';text[at]=0;
    void *value=reply(text);P.free(text);return value;
}
#ifdef MM_COMMAND_BUNDLES
static int begin_bundle(owner *o,unsigned count) {
    /* Collector admitted before prepare or execution. Each segment creates at
     * most one new pending/direct tag; an initial pending tag adds one. Thus
     * 2*N slots suffice for N>=1; N0 prepare/execute emits no settled event. */
    size_t bytes=(size_t)count*2u*sizeof(uint16_t);
    if(o->bundle_active || (bytes && P.free_bytes()<MM_GRAPHICS_QUEUE_HEADROOM+bytes))return 0;
    uint16_t *tags=bytes?P.alloc(bytes):0;
    if(bytes && !tags)return 0;
    o->bundle_tags=tags;o->bundle_count=0;o->bundle_capacity=(uint16_t)(count*2u);
    o->bundle_overflow=0;o->bundle_active=1;return 1;
}
#endif
static void flush_settled(owner *o) {
    static const char prefix[]="{\"glassly\":\"scene\",\"abi\":1,\"result\":\"settled\",\"tag\":";
#ifdef MM_COMMAND_BUNDLES
    uint16_t *tags=o->bundle_active?o->bundle_tags:o->settled_tags;
    unsigned count=o->bundle_active?o->bundle_count:o->settled_count;
    for (unsigned i=0;i<count;i++) {
#else
    for (unsigned i=0;i<o->settled_count;i++) {
#endif
        char text[sizeof(prefix)+7],digits[5];size_t at=0,n=0;
        for (;at<sizeof(prefix)-1;at++) text[at]=prefix[at];
#ifdef MM_COMMAND_BUNDLES
        unsigned tag=tags[i];
#else
        unsigned tag=o->settled_tags[i];
#endif
        do {digits[n++]=(char)('0'+tag%10);tag/=10;} while(tag);
        while(n) text[at++]=digits[--n];
        text[at++]='}';text[at]=0;
        void *response=reply(text);
        if(response){P.send(o->event,response);P.release(&response);}
    }
#ifdef MM_COMMAND_BUNDLES
    if(o->bundle_active){
        uint16_t *memory=o->bundle_tags;
        o->bundle_tags=0;o->bundle_count=o->bundle_capacity=0;
        o->bundle_active=o->bundle_overflow=0;
        if(memory)P.free(memory);
    }
#endif
    o->settled_count=0;
}
#endif
void glassly_graphics_probe(uint32_t command, void *request,
                            const uint8_t *sequence, void **response) {
    (void)command; (void)sequence;
    if (request) P.release(&request);
    /* Add bounded hexadecimal allocator snapshots without importing printf or
     * allocating a formatting buffer. json() copies the string synchronously. */
    /* MM_LEAN_CAPABILITIES drops keys no client reads (code space). */
#ifdef MM_LEAN_CAPABILITIES
#define MM_CAP(text)
#else
#define MM_CAP(text) text
#endif
    static const char template[]="{\"glassly\":\"graphics-runtime\",\"abi\":1," MM_CAP("\"profile\":\"H001Y-1.0.3.127\",")
                   "\"width\":600,\"height\":350,"
#ifdef MM_MINIMAL_LAUNCHER
                   "\"version\":\"GLASSLYCFW/" MM_STRING(MM_CFW_REVISION) "\",\"displayOwner\":\"minimal\","
#endif
#ifdef MM_NOTIFICATION_RELAY
                   "\"displaySettings\":{\"position\":10,\"depth\":11,\"min\":0,\"max\":8},"
                   "\"notifications\":{\"command\":120,\"transport\":\"poll\",\"leaseTicks\":90000},"
#endif
#ifdef MM_SENSOR_CAPTURE
                   "\"sensors\":{\"command\":118,\"version\":1,\"capture\":\"passive-buffered\",\"capacity\":32,\"batch\":4,\"batchVersion\":2,\"finish\":5,\"release\":6,\"drainTicks\":30000,\"imu\":\"icm42670-registers\",\"als\":\"native-0-1000\",\"leaseTicks\":90000,\"activeAls\":1,\"activeAlsMinMs\":100,\"activeAlsMaxMs\":5000},"
#endif
#ifdef MM_MICROPHONE_CONTROL
                   "\"microphone\":{\"command\":119,\"version\":1,\"codec\":\"opus\",\"sampleRate\":16000,\"channels\":1,\"bitrate\":16000,\"leaseTicks\":90000},"
#endif
#ifdef MM_WAKE_CONTROL
                   "\"ownership\":{\"command\":121,\"leaseTicks\":90000,\"fallbackTicks\":400,\"claimedTicks\":5000},"
#endif
#ifdef MM_GRAPHICS_FLASH_READ
                   MM_CAP("\"flashRead\":123,")
#endif
#ifdef MM_GRAPHICS_INPUT
                   "\"inputObserver\":{\"command\":124,\"capacity\":32,\"leaseTicks\":30000},"
#endif
#ifdef MM_GRAPHICS_SCENE
#ifdef MM_RASTER_COMMANDS
#ifdef MM_RECT_COPY
#ifdef MM_COMMAND_BUNDLES
#ifdef MM_TEXT_COMMANDS
#ifdef MM_DIAGNOSTIC_COMMANDS
                   MM_CAP("\"modes\":[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],\"diagnostics\":\"native-v1\",\"snapshotBytes\":20,\"cleanup\":\"graphics-input-current-screen\",\"rasterLens\":\"first-left\",")
#else
                   "\"modes\":[3,6,8,9,11,15,19,20,36,37,38,39,40,41],\"rasterLens\":\"first-left\","
#endif
                   MM_CAP("\"bundleModes\":[3,6,9,15,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,\"textMaxBytes\":255,\"textFont\":\"native-resource\",\"missingGlyph\":\"reject\",")
#else
                   "\"modes\":[3,6,8,9,11,19,20,36,37,38,39,40,41],\"rasterLens\":\"first-left\","
                   "\"bundleModes\":[3,6,9,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,"
#endif
#else
                   "\"modes\":[3,6,9,11,19,20,36,37,38,39,40,41],\"rasterLens\":\"first-left\","
#endif
#else
                   "\"modes\":[3,6,11,19,20,36,37,38,39,40,41],\"rasterLens\":\"first-left\","
#endif
#ifdef MM_FLASH_SCENE
#ifdef MM_RECORD_TRANSPORT
                   "\"modeHighBit\":true,"
                   "\"recordTransport\":{\"mode\":126,\"version\":1,\"maxPacketBytes\":128,\"maxRecordBytes\":65535,\"replyCapacity\":64,\"endpoint\":1,\"leaseTicks\":30000},"
#endif
                   "\"maxMessageBytes\":65535,\"maxWireMessageBytes\":8192,\"largeMessage\":{\"mode\":127,\"chunkBytes\":1024,\"crc\":\"crc32-ieee\"},"
#else
                   "\"maxMessageBytes\":8192,"
#endif
#else
                   "\"modes\":[11,19,20,36,37,38,39,40,41],\"maxMessageBytes\":8192,"
#endif
#ifdef MM_FLASH_SCENE
                   "\"storeKiB\":256," MM_CAP("\"assetStorage\":\"flash-volatile-map\",")
#else
                   "\"storeKiB\":64,"
#endif
                   MM_CAP("\"builtinText\":true,\"emptyGeometry\":\"lease-only\",")
#else
                   "\"modes\":[11,36],\"shapeTypes\":[1,2,3,4,5,6,7,8,9,10,11,12,13],"
#endif
#ifdef MM_FLASH_SCENE
                   MM_CAP("\"maxGeometryRecords\":255,\"leaseTicks\":30000,\"tickMs\":1,")
#else
                   "\"maxGeometryRecords\":255,\"leaseTicks\":1000,\"tickMs\":1,"
#endif
#ifdef MM_FLASH_CANARY
                   MM_CAP("\"flashCanary\":122,\"registryBytes\":256,\"writableStaticBytes\":256,")
#else
                   "\"writableStaticBytes\":0,"
#endif
                   "\"freeBytesHex\":\"@@@@@@@@\",\"lowWaterBytesHex\":\"@@@@@@@@\"}";
#ifdef MM_FLASH_CANARY
    char *text=P.alloc(sizeof(template));
    if(!text){*response=reply(no_memory);return;}
#else
    char text[sizeof(template)];
#endif
    for (size_t i=0;i<sizeof(template);i++) text[i]=template[i];
    const uint32_t values[2]={P.free_bytes(),P.low_water_bytes()};
    unsigned which=0;
    for (size_t i=0;i<sizeof(template)-8 && which<2;i++) {
        if (text[i]=='@') {
            static const char hex[]="0123456789abcdef";
            for (unsigned n=0;n<8;n++) text[i+n]=hex[(values[which]>>(28-4*n))&15u];
            which++; i+=7;
        }
    }
    *response=reply(text);
#ifdef MM_FLASH_CANARY
    P.free(text);
#endif
}
void glassly_graphics_command(uint32_t command, void *request,
                              const uint8_t *sequence, void **response) {
    (void)command;
    const uint8_t *data=0; size_t length=0;
    *response=0;
    if (!sequence || !P.request_bytes(request,&data,&length) ||
        length>MM_GRAPHICS_MAX_MESSAGE || !valid_message(data,length)) {
        if (request) P.release(&request);
        *response=reply(invalid); return;
    }
#ifdef MM_GRAPHICS_SCENE
    /* post() uses native allocating queue machinery. Reserve its copy and our
     * temporary job with a separate transient reserve. The display worker's
     * persistent scene allocations retain the larger48KiB margin. */
    if (P.free_bytes()<MM_GRAPHICS_QUEUE_HEADROOM+2u*(length+MM_GRAPHICS_JOB_HEADER)+8u) {
        if (request) P.release(&request);
        *response=reply(no_memory); return;
    }
#endif
    uint8_t *job=P.alloc(length+MM_GRAPHICS_JOB_HEADER);
    if (!job) { if (request) P.release(&request); *response=reply(no_memory); return; }
    job[0]=1; job[1]=*sequence; job[2]=(uint8_t)length; job[3]=(uint8_t)(length>>8);
    for (size_t i=0;i<length;i++) job[MM_GRAPHICS_JOB_HEADER+i]=data[i];
    if (request) P.release(&request);
    P.post(job,length+MM_GRAPHICS_JOB_HEADER);
    P.free(job);
    /* Admission may silently drop: no immediate success reply. Only execution
     * on the display worker produces the correlated completion. */
}
#ifdef MM_FLASH_SCENE
#define EXEC_EVENT event
static int execute_inner(uint8_t event,const uint8_t *data,size_t length,uint8_t cap,uint8_t *record_reply,uint8_t *record_count) {
#else
#define EXEC_EVENT job[1]
void glassly_graphics_display(void *envelope) {
    const uint8_t *e=envelope;
    if (!e || (e[1]&63u)!=63u || ((uint32_t)e[4]|((uint32_t)e[5]<<8))!=MM_GRAPHICS_QUEUE_EVENT)
        return;
    size_t size=(size_t)e[6]|((size_t)e[7]<<8);
    if (size<MM_GRAPHICS_JOB_HEADER || size>MM_GRAPHICS_JOB_HEADER+MM_GRAPHICS_MAX_MESSAGE)
        return;
    const uint8_t *job=e+8, *data=job+MM_GRAPHICS_JOB_HEADER;
#ifdef MM_GRAPHICS_INPUT
    if (job[0]==2) {glassly_input_display(envelope);return;}
#ifdef MM_WAKE_CONTROL
    if (job[0]==3) {glassly_wake_display(envelope);return;}
#endif
#endif
    size_t length=(size_t)job[2]|((size_t)job[3]<<8);
#endif
    const char *result=invalid;
#ifdef MM_GRAPHICS_SCENE
    owner *executed=0;
    void *scene_response=0;
#endif
#ifdef MM_FLASH_SCENE
    if (valid_message(data,length)) {
#else
    if (job[0]==1 && length==size-MM_GRAPHICS_JOB_HEADER && valid_message(data,length)) {
#endif
        void *parent=P.screen();
        owner *o=parent ? P.find_owner(parent,deleted) : 0;
        if (o && o->magic!=OWNER_MAGIC) o=0;
#ifdef MM_DIAGNOSTIC_COMMANDS
        if((data[0]&127u)==7){
#ifdef MM_RECORD_TRANSPORT
            if(record_reply){
                if(cap<20 || mm_diagnostics_snapshot(parent,length>=2?data[1]:255u,record_reply))return -1;
                *record_count=20;return 0;
            }
#endif
            scene_response=mm_diagnostics_control(parent,length>=2?data[1]:255u);
            result=scene_response?ok:no_memory;
        }else if((data[0]&127u)==11){
#ifdef MM_MICROPHONE_CONTROL
            glassly_microphone_cleanup();
#ifdef MM_SENSOR_CAPTURE
    glassly_sensor_cleanup();
#endif
#endif
#ifdef MM_NOTIFICATION_RELAY
            glassly_notification_cleanup();
#endif
            uint16_t epoch=0;
            if(o && o->scene.initialized){mm_scene_session_dispose(&o->scene);epoch=o->scene.core.cache_epoch;}
            mm_diagnostics_cleanup(parent,epoch);
#ifdef MM_GRAPHICS_INPUT
            glassly_input_cleanup(parent);
#ifdef MM_WAKE_CONTROL
    glassly_wake_cleanup(parent);
#endif
#endif
            if(o)P.image_delete(o->image);
            result=cleared;
#else
        if (data[0]==11) {
            if (o) P.image_delete(o->image);
            result=cleared;
#endif
        } else if (!parent || !P.launcher_active()) {
            if (o) P.image_delete(o->image);
            result=busy;
#ifndef MM_GRAPHICS_SCENE
        } else if (data[1]==0) {
            if (o) o->started=P.now();
            result=ok;
#endif
        } else {
            if (!o) o=create(parent);
            if (!o) result=no_memory;
            else {
#ifdef MM_GRAPHICS_SCENE
                o->started=P.now();o->event=EXEC_EVENT;executed=o;
#ifdef MM_FLASH_SCENE
                int initialized=initialize_scene(o);
                if(initialized)result=initialized==-4 ? "{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"storage-unavailable\"}":no_memory;
#else
                if (initialize_scene(o)) result=no_memory;
#endif
                else {
#ifdef MM_COMMAND_BUNDLES
                    if((data[0]&127u)==8 && !begin_bundle(o,data[1])) result=no_memory;
                    else {
#endif
#if defined(MM_FLASH_SCENE) && !defined(MM_RAW_PRESENT)
                    glassly_graphics_detach(o->image);
#endif
#ifdef MM_RECORD_TRANSPORT
                    if(record_reply)o->scene.core.cache_reply_cap=cap;
#endif
                    int status=mm_scene_session_dispatch(&o->scene,data,length);
#ifdef MM_RECORD_TRANSPORT
                    if(record_reply){
                        *record_count=o->scene.core.cache_reply_len;
                        if(*record_count>cap){status=-1;*record_count=0;}
                        for(unsigned i=0;i<*record_count;i++)record_reply[i]=o->scene.core.cache_reply[i];
                        o->scene.core.cache_reply_cap=250;
                    }
#endif
#ifdef MM_FLASH_SCENE
                    if(o->scene.core.storage_io || o->scene.core.shadow_invalid){
                        glassly_graphics_detach(o->image);
#ifdef MM_RAW_PRESENT
                        o->lvgl_stale=1;
#endif
#ifdef MM_SCENE_STEREO_EYES
                        o->scene.core.eye_synced=0;
#endif
                        result="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"storage-error\"}";
                        status=-4;
                    }
#ifdef MM_RAW_PRESENT
                    /* Presenting commands already copied their boxes; only a
                     * hidden fallback object needs restoring here. */
                    if(status!=-4 && o->lvgl_stale)scene_present(o,&o->scene.raster,0);
#else
                    /* Non-presenting commands retain a valid previous raster. */
                    if(status!=-4)scene_present(o,&o->scene.raster,0);
#endif
#endif
#ifdef MM_DIAGNOSTIC_COMMANDS
                    if(status)mm_diagnostics_failure(parent,data[0],status==-3);
#endif
#ifdef MM_COMMAND_BUNDLES
                    if(o->bundle_overflow)result="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"bundle-event-overflow\"}";
                    else
#endif
                    if (!status) {
                        result=ok;
                        if ((data[0]&127u)>=37 && (data[0]&127u)<=41) scene_response=cache_response(o);
#ifdef MM_COMMAND_BUNDLES
                        else if((data[0]&127u)==8 && o->scene.core.cache_reply_len)scene_response=cache_response(o);
#endif
                    } else
#ifdef MM_TEXT_COMMANDS
                    if(status==-3)result=no_memory;else
#endif
#ifdef MM_FLASH_SCENE
                    if(status!=-4)
#endif
                    result=status==-2 ? busy:invalid;
#ifdef MM_COMMAND_BUNDLES
                    }
#endif
                }
#else
                mm_raster target={(uint8_t *)o->descriptor.data+64,MM_GRAPHICS_PIXELS,MM_GRAPHICS_WIDTH,
                                  MM_GRAPHICS_HEIGHT,MM_GRAPHICS_STRIDE};
                if (mm_geometry_mode36(&target,data,length)==MM_GEOMETRY_OK) {
                    o->started=P.now();
                    P.cache_invalidate(&o->descriptor);
                    P.image_source(o->image,&o->descriptor);
                    result=ok;
                }
#endif
            }
        }
    }
#ifdef MM_GRAPHICS_SCENE
    void *response=scene_response ? scene_response:reply(result);
#else
    void *response=reply(result);
#endif
    if (response) {
#ifdef MM_RECORD_TRANSPORT
        if(!record_reply)
#endif
        P.send(EXEC_EVENT,response);
        P.release(&response);
    }
#ifdef MM_GRAPHICS_SCENE
    if (executed) flush_settled(executed);
#endif
    /* Envelope is still exclusively owned/freed by the stock worker. */
#ifdef MM_FLASH_SCENE
#ifndef MM_RECORD_TRANSPORT
    (void)cap;(void)record_reply;(void)record_count;
#endif
    return result==ok || result==cleared ? 0:-1;
#endif
}

#undef EXEC_EVENT
#ifdef MM_FLASH_SCENE
static void execute(uint8_t event,const uint8_t *data,size_t length){(void)execute_inner(event,data,length,0,0,0);}
#ifdef MM_RECORD_TRANSPORT
static int execute_record(uint8_t event,const uint8_t *data,uint16_t length,uint8_t cap,uint8_t *reply,uint8_t *count){
    *count=0;return execute_inner(event,data,length,cap,reply,count);
}
#endif
static const char large_ok[]="{\"glassly\":\"large-message\",\"abi\":1,\"result\":\"accepted\"}";
static void *large_allocate(size_t n){return P.free_bytes()>=MM_GRAPHICS_QUEUE_HEADROOM+n?P.alloc(n):0;}
void glassly_graphics_display(void *envelope) {
    const uint8_t *e=envelope;
    if (!e || (e[1]&63u)!=63u || ((uint32_t)e[4]|((uint32_t)e[5]<<8))!=MM_GRAPHICS_QUEUE_EVENT)
        return;
    size_t size=(size_t)e[6]|((size_t)e[7]<<8);
    if (size<MM_GRAPHICS_JOB_HEADER || size>MM_GRAPHICS_JOB_HEADER+MM_GRAPHICS_MAX_MESSAGE)
        return;
    const uint8_t *job=e+8, *data=job+MM_GRAPHICS_JOB_HEADER;
#ifdef MM_GRAPHICS_INPUT
    if (job[0]==2) {glassly_input_display(envelope);return;}
#ifdef MM_WAKE_CONTROL
    if (job[0]==3) {glassly_wake_display(envelope);return;}
#endif
#endif
    size_t length=(size_t)job[2]|((size_t)job[3]<<8);

    if(job[0]!=1 || length!=size-MM_GRAPHICS_JOB_HEADER)return;
#ifdef MM_FLASH_SCENE
    void *parent=P.screen();owner *o=parent?P.find_owner(parent,deleted):0;
    if(o && o->magic!=OWNER_MAGIC)o=0;
#ifdef MM_RECORD_TRANSPORT
    if(length && data[0]==MM_RECORD_MODE){
        const char *result=invalid;mm_record_session *session=0;
        if(!mm_record_valid(data,length))result=invalid;
        else if(!parent || !P.launcher_active())result=busy;
        else if(o && o->assembly.data)result=invalid;
        else {
            if(!o)o=create(parent);
            if(!o)result=no_memory;
            else {
                if(!o->records){
                    mm_record_platform platform={P.alloc,P.free,P.free_bytes,execute_record};
                    o->records=mm_record_create(&platform);
                }
                session=o->records;o->records_started=o->started=P.now();
                result=session?mm_record_process(session,job[1],data,length):no_memory;
                if(!result)result=invalid;
            }
        }
        void *response=reply(result);
        if(response){P.send(job[1],response);P.release(&response);}
        mm_record_finish(session);return;
    }
#endif
    if(length && data[0]==MM_LARGE_WIRE_MODE){
        const char *result=invalid;uint8_t *record=0;size_t record_length=0;
        if(!parent || !P.launcher_active())result=busy;
        else {
            if(!o)o=create(parent);
            if(!o)result=no_memory;
            else {
                o->started=P.now();
                int rc=mm_large_accept(&o->assembly,data,length,large_allocate,P.free,&record,&record_length);
                if(rc==MM_LARGE_DONE){
                    if(record[0]!=MM_LARGE_WIRE_MODE
#ifdef MM_RECORD_TRANSPORT
                       && record[0]!=MM_RECORD_MODE
#endif
                    )execute(job[1],record,record_length);
                    else {void *r=reply(invalid);if(r){P.send(job[1],r);P.release(&r);}}
                    P.free(record);return;
                }
                result=rc==MM_LARGE_OK?large_ok:rc==MM_LARGE_MEMORY?no_memory:invalid;
            }
        }
        void *r=reply(result);if(r){P.send(job[1],r);P.release(&r);}return;
    }
    /* Preserve an incomplete record until commit/abort/lease cleanup. */
    if(o && o->assembly.data && length && data[0]!=11 && !(length==2 && data[0]==36 && !data[1])){
        void *r=reply(invalid);if(r){P.send(job[1],r);P.release(&r);}return;
    }
#endif
    execute(job[1],data,length);
}

#endif /* MM_FLASH_SCENE wrapper */
