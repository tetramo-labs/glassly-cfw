/* G2 mode9 packed GRAY4 copy, explicit single-display first/left policy. MIT. */
#ifndef MM_RECT_COPY_COMMANDS_H
#define MM_RECT_COPY_COMMANDS_H
#include "geometry.h"
/* [9][source L,T,W,H:u16LE][destination L,T,W,H:u16LE]; minimum17B.
 * 0x89 requires33B but uses only the first/left pair. Trailing bytes ignored as
 * upstream. Selected rectangles must have equal positive sizes, wholly inside
 * target. Overlap and self-copy legal; no clipping. No allocations/presentation.
 * Stable serialized source/target required; all validation precedes writes.
 * Descriptor/input/target aliases and integer-span overflow are rejected. */
int mm_rect_copy_validate(const mm_raster *,const uint8_t *,size_t);
int mm_rect_copy_draw(const mm_raster *,const uint8_t *,size_t);
#endif
