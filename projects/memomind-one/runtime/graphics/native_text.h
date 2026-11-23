/* MemoMind resource-font GRAY4 adapter. MIT; native proof: font-adapter/report.md. */
#ifndef MM_GRAPHICS_NATIVE_TEXT_H
#define MM_GRAPHICS_NATIVE_TEXT_H
#include "../portable/scene.h"
#define MM_NATIVE_TEXT_DEFAULT_FONT UINT32_C(0x0438f77c)
#define MM_NATIVE_TEXT_LARGE_FONT UINT32_C(0x0438f75c)
#define MM_NATIVE_TEXT_EMOJI_FONT UINT32_C(0x04385e7c)
#ifdef MM_TEXT_COMMANDS
#define MM_NATIVE_TEXT_MAX_BYTES 255u
#else
#define MM_NATIVE_TEXT_MAX_BYTES 128u
#endif
/* uint32 handle keeps the actual 16-byte target descriptor layout on hosts. */
typedef struct {
    uint32_t font;
    uint16_t advance,box_w,box_h;
    int16_t ofs_x,ofs_y;
    uint8_t bpp_flags,reserved;
} mm_native_text_glyph;
typedef struct {
    void *context;
    uint32_t root_font;
    int (*ready)(void *);
    int (*font_info)(void *,uint32_t,int32_t *height,int32_t *baseline,uint8_t *flags);
    int (*metrics)(void *,uint32_t,mm_native_text_glyph *,uint32_t,uint32_t);
    const uint8_t *(*bitmap)(void *,uint32_t,uint32_t);
    /* Glyph boxes, offsets, advances and the baseline drawn at num/den of the
     * resource font's size (0/0 = as is); control shifts stay in panel pixels. */
    uint8_t scale_num,scale_den;
} mm_native_text_api;
/* The default resource font is a 34 px line with its baseline 7 px up. At 4/5
 * it is the G2 builtin font's 27 px line and 22 px baseline, so default text
 * is the size the phone mirror and the Even G2 draw it (GLASSLYCFW/13). */
#define MM_NATIVE_TEXT_SCALE_NUM 4u
#define MM_NATIVE_TEXT_SCALE_DEN 5u
/* user is a const mm_native_text_api*, not a scene owner. With firmware macro,
 * NULL selects mm_native_text_firmware_api. Caller owns display serialization
 * and lease, and keeps API/resources/input/target stable for this entire call.
 * Callbacks must return stable results across preflight and drawing; bitmap
 * storage is borrowed, readable for ceil(w*h*bpp/8), and never freed here.
 * Only the three proved mapped-resource font handles and 1/2bpp are accepted.
 * Missing/unresolved/dynamic glyphs reject the whole string in preflight.
 * Pixels and dirty stay unchanged on validation/preflight failure; token
 * scratch may change. No allocation, native render calls, or writable globals.
 * A scaled API draws each output pixel as the mean of a 2x2 sample of the
 * glyph box; at 1/1 that is the glyph pixel itself.
 */
int mm_native_builtin_text(void *user,const mm_raster *,const uint8_t *,size_t,
                           mm_scene_dirty *,uint32_t *,size_t);
#ifdef MM_NATIVE_TEXT_FIRMWARE
extern const mm_native_text_api mm_native_text_firmware_api;
#endif
#endif
