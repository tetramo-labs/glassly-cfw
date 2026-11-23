/* G2 path compiler/raster adaptation. MIT; see PROVENANCE.md and LICENSE. */
#ifndef MEMOMIND_PORTABLE_VECTOR_H
#define MEMOMIND_PORTABLE_VECTOR_H
#include "geometry.h"
#define MM_VECTOR_MAX_EDGES 512u
#define MM_VECTOR_MAX_BYTES 8192u
#define MM_VECTOR_MAX_COMMANDS 1024u
#define MM_VECTOR_MAX_DIMENSION 1024u
#define MM_VECTOR_MAX_ANGLE (360*256*100)
typedef struct { int32_t x0,y0,x1,y1; } mm_vector_edge;
typedef struct {
    mm_vector_edge edges[MM_VECTOR_MAX_EDGES];
    int32_t xs[MM_VECTOR_MAX_EDGES];
    int8_t winds[MM_VECTOR_MAX_EDGES];
} mm_vector_work;
typedef struct { uint16_t count; uint8_t rule,pad; mm_vector_edge edges[]; } mm_vector_path;
typedef struct { int32_t angle; int16_t px,py; } mm_vector_rotation;
typedef struct { int16_t x,y; uint16_t scale; mm_vector_rotation rotation; } mm_vector_transform;
enum { MM_VECTOR_MESSAGE=-1, MM_VECTOR_CAPACITY=-2, MM_VECTOR_TARGET=-3,
       MM_VECTOR_ALIAS=-4, MM_VECTOR_TRANSFORM=-5 };
/* Caller allocates aligned workspace and path storage explicitly; no allocator
 * callbacks, global work buffer, native imports or hidden allocations. */
size_t mm_vector_path_bytes(unsigned count);
/* Returns edge count (including zero), or a negative error. Commands: M0/L1,
 * Q2/C3/Z4, signed LE16 Q4 pairs, every contour explicitly closed. Rule0 nonzero,
 * rule1 evenodd. Workspace may change on failure; output path never changes on
 * failure. path=NULL/capacity=0 compiles/measures only; use path_bytes(result).
 * All accessed buffers must be valid, distinct and stable throughout the call. */
int mm_vector_compile(mm_vector_work *work,size_t work_bytes,const uint8_t *commands,
                      size_t length,uint8_t rule,mm_vector_path *path,size_t capacity);
/* Compiled edge endpoints are restricted to signed16 source Q4 range. Path bytes
 * include header and complete count edges. Transform scale Q8 0..2048 and angle
 * ±100 turns. Dimensions<=1024 protect unchanged stroke integer intermediates.
 * Validation completes before framebuffer writes; workspace/path/framebuffer
 * overlap is rejected. Renderer is synchronous, without presentation ownership. */
int mm_vector_draw_path(const mm_raster *target,mm_vector_work *work,size_t work_bytes,
                        const mm_vector_path *path,size_t path_bytes,
                        const mm_vector_transform *transform,uint8_t color);
int mm_vector_draw_shape(const mm_raster *target,mm_vector_work *work,size_t work_bytes,
                         const uint8_t *record,size_t length,const mm_vector_rotation *rotation);
#ifdef MM_SCENE_EXTERNAL_STORE
#include "scene_store.h"
/* Descriptor, store table/state, transform and source bytes must not overlap
 * workspace or pixels. Alias rejection happens before reads or mutations. */
int mm_vector_draw_path_reader(const mm_raster *,mm_vector_work *,size_t,
                               const mm_scene_bytes *,const mm_vector_transform *,uint8_t);
#endif
#endif
