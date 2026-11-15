/* Host check of vector.c + geom.c on a 540x220 L8 canvas: compiles a path
 * (hex command bytes, the wire format of PATH records), draws it, and
 * compares pixel probes; or rotates a geometry record. Writes a PGM when
 * VECTOR_PGM names a file. Built by tools/host/run_vector_tests.sh.
 *
 *   vector_test path <rule 0|1> <scaleQ8> <x> <y> <angleDeg*256> <px> <py> <hex> [x,y,gray]...
 *   vector_test shape <type> <width> <p0..p7 (8 ints)> <angleDeg*256> <px> <py> [x,y,gray]...
 *   vector_test fill-equivalence <trials>
 *
 * A probe passes when the canvas gray (0..15 after /17) matches; exit 1 on
 * the first mismatch, printing every probe. fill-equivalence fills random
 * contours and edge soups with cv_fill and with the all-edges scan it
 * replaced (revision 15) and requires identical canvases. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cfw.h"

uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
void cfw_zero(void *p, uint32_t n) { memset(p, 0, n); }

#include "geom.c"
#include "vector.c"

/* The revision 14 fill: every edge tested at every sub-row. */
static void ref_fill(customCfwContext *ctx, cfw_vector_work *w, uint32_t n, uint8_t rule) {
    if (!n || !ctx->canvas_buf) return;
    int32_t ymin = w->edges[0].y0, ymax = ymin;
    for (uint32_t i = 0; i < n; i++) {
        const cfw_edge *e = &w->edges[i];
        if (e->y0 < ymin) ymin = e->y0;
        if (e->y1 < ymin) ymin = e->y1;
        if (e->y0 > ymax) ymax = e->y0;
        if (e->y1 > ymax) ymax = e->y1;
    }
    int32_t row0 = g_div_floor(ymin, GQ4), row1 = g_div_floor(ymax, GQ4);
    if (row0 < 0) row0 = 0;
    if (row1 >= CFW_H) row1 = CFW_H - 1;
    g_row r;
    for (int32_t row = row0; row <= row1; row++) {
        g_row_begin(&r);
        for (int32_t s = 0; s < GSUB; s++) {
            int32_t yc = g_sub_y(row, s);
            uint32_t k = 0;
            for (uint32_t i = 0; i < n; i++) {
                cfw_edge e = w->edges[i];
                int8_t winding = 1;
                if (e.y0 == e.y1) continue;
                if (e.y0 > e.y1) { int32_t v = e.x0; e.x0 = e.x1; e.x1 = v; v = e.y0; e.y0 = e.y1; e.y1 = v; winding = -1; }
                if (yc < e.y0 || yc >= e.y1) continue;
                w->xs[k] = e.x0 + cv_muldiv(yc - e.y0, e.x1 - e.x0, e.y1 - e.y0);
                w->winds[k++] = winding;
            }
            cv_sort(w, k);
            int32_t winding = 0, start = 0;
            for (uint32_t i = 0; i < k;) {
                int32_t x = w->xs[i], delta = 0;
                uint32_t hits = 0;
                do { delta += w->winds[i++]; hits++; } while (i < k && w->xs[i] == x);
                int before = rule ? (winding & 1) : (winding != 0);
                winding = rule ? (winding ^ (int32_t)(hits & 1u)) : (winding + delta);
                int after = rule ? (winding & 1) : (winding != 0);
                if (!before && after) start = x;
                if (before && !after) g_row_add(&r, start, x, 1);
            }
        }
        g_row_flush(ctx, &r, row);
    }
}

static uint32_t seed = 12345;
static int32_t rnd(int32_t lo, int32_t hi) { seed = seed * 1103515245u + 12345u; return lo + (int32_t)((seed >> 8) % (uint32_t)(hi - lo + 1)); }

static int fill_equivalence(customCfwContext *ctx, uint8_t *canvas, int trials) {
    static cfw_vector_work a, b;
    static uint8_t want[CFW_W * CFW_H];
    for (int t = 0; t < trials; t++) {
        uint32_t n = 0;
        int soup = t % 3 == 2, snap = t % 4 == 1;   /* raw edges / coordinates on a coarse grid (many equal crossings) */
        int32_t span = t % 5 == 0 ? 40 : 700, cx = rnd(-100, 640), cy = rnd(-60, 280);
        uint32_t want_n = (uint32_t)rnd(1, PATH_MAX_EDGES);
        while (n < want_n) {
            uint32_t sides = soup ? 1 : (uint32_t)rnd(3, 24);
            int32_t fx = 0, fy = 0, px = 0, py = 0;
            for (uint32_t k = 0; k < sides && n < want_n; k++) {
                int32_t x = (cx + rnd(-span, span)) * 16 + (snap ? 0 : rnd(0, 15)), y = (cy + rnd(-span / 2, span / 2)) * 16 + (snap ? 0 : rnd(0, 15));
                if (snap) { x &= ~63; y &= ~31; }
                if (soup) { a.edges[n++] = (cfw_edge){ x, y, x + rnd(-400, 400), rnd(0, 3) ? y + rnd(-400, 400) : y }; continue; }
                if (k) a.edges[n++] = (cfw_edge){ px, py, x, y }; else { fx = x; fy = y; }
                px = x; py = y;
            }
            if (!soup && n < want_n) a.edges[n++] = (cfw_edge){ px, py, fx, fy };
        }
        b = a;
        uint8_t rule = (uint8_t)(t & 1);
        ctx->draw_gray = (uint8_t)(rnd(1, 15) * 17);
        for (uint32_t i = 0; i < CFW_W * CFW_H; i++) canvas[i] = (uint8_t)(rnd(0, 15) * 17);
        memcpy(want, canvas, sizeof want);
        ctx->canvas_buf = want; ref_fill(ctx, &b, n, rule);
        ctx->canvas_buf = canvas; cv_fill(ctx, &a, n, rule);
        if (memcmp(want, canvas, sizeof want)) { printf("trial %d (%u edges, rule %u) differs\n", t, n, rule); return 1; }
    }
    printf("fill-equivalence: %d random fills identical to the all-edges scan\n", trials);
    return 0;
}

static int hexval(char c) { return c >= '0' && c <= '9' ? c - '0' : (c | 32) - 'a' + 10; }

static int probes(customCfwContext *ctx, int argc, char **argv, int from) {
    int fail = 0;
    for (int i = from; i < argc; i++) {
        int x, y, g;
        if (sscanf(argv[i], "%d,%d,%d", &x, &y, &g) != 3) { fprintf(stderr, "bad probe %s\n", argv[i]); return 1; }
        int got = (ctx->canvas_buf[y * CFW_W + x] + 8) / 17;
        int ok = got == g;
        printf("  probe (%d,%d) expected %d got %d %s\n", x, y, g, got, ok ? "ok" : "MISMATCH");
        if (!ok) fail = 1;
    }
    return fail;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: see source\n"); return 2; }
    static customCfwContext ctx;
    static uint8_t canvas[CFW_W * CFW_H];
    static cfw_vector_work work;
    memset(&ctx, 0, sizeof ctx);
    memset(canvas, 0, sizeof canvas);
    ctx.canvas_buf = canvas;
    ctx.vector_work = &work;
    ctx.draw_gray = 15 * 17;
    int from;
    if (!strcmp(argv[1], "fill-equivalence")) return fill_equivalence(&ctx, canvas, argc > 2 ? atoi(argv[2]) : 200);
    if (!strcmp(argv[1], "path")) {
        if (argc < 10) return 2;
        uint8_t rule = (uint8_t)atoi(argv[2]);
        int16_t p[8] = { (int16_t)atoi(argv[4]), (int16_t)atoi(argv[5]), (int16_t)atoi(argv[3]), 0, 0, 0, 0, 0 };
        cfw_rotation t;
        memset(&t, 0, sizeof t);
        t.angle = atoi(argv[6]); t.px = (int16_t)atoi(argv[7]); t.py = (int16_t)atoi(argv[8]);
        const char *hex = argv[9];
        size_t n = strlen(hex) / 2;
        uint8_t *cmds = malloc(n);
        for (size_t i = 0; i < n; i++) cmds[i] = (uint8_t)(hexval(hex[2 * i]) << 4 | hexval(hex[2 * i + 1]));
        int edges = cfw_vec_compile(&work, cmds, (uint32_t)n);
        if (edges < 0) { printf("compile refused\n"); return 1; }
        printf("compiled %zu command bytes into %d edges\n", n, edges);
        cfw_path *path = malloc(sizeof(cfw_path) + (size_t)edges * sizeof(cfw_edge));
        path->count = (uint16_t)edges; path->rule = rule; path->pad = 0;
        memcpy(path->edges, work.edges, (size_t)edges * sizeof(cfw_edge));
        cfw_vec_path_draw(&ctx, &work, path, p, &t);
        from = 10;
    } else if (!strcmp(argv[1], "shape")) {
        if (argc < 15) return 2;
        cfw_object o;
        memset(&o, 0, sizeof o);
        o.id = 1; o.type = (uint8_t)atoi(argv[2]); o.width = (uint8_t)atoi(argv[3]);
        for (int i = 0; i < 8; i++) o.p[i] = (int16_t)atoi(argv[4 + i]);
        o.rotation.angle = atoi(argv[12]); o.rotation.px = (int16_t)atoi(argv[13]); o.rotation.py = (int16_t)atoi(argv[14]);
        if (cfw_vec_rotated(&o.rotation)) cfw_vec_shape_draw(&ctx, &work, &o);
        else cfw_geom_draw(&ctx, o.type, o.width, o.p);
        from = 15;
    } else return 2;
    const char *pgm = getenv("VECTOR_PGM");
    if (pgm) {
        FILE *f = fopen(pgm, "wb");
        if (f) { fprintf(f, "P5\n%d %d\n255\n", CFW_W, CFW_H); fwrite(canvas, 1, sizeof canvas, f); fclose(f); }
    }
    return probes(&ctx, argc, argv, from);
}
