/* MIT. Production native adapter with explicit stock boundary mocks. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MM_NOTIFICATION_TEST 1
#include "../../../graphics/notification_native.c"
static registry registry_memory;
static uint32_t ticks=100,free_heap=400000;
static unsigned locked,allocations,post_count,action_count;
static uint8_t peer_state[16],posted[8];
static int post_error;
static const uint8_t *request_data;static size_t request_size;
void glassly_canary_enter(void){assert(!locked);locked=1;}
void glassly_canary_leave(void){assert(locked);locked=0;}
int glassly_canary_layout_valid(void){return 1;}
void *mm_notification_registry(void){return &registry_memory;}
static uint32_t post_mock(uint32_t topic,uint32_t event,const void *p,uint32_t n){
    assert(!locked && topic==0 && event==0x280 && n==8);memcpy(posted,p,n);post_count++;return post_error;
}
static uint8_t *peer_mock(const uint8_t *p){assert(!locked && p[0]==1);return peer_state;}
static uint32_t action_mock(const uint8_t *p,const uint8_t *uid,uint8_t kind){
    assert(!locked && p[0]==1 && uid[0]==42 && kind==0);action_count++;return 0;
}
void *mm_notification_function(uintptr_t address){
    if(address==0x042361b8)return post_mock;
    if(address==0x042113ce)return peer_mock;
    if(address==0x04318ee6)return action_mock;
    assert(!"unknown native call");return 0;
}
static int bytes(void *r,const uint8_t **p,size_t *n){assert(r);*p=request_data;*n=request_size;return 1;}
static void release(void **r){*r=0;}
static void *json(const char *s){assert(!locked);size_t n=strlen(s)+1;char *p=malloc(n);memcpy(p,s,n);return p;}
static void *status(uint32_t s,const char *p){(void)p;assert(s==2 || s==4);return json("invalid");}
static void *alloc(size_t n){assert(!locked);allocations++;return malloc(n);}
static void dealloc(void *p){assert(!locked);free(p);}
static uint32_t clock_now(void){return ticks;}
static uint32_t free_bytes(void){assert(!locked);return free_heap;}
const mm_graphics_platform mm_graphics_native={.request_bytes=bytes,.release=release,.json=json,.status=status,.alloc=alloc,.free=dealloc,.now=clock_now,.free_bytes=free_bytes};
static char *command(uint8_t op){
    static uint8_t p[9]={'A','N',1,0,42,0,0,0,0};p[3]=op;
    request_data=p;request_size=op==4?9:4;void *response=0;
    glassly_notification_command(0x78,(void *)1,0,&response);assert(response);return response;
}
static void expect(uint8_t op,const char *expected){char *r=command(op);assert(strstr(r,expected));free(r);}
static void source(uint8_t event){uint8_t p[14]={1,2,3,4,5,6,event,0x18,1,1,42};glassly_notification_observe(0x25a,p,14);}
int main(void){
    expect(3,"unavailable");expect(1,"\"active\":1");
    unsigned before=allocations;source(0);assert(allocations==before);
    expect(0,"414e0101001801012a000000");
    owner *o=registry_memory.context;
    uint8_t descriptor[16]={1,2,3,4,5,6,0};
    uint8_t body[]={42,0,0,0,1,3,0,'a','b','c',3,2,0,'h','i'};
    descriptor[12]=sizeof(body);
    lock();assert(mm_ancs_ingress_event(&o->ingress,0x25b,descriptor,16,body,sizeof(body)));unlock();
    memset(body,0,sizeof(body));expect(0,"616263");
    uint8_t action_peer[6];uint32_t generation;
    mm_ancs_uid *item=&o->ingress.uids[0];
    item->flags=8;assert(mm_ancs_ingress_action(&o->ingress,42,0,action_peer,&generation));
    assert(!mm_ancs_ingress_action(&o->ingress,42,1,action_peer,&generation));
    item->flags=16;assert(!mm_ancs_ingress_action(&o->ingress,42,0,action_peer,&generation));
    assert(mm_ancs_ingress_action(&o->ingress,42,1,action_peer,&generation));
    item->flags=32;assert(!mm_ancs_ingress_action(&o->ingress,42,0,action_peer,&generation));
    assert(!mm_ancs_ingress_action(&o->ingress,42,1,action_peer,&generation));item->flags=24;
    uint16_t head=o->relay.ancs_head;
    uint8_t bad[]={42,0,0,0,1,1,0,'x',3,4,0,'y'};descriptor[12]=sizeof(bad);
    lock();assert(!mm_ancs_ingress_event(&o->ingress,0x25b,descriptor,16,bad,sizeof(bad)));unlock();assert(head==o->relay.ancs_head);
    uint8_t app[]={ 'a',0,0,4,0,'N','a','m','e'};descriptor[6]=1;descriptor[12]=sizeof(app);
    lock();assert(mm_ancs_ingress_event(&o->ingress,0x25b,descriptor,16,app,sizeof(app)));unlock();expect(0,"4e616d65");
    expect(4,"\"actionResult\":1");assert(post_count==1);
    glassly_notification_observe(ACTION_EVENT,posted,8);assert(action_count==1 && peer_state[12]==1);expect(0,"\"actionResult\":2");
    glassly_notification_observe(ACTION_EVENT,posted,8);assert(action_count==1);
    expect(4,"\"actionResult\":1");glassly_notification_observe(ACTION_EVENT,posted,8);expect(0,"\"actionResult\":3");assert(action_count==1);
    peer_state[12]=0;expect(4,"\"actionResult\":1");source(2);source(0);
    glassly_notification_observe(ACTION_EVENT,posted,8);assert(action_count==1);expect(0,"\"actionResult\":4");
    source(0);assert(o->relay.ancs_tail!=o->relay.ancs_head);
    uint32_t session=o->ingress.session;
    uint8_t disconnected[12]={1,2,3,4,5,6};glassly_notification_observe(0x258,disconnected,12);
    assert(o->ingress.session==session+1 && o->relay.ancs_tail==o->relay.ancs_head);
    expect(4,"\"actionResult\":4");
    source(0);assert(o->ingress.session==session+2);
    source(1);assert(o->ingress.session==session+2);
    source(0);post_error=11;free(command(4));expect(0,"\"actionResult\":5");post_error=0;
    source(0);for(unsigned i=0;i<400;i++)source(1);assert(o->relay.ancs_drops>0);
    expect(2,"\"active\":0");expect(1,"\"active\":1");assert(o->relay.ancs_tail==o->relay.ancs_head);
    ticks+=90001;source(0);expect(0,"\"active\":0");expect(4,"\"actionResult\":4");
    expect(1,"\"active\":1");source(0);glassly_notification_cleanup();assert(!o->relay.ancs_lease_deadline && !o->ingress.connected);
    expect(1,"\"active\":1");source(0);expect(0,"414e0101");
    free(registry_memory.context);puts("Native ANCS adapter: delivery, borrowed data, malformed atomicity, actions, busy, stale UID, disconnect, overflow, lease and cleanup passed");
}
