/* Built-in text for the scene core: mode-15 messages and text shapes drawn in
 * the stock LVGL default face (stock.h NIMO_TEXT_FONT). MIT. */
#ifndef NIMO_TEXT_H
#define NIMO_TEXT_H
#include <stddef.h>
#include <stdint.h>
#include "scene.h"

#define NIMO_TEXT_MAX_BYTES 255u

/* src is [x s16][y s16][options][len][len UTF-8 bytes], the MemoMind/G2
 * built-in text record: y is the top of the font's line, options' low nibble
 * the level a full-ink pixel gets, 0x10 leaves zero pixels untouched, 0x20
 * inverts. Bytes 1..31 move the pen by (byte - 11) px. Kerning is not applied,
 * so a line is as wide as the sum of its glyph advances.
 *
 * The whole string is checked first: malformed UTF-8 or a character the face
 * lacks returns -1 with the pixels and dirty unchanged. Glyphs are clipped to
 * target; the box they cover is added to dirty as one entry (the last
 * entry grows instead of filling the list). No allocation; user is unused. */
int nimo_builtin_text(void *user, const mm_raster *target, const uint8_t *src, size_t len, mm_scene_dirty *dirty);
#endif
