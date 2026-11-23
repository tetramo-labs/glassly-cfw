/* MIT. Owned RFC1950 decoder for the G2 record transport. */
#ifndef MM_INFLATER_H
#define MM_INFLATER_H
#include <stddef.h>
#include <stdint.h>
typedef struct {
    void *user;
    void *(*allocate)(void *,size_t);
    void (*release)(void *,void *);
} mm_inflater_allocator;
/* Serialized calls. Allocator identity must stay unchanged until end. Input and
 * output are borrowed, nonoverlapping buffers. A failed context requires end.
 * Capacity includes the transport's overflow sentinel; full output is failure. */
int mm_inflater_decode(const mm_inflater_allocator *,void **state,
                       const uint8_t *,uint16_t,uint8_t *,uint32_t,uint32_t *);
void mm_inflater_end(void **state);
#endif
