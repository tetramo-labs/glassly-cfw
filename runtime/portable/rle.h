/* Bounded G2 4bpp RLE adaptation. MIT; see PROVENANCE.md and LICENSE. */
#ifndef MEMOMIND_PORTABLE_RLE_H
#define MEMOMIND_PORTABLE_RLE_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t *pixels;
    size_t bytes;
    uint32_t rowbytes, rows, stride;
} mm_rle_surface;
enum { MM_RLE_OK=0, MM_RLE_TARGET=-1, MM_RLE_MESSAGE=-2,
       MM_RLE_CAPACITY=-3, MM_RLE_ALIAS=-4 };
/* Token forms [count4|color4], [color4,count8], [color4,0,countLE16].
 * Noncanonical positive counts are valid; zero counts are invalid. Validation
 * consumes the complete stream and requires exactly expected_pixels nibbles.
 * expected_pixels must be positive. No target, allocation or writes. */
int mm_rle_validate(const uint8_t *src, size_t length, uint32_t expected_pixels);
int mm_rle_surface_validate(const mm_rle_surface *surface);
/* Mode3/6 packed rows: rowbytes*2 nibbles per row, including an odd-visible-
 * width padding nibble. Stride padding remains untouched. All malformed streams
 * and source/target overlap are rejected before any writes. No clipping. */
int mm_rle_decode(const mm_rle_surface *surface, const uint8_t *src, size_t length);
/* Decode a byte-aligned window within a complete validated surface. Bounds
 * use the parent surface, including windows at its bottom/right edge. Same
 * prevalidation/no-partial-write contract as decode; no caller metadata writes. */
int mm_rle_decode_window(const mm_rle_surface *,uint32_t x_byte,uint32_t y,
                         uint32_t rowbytes,uint32_t rows,const uint8_t *,size_t);
/* Canonical encoding splits runs at 65535, choosing shortest count form.
 * dst=NULL/capacity=0 queries exact size. written is required, must not overlap
 * either input, metadata or output. An aliased written pointer is untouched;
 * otherwise errors set it to zero except insufficient capacity (required size). Insufficient capacity leaves dst unchanged.
 * Caller owns all buffers and keeps them stable; no heap or device access. */
int mm_rle_encode(const mm_rle_surface *surface, uint8_t *dst, size_t capacity,
                  size_t *written);
#endif
