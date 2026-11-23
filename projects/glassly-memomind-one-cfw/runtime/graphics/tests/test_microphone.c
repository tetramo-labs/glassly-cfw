#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MM_MICROPHONE_TEST 1
#include "../microphone_native.c"
static uint8_t memory[0x60000];
static uint32_t ticks,post_error,timer_error,start_calls,stop_calls,cancel_calls,timer_calls;
static unsigned critical,app_worker,delay_start,fail_stop,cancel_during_start;
static uint8_t control_job[32],watch_job[8];static uint32_t control_size;
static const uint8_t peer[6]={1,2,3,4,5,6};
static const uint8_t uuid[20]={4,0,0,0,0,0,0x20,0x24,0,0,0x10,0,0x80,0,0,0x80,0x5f,0x9b,0x34,0xfb};
static const uint8_t config[13]={'M','C',1,1,0,1,3,0,160,0,160,0,2};
void *mm_microphone_memory(uintptr_t a){assert(a>=0x02000000 && a<0x02060000);return memory+(a-0x02000000);}
int glassly_canary_layout_valid(void){return 1;}
void glassly_canary_enter(void){assert(!critical);critical=1;}
void glassly_canary_leave(void){assert(critical);critical=0;}
static uint32_t clock_now(void){assert(!critical);return ticks;}
static uint32_t queue(uint32_t task,uint32_t event,const void *p,uint32_t n){
    assert(!critical && task==0x13 && event==CONTROL_EVENT && n<=sizeof(control_job));
    if(!post_error){memcpy(control_job,p,n);control_size=n;}return post_error;
}
static uint32_t timer(uint32_t task,uint32_t event,const void *p,uint32_t n,uint32_t delay){
    assert(app_worker && !critical && task==0x13 && event==WATCH_EVENT && n==8 && delay==1000);
    timer_calls++;if(!timer_error)memcpy(watch_job,p,n);return timer_error;
}
static uint32_t cancel(uint32_t task,uint32_t event){assert(app_worker && !critical && task==0x13 && event==1);cancel_calls++;return 0;}
static void format(uint32_t selected){assert(app_worker && !critical && selected==0);}
static void native_start(uint32_t event,const void *p,uint32_t n){
    assert(app_worker && !critical && event==1 && n==7 && !memcmp(p,peer,6) && ((const uint8_t *)p)[6]==5);
    start_calls++;memcpy((void *)MEM(0x020127e0),p,6);*MEM(0x02011968)=1;
    if(!delay_start)*MEM(0x0201196c)=1;
    if(cancel_during_start)glassly_microphone_cleanup();
}
static uint32_t native_stop(void){
    assert(app_worker && !critical);stop_calls++;
    if(!fail_stop){*MEM(0x0201196c)=0;*MEM(0x02011968)=0;}
    return fail_stop?9:0;
}
static void native_cleanup(const char *reason){assert(app_worker && !critical && reason && !*MEM(0x0201196c));*MEM(0x02011968)=0;}
void *mm_microphone_function(uintptr_t a){
    switch(a){case 0x0200f6e8:return clock_now;case 0x042361b8:return queue;case 0x042363f4:return timer;
    case 0x04236404:return cancel;case 0x04209de8:return format;case 0x0420a316:return native_start;case 0x0420a232:return native_stop;case 0x04209998:return native_cleanup;}
    assert(0);return 0;
}
typedef struct {const uint8_t *p;size_t n;} request;
static int request_bytes(void *r,const uint8_t **p,size_t *n){request *q=r;*p=q->p;*n=q->n;return 1;}
static void release(void **p){*p=0;}
static void *json(const char *s){size_t n=strlen(s)+1;char *p=malloc(n);assert(p);memcpy(p,s,n);return p;}
static void *status(uint32_t code,const char *s){(void)code;(void)s;return json("allocation failed");}
const mm_graphics_platform mm_graphics_native={.request_bytes=request_bytes,.release=release,.json=json,.status=status,.alloc=malloc,.free=free};
static char *send(const uint8_t *p,size_t n){request q={p,n};void *response=0;uint8_t event=1;glassly_microphone_command(0x77,&q,&event,&response);assert(response);return response;}
static char *op(uint8_t operation){uint8_t p[4]={'M','C',1,operation};return send(p,4);}
static void queued(const uint8_t *p,size_t n){char *s=send(p,n);assert(strstr(s,"\"result\":\"queued\""));free(s);}
static void run_job(void){assert(control_size);app_worker=1;glassly_microphone_task(CONTROL_EVENT,control_job,control_size);app_worker=0;control_size=0;}
static void tick(void){uint8_t p[8];memcpy(p,watch_job,8);app_worker=1;glassly_microphone_task(WATCH_EVENT,p,8);app_worker=0;}
static void reset(void){
    memset(memory,0,sizeof(memory));memset(watch_job,0,8);control_size=0;ticks=100;
    post_error=timer_error=start_calls=stop_calls=cancel_calls=timer_calls=0;
    critical=app_worker=delay_start=fail_stop=cancel_during_start=0;
    *MEM(0x02013c7c)=1;*MEM(0x02013c7e)=4;memcpy((void *)MEM(0x02013c83),peer,6);
}
static void begin(void){queued(config,13);assert(start_calls==0);run_job();assert(start_calls==1 && get()->phase==STREAMING);}
static void check_quiet(void){uint8_t data[12]={0x52,0x92};assert(!glassly_microphone_spp(peer,uuid,data,sizeof(data)));}
static void test_lifecycle(void){
    reset();check_quiet();begin();uint8_t audio[61]={0x52,0x92,0,0,0,0,1,0,0,0,0,255};
    assert(glassly_microphone_spp(peer,uuid,audio,sizeof(audio)));assert(get()->frames==1);
    char *s=op(2);assert(strstr(s,"4d43010100010300a000a00002010101000000a000"));free(s);
    ticks+=80000;queued(config,13);run_job();assert(start_calls==1 && stop_calls==0);
    ticks+=89999;assert(glassly_microphone_spp(peer,uuid,audio,sizeof(audio)));
    ticks++;check_quiet();assert(*MEM(0x0201196c)==1);tick();assert(stop_calls==1 && !*MEM(0x0201196c) && get()->error==EXPIRED);
    uint8_t other[20];memcpy(other,uuid,20);other[7]=0x26;assert(glassly_microphone_spp(peer,other,audio,sizeof(audio)));
}
static void test_cancellation_and_failures(void){
    reset();queued(config,13);glassly_microphone_cleanup();run_job();assert(!start_calls && get()->error==CANCELLED);
    reset();cancel_during_start=1;queued(config,13);run_job();assert(start_calls==1 && stop_calls==1);check_quiet();
    reset();timer_error=11;queued(config,13);run_job();assert(!start_calls && get()->error==SCHEDULE);check_quiet();
    reset();post_error=11;char *s=send(config,13);assert(strstr(s,"queue-failed"));free(s);assert(!start_calls && !get()->pending);
    reset();begin();fail_stop=1;s=op(3);free(s);check_quiet();run_job();assert(get()->phase==STOPPING && stop_calls==1);
    fail_stop=0;tick();assert(get()->phase==IDLE && stop_calls==2);
    reset();begin();timer_error=11;tick();check_quiet();assert(stop_calls==1 && get()->error==SCHEDULE);
    reset();begin();post_error=11;s=op(3);free(s);check_quiet();tick();assert(stop_calls==1);
}
static void test_ownership_and_delayed_start(void){
    reset();*MEM(0x0201196c)=1;queued(config,13);run_job();assert(!start_calls && get()->error==BUSY);
    reset();*MEM(0x02013c7c)=3;queued(config,13);run_job();assert(!start_calls && get()->error==NO_LINK);
    reset();delay_start=1;queued(config,13);run_job();assert(get()->phase==STARTING);ticks+=5000;tick();assert(!get()->active && get()->error==START_TIMEOUT && cancel_calls==1 && !*MEM(0x02011968));delay_start=0;queued(config,13);run_job();assert(start_calls==2 && get()->phase==STREAMING);
    reset();begin();MEM(0x020127e0)[0]=99;tick();check_quiet();assert(!stop_calls && get()->error==OWNER_CHANGED);
    reset();begin();glassly_microphone_link(0,0,peer);check_quiet();tick();assert(stop_calls==1 && get()->error==DISCONNECTED);
    reset();begin();glassly_microphone_cleanup();check_quiet();tick();assert(stop_calls==1);
    reset();delay_start=1;queued(config,13);run_job();delay_start=0;uint8_t start[7]={1,2,3,4,5,6,5};app_worker=1;glassly_microphone_task(1,start,7);app_worker=0;assert(get()->phase==STREAMING && start_calls==2);
    app_worker=1;glassly_microphone_task(1,start,7);app_worker=0;assert(start_calls==2);
}
static void test_protocol_and_wrap(void){
    reset();begin();*MEM(0x0201196c)=0;tick();assert(!get()->active && !get()->owned && get()->error==NATIVE);
    reset();uint8_t bad[13];memcpy(bad,config,13);bad[6]=0;char *s=send(bad,13);assert(strstr(s,"unsupported"));free(s);assert(!control_size);
    s=send(config,12);assert(strstr(s,"invalid"));free(s);
    queued(config,13);s=send(config,13);assert(strstr(s,"busy"));free(s);run_job();
    reset();ticks=UINT32_MAX-40000;begin();ticks+=89999;uint8_t audio[12]={0};assert(glassly_microphone_spp(peer,uuid,audio,sizeof(audio)));ticks++;check_quiet();tick();assert(stop_calls==1);
    reset();uint8_t dry[13];memcpy(dry,config,13);dry[12]=0;queued(dry,13);run_job();assert(!start_calls && get()->phase==CONFIGURED);ticks+=90000;tick();assert(!get()->active && !stop_calls);
    reset();*MEM(0x02013c7c)=2;*MEM(0x02013c80)=9;memcpy((void *)MEM(0x02013c8f),peer,6);begin();assert(glassly_microphone_iap2(peer,9,0,0));assert(glassly_microphone_iap2(peer,8,0,0));glassly_microphone_cleanup();assert(!glassly_microphone_iap2(peer,9,0,0));assert(glassly_microphone_iap2(peer,8,0,0));
}
int main(void){test_lifecycle();test_cancellation_and_failures();test_ownership_and_delayed_start();test_protocol_and_wrap();puts("microphone lifecycle: passed");}
