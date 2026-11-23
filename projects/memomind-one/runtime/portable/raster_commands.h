/* Optional G2 mode3/6 single-display raster adapter. MIT. */
#ifndef MM_RASTER_COMMANDS_H
#define MM_RASTER_COMMANDS_H
#include "geometry.h"
/* Caller keeps input/target stable, serialized, readable/writable for declared
 * spans. No allocation or presentation. Reject descriptor/input/pixel aliases.
 * 0x83 selects the first (G2 left) bbox; both encoded dimensions must match.
 * 0x86 ignores the high bit. Frame IDs are accepted but never deduplicate.
 * validate and draw reject malformed messages before any pixel writes. */
int mm_raster_command_validate(const mm_raster *,const uint8_t *,size_t);
int mm_raster_command_draw(const mm_raster *,const uint8_t *,size_t);
#endif
