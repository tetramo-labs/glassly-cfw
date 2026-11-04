/* MIT. Passive native acquisition snapshots; no sensor power ownership. */
#ifndef MM_SENSOR_CAPTURE_H
#define MM_SENSOR_CAPTURE_H
#include "graphics.h"
uint32_t glassly_sensor_begin(uint32_t mask);
void glassly_sensor_finish(uint32_t mask,uint32_t generation,const uint8_t *sample);
void glassly_sensor_cleanup(void);
void glassly_sensor_watch(const uint8_t *,uint32_t);
void glassly_sensor_command(uint32_t,void *,const uint8_t *,void **);
#endif
