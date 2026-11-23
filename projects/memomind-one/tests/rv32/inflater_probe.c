#include "inflater.h"
extern void *probe_allocate(void *,size_t);
extern void probe_release(void *,void *);
int probe_decode(void **state,const uint8_t *input,uint16_t length,uint8_t *output,
                 uint32_t capacity,uint32_t *produced){
    mm_inflater_allocator a={0,probe_allocate,probe_release};
    return mm_inflater_decode(&a,state,input,length,output,capacity,produced);
}
