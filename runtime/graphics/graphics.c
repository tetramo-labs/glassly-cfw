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
#define P mm_graphics_native
#define OWNER_MAGIC 0x474c4931u
typedef struct {
    uint32_t magic, started;
    void *parent, *image, *timer;
    mm_native_image descriptor;
#ifdef MM_FLASH_SCENE
    mm_large_message assembly;
#endif
#ifdef MM_GRAPHICS_SCENE
    mm_scene_session scene;
    uint16_t settled_tags[4];
    uint8_t settled_count, event;
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
    if (data[0]>=37 && data[0]<=41) return length>=5;
    return length>=2 && (data[0]==19 || data[0]==20 || data[0]==36);
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
static void scene_present(void *,const mm_raster *);
#endif
#endif
static void tick(void *timer) {
    owner *o=P.timer_userdata(timer);
    if (!o || o->magic!=OWNER_MAGIC) return;
#ifdef MM_WAKE_CONTROL
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
#ifdef MM_FLASH_SCENE
    int detached=o->scene.timer_armed && (uint32_t)(P.now()-o->scene.timer_started)>=o->scene.timer_period;
    if(detached)glassly_graphics_detach(o->image);
#endif
    mm_scene_session_pump(&o->scene);
#ifdef MM_FLASH_SCENE
    if(detached)scene_present(o,&o->scene.raster);
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
static void scene_present(void *user,const mm_raster *raster) {
    owner *o=user;(void)raster;
#ifdef MM_FLASH_SCENE
    if(o->scene.core.shadow_invalid){glassly_graphics_detach(o->image);return;}
#endif
#ifdef MM_COMMAND_BUNDLES
    if(o->bundle_active && o->bundle_overflow)return;
#endif
    P.cache_invalidate(&o->descriptor);P.image_source(o->image,&o->descriptor);
#ifdef MM_WAKE_CONTROL
    glassly_wake_presented(o->parent);
#endif
#ifdef MM_FLASH_SCENE
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
    static const char template[]="{\"glassly\":\"graphics-runtime\",\"abi\":1,\"profile\":\"H001Y-1.0.3.127\","
                   "\"width\":600,\"height\":350,"
#ifdef MM_MINIMAL_LAUNCHER
                   "\"version\":\"GLASSLYCFW/" MM_STRING(MM_CFW_REVISION) "\",\"displayOwner\":\"minimal\","
#endif
#ifdef MM_NOTIFICATION_RELAY
                   "\"displaySettings\":{\"position\":10,\"depth\":11,\"min\":0,\"max\":8},"
                   "\"notifications\":{\"command\":120,\"transport\":\"poll\",\"leaseTicks\":90000},"
#endif
#ifdef MM_WAKE_CONTROL
                   "\"ownership\":{\"command\":121,\"leaseTicks\":90000,\"fallbackTicks\":400,\"claimedTicks\":5000},"
#endif
#ifdef MM_GRAPHICS_FLASH_READ
                   "\"flashRead\":123,"
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
                   "\"modes\":[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],\"diagnostics\":\"native-v1\",\"snapshotBytes\":20,\"cleanup\":\"graphics-input-current-screen\",\"rasterLens\":\"first-left\","
#else
                   "\"modes\":[3,6,8,9,11,15,19,20,36,37,38,39,40,41],\"rasterLens\":\"first-left\","
#endif
                   "\"bundleModes\":[3,6,9,15,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,\"textMaxBytes\":255,\"textFont\":\"native-resource\",\"missingGlyph\":\"reject\","
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
                   "\"maxMessageBytes\":65535,\"maxWireMessageBytes\":8192,\"largeMessage\":{\"mode\":127,\"chunkBytes\":1024,\"crc\":\"crc32-ieee\"},"
#else
                   "\"maxMessageBytes\":8192,"
#endif
#else
                   "\"modes\":[11,19,20,36,37,38,39,40,41],\"maxMessageBytes\":8192,"
#endif
#ifdef MM_FLASH_SCENE
                   "\"storeKiB\":256,\"assetStorage\":\"flash-volatile-map\","
#else
                   "\"storeKiB\":64,"
#endif
                   "\"builtinText\":true,\"emptyGeometry\":\"lease-only\","
#else
                   "\"modes\":[11,36],\"shapeTypes\":[1,2,3,4,5,6,7,8,9,10,11,12,13],"
#endif
#ifdef MM_FLASH_SCENE
                   "\"maxGeometryRecords\":255,\"leaseTicks\":30000,\"tickMs\":1,"
#else
                   "\"maxGeometryRecords\":255,\"leaseTicks\":1000,\"tickMs\":1,"
#endif
#ifdef MM_FLASH_CANARY
                   "\"flashCanary\":122,\"registryBytes\":256,\"writableStaticBytes\":256,"
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
static void execute(uint8_t event,const uint8_t *data,size_t length) {
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
            scene_response=mm_diagnostics_control(parent,length>=2?data[1]:255u);
            result=scene_response?ok:no_memory;
        }else if((data[0]&127u)==11){
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
#ifdef MM_GRAPHICS_SCENE
        } else if (data[0]==36 && length==2 && data[1]==0) {
#else
        } else if (data[1]==0) {
#endif
            if (o) o->started=P.now();
            result=ok;
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
#ifdef MM_FLASH_SCENE
                    glassly_graphics_detach(o->image);
#endif
                    int status=mm_scene_session_dispatch(&o->scene,data,length);
#ifdef MM_FLASH_SCENE
                    if(o->scene.core.storage_io || o->scene.core.shadow_invalid){
                        glassly_graphics_detach(o->image);
                        result="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\"storage-error\"}";
                        status=-4;
                    }
                    /* Non-presenting commands retain a valid previous raster. */
                    if(status!=-4)scene_present(o,&o->scene.raster);
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
                        if (data[0]>=37 && data[0]<=41) scene_response=cache_response(o);
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
    if (response) { P.send(EXEC_EVENT,response); P.release(&response); }
#ifdef MM_GRAPHICS_SCENE
    if (executed) flush_settled(executed);
#endif
    /* Envelope is still exclusively owned/freed by the stock worker. */
}

#undef EXEC_EVENT
#ifdef MM_FLASH_SCENE
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
                    if(record[0]!=MM_LARGE_WIRE_MODE)execute(job[1],record,record_length);
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
