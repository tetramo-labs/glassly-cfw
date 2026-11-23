#ifndef MM_GRAPHICS_FLASH_READ_H
#define MM_GRAPHICS_FLASH_READ_H
#include "graphics.h"
#if defined(MM_FULL_STORE_READ) && !defined(MM_STORAGE_DIAGNOSTICS)
#error "Full-store reader requires storage diagnostics"
#endif
#define MM_FLASH_READ_COMMAND 0x7bu
#define MM_FLASH_READ_MAX 256u
#define MM_FLASH_READ_ALIGNMENT 256u
#define MM_FLASH_READ_WORKSPACE 1024u
#define MM_FLASH_READ_HEADROOM 32768u
/* BT service task only. No display/observer call or platform-table ABI change. */
void glassly_flash_read_command(uint32_t,void *,const uint8_t *,void **);
int glassly_flash_read_native(uint32_t device,uint32_t offset,void *destination,uint32_t length);
#endif
