/* Extracted unchanged from pinned G2 scene.c; MIT, see LICENSE. */
#include <stdint.h>
static uint32_t cfw_ease_byte_q15(uint8_t b) {
    return ((uint32_t)b * 32768u + 127u) / 255u;
}

/* One axis of a cubic bezier with P0 = 0 and P3 = 1: 3(1-t)^2 t p1 + 3(1-t) t^2 p2 + t^3. */
static uint32_t cfw_ease_axis(uint32_t t, uint32_t p1, uint32_t p2) {
    uint32_t mt = 32768u - t;
    uint64_t a = ((uint64_t)3u * mt * mt) >> 15;
    a = (a * t) >> 15;
    uint64_t b = ((uint64_t)3u * mt * t) >> 15;
    b = (b * t) >> 15;
    uint64_t c = ((uint64_t)t * t) >> 15;
    c = (c * t) >> 15;
    return (uint32_t)((a * p1 + b * p2 + (c << 15)) >> 15);
}

/* Progress (Q15) at normalized time u (Q15) along the curve: solve x(t) = u by
 * bisection, then evaluate y(t). */
static uint32_t cfw_ease_progress(uint32_t u, const uint8_t *curve) {
    if (u == 0) return 0;
    if (u >= 32768u) return 32768u;
    uint32_t x1 = cfw_ease_byte_q15(curve[0]), y1 = cfw_ease_byte_q15(curve[1]);
    uint32_t x2 = cfw_ease_byte_q15(curve[2]), y2 = cfw_ease_byte_q15(curve[3]);
    uint32_t lo = 0, hi = 32768u;
    for (uint32_t i = 0; i < 14; i++) {
        uint32_t mid = (lo + hi) >> 1;
        if (cfw_ease_axis(mid, x1, x2) < u) lo = mid; else hi = mid;
    }
    uint32_t y = cfw_ease_axis((lo + hi) >> 1, y1, y2);
    return y > 32768u ? 32768u : y;
}

