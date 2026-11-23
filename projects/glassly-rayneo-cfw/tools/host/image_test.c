/* Host check of scene.c's cached-image path: a 3x2 image `[w][h][RLE]` (an
 * odd width, so no row padding may be assumed) drawn through the real
 * decoder, LUT and blit must land pixel for pixel on the canvas, left to
 * right, and the texture options must apply. Cached-font glyphs decode one
 * image each from a table of back-to-back glyphs; nothing is decoded through
 * the store; blits clip to the canvas and to a text box.
 *
 *   clang -std=c11 -Ipatches -Ipatches/generated -o image_test tools/host/image_test.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cfw.h"
#define fw_memalign(a, n) malloc(n)
#define fw_free(p) free(p)
#define fw_tick() 100u

void cfw_zero(void *p, uint32_t n) { memset(p, 0, n); }
void cfw_page_present(customCfwContext *ctx) { (void)ctx; }
int cfw_uplink_push(customCfwContext *ctx, const uint8_t *d, uint8_t n) { (void)ctx; (void)d; (void)n; return 1; }
void cfw_anim_stop(customCfwContext *ctx) { (void)ctx; }
void cfw_anim_arm(customCfwContext *ctx) { (void)ctx; }
void cfw_anim_settled(customCfwContext *ctx, cfw_lens *L) { (void)ctx; (void)L; }
uint8_t cfw_op_check(customCfwContext *ctx, cfw_lens *L, const uint8_t *p, uint8_t *reason) { (void)ctx; (void)L; (void)p; (void)reason; return 1; }
cfw_vector_work *cfw_vec_work(customCfwContext *ctx) { (void)ctx; return NULL; }
int cfw_vec_compile(cfw_vector_work *w, const uint8_t *src, uint32_t len) { (void)w; (void)src; (void)len; return 0; }
void cfw_vec_path_draw(customCfwContext *ctx, cfw_vector_work *w, const cfw_path *path, const int16_t *p, const cfw_rotation *t) { (void)ctx; (void)w; (void)path; (void)p; (void)t; }
void cfw_vec_shape_draw(customCfwContext *ctx, cfw_vector_work *w, const cfw_object *o) { (void)ctx; (void)w; (void)o; }
int cfw_vec_rotated(const cfw_rotation *t) { (void)t; return 0; }
void cfw_geom_draw(customCfwContext *ctx, uint8_t type, uint8_t width, const int16_t *params) { (void)ctx; (void)type; (void)width; (void)params; }

uint32_t cfw_op_len(const uint8_t *p, uint32_t avail) { (void)p; (void)avail; return 0; }
void cfw_anim_freeze_all(cfw_lens *L) { (void)L; }

#include "scene.c"

static int fail;
static uint8_t canvas[CFW_W * CFW_H];
static void expect(customCfwContext *ctx, int x, int y, int gray) {
    int got = ctx->lens[0].canvas[y * CFW_W + x] / 17;
    printf("  (%d,%d) expected %2d got %2d %s\n", x, y, gray, got, got == gray ? "ok" : "MISMATCH");
    if (got != gray) fail = 1;
}
static void check(const char *what, int ok) {
    printf("  %-62s %s\n", what, ok ? "ok" : "MISMATCH");
    if (!ok) fail = 1;
}
static int ink_from(int x0, int y0, int x1, int y1) {
    int ink = 0;
    for (int y = y0; y < y1; y++) for (int x = x0; x < x1; x++) ink += canvas[y * CFW_W + x] != 0;
    return ink;
}

int main(void) {
    static customCfwContext ctx;
    static uint8_t store[CFW_STORE_MAX_BYTES];
    ctx.store = store; ctx.store_bytes = CFW_STORE_MAX_BYTES; ctx.store_granules = STORE_GRANULES_MAX; ctx.lens[0].canvas = canvas;
    store_clear(&ctx);
    /* 3x2 image, pixels row 0: 1 2 3, row 1: 4 5 6 as six single-pixel RLE tokens [1<<4|c] */
    uint8_t img[] = { 3, 2, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16 };
    cfw_object o = {0};
    o.type = SH_IMAGE; o.p[0] = 10; o.p[1] = 20;
    uint8_t lut[16];
    puts("plain (ink 15)");
    o.color = 15; make_lut(o.color, lut);
    ctx.canvas_buf = canvas;
    if (!blit_image(&ctx, img, sizeof img, 10, 20, lut, 0, CFW_W, CFW_H)) { puts("  decode FAILED"); return 1; }
    expect(&ctx, 10, 20, 1); expect(&ctx, 11, 20, 2); expect(&ctx, 12, 20, 3);
    expect(&ctx, 10, 21, 4); expect(&ctx, 11, 21, 5); expect(&ctx, 12, 21, 6);
    puts("inverse, ink 15, transparent: source 0 skipped, 15-g otherwise");
    uint8_t img2[] = { 2, 1, 0x10, 0x1f };            /* pixels 0, 15 */
    memset(canvas, 7 * 17, sizeof canvas);
    make_lut(TEX_OPT_INVERSE | TEX_OPT_TRANSPARENT | 15, lut);
    blit_image(&ctx, img2, sizeof img2, 0, 0, lut, 1, CFW_W, CFW_H);
    expect(&ctx, 0, 0, 7); expect(&ctx, 1, 0, 0);

    puts("decode needs no store space and allocates none");
    memset(canvas, 0, sizeof canvas);
    memset(ctx.store_map, 0xff, sizeof ctx.store_map);
    ctx.store_used = ctx.store_bytes;
    make_lut(15, lut);
    check("drawn with every store granule taken", blit_image(&ctx, img, sizeof img, 10, 20, lut, 0, CFW_W, CFW_H) == 3);
    expect(&ctx, 12, 21, 6);
    check("store accounting untouched", ctx.store_used == ctx.store_bytes);
    store_clear(&ctx);

    puts("exactly one image: a short or overlong stream is refused");
    check("one byte short", !blit_image(&ctx, img, sizeof img - 1, 10, 20, lut, 0, CFW_W, CFW_H));
    uint8_t longer[sizeof img + 1];
    memcpy(longer, img, sizeof img); longer[sizeof img] = 0x11;
    check("trailing token", !blit_image(&ctx, longer, sizeof longer, 10, 20, lut, 0, CFW_W, CFW_H));
    uint8_t over[] = { 2, 1, 0x3f };                  /* a 3-pixel run in a 2-pixel image */
    check("run past the last pixel", !blit_image(&ctx, over, sizeof over, 10, 20, lut, 0, CFW_W, CFW_H));

    puts("clipping: canvas edges and right/bottom limits, runs crossing rows");
    {
        /* 4x3, rows 1 2 3 4 / 5 6 7 8 / 9 10 11 12 as single-pixel tokens */
        uint8_t im[2 + 12] = { 4, 3 };
        for (int i = 0; i < 12; i++) im[2 + i] = (uint8_t)(0x10 | (i + 1));
        memset(canvas, 0, sizeof canvas);
        check("negative x and y", blit_image(&ctx, im, sizeof im, -1, -1, lut, 0, CFW_W, CFW_H) == 4);
        expect(&ctx, 0, 0, 6); expect(&ctx, 2, 0, 8); expect(&ctx, 0, 1, 10); expect(&ctx, 2, 1, 12); expect(&ctx, 3, 0, 0);
        memset(canvas, 0, sizeof canvas);
        blit_image(&ctx, im, sizeof im, CFW_W - 2, CFW_H - 1, lut, 0, CFW_W, CFW_H);
        expect(&ctx, CFW_W - 2, CFW_H - 1, 1); expect(&ctx, CFW_W - 1, CFW_H - 1, 2);
        memset(canvas, 0, sizeof canvas);
        blit_image(&ctx, im, sizeof im, 100, 100, lut, 0, 102, 102);
        expect(&ctx, 101, 101, 6); expect(&ctx, 102, 100, 0); expect(&ctx, 100, 102, 0);
        /* a single run spanning all three rows */
        uint8_t span[] = { 4, 3, 0x07, 0x0c };
        memset(canvas, 0, sizeof canvas);
        check("one run over three rows", blit_image(&ctx, span, sizeof span, 50, 50, lut, 0, 52, CFW_H) == 4);
        expect(&ctx, 51, 52, 7); expect(&ctx, 52, 51, 0); expect(&ctx, 50, 53, 0);
    }

    puts("builtin font: 'I' has ink in its cell, ' ' has none");
    memset(canvas, 0, sizeof canvas);
    uint8_t text[] = "I ";
    draw_font_text(&ctx, font_builtin, FONT_BUILTIN_BYTES, 1, text, 2, 0, 0, (make_lut(15, lut), lut), 0, CFW_W, CFW_H);
    int ink = 0, blank = 0;
    for (int y = 0; y < 20; y++) for (int x = 0; x < 12; x++) { ink += canvas[y * CFW_W + x] != 0; blank += canvas[y * CFW_W + 12 + x] != 0; }
    printf("  'I' ink pixels %d (%s), ' ' ink pixels %d (%s)\n", ink, ink > 10 ? "ok" : "MISMATCH", blank, blank == 0 ? "ok" : "MISMATCH");
    if (ink <= 10 || blank) fail = 1;

    puts("cached font: glyphs back to back, each decoded on its own");
    {
        /* [96 x u32 offsets]['A' 2x2 of 15]['B' 3x1 of 5] */
        uint8_t font[384 + 6];
        memset(font, 0, sizeof font);
        cfw_put32(font + ('A' - 32) * 4, 384); font[384] = 2; font[385] = 2; font[386] = 0x4f;
        cfw_put32(font + ('B' - 32) * 4, 387); font[387] = 3; font[388] = 1; font[389] = 0x35;
        check("the table validates as a font asset", asset_content_valid(font, sizeof font, ASSET_FONT));
        memset(canvas, 0, sizeof canvas);
        const uint8_t a[] = "A", ab[] = "AB";
        check("the first glyph draws", draw_font_text(&ctx, font, sizeof font, 0, a, 1, 100, 50, lut, 0, CFW_W, CFW_H));
        expect(&ctx, 100, 50, 15); expect(&ctx, 101, 51, 15); expect(&ctx, 102, 50, 0);
        check("both glyphs draw", draw_font_text(&ctx, font, sizeof font, 0, ab, 2, 100, 60, lut, 0, CFW_W, CFW_H));
        expect(&ctx, 101, 61, 15); expect(&ctx, 102, 60, 5); expect(&ctx, 104, 60, 5); expect(&ctx, 105, 60, 0);
    }

    puts("TEXT_INLINE box: right/bottom clip where w/h > 0, the canvas otherwise (G2)");
    {
        static uint8_t full[CFW_W * CFW_H];
        uint8_t s[] = "MMMM";
        cfw_object t = {0};
        t.type = SH_TEXT_INLINE; t.flags = OBJ_VISIBLE; t.color = 15;
        t.p[0] = 200; t.p[1] = 100;
        uint32_t off = store_alloc(&ctx, sizeof s);
        memcpy(store + off, s, sizeof s);
        t.text_off = off; t.text_len = 4;
        memset(canvas, 0, sizeof canvas);
        draw_text(&ctx, &t);
        memcpy(full, canvas, sizeof canvas);
        int whole = ink_from(0, 0, CFW_W, CFW_H);
        check("unclipped text drew ink", whole > 40);
        check("ink right of x + 20 when unclipped", ink_from(220, 0, CFW_W, CFW_H) > 0);
        t.p[2] = 20; t.p[3] = 10;
        memset(canvas, 0, sizeof canvas);
        draw_text(&ctx, &t);
        check("no ink at or right of x + w", ink_from(220, 0, CFW_W, CFW_H) == 0);
        check("no ink at or below y + h", ink_from(0, 110, CFW_W, CFW_H) == 0);
        int same = 1;
        for (int y = 100; y < 110; y++) for (int x = 200; x < 220; x++) same &= canvas[y * CFW_W + x] == full[y * CFW_W + x];
        check("inside the box the pixels are the unclipped ones", same);
        t.p[2] = 0; t.p[3] = -5;
        memset(canvas, 0, sizeof canvas);
        draw_text(&ctx, &t);
        check("zero or negative w/h leave the canvas as the clip", !memcmp(canvas, full, sizeof canvas));
        t.p[0] = -10; t.p[2] = 5;
        memset(canvas, 0, sizeof canvas);
        draw_text(&ctx, &t);
        check("a box ending left of the canvas draws nothing", ink_from(0, 0, CFW_W, CFW_H) == 0);
    }
    return fail;
}
