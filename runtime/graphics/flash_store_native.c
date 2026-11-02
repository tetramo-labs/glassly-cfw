/* H001Y1.0.3.127 fixed native tail binding. See FLASH_STORE_NATIVE.md.
 * Native wrappers own native locking; no CUS8 callbacks/package state touched. */
#include "flash_store_native.h"
#define MAGIC UINT32_C(0x4d464e31)
#ifndef MM_FLASH_NATIVE_HOST_TEST
_Static_assert(sizeof(void *)==4,"Only the pinned RV32 ABI is supported");
#define FN(a,t) ((t)(uintptr_t)(a))
static int native_read(uint32_t d,uint32_t o,void *p,uint32_t n) {
    typedef int (*f)(uint32_t,uint32_t,void *,uint32_t);
    return FN(0x04329ad8u,f)(d,o,p,n);
}
static int native_program(uint32_t d,uint32_t o,const void *p,uint32_t n) {
    typedef int (*f)(uint32_t,uint32_t,const void *,uint32_t);
    return FN(0x04329b1eu,f)(d,o,p,n);
}
static int native_erase(uint32_t d,uint32_t o,uint32_t n) {
    typedef int (*f)(uint32_t,uint32_t,uint32_t);
    return FN(0x04329a14u,f)(d,o,n);
}
static void native_cache(uint32_t d,uint32_t a,uint32_t n) {
    typedef void (*f)(uint32_t,uint32_t,uint32_t);
    FN(0x04324beau,f)(d,a,n);
}
#else
#define native_read mm_flash_test_read
#define native_program mm_flash_test_program
#define native_erase mm_flash_test_erase
#define native_cache mm_flash_test_cache
#endif
static int span(const void *p,size_t n) {
    uintptr_t a=(uintptr_t)p;
    if(!p || !n || n>UINTPTR_MAX-a)return 0;
#ifndef MM_FLASH_NATIVE_HOST_TEST
    if(a<MM_FLASH_NATIVE_SRAM_BASE || a>=MM_FLASH_NATIVE_SRAM_END ||
       n>MM_FLASH_NATIVE_SRAM_END-a)return 0;
#endif
    return 1;
}
static int overlaps(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=y ? y-x<an : x-y<bn;
}
static int context(mm_flash_native *s) {
    return span(s,sizeof(*s)) && !((uintptr_t)s%_Alignof(mm_flash_native)) && s->magic==MAGIC;
}
static int admit(mm_flash_native *s,uint32_t off,size_t n,unsigned operation) {
    if(!context(s))return MM_FLASH_NATIVE_STATE;
    if(s->busy)return MM_FLASH_NATIVE_BUSY;
    if(off<MM_FLASH_NATIVE_BASE || off>=MM_FLASH_NATIVE_END || !n || n>MM_FLASH_NATIVE_END-off)
        return MM_FLASH_NATIVE_RANGE;
    if(operation==MM_FLASH_NATIVE_ERASE) {
        if(n!=4096 || (off&4095u))return MM_FLASH_NATIVE_RANGE;
    }else if(operation==MM_FLASH_NATIVE_PROGRAM) {
        if(n!=256 || (off&255u))return MM_FLASH_NATIVE_RANGE;
    }else if(n>256 || n>256u-(off&255u))return MM_FLASH_NATIVE_RANGE;
    unsigned sector=(off-MM_FLASH_NATIVE_BASE)>>12;
    if(s->real_unavailable[sector>>3]&(1u<<(sector&7u)))return MM_FLASH_NATIVE_BAD_SECTOR;
    return 0;
}
static int buffer(mm_flash_native *s,const void *p,size_t n) {
    if(!span(p,n))return MM_FLASH_NATIVE_ARGUMENT;
    return overlaps(p,n,s,sizeof(*s)) ? MM_FLASH_NATIVE_ALIAS:0;
}
static void begin(mm_flash_native *s,unsigned phase) {s->busy=1;s->phase=(uint8_t)phase;s->last_native_status=0;}
static int finish(mm_flash_native *s,int status) {s->busy=0;return status;}
int mm_flash_native_init(mm_flash_native *s,const uint8_t map[32]) {
    if(!span(s,sizeof(*s)) || (uintptr_t)s%_Alignof(mm_flash_native) || !span(map,32))return MM_FLASH_NATIVE_ARGUMENT;
    if(overlaps(s,sizeof(*s),map,32))return MM_FLASH_NATIVE_ALIAS;
    if(s->magic==MAGIC && s->busy)return MM_FLASH_NATIVE_BUSY;
    for(size_t i=0;i<sizeof(*s);i++)((uint8_t *)s)[i]=0;
    for(size_t i=0;i<32;i++)s->real_unavailable[i]=map[i];
    s->magic=MAGIC;return 0;
}
int mm_flash_native_callbacks(mm_flash_native *s,mm_flash_callbacks *out) {
    if(!context(s))return MM_FLASH_NATIVE_STATE;
    if(s->busy)return MM_FLASH_NATIVE_BUSY;
    if(!span(out,sizeof(*out)) || (uintptr_t)out%_Alignof(mm_flash_callbacks))return MM_FLASH_NATIVE_ARGUMENT;
    if(overlaps(out,sizeof(*out),s,sizeof(*s)))return MM_FLASH_NATIVE_ALIAS;
    out->user=s;out->read=mm_flash_native_read;out->erase=mm_flash_native_erase;out->program=mm_flash_native_program;
    return 0;
}
int mm_flash_native_read(void *user,uint32_t off,void *out,size_t n) {
    mm_flash_native *s=user;int rc=admit(s,off,n,MM_FLASH_NATIVE_READ);if(rc)return rc;
    rc=buffer(s,out,n);if(rc)return rc;
    begin(s,MM_FLASH_NATIVE_READ);rc=native_read(1,off,out,(uint32_t)n);s->last_native_status=rc;
    return finish(s,rc);
}
int mm_flash_native_program(void *user,uint32_t off,const void *data,size_t n) {
    mm_flash_native *s=user;int rc=admit(s,off,n,MM_FLASH_NATIVE_PROGRAM);if(rc)return rc;
    rc=buffer(s,data,n);if(rc)return rc;
    begin(s,MM_FLASH_NATIVE_PROGRAM);rc=native_program(1,off,data,(uint32_t)n);s->last_native_status=rc;
    native_cache(0,0x05000000u+off,(uint32_t)n);
    if(rc)return finish(s,rc);
    s->phase=MM_FLASH_NATIVE_READBACK;rc=native_read(1,off,s->verification,256);s->last_native_status=rc;
    if(rc)return finish(s,rc);
    const uint8_t *p=data;
    for(size_t i=0;i<256;i++)if(s->verification[i]!=p[i])return finish(s,MM_FLASH_NATIVE_VERIFY);
    return finish(s,0);
}
int mm_flash_native_erase(void *user,uint32_t off,size_t n) {
    mm_flash_native *s=user;int rc=admit(s,off,n,MM_FLASH_NATIVE_ERASE);if(rc)return rc;
    begin(s,MM_FLASH_NATIVE_ERASE);rc=native_erase(1,off,(uint32_t)n);s->last_native_status=rc;
    native_cache(0,0x05000000u+off,(uint32_t)n);
    if(rc)return finish(s,rc);
    s->phase=MM_FLASH_NATIVE_READBACK;
    for(uint32_t at=0;at<4096;at+=256) {
        rc=native_read(1,off+at,s->verification,256);s->last_native_status=rc;
        if(rc)return finish(s,rc);
        for(size_t i=0;i<256;i++)if(s->verification[i]!=255)return finish(s,MM_FLASH_NATIVE_VERIFY);
    }
    return finish(s,0);
}
