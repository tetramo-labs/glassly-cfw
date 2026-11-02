#ifndef MM_GRAPHICS_DIAGNOSTICS_H
#define MM_GRAPHICS_DIAGNOSTICS_H
#include "graphics.h"
/* Serialized display-task, current-screen metadata/overlay. Never source pixels. */
void *mm_diagnostics_control(void *parent,unsigned sub);
void mm_diagnostics_frame(void *parent,const uint8_t *,size_t);
void mm_diagnostics_present(void *parent,void *graphics_image);
void mm_diagnostics_failure(void *parent,unsigned mode,int allocation);
void mm_diagnostics_dispose(void *parent);
void mm_diagnostics_cleanup(void *parent,uint16_t epoch);
uint16_t mm_diagnostics_epoch(void *parent);
void glassly_diagnostics_source(void *,const mm_native_image *);
void glassly_diagnostics_hidden(void *,int);
#endif
