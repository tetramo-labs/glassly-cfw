/* Built-in text in the stock LVGL default face. Glyph boxes come from the
 * font's own get_glyph_dsc; the bitmaps are read in place from its const
 * tables and drawn into the GRAY4 canvas. No allocation, no writable statics,
 * no LVGL drawing. Same record and option bits as the MemoMind native text
 * adapter. MIT. */
#include "text.h"
#include "stock.h"

typedef struct {
    int32_t adv, w, h, ox, oy;
    uint32_t bpp;
    const uint8_t *bits;
} glyph;

static int32_t s16(const uint8_t *p)
{
    uint32_t v = p[0] | ((uint32_t)p[1] << 8);
    return v < 32768u ? (int32_t)v : (int32_t)v - 65536;
}

static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return an && bn && (x <= y ? y - x < an : x - y < bn);
}

/* One pen move (a byte 1..31, returned as itself) or one UTF-8 scalar. */
static int next(const uint8_t *p, size_t n, size_t *used, uint32_t *cp)
{
    uint32_t a = p[0];
    if (a >= 1u && a <= 0x7Fu) {
        *used = 1;
        *cp = a;
        return 1;
    }
    if (a >= 0xC2u && a <= 0xDFu) {
        if (n < 2 || (p[1] & 0xC0u) != 0x80u) return 0;
        *used = 2;
        *cp = ((a & 31u) << 6) | (p[1] & 63u);
        return 1;
    }
    if (a >= 0xE0u && a <= 0xEFu) {
        if (n < 3 || (p[1] & 0xC0u) != 0x80u || (p[2] & 0xC0u) != 0x80u || (a == 0xE0u && p[1] < 0xA0u) ||
            (a == 0xEDu && p[1] >= 0xA0u)) return 0;
        *used = 3;
        *cp = ((a & 15u) << 12) | ((uint32_t)(p[1] & 63u) << 6) | (p[2] & 63u);
        return 1;
    }
    if (a >= 0xF0u && a <= 0xF4u) {
        if (n < 4 || (p[1] & 0xC0u) != 0x80u || (p[2] & 0xC0u) != 0x80u || (p[3] & 0xC0u) != 0x80u ||
            (a == 0xF0u && p[1] < 0x90u) || (a == 0xF4u && p[1] >= 0x90u)) return 0;
        *used = 4;
        *cp = ((a & 7u) << 18) | ((uint32_t)(p[1] & 63u) << 12) | ((uint32_t)(p[2] & 63u) << 6) | (p[3] & 63u);
        return 1;
    }
    return 0;
}

static int lookup(uint32_t cp, glyph *g)
{
    const nimo_font *font = NIMO_TEXT_FONT;
    nimo_glyph_dsc d;
    d.format = 0;
    d.gid = 0;
    if (!nimo_font_glyph(font, &d, cp, 0)) return 0;
    if ((d.format != 1u && d.format != 2u && d.format != 4u) || d.adv_w > 64u || d.box_w > 64u || d.box_h > 64u)
        return 0;
    g->adv = d.adv_w;
    g->w = d.box_w;
    g->h = d.box_h;
    g->ox = d.ofs_x;
    g->oy = d.ofs_y;
    g->bpp = d.format;
    g->bits = 0;
    if (d.box_w == 0 || d.box_h == 0) return 1;
    if (d.gid == 0) return 0;
    g->bits = font->dsc->glyph_bitmap + (font->dsc->glyph_dsc[d.gid].index_adv & 0xFFFFFu);
    return 1;
}

/* One box per string. A full list means "the whole raster" to every caller,
 * so the last free slot grows instead of filling the list. */
static void dirty_add(mm_scene_dirty *dirty, const int32_t *box)
{
    if (dirty == 0 || box[0] >= box[2] || dirty->n >= MM_SCENE_RECT_MAX) return;
    int32_t l = box[0], t = box[1], r = box[2], b = box[3];
    if (dirty->n + 1u < MM_SCENE_RECT_MAX || dirty->n == 0) {
        dirty->r[dirty->n++] = (mm_scene_rect){ (uint16_t)l, (uint16_t)t, (uint16_t)(r - l), (uint16_t)(b - t) };
        return;
    }
    mm_scene_rect *p = &dirty->r[dirty->n - 1u];
    int32_t pr = (int32_t)p->l + p->w, pb = (int32_t)p->t + p->h;
    if (p->l < l) l = p->l;
    if (p->t < t) t = p->t;
    if (pr > r) r = pr;
    if (pb > b) b = pb;
    *p = (mm_scene_rect){ (uint16_t)l, (uint16_t)t, (uint16_t)(r - l), (uint16_t)(b - t) };
}

static void draw(const mm_raster *target, const glyph *g, int32_t gx, int32_t gy, uint32_t options, int32_t *box)
{
    int32_t l = gx < 0 ? 0 : gx, t = gy < 0 ? 0 : gy, r = gx + g->w, b = gy + g->h;
    if (r > (int32_t)target->width) r = (int32_t)target->width;
    if (b > (int32_t)target->height) b = (int32_t)target->height;
    if (l >= r || t >= b) return;
    uint32_t mask = (1u << g->bpp) - 1u, level = options & 15u;
    for (int32_t py = t; py < b; py++) {
        uint8_t *row = target->pixels + (size_t)py * target->stride;
        uint32_t bit = ((uint32_t)(py - gy) * (uint32_t)g->w + (uint32_t)(l - gx)) * g->bpp;
        for (int32_t px = l; px < r; px++, bit += g->bpp) {
            uint32_t v = ((uint32_t)g->bits[bit >> 3] >> (8u - g->bpp - (bit & 7u))) & mask;
            v = v * 15u / mask;
            if (v == 0 && (options & 16u)) continue;
            if (options & 32u) v = 15u - v;
            v = v * level / 15u;
            uint8_t *p = row + ((uint32_t)px >> 1);
            *p = (px & 1) ? (uint8_t)((*p & 0xF0u) | v) : (uint8_t)((*p & 0x0Fu) | (v << 4));
        }
    }
    if (box[0] >= box[2]) {
        box[0] = l;
        box[1] = t;
        box[2] = r;
        box[3] = b;
        return;
    }
    if (l < box[0]) box[0] = l;
    if (t < box[1]) box[1] = t;
    if (r > box[2]) box[2] = r;
    if (b > box[3]) box[3] = b;
}

int nimo_builtin_text(void *user, const mm_raster *target, const uint8_t *src, size_t len, mm_scene_dirty *dirty)
{
    (void)user;
    if (target == 0 || src == 0 || mm_raster_validate(target) != MM_GEOMETRY_OK || len < 6 || len != 6u + src[5] ||
        (dirty != 0 && dirty->n > MM_SCENE_RECT_MAX) || overlap(target->pixels, target->bytes, src, len) ||
        (dirty != 0 && overlap(target->pixels, target->bytes, dirty, sizeof *dirty)))
        return -1;
    const nimo_font *font = NIMO_TEXT_FONT;
    int32_t line = font->line_height, base = font->base_line;
    if (line <= 0 || line > 64 || base < 0 || base >= line) return -1;
    const uint8_t *text = src + 6;
    size_t n = src[5], used;
    uint32_t cp;
    glyph g;
    for (size_t pos = 0; pos < n; pos += used)
        if (!next(text + pos, n - pos, &used, &cp) || (cp >= 32u && !lookup(cp, &g))) return -1;
    int32_t x = s16(src), y = s16(src + 2), box[4] = { 0, 0, 0, 0 };
    for (size_t pos = 0; pos < n; pos += used) {
        (void)next(text + pos, n - pos, &used, &cp);
        if (cp < 32u) {
            x += (int32_t)cp - 11;
            continue;
        }
        (void)lookup(cp, &g);
        if (g.bits != 0) draw(target, &g, x + g.ox, y + line - base - g.oy - g.h, src[4], box);
        x += g.adv;
    }
    dirty_add(dirty, box);
    return 0;
}
