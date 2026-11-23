/* MIT. zlib's own source and notices are retained under ../vendor/zlib. */
#include "inflater.h"
#include "../vendor/zlib/zlib.h"
typedef struct {
    z_stream stream;
    mm_inflater_allocator allocator;
    int failed;
} decoder;
static voidpf allocate(voidpf p,uInt count,uInt bytes){
    decoder *d=p;
    if(!bytes || (size_t)count>SIZE_MAX/bytes)return 0;
    return d->allocator.allocate(d->allocator.user,(size_t)count*bytes);
}
static void release(voidpf p,voidpf bytes){
    decoder *d=p;
    if(bytes)d->allocator.release(d->allocator.user,bytes);
}
void mm_inflater_end(void **state){
    if(!state || !*state)return;
    decoder *d=*state;
    *state=0;
    inflateEnd(&d->stream);
    d->allocator.release(d->allocator.user,d);
}
int mm_inflater_decode(const mm_inflater_allocator *a,void **state,
                       const uint8_t *input,uint16_t bytes,uint8_t *output,
                       uint32_t capacity,uint32_t *produced){
    if(!produced)return -1;
    *produced=0;
    if(!a || !a->allocate || !a->release || !state || !input || !bytes ||
       !output || !capacity)return -1;
    decoder *d=*state;
    if(d && (d->failed || d->allocator.user!=a->user ||
       d->allocator.allocate!=a->allocate || d->allocator.release!=a->release))return -1;
    if(!d){
        d=a->allocate(a->user,sizeof(*d));if(!d)return -1;
        for(size_t i=0;i<sizeof(*d);i++)((uint8_t *)d)[i]=0;
        d->allocator=*a;
        d->stream.zalloc=allocate;d->stream.zfree=release;d->stream.opaque=d;
        if(inflateInit2(&d->stream,15)!=Z_OK){a->release(a->user,d);return -1;}
        *state=d;
    }
    z_stream *z=&d->stream;
    z->next_in=(Bytef *)(uintptr_t)input;z->avail_in=bytes;
    z->next_out=output;z->avail_out=capacity;
    while(z->avail_in){
        uInt before=z->avail_in,space=z->avail_out;
        if(inflate(z,Z_NO_FLUSH)!=Z_OK || !z->avail_out ||
           (before==z->avail_in && space==z->avail_out)){d->failed=1;break;}
    }
    *produced=capacity-z->avail_out;
    z->next_in=0;z->next_out=0;z->avail_in=0;z->avail_out=0;
    return d->failed?-1:0;
}
