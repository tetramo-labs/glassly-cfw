/* Test-only original G2 host adapter. Source revision/hashes checked by runner.
 * Includes the pinned upstream host stubs, never firmware entry points. */
#define main g2_unused_host_suite_main
#include G2_REFERENCE_SOURCE
#undef main
#include "../geometry.h"

int g2_geometry_reference(const mm_raster *target, const uint8_t *data, size_t length) {
    if (length < 2 || data[0] != 36) return -1;
    return cfw_shapes_immediate(target->pixels, target->stride, target->width,
                               target->height, data + 1, (uint32_t)length - 1, 0);
}
