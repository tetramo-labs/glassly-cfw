/* Serialized display-worker adapter for the portable retained scene. MIT. */
#ifndef MM_SCENE_SESSION_H
#define MM_SCENE_SESSION_H
#include "scene.h"
#ifdef MM_FLASH_SCENE
#include "scene_flash_store.h"
#endif

/* Native policy, separate from the portable G2 capacities. Counts allocator
 * headers as well as scene storage; the caller owns the canvas and session. */
#define MM_SCENE_SESSION_BUDGET (170u * 1024u)
#define MM_SCENE_SESSION_HEADROOM (48u * 1024u)

typedef struct {
    void *user;
    void *(*allocate)(void *, size_t);
    void (*deallocate)(void *, void *);
    uint32_t (*free_bytes)(void *);
    uint32_t (*now_ms)(void *);
    int (*active)(void *);
    void (*present)(void *, const mm_raster *);
    void (*settled)(void *, uint16_t);
    int (*builtin_text)(void *,const mm_raster *,const uint8_t *,size_t,
                        mm_scene_dirty *,uint32_t *,size_t);
#ifdef MM_DIAGNOSTIC_COMMANDS
    void (*frame)(void *,const uint8_t *,size_t);
#endif
} mm_scene_session_hooks;

typedef struct {
#ifdef MM_FLASH_SCENE
    mm_flash_store flash;
    uint8_t *flash_workspace;
#endif
    mm_scene_context core;
    mm_scene_session_hooks hooks;
    mm_raster raster;
    size_t budget, headroom, live_bytes, peak_bytes;
    uint32_t timer_started, timer_period;
    uint32_t denied_allocations;
    uint8_t initialized, timer_armed;
} mm_scene_session;

/* Initialize only zero/unowned storage. All calls, including pump and dispose,
 * run on the same display worker. Hooks are synchronous and must not reenter,
 * destroy the session, or retain a borrowed pointer. No native timer is created;
 * pump is driven by the owner's existing LVGL timer. */
int mm_scene_session_init(mm_scene_session *, const mm_scene_session_hooks *,
                          const mm_raster *, size_t budget, size_t headroom,
                          uint32_t store_limit);
/* Return 0 for a parsed command, including a native-format capacity/stale reply;
 * -1 for malformed/unsupported input, -2 while the owner's lease/UI is inactive.
 * cache_reply remains owned by the session until the next call. */
int mm_scene_session_dispatch(mm_scene_session *, const uint8_t *, size_t);
void mm_scene_session_pump(mm_scene_session *);
void mm_scene_session_dispose(mm_scene_session *);
#endif
