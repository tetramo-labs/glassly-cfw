#ifndef MM_WAKE_CONTROL_H
#define MM_WAKE_CONTROL_H
#include "graphics.h"
void glassly_wake_command(uint32_t,void *,const uint8_t *,void **);
void glassly_wake_display(const void *);
void glassly_wake_observe(uint16_t);
void glassly_wake_cleanup(void *);
int glassly_wake_frame_active(void *);
void glassly_wake_presented(void *);
void glassly_graphics_drop_frame(void *);
void glassly_wake_native_on(void);
int glassly_wake_native_on_state(void);
int glassly_wake_native_blocked(void);
void glassly_wake_send(uint8_t,void *);
#endif
