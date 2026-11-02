/* Derived from pinned G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce.
 * Explicit MemoMind platform adaptation; MIT, see PROVENANCE.md. */
#define CFW_TEXTURE_OPT_TRANSPARENT 0x10u
#define CFW_TEXTURE_OPT_INVERSE 0x20u
/* Decode one RLE token without reading beyond `len`. Return its byte length and
 * pixel count, rejecting zero counts and truncated escape forms. */
static int cfw_texture_rle_token(const uint8_t *p, uint32_t len,
                                 uint32_t *used, uint32_t *count,
                                 uint8_t *color) {
    if (len < 1) return 0;
    uint8_t op = p[0];
    *color = (uint8_t)(op & 0x0fu);
    uint32_t n = op >> 4;
    if (n) {
        *used = 1;
        *count = n;
        return 1;
    }
    if (len < 2) return 0;
    n = p[1];
    if (n) {
        *used = 2;
        *count = n;
        return 1;
    }
    if (len < 4) return 0;
    n = (uint32_t)p[2] | ((uint32_t)p[3] << 8);
    if (n == 0) return 0;
    *used = 4;
    *count = n;
    return 1;
}

/* Validate one complete cached image at `offset` inside [base, base+size) and
 * determine exactly how many RLE bytes it occupies. This pass happens before
 * drawing so malformed contents cannot leave a partially modified shadow. */
static int cfw_texture_image_in(const uint8_t *base, uint32_t size, uint32_t offset,
                                cfw_cached_image *out) {
    if (base == 0 || size < 3u || offset > size - 3u) return 0;

    const uint8_t *image = base + offset;
    uint32_t width = image[0];
    uint32_t height = image[1];
    if (width == 0 || height == 0) return 0;

    const uint8_t *p = image + 2;
    uint32_t available = size - offset - 2u;
    uint32_t pos = 0;
    uint32_t left = width * height;
    while (left) {
        uint32_t used, count;
        uint8_t color;
        if (!cfw_texture_rle_token(p + pos, available - pos,
                                   &used, &count, &color) || count > left)
            return 0;
        (void)color;
        pos += used;
        left -= count;
    }

    out->rle = p;
    out->rle_len = pos;
    out->width = width;
    out->height = height;
    return 1;
}

/* Build the 4-bit color LUT. `top` 15 is the identity ramp; smaller values
 * scale the 0..15 source range proportionally into 0..top. Inverse reverses
 * the completed ramp. */
static void cfw_texture_make_lut(uint8_t options, uint8_t *lut) {
    uint32_t top = options & 0x0fu;
    for (uint32_t i = 0; i < 16u; i++) {
        uint32_t source = (options & CFW_TEXTURE_OPT_INVERSE) ? 15u - i : i;
        lut[i] = (uint8_t)((source * top) / 15u);
    }
}

/* Render a previously validated image, clipping signed coordinates to the
 * physical packed-4bpp shadow. Transparency tests the original source value,
 * before the LUT, so source color 0 is skipped even for an inverse ramp. */
static void cfw_texture_render(uint8_t *shadow, uint32_t stride,
                               uint32_t panel_w, uint32_t panel_h,
                               int32_t x0, int32_t y0,
                               const cfw_cached_image *image,
                               const uint8_t *lut, int transparent) {
    uint32_t pos = 0;
    uint32_t pixel = 0;
    while (pos < image->rle_len) {
        uint32_t used, count;
        uint8_t color;
        /* The validation pass guarantees success here. */
        if (!cfw_texture_rle_token(image->rle + pos,
                                   image->rle_len - pos,
                                   &used, &count, &color))
            return;
        pos += used;
        int skip = transparent && color == 0;
        uint8_t mapped = lut[color];
        for (uint32_t i = 0; i < count; i++, pixel++) {
            int32_t x = x0 + (int32_t)(pixel % image->width);
            int32_t y = y0 + (int32_t)(pixel / image->width);
            if (!skip && x >= 0 && y >= 0 &&
                (uint32_t)x < panel_w && (uint32_t)y < panel_h) {
                uint8_t *b = shadow + (uint32_t)y * stride + ((uint32_t)x >> 1);
                if (x & 1) *b = (uint8_t)((*b & 0xf0u) | mapped);
                else       *b = (uint8_t)((*b & 0x0fu) | (uint8_t)(mapped << 4));
            }
        }
    }
}

/* Render stock LVGL's raw A4-aligned glyph data (high nibble first, each row
 * byte-aligned). Unlike cached RLE images, glyph boxes can have signed offsets. */
static void cfw_texture_render_a4(uint8_t *shadow, uint32_t stride,
                                  uint32_t panel_w, uint32_t panel_h,
                                  int32_t x0, int32_t y0,
                                  const uint8_t *bitmap,
                                  uint32_t width, uint32_t height,
                                  const uint8_t *lut, int transparent) {
    /* Even's LV_FONT_FMT_PLAIN_ALIGNED encoder advances to a fresh byte after
     * every row even when an even-width row already ended on a byte boundary.
     * Thus every row occupies floor(width/2)+1 bytes, including a whole pad
     * byte for even widths. This is verified by every embedded 20/22 px font
     * and the external Source Han Sans font partition. */
    uint32_t row_stride = (width >> 1) + 1u;
    for (uint32_t sy = 0; sy < height; sy++) {
        int32_t y = y0 + (int32_t)sy;
        if (y < 0 || (uint32_t)y >= panel_h) continue;
        const uint8_t *row = bitmap + sy * row_stride;
        for (uint32_t sx = 0; sx < width; sx++) {
            int32_t x = x0 + (int32_t)sx;
            uint8_t packed = row[sx >> 1];
            uint8_t color = (sx & 1u) ? (packed & 0x0fu) : (packed >> 4);
            if ((transparent && color == 0) || x < 0 || (uint32_t)x >= panel_w)
                continue;
            uint8_t mapped = lut[color];
            uint8_t *dst = shadow + (uint32_t)y * stride + ((uint32_t)x >> 1);
            if (x & 1) *dst = (uint8_t)((*dst & 0xf0u) | mapped);
            else       *dst = (uint8_t)((*dst & 0x0fu) | (uint8_t)(mapped << 4));
        }
    }
}

static void cfw_texture_add_rect(cfw_rectlist *rl, int32_t x, int32_t y,
                                 uint32_t width, uint32_t height,
                                 uint32_t panel_w, uint32_t panel_h) {
    int32_t right = x + (int32_t)width;
    int32_t bottom = y + (int32_t)height;
    int32_t left = x < 0 ? 0 : x;
    int32_t top = y < 0 ? 0 : y;
    if (right > (int32_t)panel_w) right = (int32_t)panel_w;
    if (bottom > (int32_t)panel_h) bottom = (int32_t)panel_h;
    if (left < right && top < bottom)
        rl_add(rl, (uint32_t)left, (uint32_t)top,
               (uint32_t)(right - left), (uint32_t)(bottom - top));
}

/* Draw the image asset that starts at `data` (`size` bytes long). */
static int cfw_texture_draw_image_region(uint8_t *shadow, uint32_t stride,
                                         uint32_t panel_w, uint32_t panel_h,
                                         const uint8_t *data, uint32_t size,
                                         int32_t x, int32_t y, uint8_t options,
                                         cfw_rectlist *rl) {
    if (shadow == 0) return -1;
    cfw_cached_image image;
    if (!cfw_texture_image_in(data, size, 0, &image)) return -1;
    uint8_t lut[16];
    cfw_texture_make_lut(options, lut);
    cfw_texture_render(shadow, stride, panel_w, panel_h, x, y, &image,
                       lut, (options & CFW_TEXTURE_OPT_TRANSPARENT) != 0);
    cfw_texture_add_rect(rl, x, y, image.width, image.height, panel_w, panel_h);
    return 0;
}

/* A font asset is a 96-entry table of uint32 image offsets (characters
 * 32..127), each relative to the start of the asset, followed by the glyph
 * images. A zero entry means the glyph is absent. Every non-zero entry must
 * address a complete image inside the asset. */
static int cfw_texture_font_valid(const uint8_t *font, uint32_t size) {
    if (font == 0 || size < CFW_FONT_TABLE_BYTES) return 0;
    for (uint32_t i = 0; i < CFW_FONT_TABLE_CHARS; i++) {
        uint32_t off = rd32(font + i * 4u);
        if (off == 0) continue;
        cfw_cached_image image;
        if (off < CFW_FONT_TABLE_BYTES || !cfw_texture_image_in(font, size, off, &image)) return 0;
    }
    return 1;
}

/* Draw `string` with the font asset at `font`. Bytes 1..31 adjust x by -10..20;
 * byte 0, bytes above 127 and absent glyphs are invalid and nothing is drawn. */
static int cfw_texture_draw_string_region(uint8_t *shadow, uint32_t stride,
                                          uint32_t panel_w, uint32_t panel_h,
                                          const uint8_t *font, uint32_t font_size,
                                          int32_t x, int32_t y, uint8_t options,
                                          const uint8_t *string, uint32_t string_len,
                                          cfw_rectlist *rl) {
    if (shadow == 0 || string == 0 || font == 0) return -1;
    if (font_size < CFW_FONT_TABLE_BYTES) return -1;

    /* Validate every character/table entry/RLE stream before drawing any glyph. */
    uint8_t lut[16];
    cfw_texture_make_lut(options, lut);
    int transparent = (options & CFW_TEXTURE_OPT_TRANSPARENT) != 0;
    for (uint32_t i = 0; i < string_len; i++) {
        uint32_t ch = string[i];
        if (ch >= 1u && ch <= 31u) continue;
        if (ch < 32u || ch > 127u) return -1;
        uint32_t image_offset = rd32(font + (ch - 32u) * 4u);
        cfw_cached_image image;
        if (image_offset == 0 || !cfw_texture_image_in(font, font_size, image_offset, &image)) return -1;
    }

    for (uint32_t i = 0; i < string_len; i++) {
        uint32_t ch = string[i];
        if (ch <= 31u) {
            x += (int32_t)ch - 11;
            continue;
        }
        uint32_t image_offset = rd32(font + (ch - 32u) * 4u);
        cfw_cached_image image;
        /* Already validated above; the store cannot change inside this handler. */
        if (!cfw_texture_image_in(font, font_size, image_offset, &image)) return -1;
        cfw_texture_render(shadow, stride, panel_w, panel_h, x, y, &image,
                           lut, transparent);
        cfw_texture_add_rect(rl, x, y, image.width, image.height, panel_w, panel_h);
        x += (int32_t)image.width;
    }
    return 0;
}

/* Decode one strict UTF-8 scalar. Control bytes 1..31 are deliberately handled
 * by the caller before this function; NUL, malformed/overlong encodings,
 * surrogates, and values above U+10FFFF are rejected. */
static int cfw_texture_utf8(const uint8_t *src, uint32_t len,
                            uint32_t *used, uint32_t *codepoint) {
    if (len == 0) return 0;
    uint32_t a = src[0];
    if (a >= 0x20u && a <= 0x7fu) {
        *used = 1;
        *codepoint = a;
        return 1;
    }
    if (a >= 0xc2u && a <= 0xdfu) {
        if (len < 2u || (src[1] & 0xc0u) != 0x80u) return 0;
        *used = 2;
        *codepoint = ((a & 0x1fu) << 6) | (src[1] & 0x3fu);
        return 1;
    }
    if (a >= 0xe0u && a <= 0xefu) {
        if (len < 3u || (src[1] & 0xc0u) != 0x80u ||
            (src[2] & 0xc0u) != 0x80u ||
            (a == 0xe0u && src[1] < 0xa0u) ||
            (a == 0xedu && src[1] >= 0xa0u)) return 0;
        *used = 3;
        *codepoint = ((a & 0x0fu) << 12) |
                     ((uint32_t)(src[1] & 0x3fu) << 6) |
                     (src[2] & 0x3fu);
        return 1;
    }
    if (a >= 0xf0u && a <= 0xf4u) {
        if (len < 4u || (src[1] & 0xc0u) != 0x80u ||
            (src[2] & 0xc0u) != 0x80u || (src[3] & 0xc0u) != 0x80u ||
            (a == 0xf0u && src[1] < 0x90u) ||
            (a == 0xf4u && src[1] >= 0x90u)) return 0;
        *used = 4;
        *codepoint = ((a & 7u) << 18) |
                     ((uint32_t)(src[1] & 0x3fu) << 12) |
                     ((uint32_t)(src[2] & 0x3fu) << 6) |
                     (src[3] & 0x3fu);
        return 1;
    }
    return 0;
}

/* A string asset (or inline text) holds 1..CFW_SHAPE_INLINE_MAX bytes: strict
 * UTF-8 with the mode-15/20 control bytes 1..31 allowed and NUL rejected. */
static int cfw_texture_string_valid(const uint8_t *s, uint32_t len) {
    if (s == 0 || len == 0 || len > 128u) return 0;
    uint32_t pos = 0;
    while (pos < len) {
        uint32_t b = s[pos];
        if (b >= 1u && b <= 31u) { pos++; continue; }
        uint32_t used, cp;
        if (!cfw_texture_utf8(s + pos, len - pos, &used, &cp)) return 0;
        pos += used;
    }
    return 1;
}

