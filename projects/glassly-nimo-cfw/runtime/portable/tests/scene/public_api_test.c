/* Public API integration: independent owners, Memo strides and allocation budgets. MIT. */
#include "scene.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef union allocation {max_align_t alignment;struct {size_t bytes;unsigned kind;} data;} allocation;
typedef struct {
    mm_scene_context ctx;uint8_t *memory;mm_raster raster;
    size_t live,peak,budget;unsigned allocations,presents,settled,hints,inside_gate;
    uint32_t now;int lease,fail_alloc;
} owner;
static void *allocate(void *u,unsigned kind,size_t n) {
    owner *o=u;assert(!o->inside_gate);
    if(o->fail_alloc || n>o->budget-o->live)return 0;
    allocation *p=malloc(sizeof(*p)+n);assert(p);p->data.bytes=n;p->data.kind=kind;
    o->live+=n;if(o->live>o->peak)o->peak=o->live;o->allocations++;return p+1;
}
static void deallocate(void *u,unsigned kind,void *v) {
    owner *o=u;allocation *p=(allocation *)v-1;assert(p->data.kind==kind);assert(o->live>=p->data.bytes);o->live-=p->data.bytes;o->allocations--;free(p);
}
static uint32_t now(void *u){return ((owner *)u)->now;}
static int lease(void *u){return ((owner *)u)->lease;}
static int shadow(void *u,mm_raster *r){*r=((owner *)u)->raster;return 1;}
static uintptr_t timer_new(void *u,void (*cb)(void *),void *arg){(void)u;(void)cb;(void)arg;return 1;}
static void timer_start(void *u,uintptr_t t,uint32_t ms){(void)u;assert(t==1 && ms>=10 && ms<=250);}
static void timer_stop(void *u,uintptr_t t){(void)u;assert(t==1);}
static void gate(void *u){((owner *)u)->inside_gate=1;}
static void gate_signal(void *u){((owner *)u)->inside_gate=0;}
static void present(void *u,mm_scene_context *ctx,const mm_raster *r,mm_scene_dirty *dirty){owner *o=u;assert(ctx==&o->ctx && r->pixels==o->raster.pixels);o->presents++;dirty->direct_submitted=1;}
static void settled(void *u,uint16_t tag){(void)tag;((owner *)u)->settled++;}
static void hint(void *u,uint8_t n){(void)n;((owner *)u)->hints++;}
static void init(owner *o,unsigned w,unsigned h,size_t budget,uint32_t store_limit) {
    memset(o,0,sizeof(*o));o->budget=budget;o->lease=1;o->now=1234;
    size_t bytes=(size_t)320*h;o->memory=malloc(bytes+66);assert(o->memory);memset(o->memory,0xa5,bytes+66);
    o->raster=(mm_raster){o->memory+33,bytes,w,h,320};
    mm_scene_platform p={o,allocate,deallocate,now,lease,shadow,timer_new,timer_start,timer_stop,gate,gate_signal,present,settled,hint,0};
    assert(mm_scene_init(&o->ctx,&p,store_limit)==0);
}
static void w16(uint8_t *p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void w32(uint8_t *p,unsigned n){w16(p,n);w16(p+2,n>>16);}
static int send(owner *o,uint8_t mode,const uint8_t *data,size_t n){
    o->ctx.cache_reply_cap=245;mm_scene_prepare(&o->ctx,mode,data,n);o->inside_gate=1;
    mm_scene_dirty dirty={0};int result=mm_scene_dispatch(&o->ctx,mode,data,n,1,&dirty);o->inside_gate=0;return result;
}
static void reset(owner *o,unsigned expected_kib){
    uint8_t data[5]={0,0,1,0,0};assert(send(o,41,data,sizeof data)==0);
    assert(o->ctx.cache_reply_len==13 && o->ctx.cache_reply[3]==0);
    assert((unsigned)o->ctx.cache_reply[11]+((unsigned)o->ctx.cache_reply[12]<<8)==expected_kib);
}
static void put(owner *o,uint8_t color) {
    uint8_t data[33]={0};w16(data,o->ctx.cache_epoch);w16(data+2,2);data[4]=1;w32(data+5,1);w32(data+9,1);
    data[13]=3;data[14]=1;data[15]=color;w16(data+17,5);w16(data+19,5);w16(data+21,10);w16(data+23,5);
    assert(send(o,37,data,sizeof data)==0 && o->ctx.cache_reply[3]==0);
}
static void show(owner *o){uint8_t data[17]={0};w16(data,o->ctx.cache_epoch);w16(data+2,3);data[4]=1;w16(data+7,1);w32(data+9,1);w32(data+13,1);assert(send(o,38,data,sizeof data)==0 && o->ctx.cache_reply[3]==0);}
static unsigned pixel(owner *o,unsigned x,unsigned y){uint8_t b=o->raster.pixels[y*320+x/2];return x&1?b&15:b>>4;}
static void guards(owner *o){
    for(unsigned i=0;i<33;i++)assert(o->memory[i]==0xa5 && o->raster.pixels[o->raster.bytes+i]==0xa5);
    for(unsigned y=0;y<o->raster.height;y++){
        if(o->raster.width&1)assert((o->raster.pixels[y*320+o->raster.width/2]&15)==5);
        for(unsigned x=(o->raster.width+1)/2;x<320;x++)assert(o->raster.pixels[y*320+x]==0xa5);
    }
}
int main(void){
    owner a,b;init(&a,600,350,180000,MM_SCENE_MIN_STORE);init(&b,601,175,300000,128*1024);
    reset(&a,64);reset(&b,128);put(&a,7);put(&b,12);show(&a);show(&b);
    assert(pixel(&a,6,6)==7 && pixel(&b,6,6)==12 && a.presents==1 && b.presents==1);
    assert(a.ctx.scene!=b.ctx.scene && a.ctx.texture_cache!=b.ctx.texture_cache);
    guards(&a);guards(&b);
    size_t before=a.live;uint8_t invalid[3]={0};assert(send(&a,37,invalid,sizeof invalid)==-1);assert(a.live==before);
    uint8_t state[8]={0};assert(mm_scene_dispatch(&a.ctx,40,state,MM_SCENE_MAX_MESSAGE+1u,0,0)==-1);
    assert(mm_scene_dispatch(&a.ctx,37,(uint8_t *)&a.ctx,sizeof(a.ctx),0,0)==-1);
    assert(mm_scene_dispatch(&a.ctx,37,a.ctx.texture_cache,20,0,0)==-1);
    assert(mm_scene_dispatch(&a.ctx,37,a.raster.pixels,20,0,0)==-1);
    assert(mm_scene_init(&a.ctx,&a.ctx.platform,MM_SCENE_MIN_STORE)==-1);
    a.lease=0;mm_scene_lose(&a.ctx);mm_scene_reap(&a.ctx);assert(!a.allocations && a.live==0);
    assert(pixel(&b,6,6)==12 && b.allocations>0);mm_scene_release(&a.ctx);mm_scene_release(&b.ctx);
    assert(!b.allocations && !b.live);guards(&a);guards(&b);
    printf("public scene API: independent600x350/601x175 stride320 owners,64/128KiB store limits, zero leaks; peak core bytes %zu/%zu\n",a.peak,b.peak);
    free(a.memory);free(b.memory);
    /* The allocator can reject every request without changing the framebuffer. */
    init(&a,600,350,180000,MM_SCENE_MIN_STORE);a.fail_alloc=1;uint8_t req[5]={0,0,1,0,0};
    assert(send(&a,41,req,sizeof req)==0 && a.ctx.cache_reply[3]==3 && !a.allocations);
    for(size_t i=0;i<a.raster.bytes;i++)assert(a.raster.pixels[i]==0xa5);
    mm_scene_release(&a.ctx);free(a.memory);
}
