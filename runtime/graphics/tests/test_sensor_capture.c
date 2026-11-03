#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MM_SENSOR_TEST 1
#include "../sensor_capture.c"
static owner storage;
static unsigned critical,layout=1,allocation_failure,allocations;
static uint32_t ticks;
void *mm_sensor_memory(void){return &storage;}
uint32_t mm_sensor_clock(void){assert(!critical);return ticks;}
int glassly_canary_layout_valid(void){return layout;}
void glassly_canary_enter(void){assert(!critical);critical=1;}
void glassly_canary_leave(void){assert(critical);critical=0;}
typedef struct {const uint8_t *p;size_t n;} request;
static int request_bytes(void *r,const uint8_t **p,size_t *n){if(!r)return 0;request *q=r;*p=q->p;*n=q->n;return 1;}
static void release(void **p){*p=0;}
static void *json(const char *s){assert(!critical);size_t n=strlen(s)+1;assert(n<=208);char *p=malloc(n);assert(p);memcpy(p,s,n);return p;}
static void *status(uint32_t code,const char *s){(void)s;assert(code==4);return json("oom");}
static void *alloc(size_t n){assert(!critical && n==208);allocations++;return allocation_failure?0:malloc(n);}
static void free_out(void *p){assert(!critical);free(p);}
const mm_graphics_platform mm_graphics_native={.request_bytes=request_bytes,.release=release,.json=json,.status=status,.alloc=alloc,.free=free_out};
static char *send(const uint8_t *p,size_t n){request q={p,n};void *out=0;glassly_sensor_command(0x76,&q,0,&out);assert(out && !critical);return out;}
static void command(uint8_t op,uint8_t mask,const char *result){
    uint8_t b[5]={'S','C',1,op,mask};char *s=send(b,op==1?5:4);char expected[64];
    snprintf(expected,sizeof(expected),"\"result\":\"%s\"",result);assert(strstr(s,expected));free(s);
}
static void snapshot(uint8_t *out){
    uint8_t b[4]={'S','C',1,0};char *s=send(b,4);char *hex=strstr(s,"\"stateHex\":\"");assert(hex);hex+=12;
    for(unsigned i=0;i<52;i++){unsigned v;assert(sscanf(hex+i*2,"%2x",&v)==1);out[i]=(uint8_t)v;}assert(hex[104]=='"');free(s);
}
static void reset(void){memset(&storage,0,sizeof(storage));critical=allocation_failure=allocations=0;layout=1;ticks=100;}
static void lifecycle(void){
    reset();uint8_t state[52],imu[14];for(unsigned i=0;i<14;i++)imu[i]=(uint8_t)i;uint8_t als[2]={232,3};
    assert(!glassly_sensor_begin(1));snapshot(state);assert(!state[3] && !state[4]);
    command(1,3,"ok");uint32_t generation=glassly_sensor_begin(1);assert(generation==1 && glassly_sensor_begin(2)==1);
    unsigned before=allocations;glassly_sensor_finish(1,generation,imu);glassly_sensor_finish(2,generation,als);assert(allocations==before);
    memset(imu,255,sizeof(imu));als[0]=0;assert(storage.imu[0]==0 && storage.als[0]==232);
    snapshot(state);assert(state[3]==3 && state[4]==3 && state[5]==3 && state[20]==1 && state[28]==1);
    assert(!memcmp(state+36,storage.imu,14) && state[50]==232 && state[51]==3);
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
int main(void){lifecycle();expiry();boundaries();puts("sensor capture host: lifecycle, freshness, rollover, stale completion, bounds and OOM passed");return 0;}
