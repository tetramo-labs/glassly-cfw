#ifndef MM_SCENE_STORE_H
#define MM_SCENE_STORE_H
#include <stddef.h>
#include <stdint.h>
/* Optional serialized external storage. All callbacks are synchronous. A failed
 * commit must preserve the previous active bytes. abort/reset cannot fail and
 * perform no physical I/O; reset creates an empty ephemeral epoch. The caller
 * owns user and the backing region for the complete scene lifetime. */
typedef struct {
    void *user;
    uint32_t capacity;
    int (*read)(void *,uint32_t,void *,size_t);
    int (*begin)(void *);
    int (*write)(void *,uint32_t,const void *,size_t);
    int (*commit)(void *);
    void (*abort)(void *);
    void (*reset)(void *);
    int (*aliases)(void *,const void *,size_t);
} mm_scene_store;
typedef struct {
    const uint8_t *ram;
    const mm_scene_store *store;
    uint32_t offset,length;
} mm_scene_bytes;
/* Exactly one source: RAM with offset0 (NULL allowed only for length0), or a
 * store with nonnull read/aliases and a fully bounded offset+length. Typed
 * object pointers must refer to accessible memory. Integer span checks cannot
 * establish physical memory accessibility. Output buffers must not overlap
 * source bytes, store state/table, or the handle. No writable mapping is exposed.
 * read returns-1 for invalid arguments and-2 for callback failure; failed reads
 * may partially fill output. Zero reads accept NULL output after validation.
 * sub supports out==input; other partial handle aliasing is rejected. Failure
 * leaves the output handle unchanged. */
int mm_scene_bytes_read(const mm_scene_bytes *,uint32_t,void *,size_t);
int mm_scene_bytes_sub(const mm_scene_bytes *,uint32_t,uint32_t,mm_scene_bytes *);
typedef struct {
    mm_scene_bytes bytes;
    uint32_t start,used;
    uint8_t data[256];
} mm_scene_cursor;
/* init leaves cursor unchanged on failure; source bytes/backing state must not
 * alias it. read rejects destinations overlapping any part of the cursor or
 * backing source. Input must remain stable until cursor disposal/reinitialization.
 * Cursor is caller-owned, non-reentrant, and must not be modified directly. */
int mm_scene_cursor_init(mm_scene_cursor *,const mm_scene_bytes *);
int mm_scene_cursor_read(mm_scene_cursor *,uint32_t,void *,size_t);
struct mm_flash_store_adapter; /* Binding is separate from the scene core. */
#endif
