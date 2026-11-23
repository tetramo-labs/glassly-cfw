#ifndef MEMOMIND_INPUT_H
#define MEMOMIND_INPUT_H
#include "graphics.h"
#define MM_INPUT_CAPACITY 32u
#define MM_INPUT_LEASE_TICKS 30000u
#define MM_INPUT_REPLY_BYTES 2048u
void glassly_input_command(uint32_t,void *,const uint8_t *,void **);
void glassly_input_display(const void *envelope);
void glassly_input_observe(const void *envelope);
/* Independent native helpers keep the existing platform table ABI unchanged. */
void glassly_input_hide(void *image);
void glassly_input_send(uint8_t event,void *response);
#ifdef MM_DIAGNOSTIC_COMMANDS
void glassly_input_cleanup(void *parent);
#endif
#endif
