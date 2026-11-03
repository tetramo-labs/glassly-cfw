/* MIT. Snapshot ownership is independent of native sensor power. */
#include "sensor_capture.h"
#include "flash_canary.h"
#define P mm_graphics_native
#define MAGIC UINT32_C(0x534e5331)
#define LEASE 90000u
typedef struct {
    uint32_t magic,generation,deadline,imu_seq,imu_tick,als_seq,als_tick;
    uint8_t imu[14],als[2],active,valid,reserved[2];
} owner;
_Static_assert(sizeof(owner)==48,"Sensor snapshot fits final registry slot");
#ifdef MM_SENSOR_TEST
extern void *mm_sensor_memory(void);
extern uint32_t mm_sensor_clock(void);
#define MEMORY mm_sensor_memory()
#define NOW mm_sensor_clock()
#else
#define MEMORY ((void *)(uintptr_t)(MM_CANARY_REGISTRY+208))
#define NOW (((uint32_t (*)(void))(uintptr_t)0x0200f6e8u)())
#endif
static owner *get(void){
    if(!glassly_canary_layout_valid())return 0;
    owner *o=MEMORY;
    return !o->magic || o->magic==MAGIC?o:0;
}
static void expire(owner *o,uint32_t t){
    if(o->active && (int32_t)(o->deadline-t)<=0){o->active=0;o->valid=0;}
}
uint32_t glassly_sensor_begin(uint32_t mask){
    owner *o=get();if(!o)return 0;
    uint32_t t=NOW,g=0;glassly_canary_enter();expire(o,t);
    if(o->active&mask)g=o->generation;
    glassly_canary_leave();return g;
}
void glassly_sensor_finish(uint32_t mask,uint32_t generation,const uint8_t *sample){
    owner *o=get();if(!o || !sample || !generation || (mask!=1 && mask!=2))return;
    uint32_t t=NOW;glassly_canary_enter();expire(o,t);
    if(o->generation==generation && (o->active&mask)){
        uint32_t *seq=mask==1?&o->imu_seq:&o->als_seq,*tick=mask==1?&o->imu_tick:&o->als_tick;
        if(*seq==UINT32_MAX){o->active&=(uint8_t)~mask;o->valid&=(uint8_t)~mask;}
        else if(!(o->valid&mask) || (int32_t)(t-*tick)>=0){
            uint8_t *out=mask==1?o->imu:o->als;
            for(unsigned i=0;i<(mask==1?14u:2u);i++)out[i]=sample[i];
            *tick=t;(*seq)++;o->valid|=(uint8_t)mask;
        }
    }
    glassly_canary_leave();
}
void glassly_sensor_cleanup(void){
    owner *o=get();if(!o)return;
    glassly_canary_enter();o->active=0;o->valid=0;glassly_canary_leave();
}
static void put(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(i*8));}
static void *reply(const char *result){
    owner s;uint8_t *bytes=(uint8_t *)&s;for(size_t i=0;i<sizeof(s);i++)bytes[i]=0;
    owner *o=get();if(o){glassly_canary_enter();s=*o;glassly_canary_leave();}
    uint32_t t=NOW;expire(&s,t);
    uint8_t b[52]={'S','C',1,s.active,s.valid,0,0,0};
    if((s.valid&1) && (uint32_t)(t-s.imu_tick)<=1000)b[5]|=1;
    if((s.valid&2) && (uint32_t)(t-s.als_tick)<=5000)b[5]|=2;
    put(b+8,s.generation);put(b+12,t);put(b+16,s.active?s.deadline:0);
    if(s.valid&1){put(b+20,s.imu_seq);put(b+24,s.imu_tick);for(unsigned i=0;i<14;i++)b[36+i]=s.imu[i];}
    if(s.valid&2){put(b+28,s.als_seq);put(b+32,s.als_tick);b[50]=s.als[0];b[51]=s.als[1];}
    char *out=P.alloc(208);if(!out)return P.status(4,0);
    char *p=out;const char *prefix="{\"glassly\":\"sensors\",\"abi\":1,\"result\":\"";
    while(*prefix)*p++=*prefix++;
    while(*result)*p++=*result++;
    const char *middle="\",\"stateHex\":\"";while(*middle)*p++=*middle++;
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<sizeof(b);i++){*p++=hex[b[i]>>4];*p++=hex[b[i]&15];}
    *p++='"';*p++='}';*p=0;void *r=P.json(out);P.free(out);return r;
}
void glassly_sensor_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t op=255,mask=0;
    if(P.request_bytes(request,&p,&n) && p && n>=4 && p[0]=='S' && p[1]=='C' && p[2]==1 && p[3]<=3 &&
       n==(p[3]==1?5u:4u) && (p[3]!=1 || (p[4]>=1 && p[4]<=3))){op=p[3];if(op==1)mask=p[4];}
    if(request)P.release(&request);
    if(op==255){*response=reply("invalid");return;}
    owner *o=get();if(!o){*response=reply("unavailable");return;}
    uint32_t t=NOW;const char *result="ok";
    glassly_canary_enter();expire(o,t);
    if(op==1){
        if(o->generation==UINT32_MAX)result="exhausted";
        else {o->magic=MAGIC;o->generation++;o->deadline=t+LEASE;o->active=mask;o->valid=0;o->imu_seq=0;o->als_seq=0;}
    }else if(op==2){o->active=0;o->valid=0;}
    else if(op==3){if(o->active)o->deadline=t+LEASE;else result="inactive";}
    glassly_canary_leave();*response=reply(result);
}
