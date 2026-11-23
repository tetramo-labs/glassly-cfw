/* Serialized UI-task adapter for the portable retained scene, ported from the
 * MemoMind runtime (runtime/graphics/scene_session.c there). NIMO keeps its
 * raw-present path, bundles, raster/rect-copy modes and built-in text (mode 15
 * and text shapes, GLASSLYCFW/12) and drops the flash store and diagnostics. MIT. */
#ifndef NIMO_SCENE_SESSION_H
#define NIMO_SCENE_SESSION_H
#include "scene.h"

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
    /* dirty lists the changed boxes, or is NULL when the whole raster changed. */
    void (*present)(void *, const mm_raster *, const mm_scene_dirty *);
    void (*settled)(void *, uint16_t);
    /* Optional progress marks for crash breadcrumbs (MM_SCENE_MARK_*). */
    void (*mark)(void *, unsigned);
    /* Optional built-in text (text.h's record); 0 drawn, -1 nothing drawn. */
    int (*builtin_text)(void *, const mm_raster *, const uint8_t *, size_t, mm_scene_dirty *);
} mm_scene_session_hooks;

/* Drawing for a message or an animation frame is about to start. */
#define MM_SCENE_MARK_RENDER 1u

typedef struct {
    mm_scene_context core;
    mm_scene_session_hooks hooks;
    mm_raster raster;
    size_t budget, headroom, live_bytes, peak_bytes;
    uint32_t timer_started, timer_period;
    uint32_t denied_allocations;
    uint8_t initialized, timer_armed;
    /* Boxes drawn by a bundle's segments; bundle_full when a segment drew outside them. */
    mm_scene_dirty bundle_dirty;
    uint8_t bundle_full;
    /* Eye a standalone SHOW names in flag bits 4-5 (1 left, 2 right); 0 both
     * (bundles and every other mode present to both eyes). */
    uint8_t lens;
} mm_scene_session;

/* Initialize only zero/unowned storage. All calls, including pump and dispose,
 * run on the UI task. Hooks are synchronous and must not reenter, destroy the
 * session, or retain a borrowed pointer. No native timer is created; the owner
 * drives pump from its own LVGL timer. */
int mm_scene_session_init(mm_scene_session *, const mm_scene_session_hooks *,
                          const mm_raster *, size_t budget, size_t headroom,
                          uint32_t store_limit);
/* Return 0 for a parsed command, including a native-format capacity/stale reply;
 * -1 for malformed/unsupported input, -2 while the owner's lease is inactive.
 * cache_reply remains owned by the session until the next call. */
int mm_scene_session_dispatch(mm_scene_session *, const uint8_t *, size_t);
void mm_scene_session_pump(mm_scene_session *);
void mm_scene_session_dispose(mm_scene_session *);
#endif
