#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MM_SENSOR_TEST 1
#include "../sensor_capture.c"
static owner storage;
static unsigned critical,layout=1,allocation_failure,allocations,schedule_error,schedules,arenas;
static size_t fail_size;
uint32_t mm_sensor_schedule(uint32_t generation){assert(!critical && generation);schedules++;return schedule_error;}
static unsigned sample_schedules,sample_schedule_error,reads,read_result=1;static uint32_t sample_interval,sample_generation;
static uint8_t als_flags;static unsigned settings;static uint8_t setting_values[16];
uint32_t mm_sensor_schedule_sample(uint32_t generation,uint32_t interval){assert(!critical && generation && interval);sample_schedules++;sample_generation=generation;sample_interval=interval;return sample_schedule_error;}
uint8_t mm_sensor_als_flags(void){assert(!critical);return als_flags;}
void mm_sensor_als_setting(uint32_t key,const uint8_t *value){assert(!critical && key==0x5904 && value && *value<=1 && settings<sizeof(setting_values));setting_values[settings++]=*value;if(*value)als_flags|=8;else als_flags&=(uint8_t)~8;}
int mm_sensor_als_read(uint16_t *out){assert(!critical && out);reads++;if(read_result){uint8_t als[2]={200,0};*out=200;glassly_sensor_finish(2,storage.generation,als);}return read_result;}
static uint32_t ticks;
void *mm_sensor_memory(void){return &storage;}
uint32_t mm_sensor_clock(void){assert(!critical);return ticks;}
int glassly_canary_layout_valid(void){return layout;}
void glassly_canary_enter(void){assert(!critical);critical=1;}
void glassly_canary_leave(void){assert(critical);critical=0;}
typedef struct {const uint8_t *p;size_t n;} request;
static int request_bytes(void *r,const uint8_t **p,size_t *n){if(!r)return 0;request *q=r;*p=q->p;*n=q->n;return 1;}
static void release(void **p){*p=0;}
static void *json(const char *s){assert(!critical);size_t n=strlen(s)+1;assert(n<=384);char *p=malloc(n);assert(p);memcpy(p,s,n);return p;}
static void *status(uint32_t code,const char *s){(void)s;assert(code==4);return json("oom");}
static void *alloc(size_t n){assert(!critical && (n==208 || n==384 || n==788));allocations++;if(allocation_failure || n==fail_size)return 0;if(n==788)arenas++;return malloc(n);}
static uint32_t free_bytes(void){return 65536;}
static void free_out(void *p){assert(!critical);free(p);}
const mm_graphics_platform mm_graphics_native={.request_bytes=request_bytes,.release=release,.json=json,.status=status,.alloc=alloc,.free=free_out,.free_bytes=free_bytes};
static char *send(const uint8_t *p,size_t n){request q={p,n};void *out=0;glassly_sensor_command(0x76,&q,0,&out);assert(out && !critical);return out;}
static void command(uint8_t op,uint8_t mask,const char *result){
    uint8_t b[5]={'S','C',1,op,mask};char *s=send(b,op==1?5:4);char expected[64];
    snprintf(expected,sizeof(expected),"\"result\":\"%s\"",result);assert(strstr(s,expected));free(s);
}
static void snapshot(uint8_t *out){
    uint8_t b[4]={'S','C',1,0};char *s=send(b,4);char *hex=strstr(s,"\"stateHex\":\"");assert(hex);hex+=12;
    for(unsigned i=0;i<52;i++){unsigned v;assert(sscanf(hex+i*2,"%2x",&v)==1);out[i]=(uint8_t)v;}assert(hex[104]=='"');free(s);
}
static void reset(void){if(storage.data)free(storage.data);memset(&storage,0,sizeof(storage));schedule_error=schedules=0;fail_size=0;critical=allocation_failure=allocations=0;layout=1;ticks=100;
    sample_schedules=sample_schedule_error=reads=settings=0;read_result=1;sample_interval=sample_generation=0;als_flags=2;memset(setting_values,0,sizeof(setting_values));}
static void lifecycle(void){
    reset();uint8_t state[52],imu[14];for(unsigned i=0;i<14;i++)imu[i]=(uint8_t)i;uint8_t als[2]={232,3};
    assert(!glassly_sensor_begin(1));snapshot(state);assert(!state[3] && !state[4]);
    command(1,3,"ok");uint32_t generation=glassly_sensor_begin(1);assert(generation==1 && glassly_sensor_begin(2)==1);
    unsigned before=allocations;glassly_sensor_finish(1,generation,imu);glassly_sensor_finish(2,generation,als);assert(allocations==before);
    memset(imu,255,sizeof(imu));als[0]=0;assert(storage.data->imu[0]==0 && storage.data->als[0]==232);
    snapshot(state);assert(state[3]==3 && state[4]==3 && state[5]==3 && state[20]==1 && state[28]==1);
    assert(!memcmp(state+36,storage.data->imu,14) && state[50]==232 && state[51]==3);
    ticks+=1001;snapshot(state);assert(state[4]==3 && state[5]==2);
    ticks+=4000;snapshot(state);assert(state[4]==3 && !state[5]);
    command(3,0,"ok");assert(storage.deadline==ticks+LEASE);
    command(2,0,"ok");glassly_sensor_finish(1,generation,imu);snapshot(state);assert(!state[3] && !state[4]);
    for(unsigned i=16;i<52;i++)assert(!state[i]);
    command(1,1,"ok");assert(!glassly_sensor_begin(2));glassly_sensor_finish(1,generation,imu);assert(!storage.valid);
    generation=glassly_sensor_begin(1);assert(generation==2);glassly_sensor_finish(1,generation,imu);assert(storage.valid==1);
    glassly_sensor_cleanup();glassly_sensor_cleanup();glassly_sensor_finish(1,generation,imu);assert(!storage.valid && !storage.active);
    command(3,0,"inactive");
}
static void expiry(void){
    reset();ticks=UINT32_MAX-50;command(1,3,"ok");uint32_t generation=glassly_sensor_begin(1);uint8_t imu[14]={0};
    ticks+=LEASE-1;glassly_sensor_finish(1,generation,imu);assert(storage.valid==1);
    ticks++;glassly_sensor_finish(1,generation,imu);assert(!storage.valid && !storage.active && !glassly_sensor_begin(1));
    command(3,0,"inactive");command(1,1,"ok");generation=glassly_sensor_begin(1);
    ticks+=LEASE;uint8_t s[52];snapshot(s);assert(!s[3] && !s[4]);
    glassly_sensor_finish(1,generation,imu);assert(!storage.valid);
}
static void boundaries(void){
    reset();command(1,3,"ok");owner before=storage;
    const uint8_t p[6]={'S','C',1,1,3,0};
    for(size_t n=0;n<=6;n++)if(n!=5){char *s=send(p,n);assert(strstr(s,"invalid"));free(s);assert(!memcmp(&before,&storage,sizeof(before)));}
    for(unsigned i=0;i<5;i++){uint8_t bad[5];memcpy(bad,p,5);bad[i]=i==3?4:0;char *s=send(bad,5);assert(strstr(s,"invalid"));free(s);assert(!memcmp(&before,&storage,sizeof(before)));}
    uint8_t imu[14]={1};glassly_sensor_finish(3,1,imu);glassly_sensor_finish(1,0,imu);glassly_sensor_finish(1,1,0);assert(!storage.valid);
    storage.generation=UINT32_MAX;command(1,3,"exhausted");assert(storage.generation==UINT32_MAX);
    storage.imu_seq=UINT32_MAX;glassly_sensor_finish(1,UINT32_MAX,imu);assert(storage.active==2 && !storage.valid);
    layout=0;command(1,3,"unavailable");assert(!glassly_sensor_begin(2));glassly_sensor_cleanup();assert(storage.active==2);
    layout=1;storage.magic=1;command(1,3,"unavailable");assert(!glassly_sensor_begin(1));
    reset();allocation_failure=1;uint8_t start[5]={'S','C',1,1,3};char *s=send(start,5);assert(!strcmp(s,"oom"));free(s);
    allocation_failure=0;command(2,0,"ok");assert(!storage.active);
}
static void watch(void){uint8_t b[8];put(b,MAGIC);put(b+4,storage.generation);glassly_sensor_watch(b,sizeof(b));}
static char *poll(uint32_t generation,uint32_t ack){uint8_t p[12]={'S','C',1,4};put(p+4,generation);put(p+8,ack);return send(p,sizeof(p));}
static void buffered(void){
    reset();command(1,3,"ok");uint32_t gen=storage.generation;uint8_t imu[14]={1};
    for(unsigned i=0;i<40;i++){ticks++;glassly_sensor_finish(1,gen,imu);}
    assert(storage.count==32 && storage.drops==8 && storage.sequence==40);
    char *a=poll(gen,0),*b=poll(gen,0);assert(!strcmp(a,b) && strstr(a,"sensor-batch"));free(a);free(b);
    a=poll(gen,12);free(a);assert(storage.ack==12 && storage.count==28);
    a=poll(gen,11);assert(strstr(a,"invalid"));free(a);assert(storage.ack==12 && storage.count==28);
    a=poll(gen,41);assert(strstr(a,"invalid"));free(a);assert(storage.ack==12);
    a=poll(gen+1,40);assert(strstr(a,"stale"));free(a);assert(storage.ack==12);
    arena *old=storage.data;fail_size=788;command(1,3,"allocation-failed");assert(storage.data==old && storage.generation==gen);
    fail_size=0;command(1,3,"ok");assert(storage.generation==gen+1 && !storage.count && !storage.sequence);
    glassly_sensor_finish(1,gen,imu);assert(!storage.count);
    uint8_t obsolete[8];put(obsolete,MAGIC);put(obsolete+4,gen);glassly_sensor_watch(obsolete,8);assert(storage.active==3);
    ticks+=90000;watch();assert(!storage.data && !storage.active && !storage.count);
    command(1,3,"ok");schedule_error=11;watch();assert(!storage.data && !storage.active);
    command(1,3,"schedule-failed");assert(!storage.data && !storage.active);
    schedule_error=0;command(1,3,"ok");storage.sequence=UINT32_MAX;glassly_sensor_finish(1,storage.generation,imu);assert(!storage.active);watch();assert(!storage.data);
    command(1,3,"ok");glassly_sensor_cleanup();assert(!storage.data);
}
static char *seal(uint32_t generation,uint32_t ack){uint8_t p[12]={'S','C',1,5};put(p+4,generation);put(p+8,ack);return send(p,sizeof(p));}
static char *release_capture(uint32_t generation,uint32_t ack){uint8_t p[12]={'S','C',1,6};put(p+4,generation);put(p+8,ack);return send(p,sizeof(p));}
static void release_owned(void){
    reset();command(1,3,"ok");uint32_t gen=storage.generation;uint8_t imu[14]={1};glassly_sensor_finish(1,gen,imu);
    char *a=release_capture(gen+1,0);assert(strstr(a,"stale") && storage.active==3);free(a);
    a=release_capture(gen,2);assert(strstr(a,"invalid") && storage.active==3);free(a);
    a=release_capture(gen,1);assert(strstr(a,"released") && !storage.data && storage.ack==1);free(a);
    a=release_capture(gen,1);assert(strstr(a,"released"));free(a);
    command(1,3,"ok");a=release_capture(gen,1);assert(strstr(a,"stale") && storage.active==3);free(a);
    a=seal(storage.generation,0);free(a);a=release_capture(storage.generation,0);assert(strstr(a,"released") && !storage.data);free(a);
}
static void draining(void){
    reset();ticks=UINT32_MAX-100;command(1,3,"ok");uint32_t gen=storage.generation;uint8_t imu[14]={1};
    for(unsigned i=0;i<40;i++)glassly_sensor_finish(1,gen,imu);
    char *a=seal(gen+1,0);assert(strstr(a,"stale") && storage.active==3);free(a);
    a=seal(gen,41);assert(strstr(a,"invalid") && storage.active==3);free(a);
    fail_size=384;a=seal(gen,8);assert(!strcmp(a,"oom"));free(a);fail_size=0;
    assert(!storage.active && storage.valid==SEALED && storage.count==32 && storage.sequence==40);
    uint32_t deadline=storage.deadline;assert(deadline==ticks+DRAIN_LEASE);
    glassly_sensor_finish(1,gen,imu);assert(!glassly_sensor_begin(1) && storage.sequence==40);
    a=seal(gen,8);char *b=poll(gen,8);assert(!strcmp(a,b) && strstr(a,"\"abi\":2"));free(a);free(b);
    uint8_t state[52];snapshot(state);assert(!state[3] && !state[4] && storage.count==32);
    command(3,0,"inactive");assert(storage.data && storage.deadline==deadline);
    ticks+=1000;watch();assert(storage.data && storage.deadline==deadline);
    a=seal(gen,8);free(a);assert(storage.deadline==deadline);
    for(unsigned ack=12;ack<=40;ack+=4){a=poll(gen,ack);assert(strstr(a,"ok"));free(a);assert(storage.count==40-ack);}
    assert(storage.data && storage.ack==40 && storage.drops==8);
    command(2,0,"ok");assert(!storage.data);
    command(1,3,"ok");gen=storage.generation;a=seal(gen,0);free(a);deadline=storage.deadline;
    ticks=deadline-1;watch();assert(storage.data);ticks++;watch();assert(!storage.data);
    a=seal(gen,0);assert(strstr(a,"inactive"));free(a);
    command(1,3,"ok");gen=storage.generation;a=seal(gen,0);free(a);command(1,3,"ok");
    a=seal(gen,0);assert(strstr(a,"stale") && storage.active==3);free(a);
    a=seal(storage.generation,0);free(a);schedule_error=11;watch();assert(!storage.data);
}
static void start_active(uint8_t mask,uint32_t interval,const char *result){
    uint8_t b[7]={'S','C',1,1,mask,(uint8_t)interval,(uint8_t)(interval>>8)};char *s=send(b,7);char expected[64];
    snprintf(expected,sizeof(expected),"\"result\":\"%s\"",result);assert(strstr(s,expected));free(s);
}
static void sample(void){uint8_t b[8];put(b,MAGIC);put(b+4,sample_generation);glassly_sensor_sample(b,sizeof(b));}
static void active_sampling(void){
    reset();
    /* Passive starts never touch the sensor or schedule samples. */
    command(1,3,"ok");assert(!sample_schedules && !settings && !storage.data->interval && !storage.data->forced);
    sample();assert(!reads);
    /* An interval needs light in the mask and clamps to the stock range. */
    start_active(1,500,"invalid");start_active(2,0,"invalid");
    uint8_t six[6]={'S','C',1,1,3,244};char *s=send(six,6);assert(strstr(s,"invalid"));free(s);
    /* Suspended (auto-brightness off): the start forces the sensor and the arena remembers it. */
    start_active(3,50,"ok");assert(storage.data->interval==100 && sample_interval==100 && sample_generation==storage.generation);
    assert(settings==1 && setting_values[0]==1 && storage.data->forced && (als_flags&8));
    /* A restart releases the old arena's force before forcing again. */
    start_active(2,9000,"ok");assert(storage.data->interval==5000 && sample_interval==5000 && storage.active==2);
    assert(settings==3 && !setting_values[1] && setting_values[2]==1 && storage.data->forced && (als_flags&8));
    unsigned scheduled=sample_schedules;sample();assert(reads==1 && sample_schedules==scheduled+1 && storage.valid==2 && storage.count==1);
    uint8_t state[52];snapshot(state);assert(state[50]==200 && !state[51]);
    /* A read failure publishes nothing and keeps sampling. */
    read_result=0;sample();assert(reads==2 && storage.count==1 && sample_schedules==scheduled+2);read_result=1;
    /* Stale generation and the lease expiry stop the sampling without a read. */
    uint8_t stale[8];put(stale,MAGIC);put(stale+4,storage.generation+1);glassly_sensor_sample(stale,8);assert(reads==2);
    ticks+=LEASE;sample();assert(reads==2 && sample_schedules==scheduled+2 && storage.data);
    /* The watchdog detaches the expired arena, releasing the force. */
    watch();assert(!storage.data && settings==4 && !setting_values[3] && !(als_flags&8));
    /* Already running or already forced: no setting change, release leaves it alone. */
    settings=0;als_flags=2|4;start_active(3,250,"ok");assert(!settings && !storage.data->forced);command(2,0,"ok");assert(!settings);
    als_flags=2|8;start_active(3,250,"ok");assert(!settings && !storage.data->forced);command(2,0,"ok");assert(!settings);
    /* Stop, restart, cleanup and release all undo a force exactly once. */
    als_flags=2;start_active(3,250,"ok");assert(settings==1 && setting_values[0]==1);
    start_active(3,300,"ok");assert(settings==3 && !setting_values[1] && setting_values[2]==1 && storage.data->forced);
    command(2,0,"ok");assert(settings==4 && !setting_values[3] && !(als_flags&8));
    settings=0;start_active(3,250,"ok");assert(settings==1);glassly_sensor_cleanup();assert(settings==2 && !setting_values[1]);
    settings=0;start_active(3,250,"ok");assert(settings==1);uint32_t gen=storage.generation;
    char *r=release_capture(gen,0);assert(strstr(r,"released") && settings==2 && !setting_values[1]);free(r);
    /* A failed sample schedule cancels the start and its force. */
    settings=0;sample_schedule_error=11;start_active(3,250,"schedule-failed");assert(!storage.data && settings==2 && !setting_values[1]);
    sample_schedule_error=0;settings=0;start_active(3,250,"ok");sample_schedule_error=11;sample();assert(!storage.data && settings==2);
    sample_schedule_error=0;
    /* Draining freezes sampling too. */
    settings=0;start_active(3,250,"ok");gen=storage.generation;r=seal(gen,0);free(r);reads=0;sample();assert(!reads && storage.data);
    r=release_capture(gen,0);free(r);assert(settings==2);
}
int main(void){lifecycle();expiry();boundaries();buffered();draining();release_owned();active_sampling();reset();puts("sensor capture host: lifecycle, freshness, rollover, stale completion, bounds, OOM and active light sampling passed");return 0;}
