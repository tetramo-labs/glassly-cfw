/* G2 geometry adaptation, 2026-10-31. See PROVENANCE.md and LICENSE (MIT). */
#ifndef MEMOMIND_PORTABLE_GEOMETRY_H
#define MEMOMIND_PORTABLE_GEOMETRY_H
#include <stddef.h>
#include <stdint.h>

/* Byte-aligned GRAY4: even x occupies the high nibble. Padding and an odd
 * row's unused low nibble are preserved. No allocation or device access. */
typedef struct {
    uint8_t *pixels;
    size_t bytes;
    uint32_t width;
    uint32_t height;
    uint32_t stride;
} mm_raster;

enum {
    MM_GEOMETRY_OK = 0,
    MM_GEOMETRY_TARGET = -1,
    MM_GEOMETRY_MESSAGE = -2,
    MM_GEOMETRY_UNSUPPORTED = -3,
    MM_GEOMETRY_ALIAS = -4
};
#define MM_GEOMETRY_MODE 36u
#define MM_GEOMETRY_RECORD_BYTES 20u
#define MM_GEOMETRY_MAX_RECORDS 255u
#define MM_GEOMETRY_MAX_MESSAGE (2u + MM_GEOMETRY_MAX_RECORDS * MM_GEOMETRY_RECORD_BYTES)
#define MM_RASTER_MAX_DIMENSION 4096u

int mm_raster_validate(const mm_raster *target);
int mm_raster_pixel(const mm_raster *target, int32_t x, int32_t y, uint8_t color);
int mm_raster_span(const mm_raster *target, int32_t x0, int32_t x1, int32_t y, uint8_t color);
int mm_raster_clear(const mm_raster *target, uint8_t color);

/* Full raw mode36 message: [36][count:u8][count * 20-byte geometric records].
 * Record: type1..13, flags, color, width, eight signed LE16 parameters.
 * As upstream, immediate geometry ignores flags, masks color to four bits,
 * clamps coordinates, and interprets width by primitive. Unsupported types,
 * stereo mode bit, truncation/trailing bytes and framebuffer aliasing are
 * rejected before any pixels change. Empty count is a valid no-op.
 * Caller serializes rendering and keeps target/input stable during the call.
 * This is a synchronous memory renderer, not an atomic device presentation. */
/* Pure syntax/type validation; no framebuffer or allocation needed. The render
 * call repeats validation because the caller must still keep input stable. */
int mm_geometry_validate_message(const uint8_t *message, size_t length);
int mm_geometry_mode36(const mm_raster *target, const uint8_t *message, size_t length);
#endif
