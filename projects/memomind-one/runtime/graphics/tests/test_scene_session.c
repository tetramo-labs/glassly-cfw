/* Actual scene/session integration; native heap/display are explicit mocks. */
#include "scene_session.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef union { max_align_t alignment; size_t size; } native_header;
typedef struct {
    mm_scene_session session;
    uint8_t *pixels;
    size_t capacity,used,peak;
    uint32_t now;
    unsigned allocations,attempts,fail_at,presents,settled;
    uint16_t last_tag,request;
    int active,simulate_wire;
    size_t wire_bytes;
} device;
static void *allocate(void *user,size_t size) {
    device *d=user;d->attempts++;
    if(d->attempts==d->fail_at || size>d->capacity-d->used)return 0;
    native_header *h=malloc(sizeof(*h)+size);assert(h);h->size=size;
    d->used+=size;if(d->used>d->peak)d->peak=d->used;d->allocations++;return h+1;
}
static void deallocate(void *user,void *p) {
    device *d=user;native_header *h=(native_header *)p-1;
    assert(d->used>=h->size && d->allocations);d->used-=h->size;d->allocations--;free(h);
}
static uint32_t free_bytes(void *u){device *d=u;return (uint32_t)(d->capacity-d->used-d->wire_bytes);}
static uint32_t now(void *u){return ((device *)u)->now;}
static int active(void *u){return ((device *)u)->active;}
static void present(void *u,const mm_raster *r,const mm_scene_dirty *dirty) {
    (void)dirty;
    device *d=u;assert(r->pixels==d->pixels);d->presents++;
}
static void settled(void *u,uint16_t tag){device *d=u;d->settled++;d->last_tag=tag;}
static void init(device *d,unsigned w,unsigned h,size_t capacity,size_t budget,uint32_t store) {
    memset(d,0,sizeof(*d));d->active=1;d->capacity=capacity;d->now=1234;
    d->pixels=calloc((size_t)(w+1)/2,h);assert(d->pixels);
    mm_raster raster={d->pixels,(size_t)((w+1)/2)*h,w,h,(w+1)/2};
    mm_scene_session_hooks hooks={d,allocate,deallocate,free_bytes,now,active,present,settled,0};
    assert(!mm_scene_session_init(&d->session,&hooks,&raster,budget,MM_SCENE_SESSION_HEADROOM,store));
}
static void dispose(device *d) {
    mm_scene_session_dispose(&d->session);mm_scene_session_pump(&d->session);
    assert(!d->allocations && !d->used && !d->session.live_bytes && !d->session.timer_armed);
    mm_scene_session_dispose(&d->session);free(d->pixels);
}
static void w16(uint8_t *p,unsigned x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void w32(uint8_t *p,unsigned x){w16(p,x);w16(p+2,x>>16);}
static unsigned r16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
static uint32_t r32(const uint8_t *p){return r16(p)|(uint32_t)r16(p+2)<<16;}
static unsigned pixel(device *d,unsigned x,unsigned y) {
    mm_raster *r=&d->session.raster;assert(x<r->width && y<r->height);
    uint8_t b=d->pixels[y*r->stride+x/2];return x&1?b&15:b>>4;
}
static int send(device *d,uint8_t *p,size_t size) {
    if(p[0]>=37 && p[0]<=41 && size>=5) {
        w16(p+1,d->session.core.cache_epoch);w16(p+3,++d->request);
    }
    if(d->simulate_wire) {
        /* Request is already resident at native callback admission. The job
         * and queue copy coexist transiently; only envelope survives dispatch. */
        size_t free_at_admission=d->capacity-d->used-size-16;
        if(free_at_admission<32u*1024u+2u*(size+4u)+8u)
            fprintf(stderr,"wire admission failure mode%u size%zu live%zu free%zu\n",p[0],size,d->used,free_at_admission);
        assert(free_at_admission>=32u*1024u+2u*(size+4u)+8u);
        d->wire_bytes=size+12u;
    }
    int result=mm_scene_session_dispatch(&d->session,p,size);
    d->wire_bytes=0;
    assert(d->used==d->session.live_bytes && d->used<=d->session.budget);
    assert(d->capacity-d->used>=MM_SCENE_SESSION_HEADROOM);
    return result;
}
static unsigned status(device *d){assert(d->session.core.cache_reply_len>=10);return d->session.core.cache_reply[3];}
static void reset(device *d){uint8_t p[]={41,0,0,0,0,0};assert(!send(d,p,sizeof p));}
static void put(device *d) {
    uint8_t p[34]={37};p[5]=1;w32(p+6,1);w32(p+10,1);
    p[14]=3;p[15]=1;p[16]=7;w16(p+18,5);w16(p+20,5);w16(p+22,10);w16(p+24,5);
    assert(!send(d,p,sizeof p));
}
static void show(device *d) {
    uint8_t p[18]={38};p[5]=5;w16(p+8,1);w32(p+10,1);w32(p+14,1);
    assert(!send(d,p,sizeof p));assert(status(d)==0);
}
static void animate(device *d) {
    uint8_t p[24]={38};p[5]=7; /* present/keep/tag; zero puts and references */
    p[10]=4;w32(p+11,1);w16(p+15,100);w16(p+17,0);p[19]=10;
    p[20]=0;p[21]=0;p[22]=255;p[23]=255;
    assert(!send(d,p,sizeof p));assert(status(d)==0 && d->session.timer_armed);
}
static void advance(device *d,uint32_t ms){d->now+=ms;mm_scene_session_pump(&d->session);}
static void lifecycle(void) {
    device d;init(&d,600,350,227000,MM_SCENE_SESSION_BUDGET,MM_SCENE_MIN_STORE);
    reset(&d);assert(status(&d)==0 && r16(d.session.core.cache_reply+11)==64);
    put(&d);assert(status(&d)==0);show(&d);assert(pixel(&d,6,6)==7 && d.presents==1);
    animate(&d);unsigned presents=d.presents,settles=d.settled;
    advance(&d,1);assert(d.presents==presents);
    advance(&d,1000);assert(d.presents==presents+1 && pixel(&d,106,6)==7 && pixel(&d,6,6)==0);
    assert(d.settled==settles+1 && !d.session.timer_armed);
    /* Native wrap and late display scheduling use elapsed time, no frame backlog. */
    d.now=UINT32_MAX-10;animate(&d);advance(&d,1000);assert(!d.session.timer_armed);
    uint8_t raw[]={36,1,3,1,15,0,0,0,0,0,3,0,3,0,0,0,0,0,0,0,0,0};
    assert(!send(&d,raw,sizeof raw));assert(pixel(&d,1,1)==15 && !d.session.timer_armed);
    size_t peak=d.session.peak_bytes;d.active=0;advance(&d,1);
    assert(!d.used && !d.session.timer_armed && !d.session.core.scene);
    assert(mm_scene_session_dispatch(&d.session,raw,sizeof raw)==-2);
    d.active=1;reset(&d);assert(status(&d)==0);dispose(&d);
    printf("native-policy lifecycle: peak scene bytes %zu, 64KiB store, expiry/reacquire/wrap/late-tick passed\n",peak);
}
static void failures(void) {
    for(unsigned fail=1;fail<=9;fail++) {
        device d;init(&d,600,350,227000,MM_SCENE_SESSION_BUDGET,MM_SCENE_MIN_STORE);d.fail_at=fail;
        reset(&d);put(&d);dispose(&d);
    }
    device d;init(&d,600,350,MM_SCENE_SESSION_HEADROOM+100,MM_SCENE_SESSION_BUDGET,MM_SCENE_MIN_STORE);
    reset(&d);assert(status(&d)==3 && !d.used && d.session.denied_allocations);dispose(&d);
    init(&d,600,350,227000,1,MM_SCENE_MIN_STORE);reset(&d);assert(status(&d)==3 && !d.used);dispose(&d);
    init(&d,600,350,227000,MM_SCENE_SESSION_BUDGET,MM_SCENE_MIN_STORE);
    uint8_t bad[]={38,0};assert(send(&d,bad,sizeof bad)==-1);
    assert(mm_scene_session_dispatch(&d.session,bad,MM_SCENE_MAX_MESSAGE+1u)==-1);
    assert(mm_scene_session_dispatch(&d.session,0,1)==-1);dispose(&d);
    puts("native-policy allocation failures, aggregate budget, headroom and malformed input passed");
}
static void replay(const char *file,int native_policy) {
    FILE *f=fopen(file,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long count=ftell(f);assert(count>0 && count<64*1024*1024);rewind(f);
    uint8_t *data=malloc((size_t)count);assert(data);assert(fread(data,1,(size_t)count,f)==(size_t)count);fclose(f);
    device d;
    if(native_policy){init(&d,600,350,227000,MM_SCENE_SESSION_BUDGET,MM_SCENE_MIN_STORE);d.simulate_wire=1;}
    else init(&d,640,480,2*1024*1024,1024*1024,MM_SCENE_MAX_STORE);
    size_t pos=0,messages=0,probes=0,clipped=0;
    while(pos<(size_t)count) {
        uint8_t kind=data[pos++];size_t available=(size_t)count-pos;
        if(kind==1) {
            assert(available>=2);unsigned n=r16(data+pos);pos+=2;assert(n>=2 && n<=(size_t)count-pos);
            assert(!send(&d,data+pos,n));
            if(d.session.core.cache_reply_len>=10) {unsigned code=status(&d);assert(code==0 || code==5 || code==6 || code==7);}
            pos+=n;messages++;
        } else if(kind==2) {
            assert(available>=4);uint32_t ms=r32(data+pos);pos+=4;assert(ms<=60000);
            while(ms){uint32_t step=ms<33?ms:33;advance(&d,step);ms-=step;}
        } else if(kind==3) {
            assert(available>=1);unsigned n=data[pos++];assert(n<=(size_t)count-pos);pos+=n;
        } else if(kind==4) {
            assert(available>=5);unsigned x=r16(data+pos),y=r16(data+pos+2),color=data[pos+4];pos+=5;
            if(x>=d.session.raster.width || y>=d.session.raster.height){clipped++;continue;}
            if(pixel(&d,x,y)!=color)fprintf(stderr,"pixel failure %s message%zu (%u,%u) expected%u actual%u\n",file,messages,x,y,color,pixel(&d,x,y));
            assert(pixel(&d,x,y)==color);probes++;
        } else {assert(kind==5);}
    }
    size_t peak=d.session.peak_bytes;
    dispose(&d);free(data);printf("session replay (%s): %zu messages, %zu pixel probes, %zu out-of-bounds probes omitted, peak%zu; %s\n",native_policy?"native600x350/64KiB":"original640x480/256KiB",messages,probes,clipped,peak,file);
}
int main(int argc,char **argv) {
    lifecycle();failures();for(int i=1;i<argc;i++){replay(argv[i],0);replay(argv[i],1);}return 0;
}
