/* Host ownership/scheduling tests. Native routines are explicit mocks, not an
 * assertion that stock LVGL handles OOM gracefully. ASan/UBSan catch lifetimes. */
#include "graphics.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef struct request { uint8_t *data; size_t length; int valid; } request;
typedef struct image { void *parent; mm_callback deleted; void *owner;
    const mm_native_image *source; struct image *next; } image;
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
static char last_response[1024];

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
static int on_delete(void *p,mm_callback cb,void *o) {
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
    glassly_graphics_command(0x7d,request_live,event,&response);
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
static void geometry(uint8_t *m,uint8_t count) {
    memset(m,0,2+20u*count);m[0]=36;m[1]=count;
    for(unsigned i=0;i<count;i++) {
        uint8_t *r=m+2+20*i;r[0]=1;r[2]=(uint8_t)(1+i%15);r[4]=(uint8_t)i;r[8]=(uint8_t)i;
    }
}
static void input_validation(void) {
    uint8_t e=97,m[42];geometry(m,2);
    unsigned before=posts;
    for(size_t n=0;n<sizeof(m);n++) {
        void *r=command(m,n,1,&e);assert(r && strstr(r,"invalid"));release(&r);
    }
    void *r=command(m,sizeof(m),0,&e);assert(r && strstr(r,"invalid"));release(&r);
    r=command(m,sizeof(m),1,0);assert(r && strstr(r,"invalid"));release(&r);
    m[22]=14;r=command(m,sizeof(m),1,&e);assert(r && strstr(r,"invalid"));release(&r);
    assert(posts==before && !images && own_allocations==0);
    uint8_t huge[MM_GEOMETRY_MAX_MESSAGE+1]={0};r=command(huge,sizeof(huge),1,&e);
    assert(r && strstr(r,"invalid"));release(&r);
}
static void correlation_and_render(void) {
    uint8_t m[MM_GEOMETRY_MAX_MESSAGE],e=231;geometry(m,255);
    unsigned sent=sends,created=image_creates;
    assert(!command(m,sizeof(m),1,&e));assert(queued && !images && sends==sent && !own_allocations);
    /* Original TLV storage has been freed; queued copy alone survives. */
    deliver();assert(sends==sent+1 && last_event==e && strstr(last_response,"scheduled"));
    assert(images && timers && own_allocations==2 && image_creates==created+1);
    assert(images->source->data[64]==0x12);
    const mm_native_image *descriptor=images->source;
    geometry(m,1);m[4]=15;now_value=100;
    assert(!command(m,22,1,&e));deliver();assert(images->source==descriptor && image_creates==created+1);
    assert(images->source->data[64]==0xf2);
    now_value=1099;tick_once();assert(images);
    now_value=1100;tick_once();assert(!images && !timers && !own_allocations);
}
static void failure_paths(void) {
    uint8_t m[22],e=7;geometry(m,1);
    /* job, small owner, then large pixel allocation, each failure independently */
    for(int failure=1;failure<=3;failure++) {
        clear_all();fail_alloc_number=failure;
        void *r=command(m,sizeof(m),1,&e);
        if(failure==1){assert(r && strstr(r,"allocation-failed"));release(&r);}
        else{assert(!r);deliver();assert(strstr(last_response,"allocation-failed"));}
        assert(!images && !timers && !own_allocations);
    }
    for(int failure=0;failure<3;failure++) {
        clear_all();fail_image=failure==0;fail_event=failure==1;fail_timer=failure==2;
        assert(!command(m,sizeof(m),1,&e));deliver();assert(strstr(last_response,"allocation-failed"));
        assert(!images && !timers && !own_allocations);
    }
    clear_all();free_value=1024;assert(!command(m,sizeof(m),1,&e));deliver();
    assert(strstr(last_response,"allocation-failed") && !images && !own_allocations);
    clear_all();free_value=110*1024;assert(!command(m,sizeof(m),1,&e));deliver();
    assert(strstr(last_response,"allocation-failed") && !images && !timers && !own_allocations);
    clear_all();drop=1;unsigned sent=sends;assert(!command(m,sizeof(m),1,&e));
    assert(!queued && !images && !own_allocations && sends==sent);
    clear_all();fail_json=1;uint8_t bad=0;void *r=command(&bad,1,1,&e);
    assert(r && !strcmp(r,"status4"));release(&r);
    fail_status=1;r=command(&bad,1,1,&e);assert(!r && !request_live);
    clear_all();
}
static void lifecycle(void) {
    uint8_t m[22],e=1;geometry(m,1);
    for(unsigned i=0;i<100;i++) {
        now_value=0xfffffff0u;
        assert(!command(m,sizeof(m),1,&e));deliver();
        now_value=0x10;tick_once();assert(images);
        if(i%4==0) { uint8_t clear=11;assert(!command(&clear,1,1,&e));deliver();assert(strstr(last_response,"cleared")); }
        else if(i%4==1) { launcher=0;tick_once();launcher=1; }
        else if(i%4==2) { screen_value=(void *)0x5678;tick_once();screen_value=(void *)0x1234; }
        else delete_image(images); /* stock parent cleanup callback */
        assert(!images && !timers && !own_allocations);
    }
    launcher=0;assert(!command(m,sizeof(m),1,&e));deliver();
    assert(strstr(last_response,"stock-ui-active") && !images);launcher=1;
    uint8_t empty[]={36,0};assert(!command(empty,sizeof(empty),1,&e));deliver();assert(!images);
    assert(!command(m,sizeof(m),1,&e));deliver();now_value=500;
    assert(!command(empty,sizeof(empty),1,&e));deliver();now_value=1499;tick_once();assert(images);
    now_value=1500;tick_once();assert(!images && !own_allocations);
}
static void malformed_queue(void) {
    uint8_t m[22],e=22;geometry(m,1);unsigned sent=sends;
    assert(!command(m,sizeof(m),1,&e));queued[10]++;deliver();
    assert(sends==sent+1 && strstr(last_response,"invalid") && !images);
    assert(!command(m,sizeof(m),1,&e));queued[8]=2;deliver();assert(strstr(last_response,"invalid"));
    assert(!command(m,sizeof(m),1,&e));queued[1]=0;sent=sends;deliver();assert(sent==sends);
    assert(!command(m,sizeof(m),1,&e));queued[6]=0;queued[7]=0;sent=sends;deliver();assert(sent==sends);
    assert(!images && !timers && !own_allocations);
}
static void diagnostic(void) {
    void *r=0;glassly_graphics_probe(0x7e,0,0,&r);assert(r);
    assert(strstr(r,"\"width\":600") && strstr(r,"\"freeBytesHex\":\"00100000\""));
    assert(strstr(r,"\"lowWaterBytesHex\":\"00012345\"") && !strchr(r,'@'));
    assert(strlen(r)<503);release(&r);
    assert(!images && !timers && !own_allocations);
}
int main(void) {
    input_validation();correlation_and_render();clear_all();failure_paths();lifecycle();clear_all();
    malformed_queue();diagnostic();clear_all();
    printf("PASS: strict requests/max255 geometry, correlated execution, queue drop, allocation failures, "
           "100 lifecycle cycles, expiry/wrap, stock UI yield, copied TLV lifetime; %u requests freed, %u completions\n",
           request_frees,sends);
    return 0;
}
