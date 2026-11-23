/* Retained G2 scene/cache port with explicit platform ownership. MIT. */
#ifndef MM_PORTABLE_SCENE_H
#define MM_PORTABLE_SCENE_H
#include "geometry.h"
#include "vector.h"
#ifdef MM_SCENE_EXTERNAL_STORE
#include "scene_store.h"
#define MM_SCENE_STORAGE_IO (-3)
#endif
#define MM_SCENE_MAGIC 0xc0ffee72u
#define MM_SCENE_MAX_STORE (256u*1024u)
#define MM_SCENE_MIN_STORE (64u*1024u)
#define MM_SCENE_RECT_MAX 16u
#define MM_SCENE_MAX_MESSAGE 65535u
#define MM_SCENE_PERSISTENT 0u
#define MM_SCENE_WORKSPACE 1u
typedef struct { uint16_t l,t,w,h; } mm_scene_rect;
typedef struct { uint32_t n;uint8_t direct_submitted,direct_failed;mm_scene_rect r[MM_SCENE_RECT_MAX]; } mm_scene_dirty;
struct cfw_cache_s;
typedef struct mm_scene_context mm_scene_context;
typedef struct {
    void *user;
    void *(*allocate)(void *,unsigned,size_t);
    void (*deallocate)(void *,unsigned,void *);
    uint32_t (*now_ms)(void *);
    int (*lease_active)(void *);
    int (*shadow)(void *,mm_raster *);
    uintptr_t (*timer_new)(void *,void (*)(void *),void *);
    void (*timer_start)(void *,uintptr_t,uint32_t);
    void (*timer_stop)(void *,uintptr_t);
    void (*gate_wait)(void *);
    void (*gate_signal)(void *);
    void (*present)(void *,mm_scene_context *,const mm_raster *,mm_scene_dirty *);
    void (*settled)(void *,uint16_t);
    void (*reply_capacity_hint)(void *,uint8_t);
    /* Native built-in font ABI is intentionally outside the core. The callback
     * must prevalidate before drawing. Tests use upstream's original box font. */
    int (*builtin_text)(void *,const mm_raster *,const uint8_t *,size_t,mm_scene_dirty *,uint32_t *,size_t);
} mm_scene_platform;
struct mm_scene_context {
    uint32_t magic;
    mm_scene_platform platform;
    uint32_t store_limit;
    mm_raster raster;
    struct cfw_cache_s *scene;
    uintptr_t scene_timer;
    uint8_t *texture_cache;
    uint32_t texture_cache_size;
    uint16_t cache_epoch;
    uint8_t cache_lost,cache_reply_cap,cache_reply_len,direct_pending,shadow_stale;
    uint8_t cache_reply[255];
#ifdef MM_SCENE_EXTERNAL_STORE
    mm_scene_store external_store;
    uint8_t external_ready,storage_io,shadow_invalid;
#endif
    uint8_t shape_text_buf[136];
    uint32_t shape_tokens[128];
#ifdef MM_SCENE_STEREO_EYES
    /* Eye of the render pass in progress: 0 both, 1 left, 2 right. Objects
     * whose id has bit 31 belong to one eye (bit 30: 0 left, 1 right). With
     * MM_SCENE_FIXED_EYE the owner drives one panel per context: it sets eye
     * once and every render skips the other eye's objects (no per-eye passes). */
    uint8_t eye;
#endif
};
/* Context owns allocations made through platform; caller owns shadow and timer.
 * Single serialized message owner. prepare must precede the display gate;
 * dispatch/render/reap/release require the caller's gate ownership. */
int mm_scene_init(mm_scene_context *,const mm_scene_platform *,uint32_t store_limit);
#ifdef MM_SCENE_EXTERNAL_STORE
/* Store configuration is copied; caller owns its backing context. No binding or
 * I/O occurs until prepare. Failed rendering may invalidate shared pixels: the
 * caller must not present/use them while shadow_invalid is set. */
int mm_scene_init_with_store(mm_scene_context *,const mm_scene_platform *,const mm_scene_store *);
#endif
#ifdef MM_RASTER_COMMANDS
/* Optional raster adapter: reject input aliases with every core-owned span
 * before takeover can mutate it. Caller keeps storage stable/serialized. */
int mm_scene_raster_input_valid(mm_scene_context *,const uint8_t *,size_t);
#endif
void mm_scene_prepare(mm_scene_context *,uint8_t mode,const uint8_t *,size_t);
#ifdef MM_SCENE_RESET_UNDO_TRIM
/* Native memory policy. Call immediately after a successful whole-request
 * RESET, outside dispatch/bundles, on the serialized display owner. Validates
 * the empty reset state and fresh reply; returns payload bytes released. The
 * paired allocator owns its header. Does not release store/vector/canvas or
 * change replies. This policy also requires undo before any PUT mutation. */
size_t mm_scene_trim_reset_undo(mm_scene_context *);
#endif
int mm_scene_dispatch(mm_scene_context *,uint8_t mode,const uint8_t *,size_t,int present,mm_scene_dirty *);
int mm_scene_immediate(mm_scene_context *,const mm_raster *,const uint8_t *,size_t,mm_scene_dirty *);
#ifdef MM_COMMAND_BUNDLES
/* Bundle executor already masks the highbit. Entire borrowed message remains
 * subject to the same ownership/alias checks; no copied header is needed. */
int mm_scene_immediate_mode(mm_scene_context *,const mm_raster *,const uint8_t *,size_t,uint8_t,mm_scene_dirty *);
#endif
void mm_scene_tick(void *);
void mm_scene_render_if_due(mm_scene_context *,uint8_t *);
/* Same, appending the rendered boxes to dirty (nothing when no render was due). */
void mm_scene_render_if_due_rects(mm_scene_context *,uint8_t *,mm_scene_dirty *);
void mm_scene_takeover(mm_scene_context *);
void mm_scene_lose(mm_scene_context *);
void mm_scene_reap(mm_scene_context *);
void mm_scene_release(mm_scene_context *);
#endif
