#include "scene_store.h"
static int span(const void *p,size_t n){return p&&n<=UINTPTR_MAX-(uintptr_t)p;}
static int overlap(const void *a,size_t n,const void *b,size_t m){uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return n&&m&&(x<=y?y-x<n:x-y<m);}
static int valid(const mm_scene_bytes *b){
    if(!span(b,sizeof(*b)))return 0;
    if(b->store)return !b->ram&&span(b->store,sizeof(*b->store))&&b->store->read&&b->store->aliases&&
        b->offset<=b->store->capacity&&b->length<=b->store->capacity-b->offset;
    return !b->offset&&(!b->length||span(b->ram,b->length));
}
static int data_alias(const mm_scene_bytes *b,const void *p,size_t n){
    if(b->store)return overlap(p,n,b->store,sizeof(*b->store))||b->store->aliases(b->store->user,p,n);
    return overlap(p,n,b->ram,b->length);
}
int mm_scene_bytes_read(const mm_scene_bytes *b,uint32_t off,void *out,size_t n) {
    if(!valid(b)||off>b->length||n>b->length-off)return -1;
    if(!n)return 0;
    if(!span(out,n)||overlap(out,n,b,sizeof(*b))||data_alias(b,out,n))return -1;
    if(b->store)return b->store->read(b->store->user,b->offset+off,out,n)?-2:0;
    uint8_t *d=out;for(size_t i=0;i<n;i++)d[i]=b->ram[off+i];return 0;
}
int mm_scene_bytes_sub(const mm_scene_bytes *b,uint32_t off,uint32_t n,mm_scene_bytes *out) {
    if(!valid(b)||!span(out,sizeof(*out))||off>b->length||n>b->length-off||
       (out!=b&&overlap(out,sizeof(*out),b,sizeof(*b)))||data_alias(b,out,sizeof(*out)))return -1;
    mm_scene_bytes result=*b;result.length=n;
    if(b->store)result.offset+=off; /* valid() bounded offset+length first. */
    else if(b->ram)result.ram+=off;
    *out=result;return 0;
}
int mm_scene_cursor_init(mm_scene_cursor *c,const mm_scene_bytes *b){
    if(!valid(b)||!span(c,sizeof(*c))||data_alias(b,c,sizeof(*c)))return -1;
    mm_scene_bytes saved=*b;c->bytes=saved;c->start=c->used=0;return 0;
}
int mm_scene_cursor_read(mm_scene_cursor *c,uint32_t off,void *dst,size_t n) {
    if(!span(c,sizeof(*c))||!valid(&c->bytes)||c->used>256||c->start>c->bytes.length||
       c->used>c->bytes.length-c->start||off>c->bytes.length||n>c->bytes.length-off)return -1;
    if(!n)return 0;
    if(!span(dst,n)||overlap(dst,n,c,sizeof(*c))||data_alias(&c->bytes,dst,n))return -1;
    uint8_t *out=dst;
    while(n){
        if(off<c->start||off-c->start>=c->used){
            c->start=off;c->used=c->bytes.length-off;if(c->used>256)c->used=256;
            int rc=mm_scene_bytes_read(&c->bytes,off,c->data,c->used);if(rc){c->used=0;return rc;}
        }
        size_t take=c->used-(off-c->start);if(take>n)take=n;
        for(size_t i=0;i<take;i++)out[i]=c->data[off-c->start+i];
        out+=take;off+=(uint32_t)take;n-=take;
    }
    return 0;
}
