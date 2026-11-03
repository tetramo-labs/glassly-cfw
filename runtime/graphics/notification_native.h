#ifndef MM_NOTIFICATION_NATIVE_H
#define MM_NOTIFICATION_NATIVE_H
#include "graphics.h"
void glassly_notification_command(uint32_t,void *,const uint8_t *,void **);
void glassly_notification_observe(uint32_t,const uint8_t *,uint32_t);
void glassly_notification_cleanup(void);
void glassly_notification_entry(void);
#endif
