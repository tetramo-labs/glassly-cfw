/* Host ownership/scheduling tests. Native routines are explicit mocks, not an
 * assertion that stock LVGL handles OOM gracefully. ASan/UBSan catch lifetimes. */
#include "graphics.h"
#include <stdint.h>
static uint8_t head_state;
#define MM_INPUT_HEAD_STATE head_state
#include "../input.c" /* Production TU included for explicit sequence-exhaustion boundary injection. */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef struct request { uint8_t *data; size_t length; int valid; } request;
typedef struct image { void *parent; mm_callback deleted; void *owner;
    const mm_native_image *source; int hidden; struct image *next; } image;
typedef struct timer { mm_callback callback; void *owner; struct timer *next; } timer;
static request *request_live;
static image *images;
static timer *timers;
static uint8_t *queued;
static void *screen_value=(void *)0x1234;
static uint32_t now_value,free_value=1024*1024;
static int launcher=1,drop,fail_alloc_number,alloc_attempts,own_allocations;
static int fail_image,fail_event,fail_timer,fail_json,fail_status;
static unsigned request_frees,response_frees,posts,sends,source_calls,image_creates;
static uint8_t last_event;
static char last_response[2048];
static unsigned hidden_calls, input_sends;

static int bytes(void *r,const uint8_t **d,size_t *n) {
    if (!r || r!=request_live || !request_live->valid) return 0;
    *d=request_live->data; *n=request_live->length; return 1;
}
static void release(void **p) {
    assert(p && *p);
    if (*p==request_live) {
        free(request_live->data); free(request_live); request_live=0; request_frees++;
    } else { free(*p); response_frees++; }
    *p=0;
}
static void *json(const char *s) { return fail_json ? 0 : strcpy(malloc(strlen(s)+1),s); }
static void *status(uint32_t n,const char *text) {
    assert(n==4 && !text); return fail_status ? 0 : strcpy(malloc(8),"status4");
}
static void *allocate(size_t n) {
    alloc_attempts++;
    if (alloc_attempts==fail_alloc_number) return 0;
    void *p=malloc(n); assert(p); own_allocations++; return p;
}
static void deallocate(void *p) { assert(p && own_allocations>0); own_allocations--; free(p); }
static void post(const void *data,size_t length) {
    assert(!request_live && !queued); posts++;
    if (drop) return;
    queued=calloc(1,length+8); assert(queued);
    queued[1]=0xbf;queued[4]=0x4c;queued[5]=0x47;
    queued[6]=(uint8_t)length;queued[7]=(uint8_t)(length>>8);
    memcpy(queued+8,data,length);
}
static void send(uint8_t event,void *response) {
    assert(response && strlen(response)<sizeof(last_response));
    last_event=event;sends++;strcpy(last_response,response);
}
static void *screen(void) { return screen_value; }
static int launcher_active(void) { return launcher; }
static void *find(void *parent,mm_callback cb) {
    for (image *i=images;i;i=i->next) if(i->parent==parent && i->deleted==cb) return i->owner;
    return 0;
}
static void *create_image(void *parent) {
    if(fail_image) return 0;
    image *i=calloc(1,sizeof(*i));assert(i);i->parent=parent;i->next=images;images=i;image_creates++;return i;
}
void glassly_input_hide(void *p) {image *i=p;assert(!i->hidden && !i->source);i->hidden=1;hidden_calls++;}
void glassly_input_send(uint8_t event,void *response) {input_sends++;send(event,response);puts(response);}
static int on_delete(void *p,mm_callback cb,void *o) {
    if(cb==input_deleted) assert(((image *)p)->hidden);
    if(fail_event) return 0;
    image *i=p;i->deleted=cb;i->owner=o;return 1;
}
static void image_source(void *p,const mm_native_image *source) {
    image *i=p;assert(source && source->data);
    assert(source->header==((350u<<21)|(600u<<10)|9u));
    assert(source->data_size==105064);
    for(unsigned n=0;n<16;n++) {
        uint32_t c;memcpy(&c,source->data+4*n,4);
        assert(c==(0xff000000u|(n*17u)*0x010101u));
    }
    i->source=source;source_calls++;
}
static void delete_image(void *p) {
    image *i=p,**link=&images;
    while(*link && *link!=i)link=&(*link)->next;
    assert(*link==i);*link=i->next;
    if(i->deleted)i->deleted(i->owner);
    free(i);
}
static void invalidate(const mm_native_image *d) { assert(d && d->data_size==105064); }
static void *userdata(void *p) { return p; }
static void *create_timer(mm_callback cb,uint32_t period,void *o) {
    assert(period==20);
    if(fail_timer)return 0;
    timer *t=malloc(sizeof(*t));assert(t);t->callback=cb;t->owner=o;t->next=timers;timers=t;return t;
}
static void delete_timer(void *p) {
    timer *t=p,**link=&timers;
    while(*link && *link!=t)link=&(*link)->next;
    assert(*link==t);*link=t->next;free(t);
}
static void *timer_userdata(void *p) { return ((timer *)p)->owner; }
static uint32_t now(void) { return now_value; }
static uint32_t free_bytes(void) { return free_value; }
static uint32_t low_water(void) { return 0x12345; }
const mm_graphics_platform mm_graphics_native={bytes,release,json,status,allocate,deallocate,
    post,send,screen,launcher_active,find,create_image,on_delete,image_source,delete_image,
    invalidate,userdata,create_timer,delete_timer,timer_userdata,now,free_bytes,low_water};

static void request_set(const uint8_t *data,size_t n,int valid) {
    assert(!request_live);request_live=malloc(sizeof(*request_live));assert(request_live);
    request_live->data=malloc(n?n:1);assert(request_live->data);memcpy(request_live->data,data,n);
    request_live->length=n;request_live->valid=valid;
}
static void *command(const uint8_t *data,size_t n,int valid,const uint8_t *event) {
    request_set(data,n,valid);void *response=(void *)0xdeadbeef;
    glassly_input_command(0x7c,request_live,event,&response);
    assert(!request_live);return response;
}
static void deliver(void) {
    assert(queued);uint8_t *e=queued;queued=0;glassly_graphics_display(e);free(e);
}
static void tick_once(void) { assert(timers);timer *t=timers;t->callback(t); }
static void clear_all(void) {
    while(images)delete_image(images);
    assert(!timers && !own_allocations && !request_live);
    if(queued){free(queued);queued=0;}
    alloc_attempts=fail_alloc_number=fail_image=fail_event=fail_timer=fail_json=fail_status=drop=0;
    launcher=1;screen_value=(void *)0x1234;now_value=0;free_value=1024*1024;
}
static void put32(uint8_t *p,uint32_t n) {
    for(unsigned i=0;i<4;i++) p[i]=(uint8_t)(n>>(8*i));
}
static void execute(const uint8_t *data,size_t n,const char *expected) {
    uint8_t event=0xa7;unsigned sent=sends;
    assert(!command(data,n,1,&event));assert(queued && sends==sent);
    assert(queued[8]==2 && queued[9]==event && queued[10]==n && !queued[11]);
    deliver();assert(sends==sent+1 && last_event==event);
    char result[80];snprintf(result,sizeof(result),"\"result\":\"%s\"",expected);
    if(!strstr(last_response,result))fprintf(stderr,"op=%u expected=%s got=%s\n",data[1],expected,last_response);
    assert(strstr(last_response,result));
}
static input_owner *current(void) {return input_find(screen_value);}
static void subscribe(uint32_t nonce,uint8_t mask,const char *result) {
    uint8_t data[7]={1,1,mask};put32(data+3,nonce);execute(data,7,result);
}
static void poll(uint32_t nonce,uint32_t ack,const char *result) {
    uint8_t data[10]={1,2};put32(data+2,nonce);put32(data+6,ack);execute(data,10,result);
}
static void stop(uint32_t nonce,const char *result) {
    uint8_t data[6]={1,3};put32(data+2,nonce);execute(data,6,result);
}
static void observe(unsigned cls,unsigned id,unsigned length) {
    uint8_t envelope[8]={0,(uint8_t)cls,0,0,(uint8_t)id,(uint8_t)(id>>8),
                         (uint8_t)length,(uint8_t)(length>>8)};
    int allocations=alloc_attempts,owned=own_allocations;
    unsigned sent=sends,posted=posts,created=image_creates,hidden=hidden_calls;
    image *old_images=images;timer *old_timers=timers;
    glassly_input_observe(envelope);
    assert(allocations==alloc_attempts && owned==own_allocations && sent==sends && posted==posts);
    assert(created==image_creates && hidden==hidden_calls && old_images==images && old_timers==timers);
}
static void passive_and_validation(void) {
    const uint8_t status_message[]={1,0};
    execute(status_message,2,"ok");
    assert(strstr(last_response,"\"active\":false") && strstr(last_response,"\"records\":[]"));
    assert(!images && !timers && !own_allocations);
    uint8_t e=8,data[20]={1};unsigned posted=posts;
    for(unsigned op=0;op<6;op++) for(size_t n=0;n<sizeof(data);n++) {
        memset(data,0,sizeof(data));data[0]=1;data[1]=(uint8_t)op;
        if(input_valid(data,n))continue;
        void *r=command(data,n,1,&e);assert(r && strstr(r,"invalid"));release(&r);
    }
    void *r=command(status_message,2,0,&e);assert(r && strstr(r,"invalid"));release(&r);
    r=command(status_message,2,1,0);assert(r && strstr(r,"invalid"));release(&r);
    assert(posts==posted && !own_allocations);
    free_value=32768;r=command(status_message,2,1,&e);
    assert(r && strstr(r,"allocation-failed"));release(&r);free_value=1024*1024;
    fail_alloc_number=alloc_attempts+1;r=command(status_message,2,1,&e);
    assert(r && strstr(r,"allocation-failed"));release(&r);fail_alloc_number=0;
    drop=1;assert(!command(status_message,2,1,&e));assert(!queued && !own_allocations);drop=0;
    fail_json=1;uint8_t bad=0;r=command(&bad,1,1,&e);assert(r && !strcmp(r,"status4"));release(&r);
    fail_status=1;r=command(&bad,1,1,&e);assert(!r);fail_json=fail_status=0;
}
static void filter_and_masks(void) {
    glassly_input_observe(0);observe(2,0x1f7b,0);assert(!images);
    subscribe(123,3,"ok");assert(images->hidden && !images->source && own_allocations==1);
    input_owner *o=current();assert(o && !o->count && !o->sequence);
    now_value=99;
    /* All class byte/id combinations: only 88 combinations admitted, including
     * the four high-bit aliases of each known low-six-bit class; the raise
     * timeout (class 3 id 5) of each alias is not. */
    for(unsigned cls=0;cls<256;cls++) for(unsigned id=0;id<65536;id++) observe(cls,id,0);
    assert(o->sequence==88 && o->count==32 && o->drops==56 && o->ack==0);
    for(unsigned cls=2;cls<=3;cls++) for(unsigned len=1;len<65536;len++) observe(cls,cls==2?0x1f7b:1,len);
    assert(o->sequence==88);
    assert(o->records[o->head].tick==99);
    stop(123,"ok");assert(!images && !timers && !own_allocations);
    for(unsigned mask=1;mask<=2;mask++) {
        subscribe(123,(uint8_t)mask,"ok");observe(2,0x1f7b,0);observe(3,1,0);
        o=current();assert(o->sequence==1 && o->records[o->head].class_id==(mask==1?2:3));
        stop(123,"ok");
    }
}
static unsigned last_id(const input_owner *o) {
    return o->records[(o->head+o->count-1u)%MM_INPUT_CAPACITY].id;
}
static void head_state_transitions(void) {
    head_state=0;subscribe(9,2,"ok");input_owner *o=current();
    tick_once();assert(o->sequence==0);
    observe(3,2,0);assert(o->sequence==1 && last_id(o)==2);
    observe(3,2,0);head_state=3;tick_once();assert(o->sequence==1);
    head_state=4;tick_once();assert(o->sequence==1);
    observe(3,5,0);assert(o->sequence==1);
    head_state=0;tick_once();assert(o->sequence==2 && last_id(o)==3);
    observe(3,3,0);tick_once();assert(o->sequence==2);
    head_state=3;tick_once();assert(o->sequence==3 && last_id(o)==2);
    observe(3,3,0);assert(o->sequence==4 && last_id(o)==3);
    tick_once();assert(o->sequence==5 && last_id(o)==2);
    head_state=0;stop(9,"ok");
    head_state=3;subscribe(9,1,"ok");o=current();tick_once();assert(o->sequence==0);
    head_state=0;stop(9,"ok");assert(!images && !timers && !own_allocations);
}
static void acknowledgements_and_sessions(void) {
    subscribe(0xaabbccdd,3,"ok");input_owner *o=current();
    for(unsigned i=0;i<12;i++) {now_value=i;observe(2,0x1f7b,0);}
    now_value=15;poll(o->nonce,0,"ok");assert(o->count==12 && o->ack==0 && o->renewed==15);
    assert(strstr(last_response,"\"sequence\":8,\"id\"") && !strstr(last_response,"\"sequence\":9,\"id\""));
    char lost[2048];strcpy(lost,last_response);
    now_value=16;poll(o->nonce,0,"ok");assert(!strcmp(last_response,lost));
    poll(o->nonce,3,"ok");assert(o->count==9 && o->ack==3 && o->records[o->head].sequence==4);
    poll(o->nonce,1,"ok");assert(o->count==9 && o->ack==3);
    poll(o->nonce,3,"ok");assert(o->count==9);
    uint32_t renewed=o->renewed;now_value=20;
    poll(o->nonce,13,"invalid");assert(o->count==9 && o->renewed==renewed);
    poll(99,3,"session-conflict");stop(99,"session-conflict");
    subscribe(99,3,"session-conflict");subscribe(o->nonce,1,"session-conflict");
    assert(o->renewed==renewed && o->sequence==12);
    subscribe(o->nonce,3,"ok");assert(o->renewed==20 && o->sequence==12 && o->count==9);
    now_value=21;execute((uint8_t[]){1,0},2,"ok");
    assert(o->renewed==20 && strstr(last_response,"\"records\":[]"));
    poll(o->nonce,12,"ok");assert(!o->count && o->ack==12);
    stop(o->nonce,"ok");poll(0xaabbccdd,12,"no-session");stop(0xaabbccdd,"no-session");
    subscribe(99,3,"ok");poll(0xaabbccdd,0,"session-conflict");stop(99,"ok");
}
static void overflow_and_sequence_exhaustion(void) {
    subscribe(7,3,"ok");input_owner *o=current();
    for(unsigned i=0;i<40;i++)observe(3,1,0);
    assert(o->count==32 && o->sequence==40 && o->drops==8 && o->records[o->head].sequence==9);
    poll(7,1,"ok");assert(o->count==32 && o->ack==1);
    poll(7,16,"ok");assert(o->count==24 && o->records[o->head].sequence==17);
    /* Explicit internal boundary injection, not a wire operation. */
    o->head=0;o->count=0;o->sequence=UINT32_MAX-1;o->ack=UINT32_MAX-1;o->drops=UINT32_MAX-1;
    now_value=UINT32_MAX;o->renewed=now_value;
    observe(2,0x1fb9,0);assert(o->sequence==UINT32_MAX && o->count==1 && o->exhausted);
    observe(3,8,0);observe(3,8,0);
    assert(o->drops==UINT32_MAX && o->exhausted && o->count==1);
    poll(7,UINT32_MAX-1,"ok");assert(strstr(last_response,"\"exhausted\":true"));
    assert(strstr(last_response,"\"tick\":4294967295,\"sequence\":4294967295"));
    poll(7,UINT32_MAX,"ok");assert(!o->count);stop(7,"ok");
}
static void lifecycle_and_failures(void) {
    for(unsigned scenario=0;scenario<5;scenario++) {
        clear_all();now_value=UINT32_MAX-100;launcher=0;subscribe(1,3,"ok");
        input_owner *o=current();assert(o && images->hidden);now_value=100;
        tick_once();observe(2,0x1f7b,0);assert(o->sequence==1); /* no launcher guard */
        if(scenario==0) {now_value=o->renewed+29999u;tick_once();assert(images);
            now_value++;observe(2,0x1f7b,0);assert(o->sequence==1);tick_once();}
        else if(scenario==1) {now_value=o->renewed+30000u;poll(1,0,"no-session");}
        else if(scenario==2) {screen_value=(void *)0x5678;observe(2,0x1f7b,0);assert(o->sequence==1);tick_once();}
        else if(scenario==3) delete_image(images); /* stock ancestor DELETE */
        else {now_value+=20000;subscribe(1,3,"ok");now_value+=29999;tick_once();assert(images);stop(1,"ok");}
        assert(!images && !timers && !own_allocations);
    }
    for(unsigned failure=0;failure<6;failure++) {
        clear_all();
        if(failure==0)fail_alloc_number=2; /* job succeeds, owner allocation fails */
        if(failure==1)fail_image=1;
        if(failure==2)fail_event=1;
        if(failure==3)fail_timer=1;
        if(failure==4)free_value=65536;
        if(failure==5)screen_value=0;
        subscribe(1,3,"allocation-failed");assert(!images && !timers && !own_allocations);
    }
    clear_all();fail_alloc_number=3; /* JSON buffer failure after committed creation */
    subscribe(1,3,"allocation-failed");assert(current());fail_alloc_number=0;
    subscribe(1,3,"ok");stop(1,"ok");
    clear_all();subscribe(1,3,"ok");fail_json=1;fail_status=1;
    uint8_t e=8,m[10]={1,2,1};unsigned sent=sends;
    assert(!command(m,10,1,&e));deliver();assert(sends==sent && current());
    fail_json=fail_status=0;stop(1,"ok");
    clear_all();
}
static void malformed_worker_envelopes(void) {
    uint8_t e=9,m[2]={1,0};unsigned sent=sends;
    assert(!command(m,2,1,&e));queued[1]=2;deliver();assert(sent==sends);
    assert(!command(m,2,1,&e));queued[6]=3;deliver();assert(sent==sends);
    assert(!command(m,2,1,&e));queued[10]=3;deliver();assert(strstr(last_response,"invalid"));
    assert(!images && !timers && !own_allocations);
    glassly_input_display(0);glassly_graphics_display(0);
}
int main(void) {
    passive_and_validation();filter_and_masks();clear_all();head_state_transitions();clear_all();acknowledgements_and_sessions();
    overflow_and_sequence_exhaustion();clear_all();lifecycle_and_failures();malformed_worker_envelopes();clear_all();
    assert(source_calls==0 && input_sends==sends);
    printf("PASS input: strict copied requests; all16777216 class/id pairs; ACK retention, overflow, exhaustion, wrap, hidden lifecycle and failures; %u replies\n",sends);
    return 0;
}
