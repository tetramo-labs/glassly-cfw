#ifndef MM_FLASH_BROKER_H
#define MM_FLASH_BROKER_H
#include "flash_store.h"
/* Boot-owned I/O worker. The serialized display task owns COW maps and scene;
 * it synchronously lends a buffer until the completion queue returns. Worker
 * never touches LVGL, scene state, font caches or the active raster. */
int glassly_flash_broker_bind(mm_flash_callbacks *,uint8_t unavailable[32]);
void glassly_flash_broker_worker(void *);
void glassly_flash_broker_entry(void *);
#endif
