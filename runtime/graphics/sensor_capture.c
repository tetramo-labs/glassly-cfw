/* MIT. Capture ownership is independent of native sensor power. */
#include "sensor_capture.h"
#include "flash_canary.h"
#define P mm_graphics_native
#define MAGIC UINT32_C(0x534e5332)
#define LEASE 90000u
#define CAPACITY 32u
#define BATCH 4u
#define WATCH_EVENT 0x292u
typedef struct {uint8_t bytes[24];} record;
typedef struct {uint8_t imu[14],als[2];record records[CAPACITY];} arena;
typedef struct {
    uint32_t magic,generation,deadline,imu_seq,imu_tick,als_seq,als_tick;
    arena *data;
    uint8_t active,valid,head,count;
    uint32_t ack,sequence,drops;
} owner;
_Static_assert(sizeof(owner)==48 || sizeof(void *)!=4,"Sensor owner fits final registry slot");
_Static_assert(sizeof(arena)==784,"Bounded sensor allocation");
#ifdef MM_SENSOR_TEST
extern void *mm_sensor_memory(void);
extern uint32_t mm_sensor_clock(void);
extern uint32_t mm_sensor_schedule(uint32_t);
#define MEMORY mm_sensor_memory()
#define NOW mm_sensor_clock()
#else
#define MEMORY ((void *)(uintptr_t)(MM_CANARY_REGISTRY+208))
#define NOW (((uint32_t (*)(void))(uintptr_t)0x0200f6e8u)())
#endif
static void put(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(i*8));}
static uint32_t word(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static owner *get(void){
    if(!glassly_canary_layout_valid())return 0;
    owner *o=MEMORY;return !o->magic || o->magic==MAGIC?o:0;
}
static void expire(owner *o,uint32_t t){
    if(o->active && (int32_t)(o->deadline-t)<=0){o->active=0;o->valid=0;}
}
static arena *detach(owner *o){arena *p=o->data;o->data=0;o->active=0;o->valid=0;o->count=0;o->head=0;return p;}
static void dispose(arena *p){if(p)P.free(p);}
static uint32_t schedule(uint32_t generation){
#ifdef MM_SENSOR_TEST
    return mm_sensor_schedule(generation);
#else
    uint32_t job[2]={MAGIC,generation};
    typedef uint32_t (*f)(uint32_t,uint32_t,const void *,uint32_t,uint32_t);
    return ((f)(uintptr_t)0x042363f4u)(0x13,WATCH_EVENT,job,sizeof(job),1000);
#endif
}
static void cancel_generation(owner *o,uint32_t generation){
    glassly_canary_enter();arena *p=o->generation==generation?detach(o):0;glassly_canary_leave();dispose(p);
}
void glassly_sensor_watch(const uint8_t *p,uint32_t n){
    if(!p || n!=8 || word(p)!=MAGIC)return;
    owner *o=get();if(!o)return;uint32_t generation=word(p+4),t=NOW;int active=0;arena *old=0;
    glassly_canary_enter();
    if(o->generation==generation){expire(o,t);if(o->active)active=1;else old=detach(o);}
    glassly_canary_leave();dispose(old);
    if(active && schedule(generation))cancel_generation(o,generation);
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
    if(o->generation==generation && o->data && (o->active&mask)){
        uint32_t *seq=mask==1?&o->imu_seq:&o->als_seq,*tick=mask==1?&o->imu_tick:&o->als_tick;
        if(o->sequence==UINT32_MAX){o->active=0;o->valid=0;}
        else if(*seq==UINT32_MAX){o->active&=(uint8_t)~mask;o->valid&=(uint8_t)~mask;}
        else if(!(o->valid&mask) || (int32_t)(t-*tick)>=0){
            uint8_t *out=mask==1?o->data->imu:o->data->als;
            for(unsigned i=0;i<(mask==1?14u:2u);i++)out[i]=sample[i];
            *tick=t;(*seq)++;o->valid|=(uint8_t)mask;
            if(o->count==CAPACITY){o->head=(uint8_t)((o->head+1)%CAPACITY);o->count--;if(o->drops!=UINT32_MAX)o->drops++;}
            uint8_t *r=o->data->records[(o->head+o->count)%CAPACITY].bytes;
            put(r,++o->sequence);put(r+4,t);r[8]=(uint8_t)mask;r[9]=0;
            for(unsigned i=0;i<14;i++)r[10+i]=i<(mask==1?14u:2u)?sample[i]:0;
            o->count++;
        }
    }
    glassly_canary_leave();
}
void glassly_sensor_cleanup(void){
    owner *o=get();if(!o)return;
    glassly_canary_enter();arena *p=detach(o);glassly_canary_leave();dispose(p);
}
static void *json_hex(const char *kind,const char *result,const uint8_t *b,unsigned n){
    char *out=P.alloc(n>52?384:208);if(!out)return P.status(4,0);
    char *p=out;const char *s="{\"glassly\":\"";while(*s)*p++=*s++;
    while(*kind){*p++=*kind++;}
    s="\",\"abi\":1,\"result\":\"";while(*s)*p++=*s++;
    while(*result){*p++=*result++;}
    s="\",\"stateHex\":\"";while(*s)*p++=*s++;
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<n;i++){*p++=hex[b[i]>>4];*p++=hex[b[i]&15];}
    *p++='"';*p++='}';*p=0;void *r=P.json(out);P.free(out);return r;
}
static void *reply(const char *result){
    owner s={0};uint8_t latest[16]={0},b[52]={'S','C',1};owner *o=get();
    if(o){glassly_canary_enter();s=*o;if(o->data){
        if(o->valid&1)for(unsigned i=0;i<14;i++)latest[i]=o->data->imu[i];
        if(o->valid&2){latest[14]=o->data->als[0];latest[15]=o->data->als[1];}
    }glassly_canary_leave();}
    uint32_t t=NOW;expire(&s,t);b[3]=s.active;b[4]=s.valid;
    if((s.valid&1) && (uint32_t)(t-s.imu_tick)<=1000)b[5]|=1;
    if((s.valid&2) && (uint32_t)(t-s.als_tick)<=5000)b[5]|=2;
    put(b+8,s.generation);put(b+12,t);put(b+16,s.active?s.deadline:0);
    if(s.valid&1){put(b+20,s.imu_seq);put(b+24,s.imu_tick);for(unsigned i=0;i<14;i++)b[36+i]=latest[i];}
    if(s.valid&2){put(b+28,s.als_seq);put(b+32,s.als_tick);b[50]=latest[14];b[51]=latest[15];}
    return json_hex("sensors",result,b,sizeof(b));
}
static void *batch(owner *o,uint32_t generation,uint32_t ack){
    uint8_t b[28+BATCH*24]={'S','B',1};uint32_t t=NOW;const char *result="ok";unsigned count=0;arena *old=0;
    glassly_canary_enter();expire(o,t);
    if(o->generation!=generation)result="stale";
    else if(!o->active){result="inactive";old=detach(o);}
    else if(ack<o->ack || ack>o->sequence)result="invalid";
    else {
        o->ack=ack;
        while(o->count && word(o->data->records[o->head].bytes)<=ack){o->head=(uint8_t)((o->head+1)%CAPACITY);o->count--;}
        count=o->count<BATCH?o->count:BATCH;
        for(unsigned i=0;i<count;i++)for(unsigned j=0;j<24;j++)b[28+i*24+j]=o->data->records[(o->head+i)%CAPACITY].bytes[j];
    }
    b[3]=o->active;put(b+4,o->generation);put(b+8,t);put(b+12,o->ack);put(b+16,o->sequence);put(b+20,o->drops);
    b[24]=o->count;b[25]=CAPACITY;b[26]=(uint8_t)count;
    glassly_canary_leave();dispose(old);put(b+8,NOW);return json_hex("sensor-batch",result,b,28+count*24);
}
void glassly_sensor_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t op=255,mask=0;uint32_t generation=0,ack=0;
    if(P.request_bytes(request,&p,&n) && p && n>=4 && p[0]=='S' && p[1]=='C' && p[2]==1 && p[3]<=4 &&
       n==(p[3]==1?5u:p[3]==4?12u:4u) && (p[3]!=1 || (p[4]>=1 && p[4]<=3))){
        op=p[3];if(op==1)mask=p[4];if(op==4){generation=word(p+4);ack=word(p+8);if(!generation)op=255;}
    }
    if(request)P.release(&request);
    if(op==255){*response=reply("invalid");return;}
    owner *o=get();if(!o){*response=reply("unavailable");return;}
    if(op==4){*response=batch(o,generation,ack);return;}
    arena *fresh=0,*old=0;
    if(op==1){
        if(P.free_bytes()<32768u+sizeof(arena) || !(fresh=P.alloc(sizeof(arena)))){*response=reply("allocation-failed");return;}
    }
    uint32_t t=NOW;const char *result="ok";
    glassly_canary_enter();expire(o,t);
    if(op==1){
        if(o->generation==UINT32_MAX)result="exhausted";
        else {old=detach(o);o->magic=MAGIC;generation=++o->generation;o->deadline=t+LEASE;o->active=mask;
            o->imu_seq=0;o->als_seq=0;o->ack=0;o->sequence=0;o->drops=0;o->data=fresh;fresh=0;}
    }else if(op==2 || !o->active){old=detach(o);if(op==3)result="inactive";}
    else if(op==3)o->deadline=t+LEASE;
    glassly_canary_leave();dispose(old);dispose(fresh);
    if(generation && schedule(generation)){cancel_generation(o,generation);result="schedule-failed";}
    *response=reply(result);
}
