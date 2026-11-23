/* Exact 1.0.3.127 native boundary, supported by display-adapter/proof.json.
 * Own allocations use the verified locked lower try-allocator, bypassing no
 * global hooks. Stock LVGL/response allocation can still assert on native OOM.
 */
#include "graphics.h"
#ifdef MM_GRAPHICS_INPUT
#include "input.h"
#endif
#ifdef MM_GRAPHICS_FLASH_READ
#include "flash_read.h"
#endif
#define FN(address,type) ((type)(uintptr_t)(address))
_Static_assert(sizeof(void *)==4,"Native layout requires actual RV32 pointers");
_Static_assert(sizeof(mm_native_image)==12,"Native indexed-image descriptor ABI");
static uint32_t word(const void *p, size_t offset) {
    const uint8_t *b=(const uint8_t *)p+offset;
    return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);
}
static int request_bytes(void *request,const uint8_t **data,size_t *length) {
    if (!request || word(request,0)) return 0;
    const uint8_t *h=(const uint8_t *)(uintptr_t)word(request,4);
    if (!h || h[0]!=1) return 0;
    *length=(size_t)h[1]|((size_t)h[2]<<8)|((size_t)h[3]<<16);
    *data=(const uint8_t *)(uintptr_t)word(h,4);
    return *data!=0;
}
static void post(const void *data,size_t size) {
    typedef uint32_t (*send_fn)(uint32_t,uint16_t,const void *,uint32_t,uint32_t);
    (void)FN(0x0425abe8u,send_fn)(63,MM_GRAPHICS_QUEUE_EVENT,data,(uint32_t)size,2);
}
static void send(uint8_t event,void *response) {
    typedef uint32_t (*send_fn)(uint8_t,uint8_t,uint8_t,void *,uint32_t);
    (void)FN(0x042e866eu,send_fn)(event,15,MM_GRAPHICS_COMMAND,response,1);
}
#ifdef MM_GRAPHICS_INPUT
void glassly_input_hide(void *image) {
    typedef void (*flag_fn)(void *,uint32_t);
    FN(0x042cde58u,flag_fn)(image,1);
}
void glassly_input_send(uint8_t event,void *response) {
    typedef uint32_t (*send_fn)(uint8_t,uint8_t,uint8_t,void *,uint32_t);
    (void)FN(0x042e866eu,send_fn)(event,15,0x7c,response,1);
}
#endif
#ifdef MM_GRAPHICS_FLASH_READ
int glassly_flash_read_native(uint32_t device,uint32_t offset,void *destination,uint32_t length) {
    typedef int (*read_fn)(uint32_t,uint32_t,void *,uint32_t);
    return FN(0x04329ad8u,read_fn)(device,offset,destination,length);
}
#endif
static void *screen(void) {
    typedef void *(*default_fn)(void);
    typedef void *(*active_fn)(void *);
    return FN(0x042ccc62u,active_fn)(FN(0x042d01b2u,default_fn)());
}
static int launcher_active(void) {
    typedef void *(*get_fn)(void);
    return FN(0x0425db22u,get_fn)()==(void *)0x0200fc7cu &&
           FN(0x0425daf8u,get_fn)()==(void *)0x0200fc7cu;
}
static void *find_owner(void *parent,mm_callback callback) {
    typedef uint32_t (*count_fn)(void *);
    typedef void *(*child_fn)(void *,int32_t);
    uint32_t children=FN(0x042cf47au,count_fn)(parent);
    for (uint32_t i=0;i<children;i++) {
        void *child=FN(0x042cf44eu,child_fn)(parent,(int32_t)i);
        if (!child) continue;
        const uint8_t *spec=(const uint8_t *)(uintptr_t)word(child,8);
        if (!spec) continue;
        uint32_t count=((uint32_t)spec[0x22]|((uint32_t)spec[0x23]<<8))&63u;
        const uint8_t *records=(const uint8_t *)(uintptr_t)word(spec,12);
        if (!records) continue;
        for (uint32_t j=0;j<count;j++,records+=12)
            if (word(records,0)==(uint32_t)(uintptr_t)callback && records[8]==0x21)
                return (void *)(uintptr_t)word(records,4);
    }
    return 0;
}
static int on_delete(void *image,mm_callback callback,void *owner) {
    typedef void *(*event_fn)(void *,mm_callback,uint8_t,void *);
    return FN(0x042c7894u,event_fn)(image,callback,0x21,owner)!=0;
}
static void image_source(void *image,const mm_native_image *source) {
    typedef void (*source_fn)(void *,const mm_native_image *);
    typedef void (*pos_fn)(void *,int32_t,int32_t);
    FN(0x042bd7fau,source_fn)(image,source);
    FN(0x042c963eu,pos_fn)(image,0,0);
    FN(0x042c96ecu,pos_fn)(image,MM_GRAPHICS_WIDTH,MM_GRAPHICS_HEIGHT);
}
static void *timer_userdata(void *timer) { return (void *)(uintptr_t)word(timer,12); }
static void *try_alloc(size_t size) {
    typedef void *(*allocate_fn)(uint32_t,uint32_t);
    if (!size || size>0x1ffffcu) return 0;
    return FN(0x0433c294u,allocate_fn)((uint32_t)size,0);
}
typedef void (*release_fn)(void **);
typedef void *(*json_fn)(const char *);
typedef void *(*status_fn)(uint32_t,const char *);
typedef void *(*alloc_fn)(size_t);
typedef void (*free_fn)(void *);
typedef void *(*object_fn)(void *);
typedef void (*cache_fn)(const mm_native_image *);
typedef void *(*timer_fn)(mm_callback,uint32_t,void *);
typedef uint32_t (*now_fn)(void);
#ifdef MM_RAW_PRESENT
typedef uint32_t (*slice_lock_fn)(uint32_t,uint32_t,uint32_t,uint8_t *);
typedef uint8_t *(*slice_pixels_fn)(int32_t,int32_t,uint32_t);
typedef uint32_t (*slice_submit_fn)(uint32_t,const uint16_t *,uint32_t);
#endif
const mm_graphics_platform mm_graphics_native={
    request_bytes,FN(0x042eff8eu,release_fn),FN(0x042ef9f6u,json_fn),FN(0x042ef924u,status_fn),
    try_alloc,FN(0x0434e6eeu,free_fn),post,send,screen,launcher_active,find_owner,
    FN(0x042bd7d0u,object_fn),on_delete,image_source,FN(0x042cf61cu,free_fn),
    FN(0x042b68c8u,cache_fn),FN(0x042c7854u,object_fn),FN(0x042b27cau,timer_fn),
    FN(0x042b285au,free_fn),timer_userdata,FN(0x042d02c6u,now_fn),
    FN(0x0433c460u,now_fn),FN(0x0433c4a4u,now_fn)
#ifdef MM_RAW_PRESENT
    ,FN(0x0425f20eu,slice_lock_fn),FN(0x0425f7fau,slice_pixels_fn),FN(0x0425f292u,slice_submit_fn)
#endif
};

#ifdef MM_DIAGNOSTIC_COMMANDS
#include "diagnostics.h"
void glassly_diagnostics_hidden(void *image,int hidden) {
    typedef void (*fn)(void *,uint32_t);
    if(hidden)FN(0x042cde58u,fn)(image,1);else FN(0x042cd8e4u,fn)(image,1);
}
void glassly_diagnostics_source(void *image,const mm_native_image *source) {
    typedef void (*src_fn)(void *,const mm_native_image *);
    typedef void (*xy_fn)(void *,int32_t,int32_t);
    FN(0x042bd7fau,src_fn)(image,source);FN(0x042c963eu,xy_fn)(image,0,0);
    FN(0x042c96ecu,xy_fn)(image,(source->header>>10)&2047u,source->header>>21);
}
#endif

#ifdef MM_FLASH_SCENE
void glassly_graphics_detach(void *image) {
    typedef void (*hide_fn)(void *,uint32_t);
    typedef void (*source_fn)(void *,const mm_native_image *);
    FN(0x042cde58u,hide_fn)(image,1);
    FN(0x042bd7fau,source_fn)(image,0);
}
#endif

#ifdef MM_WAKE_CONTROL
#include "wake_control.h"
void glassly_wake_native_on(void) { FN(0x042a88a8u,void (*)(void))(); }
int glassly_wake_native_on_state(void) { return FN(0x0425f99eu,int (*)(void))()!=0; }
int glassly_wake_native_blocked(void) { return FN(0x0425f9f8u,int (*)(void))()!=0; }
void glassly_wake_send(uint8_t event,void *response) {
    typedef uint32_t (*send_fn)(uint8_t,uint8_t,uint8_t,void *,uint32_t);
    (void)FN(0x042e866eu,send_fn)(event,15,0x79,response,1);
}
#endif
