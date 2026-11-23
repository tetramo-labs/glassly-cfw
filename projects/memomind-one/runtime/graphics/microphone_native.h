/* MIT. Leased native Opus recording on the stock app task. */
#ifndef MM_MICROPHONE_NATIVE_H
#define MM_MICROPHONE_NATIVE_H
#include "graphics.h"
void glassly_microphone_command(uint32_t,void *,const uint8_t *,void **);
void glassly_microphone_task(uint32_t,const uint8_t *,uint32_t);
void glassly_microphone_cleanup(void);
void glassly_microphone_link(uint32_t,uint32_t,const uint8_t *);
int glassly_microphone_spp(const uint8_t *,const uint8_t *,const uint8_t *,uint32_t);
int glassly_microphone_iap2(const uint8_t *,uint32_t,const uint8_t *,uint32_t);
#endif
