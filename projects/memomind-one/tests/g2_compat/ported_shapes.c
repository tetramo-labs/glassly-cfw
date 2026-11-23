/* Generated from pinned upstream test_immediate; MIT, see LICENSE.
 * Retained original geometric records and assertions; asset/cache portions
 * remain explicitly unimplemented. Run prepare_ports.py to reproduce. */
#define main original_shapes_reference_main
#include "upstream/patches/host/shapes_host_test.c"
#undef main
#include "geometry.h"
#undef CHECK
static unsigned memo_assertions;
#define CHECK(cond) do { memo_assertions++; if (!(cond)) { fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,#cond); g_fail++; } } while (0)
static int memo_immediate(uint8_t *pixels,uint32_t stride,uint32_t w,uint32_t h,
                          const uint8_t *src,uint32_t len,cfw_rectlist *rl) {
    (void)rl;
    uint8_t packet[MM_GEOMETRY_MAX_MESSAGE];
    if (len + 1u > sizeof(packet)) return -1;
    packet[0]=36;
    for (uint32_t i=0;i<len;i++) packet[i+1]=src[i];
    mm_raster target={pixels,(size_t)stride*h,w,h,stride};
    return mm_geometry_mode36(&target,packet,len+1u)==0 ? 0 : -1;
}
static void test_immediate_ported(const char *dir) {
    uint8_t msg[1 + 26 * CFW_SHAPE_RECORD_BYTES];
    uint8_t *p = msg + 1;
    int n = 0;
#define R(type, color, width, ...) do { int16_t v[] = { __VA_ARGS__ }; p = rec(p, type, color, width, v, (int)(sizeof v / sizeof v[0])); n++; } while (0)
    R(CFW_SHAPE_RECT,        15, 2, 8, 8, 624, 464, 12);           /* frame */
    R(CFW_SHAPE_LINE,        15, 1, 20, 20, 200, 60);
    R(CFW_SHAPE_LINE,        12, 6, 20, 80, 200, 40);
    R(CFW_SHAPE_LINE,         9, 3, 30, 120, 30, 200);              /* vertical wide */
    R(CFW_SHAPE_RECT_FILL,   10, 0, 240, 20, 100, 60, 0);
    R(CFW_SHAPE_RECT_FILL,   15, 0, 360, 20, 100, 60, 16);
    R(CFW_SHAPE_RECT,        15, 4, 480, 20, 100, 60, 20);
    R(CFW_SHAPE_CIRCLE_FILL, 15, 0, 100, 300, 60);
    R(CFW_SHAPE_CIRCLE,      15, 1, 240, 300, 60);
    R(CFW_SHAPE_CIRCLE,      12, 8, 380, 300, 60);
    R(CFW_SHAPE_CIRCLE_FILL,  8, 0, 500, 300, 1);                   /* tiny */
    R(CFW_SHAPE_TRI_FILL,    15, 0, 40, 400, 120, 400, 80, 440);
    R(CFW_SHAPE_TRI,         15, 2, 140, 440, 220, 440, 180, 400);
    R(CFW_SHAPE_QUAD_FILL,   11, 0, 250, 400, 330, 410, 320, 460, 260, 450);
    R(CFW_SHAPE_QUAD,        15, 1, 350, 400, 430, 410, 420, 460, 360, 450);
    R(CFW_SHAPE_BEZIER2,     15, 1, 20, 260, 140, 100, 220, 260);
    R(CFW_SHAPE_BEZIER3,     15, 4, 240, 200, 300, 100, 360, 300, 440, 200);
    R(CFW_SHAPE_ARC,         15, 3, 560, 120, 50, 180, 360);         /* upper half */
    R(CFW_SHAPE_ARC,         12, 1, 560, 120, 50, 0, 90);
    R(CFW_SHAPE_PIE,         15, 0, 560, 300, 50, -90, 135);
    R(CFW_SHAPE_PIE,          6, 0, 560, 400, 40, 0, 360);           /* full disc */
    R(CFW_SHAPE_LINE,        15, 1, -50, 470, 700, 250);              /* clipped both ends */
#undef R
    msg[0] = (uint8_t)n;
    uint32_t len = (uint32_t)(p - msg);
    bzero(g_shadow, sizeof g_shadow);
    cfw_rectlist rl = { 0 };
    CHECK(memo_immediate(g_shadow, IMAGE_STRIDE, IMAGE_W, IMAGE_H, msg, len, &rl) == 0);
    write_pgm(dir, "immediate", g_shadow);

    /* filled circle r=60 covers about pi*60^2 = 11310 px of color 15 at (100,300) */
    uint32_t disc = 0;
    for (int y = 230; y < 370; y++) for (int x = 30; x < 170; x++) if (pixel_at(g_shadow, x, y) == 15) disc++;
    CHECK(disc > 11000 && disc < 11600);
    CHECK(pixel_at(g_shadow, 100, 300) == 15);
    CHECK(pixel_at(g_shadow, 100, 239) == 0 && pixel_at(g_shadow, 100, 240) == 15);   /* top edge at cy - r */
    CHECK(pixel_at(g_shadow, 100, 360) == 15 && pixel_at(g_shadow, 100, 361) == 0);   /* bottom edge at cy + r */
    CHECK(pixel_at(g_shadow, 39, 300) == 0 && pixel_at(g_shadow, 40, 300) == 15 && pixel_at(g_shadow, 160, 300) == 15 && pixel_at(g_shadow, 161, 300) == 0);
    /* ring r=60 w=8: center empty, band exactly 8 px thick */
    CHECK(pixel_at(g_shadow, 380, 300) == 0 && pixel_at(g_shadow, 380, 240) == 12 && pixel_at(g_shadow, 380, 247) == 12 && pixel_at(g_shadow, 380, 248) == 0);
    /* rect fill exact size */
    CHECK(pixel_at(g_shadow, 240, 20) == 10 && pixel_at(g_shadow, 339, 79) == 10 && pixel_at(g_shadow, 340, 20) == 0 && pixel_at(g_shadow, 240, 80) == 0);
    /* rounded corner removed, straight edges kept */
    CHECK(pixel_at(g_shadow, 360, 20) == 0 && pixel_at(g_shadow, 410, 20) == 15 && pixel_at(g_shadow, 360, 50) == 15);
    /* tiny circle: r=1 -> a 3x3 block */
    CHECK(pixel_at(g_shadow, 499, 299) == 8 && pixel_at(g_shadow, 501, 301) == 8 && pixel_at(g_shadow, 498, 300) == 0 && pixel_at(g_shadow, 502, 300) == 0 && pixel_at(g_shadow, 500, 298) == 0);
    /* full pie == disc of radius 40: ~5026 px */
    uint32_t pie = 0;
    for (int y = 355; y < 445; y++) for (int x = 515; x < 605; x++) if (pixel_at(g_shadow, x, y) == 6) pie++;
    CHECK(pie > 4850 && pie < 5300);

    /* validation: wrong length, bad type, unknown asset, path record */
    CHECK(memo_immediate(g_shadow, IMAGE_STRIDE, IMAGE_W, IMAGE_H, msg, len - 1, &rl) == -1);
    msg[1] = 99;
    CHECK(memo_immediate(g_shadow, IMAGE_STRIDE, IMAGE_W, IMAGE_H, msg, len, &rl) == -1);
    msg[1] = CFW_SHAPE_RECT;
    { uint8_t cmds[] = { 0, 0, 0, 0, 0, 4 }; uint8_t pm[64]; pm[0] = 1; uint8_t *e = rec_path(pm + 1, 15, 0, 0, 0, 256, cmds, 6);
      CHECK(memo_immediate(g_shadow, IMAGE_STRIDE, IMAGE_W, IMAGE_H, pm, (uint32_t)(e - pm), &rl) == -1); }

}

int main(int argc,char **argv) {
    if(argc!=2) return 2;
    test_immediate_ported(argv[1]);
    printf("ported original geometric partition: %u original assertions, %d failures\n",memo_assertions,g_fail);
    return g_fail?1:0;
}
