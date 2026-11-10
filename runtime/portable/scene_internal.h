/* Derived from pinned G2 commite889569fe77775ed5822af6f7e47210f2984f15d.
 * Explicit MemoMind platform adaptation; MIT, see PROVENANCE.md. */
#ifndef MM_SCENE_INTERNAL_H
#define MM_SCENE_INTERNAL_H
#include "scene.h"
typedef mm_scene_context customCfwContext;
#define CFW_REPLY_HDR_SIZE 5u
typedef mm_scene_dirty cfw_rectlist;
#define CFW_RECT_MAX MM_SCENE_RECT_MAX
#define CFW_CTX_MAGIC MM_SCENE_MAGIC
/* Revision 21: bounded, compiled SVG paths; see VECTOR_PROTOCOL.md. */
#define CFW_SHAPE_PATH 18u  /* retained only, constructed by SET_PATH */
#define CFW_PATH_MAX_EDGES 512u
#define CFW_PATH_MAX_BYTES 8192u
#define CFW_PATH_SCENE_EDGES 4096u
#define CFW_PATH_MAX_COMMANDS 1024u
typedef mm_vector_edge cfw_edge;
typedef mm_vector_path cfw_path;
typedef struct {
    int32_t angle, from, to; /* unwrapped degrees * 256 */
    int16_t px, py;         /* panel-space pivot, pixels */
    uint32_t started;
    uint16_t duration;      /* milliseconds; 0 idle */
    uint8_t curve[4];
} cfw_rotation;


typedef mm_vector_work cfw_vector_work;
/* ---- Shape records (mode 36 and the object cache) --------------------------
 *
 * Geometric records are 20 bytes: [type:u8][flags:u8][color:u8][width:u8][p0..p7:int16 LE].
 * Geometry parameters are signed pixel coordinates in the 640x480 panel space
 * (negative and oversized values are clipped). Types and their parameters:
 *
 *   1  LINE          x1 y1 x2 y2                      width = stroke (1 = hairline)
 *   2  RECT          x y w h r                        stroked rounded rect, r = corner radius
 *   3  RECT_FILL     x y w h r
 *   4  CIRCLE        cx cy r                          stroked ring
 *   5  CIRCLE_FILL   cx cy r
 *   6  TRI           x1 y1 x2 y2 x3 y3                stroked
 *   7  TRI_FILL      x1 y1 x2 y2 x3 y3
 *   8  QUAD          x1 y1 x2 y2 x3 y3 x4 y4          stroked
 *   9  QUAD_FILL     x1 y1 x2 y2 x3 y3 x4 y4
 *  10  BEZIER2       x0 y0 cx cy x1 y1                quadratic, stroked
 *  11  BEZIER3       x0 y0 c0x c0y c1x c1y x1 y1      cubic, stroked
 *  12  ARC           cx cy r a0 a1                    stroked arc, degrees, 0 = +x, clockwise
 *  13  PIE           cx cy r a0 a1                    filled sector
 *
 * Asset-bearing records (revision 38) reference versioned assets of the object
 * cache by 32-bit id; there are no raw storage offsets on the wire:
 *
 *  14  IMAGE         [14][flags][options][0][x:i16][y:i16][image asset:u32]           12 bytes
 *  15  TEXT          [15][flags][options][0][x:i16][y:i16][string asset:u32]          12 bytes
 *                    string drawn with the built-in 20 px font
 *  16  TEXT_CACHED   [16][flags][options][0][x:i16][y:i16][string asset:u32][font asset:u32]
 *                    16 bytes; the string drawn with a cached font asset
 *  17  TEXT_INLINE   [17][flags][options][0][x:i16][y:i16][w:i16][h:i16][len:u8][bytes]
 *                    built-in font, string carried in the record; w/h > 0 clip to the
 *                    box. 13 header bytes + len (1..128).
 *  18  PATH          [18][flags][color][rule][x:i16][y:i16][scale:u16][len:u16][commands]
 *                    compiled filled contour (VECTOR_PROTOCOL.md); object cache only.
 *
 * `color` is the 4-bit gray for geometry. For IMAGE/TEXT types it is the
 * options byte (low nibble top color, bit 4 transparent source color 0, bit 5
 * inverse ramp). `flags` bit 0 = visible (retained objects only).
 * Circles are centered on pixel (cx,cy) and cover an odd 2r+1 px diameter (r = 1
 * is a 3x3 dot); polygons, wide lines and curves are sampled at pixel centers. */

#define CFW_SHAPE_RECORD_BYTES 20u
#define CFW_SHAPE_PARAMS       8u

#define CFW_SHAPE_NONE          0u
#define CFW_SHAPE_LINE          1u
#define CFW_SHAPE_RECT          2u
#define CFW_SHAPE_RECT_FILL     3u
#define CFW_SHAPE_CIRCLE        4u
#define CFW_SHAPE_CIRCLE_FILL   5u
#define CFW_SHAPE_TRI           6u
#define CFW_SHAPE_TRI_FILL      7u
#define CFW_SHAPE_QUAD          8u
#define CFW_SHAPE_QUAD_FILL     9u
#define CFW_SHAPE_BEZIER2      10u
#define CFW_SHAPE_BEZIER3      11u
#define CFW_SHAPE_ARC          12u
#define CFW_SHAPE_PIE          13u
#define CFW_SHAPE_IMAGE        14u
#define CFW_SHAPE_TEXT         15u
#define CFW_SHAPE_TEXT_CACHED  16u
#define CFW_SHAPE_TEXT_INLINE  17u
#define CFW_SHAPE_TYPE_MAX     18u
#define CFW_SHAPE_ASSET_BYTES  12u   /* IMAGE / TEXT record */
#define CFW_SHAPE_FONT_BYTES   16u   /* TEXT_CACHED record */
#define CFW_SHAPE_INLINE_HDR   13u   /* type flags color width x y w h len */
#define CFW_SHAPE_PATH_HDR     12u   /* type flags color rule x y scale len */
#define CFW_SHAPE_INLINE_MAX   128u  /* bytes per inline string / string asset */

#define CFW_SHAPE_FLAG_VISIBLE 0x01u
#define CFW_SHAPE_TEXT_MAX     CFW_SHAPE_INLINE_MAX

/* Packed-4bpp render target; every primitive clips to w x h. */
typedef struct {
    uint8_t *buf;
    uint32_t stride;
    int32_t  w;
    int32_t  h;
} cfw_raster;

/* A decoded record. Wire identities (asset_id/font_id) are resolved by the
 * object cache into the region pointers before drawing; a record whose assets
 * are unresolved draws nothing. */
typedef struct {
    uint8_t type;
    uint8_t flags;
    uint8_t color;
    uint8_t width;          /* stroke width; fill rule for PATH */
    int16_t p[CFW_SHAPE_PARAMS];
    const uint8_t *text;    /* TEXT_INLINE bytes (p[4] = length) / PATH commands (p[3] = length) */
    uint32_t asset_id;      /* IMAGE / TEXT / TEXT_CACHED: image or string asset */
    uint32_t font_id;       /* TEXT_CACHED: font asset */
#ifdef MM_SCENE_EXTERNAL_STORE
    mm_scene_bytes asset_region,font_region;
#endif
    const uint8_t *asset;   /* resolved image or string bytes */
    uint32_t asset_len;
    const uint8_t *font;    /* resolved font asset */
    uint32_t font_len;
} cfw_shape;

/* Capacity of the asset store (scene.c). Kept under its historical name: the
 * 256 KiB block on the EvenHub heap is the same allocation, but revision 38
 * owns it through the asset allocator instead of exposing raw offsets. */
#ifndef CFW_TEXTURE_CACHE_SIZE
#define CFW_TEXTURE_CACHE_SIZE (256u * 1024u)
#endif

/* Cached image format:  [width:u8][height:u8][4bpp RLE tokens...]
 * Font asset format:    [96 x u32 glyph offsets, relative to the asset][glyph images]
 *
 * Every helper takes an explicit (base, size) region: an asset resolved by the
 * object cache, never the whole store. Offsets are uint32 and checked as
 * `offset <= size && length <= size - offset` before any access. */
typedef struct {
    const uint8_t *rle;
    uint32_t rle_len;
    uint32_t width;
    uint32_t height;
} cfw_cached_image;

#define CFW_FONT_TABLE_CHARS 96u
#define CFW_FONT_TABLE_BYTES (CFW_FONT_TABLE_CHARS * 4u)

static int cfw_texture_image_in(const uint8_t *base, uint32_t size, uint32_t offset,
                                cfw_cached_image *out);
static int cfw_texture_font_valid(const uint8_t *font, uint32_t size);
static int cfw_texture_draw_image_region(uint8_t *shadow, uint32_t stride,
                                         uint32_t panel_w, uint32_t panel_h,
                                         const uint8_t *data, uint32_t size,
                                         int32_t x, int32_t y, uint8_t options,
                                         cfw_rectlist *rl);
static int cfw_texture_draw_string_region(uint8_t *shadow, uint32_t stride,
                                          uint32_t panel_w, uint32_t panel_h,
                                          const uint8_t *font, uint32_t font_size,
                                          int32_t x, int32_t y, uint8_t options,
                                          const uint8_t *string, uint32_t string_len,
                                          cfw_rectlist *rl);
static int cfw_texture_string_valid(const uint8_t *s, uint32_t len);
/* ---- Retained object cache (revision 38, modes 37-41) -----------------------
 *
 * Every drawable the phone defines is a versioned OBJECT with a stable 32-bit
 * id; images, cached fonts and shared strings are versioned ASSETS. Objects
 * stay resident after the view that showed them is hidden, so reopening a
 * dashboard is one SHOW of (id, version) references instead of a resend, and
 * the least recently used unpinned objects are evicted when room is needed.
 * The displayed scene is an ordered list of active objects (paint order =
 * list order, independent of storage order); its dependency closure is pinned.
 *
 * Storage: this descriptor block lives on the EvenHub heap (allocated lazily, released
 * by mode 11); variable data (asset bytes, inline strings, compiled path
 * edges) lives in the 256 KiB store on the EvenHub heap behind a 16-byte
 * granule bitmap allocator. Descriptors are reusable; a recycled index can
 * never satisfy a reference to its former occupant because references carry
 * (id, version) and are validated against the descriptor before use.
 *
 * Wire formats, replies and the transaction/eviction rules are documented at
 * the top of scene.c. */

#define CFW_CACHE_MAGIC          0x43414348u   /* 'CACH' */
#ifndef CFW_CACHE_OBJECTS
#define CFW_CACHE_OBJECTS        256u
#endif
#ifndef CFW_CACHE_ASSETS
#define CFW_CACHE_ASSETS         256u
#endif
#define CFW_CACHE_STORE_BYTES    CFW_TEXTURE_CACHE_SIZE   /* the store's maximum; the heap decides (scene.c) */
#define CFW_CACHE_STORE_MIN      (64u * 1024u)
#define CFW_CACHE_GRANULE        16u
#define CFW_CACHE_GRANULES       (CFW_CACHE_STORE_BYTES / CFW_CACHE_GRANULE)
#define CFW_CACHE_JOURNAL        64u
#define CFW_CACHE_TXN_CHUNKS     32u           /* asset chunks applied per message */
#define CFW_CACHE_TXN_REASSERTS  64u           /* same-version PUTs re-asserted per message (revision 48) */
#define CFW_CACHE_ALL_OBJECTS    0xffffffffu   /* op target: every active object */
#define CFW_SCENE_DEFAULT_PERIOD 33u           /* ms between animation frames */
#define CFW_SCENE_MIN_PERIOD     10u
#define CFW_SCENE_MAX_PERIOD     250u

/* asset kinds */
#define CFW_ASSET_IMAGE   0u
#define CFW_ASSET_FONT    1u
#define CFW_ASSET_STRING  2u
#define CFW_ASSET_EDGES   3u   /* compiled path; private to one object */

/* descriptor state bits */
#define CFW_CACHE_ST_COMPLETE 0x01u  /* asset: every byte arrived and validated */
#define CFW_CACHE_ST_STAGED   0x02u  /* created by the transaction in progress */
#define CFW_CACHE_ST_PRIVATE  0x04u  /* asset: owned by exactly one object, no id */
#define CFW_CACHE_ST_ACTIVE   0x08u  /* object: on the active list */
#define CFW_CACHE_ST_PINNED   0x10u  /* object: referenced by the transaction in progress */
#define CFW_DRAW_VALID        0x01u  /* object: drawn[] describes the panel */
#define CFW_DRAW_DIRTY        0x02u  /* object: changed since its last render */

typedef struct {
    uint32_t id;            /* 0 = free (private assets are also 0: reached via their object) */
    uint32_t version;
    uint32_t offset;        /* into the store, granule aligned */
    uint32_t length;        /* total bytes */
    uint32_t filled;        /* upload progress; == length once complete */
    uint32_t last_use;
    uint16_t refs;          /* objects holding this asset */
    uint16_t replaces;      /* unused since revision 42 (older versions are found by id at commit) */
    uint8_t  kind;
    uint8_t  state;
    uint8_t  pad[2];
} cfw_asset;

typedef struct {
    uint32_t id;            /* 0 = free */
    uint32_t version;
    uint32_t last_use;
    uint16_t asset;         /* index + 1 of the image/string/edge asset, 0 = none */
    uint16_t font;          /* index + 1 of the font asset, 0 = none */
    uint16_t replaces;      /* staged: index + 1 of the descriptor it supersedes */
    uint8_t  type;          /* CFW_SHAPE_* */
    uint8_t  flags;         /* CFW_SHAPE_FLAG_VISIBLE */
    uint8_t  color;         /* current color / options byte */
    uint8_t  width;         /* current stroke width (fill rule for PATH) */
    uint8_t  state;
    uint8_t  frames;        /* wire frame count of the running tween, 0 = idle */
    uint8_t  curve[4];      /* cubic-bezier easing x1 y1 x2 y2, each /255 */
    uint8_t  color_from, color_to;
    uint8_t  width_from, width_to;
    uint32_t started;       /* FW_MS_TICK when the tween began (revision 41: clock-based) */
    uint16_t duration;      /* frames * period at start, ms; 0 = idle */
    uint8_t  draw;          /* CFW_DRAW_*: what the last render left on the panel */
    uint8_t  pad[1];
    int16_t  p[8];          /* current geometry */
    int16_t  from[8];       /* tween start geometry */
    int16_t  to[8];         /* tween end geometry */
    cfw_rotation rotation;
    int16_t  drawn[4];      /* l, t, r, b (r, b exclusive) the last render may have touched */
} cfw_object;

typedef struct {
    uint32_t id;
    uint32_t version;       /* 0 = evicted or dropped */
    uint32_t revision;      /* cache revision that recorded it */
} cfw_journal_entry;

/* One message's staging state. Lives in the cache block, not on the stack:
 * the bridge task that runs the right lens's handlers has less stack than
 * the BLE task, and this is about 1.3 KiB. */
typedef struct {
    struct cfw_cache_s *sc;
    uint8_t *store;
    uint32_t evicted;
    uint32_t undo_count;
    uint8_t undo_active;
    uint8_t status;              /* CFW_CACHE_REPLY_* once failed; APPLIED while fine */
    uint8_t reason;
    uint8_t missing_count, missing_more;
    uint32_t missing[16];
    uint16_t staged_assets[CFW_CACHE_ASSETS];   /* in entry order, index + 1 */
    uint16_t staged_objects[CFW_CACHE_OBJECTS];
    uint16_t staged_asset_count, staged_object_count;
    uint32_t chunk_count;
    struct { uint16_t asset; uint16_t len; } chunks[CFW_CACHE_TXN_CHUNKS];
    /* Revision 48: a PUT_OBJECT whose id and version are already resident
     * re-asserts the record at commit (index + 1, and the record in the
     * message being applied) instead of being ignored. */
    uint16_t reassert_count;
    uint16_t reasserts[CFW_CACHE_TXN_REASSERTS];
    const uint8_t *reassert_records[CFW_CACHE_TXN_REASSERTS];
} cfw_txn;

typedef struct cfw_cache_s {
    uint32_t magic;
    mm_scene_context *owner;
    uint8_t *fb;            /* the owned panel shadow while the scene renders (image_buffers.c) */
    uint8_t  bg;            /* background gray the scene clears to */
    uint8_t  anim_active;   /* at least one active object has frames left */
    volatile uint8_t render_due; /* display_copy_hook must re-render before copying */
    uint8_t  period_ms;     /* animation frame period */
    uint8_t  settle_pending; /* a tagged SHOW has not reported settled yet */
    uint8_t  last_show_valid; /* last_show_request holds the last applied SHOW/HIDE */
    uint8_t  full_redraw;   /* the panel holds pixels no object accounts for: redraw everything */
    uint8_t  drawn_bg;      /* background the panel was last cleared to */
    uint8_t  pad1[2];
    int16_t  stale[4];      /* box freed objects left on the panel since the last render */
    uint8_t *drawn_fb;      /* the buffer the drawn boxes describe; 0 = none yet */
    uint16_t tag;           /* request echoed in the settled report (field 129) */
    uint16_t last_show_request;
    uint16_t active_count;
    uint32_t store_bytes;   /* capacity of the store this cache addresses (granules * 16) */
    uint32_t revision;      /* mutation counter, journaled */
    uint32_t use_clock;     /* recency counter; advances per accepted logical use */
    uint32_t journal_lost_rev; /* highest revision overwritten out of the journal ring */
    uint8_t  journal_head, journal_count, pad0[2];
    cfw_vector_work *vector_work; /* lazy, serialized by the display gate */
    struct cfw_undo_s *undo; /* allocated before the display gate, reused across PUTs */
    uint32_t undo_capacity; /* number of saved store granules that fit */
    cfw_txn txn;            /* the message being applied (handlers run one at a time) */
    uint16_t next[CFW_CACHE_OBJECTS]; /* SHOW: the incoming active list */
    uint32_t bitmap[CFW_CACHE_GRANULES / 32u];
    uint16_t active[CFW_CACHE_OBJECTS];
    cfw_journal_entry journal[CFW_CACHE_JOURNAL];
    cfw_asset assets[CFW_CACHE_ASSETS];
    cfw_object objects[CFW_CACHE_OBJECTS];
} cfw_cache;

static int  cfw_scene_dispatch(customCfwContext *ctx, uint8_t mode,
                               const uint8_t *src, uint32_t srclen,
                               int present, cfw_rectlist *rl);
static int  cfw_cache_immediate(customCfwContext *ctx, uint8_t mode, uint8_t *shadow,
                                uint32_t stride, uint32_t panel_w, uint32_t panel_h,
                                const uint8_t *src, uint32_t srclen, cfw_rectlist *rl);
static void cfw_scene_stop(customCfwContext *ctx);
static void cfw_scene_takeover(customCfwContext *ctx);
static int  cfw_scene_resync_shadow(customCfwContext *ctx, uint8_t *shadow);
static void cfw_scene_notify_settled(customCfwContext *ctx, uint16_t tag);
static void cfw_scene_release(customCfwContext *ctx);
static void cfw_scene_render_if_due(customCfwContext *ctx, uint8_t *fb);
static void cfw_cache_lose(customCfwContext *ctx);
static void cfw_cache_prepare(customCfwContext *ctx, uint8_t mode,
                              const uint8_t *src, uint32_t srclen);
/* message_transport.c: raise the reply capacity of the ingress streams. */
static void cfw_message_reply_capacity_hint(uint8_t capacity);
static void cfw_cache_reap(customCfwContext *ctx);
static void scene_tick(void *arg);

#endif
