/* Private shared vector helpers; not a device or unvalidated public API. MIT. */
#ifndef MM_GEOMETRY_INTERNAL_H
#define MM_GEOMETRY_INTERNAL_H
#include "geometry.h"
/* Caller has validated target and bounded/clipped coordinates. */
int32_t mm_geometry_private_sin_deg(int32_t angle);
void mm_geometry_private_line_q4(const mm_raster *target, int32_t x0, int32_t y0,
                                int32_t x1, int32_t y1, int32_t width, uint8_t color);
#endif
