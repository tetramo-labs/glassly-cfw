/* Derived from pinned G2 commite889569fe77775ed5822af6f7e47210f2984f15d.
 * Explicit MemoMind platform adaptation; MIT, see PROVENANCE.md. */
/* Which parameters are x / y coordinates, per type (used for clamping and for
 * glides, which translate exactly these). PATH: p0/p1 translate the asset. */
static const uint8_t cfw_shape_xmask_tab[CFW_SHAPE_TYPE_MAX + 1] = {
    0x00, 0x05, 0x01, 0x01, 0x01, 0x01, 0x15, 0x15, 0x55, 0x55,
    0x15, 0x55, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
};
static const uint8_t cfw_shape_ymask_tab[CFW_SHAPE_TYPE_MAX + 1] = {
    0x00, 0x0a, 0x02, 0x02, 0x02, 0x02, 0x2a, 0x2a, 0xaa, 0xaa,
    0x2a, 0xaa, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02,
};

/* Parameters a TWEEN may target (bits 0-7 = p0..p7, 0x100 color, 0x200 width).
 * Asset-bearing records may only move (and fade for inline text); an asset id
 * is an identity, never an animation target. */
static uint32_t cfw_shape_tween_mask(uint8_t type) {
    switch (type) {
    case CFW_SHAPE_LINE:        return 0x30fu;
    case CFW_SHAPE_RECT: case CFW_SHAPE_RECT_FILL:
    case CFW_SHAPE_ARC:  case CFW_SHAPE_PIE:         return 0x31fu;
    case CFW_SHAPE_CIRCLE: case CFW_SHAPE_CIRCLE_FILL: return 0x307u;
    case CFW_SHAPE_TRI: case CFW_SHAPE_TRI_FILL: case CFW_SHAPE_BEZIER2: return 0x33fu;
    case CFW_SHAPE_QUAD: case CFW_SHAPE_QUAD_FILL: case CFW_SHAPE_BEZIER3: return 0x3ffu;
    case CFW_SHAPE_IMAGE: case CFW_SHAPE_TEXT: case CFW_SHAPE_TEXT_CACHED: return 0x103u;
    case CFW_SHAPE_TEXT_INLINE: return 0x10fu;
    case CFW_SHAPE_PATH:        return 0x107u;   /* x, y, Q8 scale, color */
    default:                    return 0;
    }
}

/* Byte length of the record at `rec`, or 0 when it is truncated or malformed. */
static uint32_t cfw_shape_record_len(const uint8_t *rec, uint32_t avail) {
    if (avail < 1u) return 0;
    uint32_t type = rec[0];
    if (type == CFW_SHAPE_NONE || type > CFW_SHAPE_TYPE_MAX) return 0;
    if (type <= CFW_SHAPE_PIE) return avail >= CFW_SHAPE_RECORD_BYTES ? CFW_SHAPE_RECORD_BYTES : 0;
    if (type == CFW_SHAPE_IMAGE || type == CFW_SHAPE_TEXT)
        return avail >= CFW_SHAPE_ASSET_BYTES ? CFW_SHAPE_ASSET_BYTES : 0;
    if (type == CFW_SHAPE_TEXT_CACHED)
        return avail >= CFW_SHAPE_FONT_BYTES ? CFW_SHAPE_FONT_BYTES : 0;
    if (type == CFW_SHAPE_TEXT_INLINE) {
        if (avail < CFW_SHAPE_INLINE_HDR) return 0;
        uint32_t len = rec[CFW_SHAPE_INLINE_HDR - 1u];
        if (len == 0 || len > CFW_SHAPE_INLINE_MAX || CFW_SHAPE_INLINE_HDR + len > avail) return 0;
        return CFW_SHAPE_INLINE_HDR + len;
    }
    /* PATH */
    if (avail < CFW_SHAPE_PATH_HDR) return 0;
    uint32_t len = rd16(rec + 10);
    if (len == 0 || len > CFW_PATH_MAX_BYTES || CFW_SHAPE_PATH_HDR + len > avail) return 0;
    return CFW_SHAPE_PATH_HDR + len;
}

static void cfw_shape_masks(uint8_t type, uint8_t *xmask, uint8_t *ymask) {
    if (type > CFW_SHAPE_TYPE_MAX) type = 0;
    *xmask = cfw_shape_xmask_tab[type];
    *ymask = cfw_shape_ymask_tab[type];
}

/* Decode a record whose length cfw_shape_record_len already accepted. */
static void cfw_shape_decode(const uint8_t *rec, cfw_shape *out) {
    out->type = rec[0];
    out->flags = rec[1];
    out->color = rec[2];
    out->width = rec[3];
    out->text = 0;
    out->asset_id = out->font_id = 0;
    out->asset = out->font = 0;
    out->asset_len = out->font_len = 0;
#ifdef MM_SCENE_EXTERNAL_STORE
    out->asset_region=(mm_scene_bytes){0};out->font_region=(mm_scene_bytes){0};
#endif
    for (uint32_t i = 0; i < CFW_SHAPE_PARAMS; i++) out->p[i] = 0;
    switch (rec[0]) {
    case CFW_SHAPE_TEXT_INLINE:
        for (uint32_t i = 0; i < 4u; i++) out->p[i] = (int16_t)rd16(rec + 4 + 2 * i);
        out->p[4] = (int16_t)rec[CFW_SHAPE_INLINE_HDR - 1u];
        out->text = rec + CFW_SHAPE_INLINE_HDR;
        return;
    case CFW_SHAPE_IMAGE:
    case CFW_SHAPE_TEXT:
    case CFW_SHAPE_TEXT_CACHED:
        out->p[0] = (int16_t)rd16(rec + 4);
        out->p[1] = (int16_t)rd16(rec + 6);
        out->asset_id = rd32(rec + 8);
        if (rec[0] == CFW_SHAPE_TEXT_CACHED) out->font_id = rd32(rec + 12);
        return;
    case CFW_SHAPE_PATH:
        out->p[0] = (int16_t)rd16(rec + 4);
        out->p[1] = (int16_t)rd16(rec + 6);
        out->p[2] = (int16_t)rd16(rec + 8);        /* Q8 scale, 0..2048 */
        out->p[3] = (int16_t)rd16(rec + 10);       /* command bytes */
        out->text = rec + CFW_SHAPE_PATH_HDR;
        return;
    default:
        for (uint32_t i = 0; i < CFW_SHAPE_PARAMS; i++)
            out->p[i] = (int16_t)rd16(rec + 4 + 2 * i);
        return;
    }
}

static int cfw_shape_valid(const cfw_shape *s, int allow_path) {
    if (s->type == CFW_SHAPE_NONE || s->type > CFW_SHAPE_TYPE_MAX) return 0;
    if (s->type == CFW_SHAPE_TEXT_INLINE)
        return s->text != 0 && s->p[4] > 0 && (uint16_t)s->p[4] <= CFW_SHAPE_INLINE_MAX &&
               cfw_texture_string_valid(s->text, (uint16_t)s->p[4]);
    if (s->type == CFW_SHAPE_PATH)
        return allow_path && s->text != 0 && s->width <= 1u && s->p[3] > 0 &&
               (uint16_t)s->p[2] <= 2048u && (uint16_t)s->p[3] <= CFW_PATH_MAX_BYTES;
    if (s->type == CFW_SHAPE_IMAGE || s->type == CFW_SHAPE_TEXT)
        return s->asset_id != 0;
    if (s->type == CFW_SHAPE_TEXT_CACHED)
        return s->asset_id != 0 && s->font_id != 0;
    return 1;
}

