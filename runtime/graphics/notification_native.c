/* MIT. Poll-driven ANCS relay; boot-owned storage, no producer allocation. */
#include "notification_native.h"
#include "flash_canary.h"
#include "ancs_ingress.h"
#define P mm_graphics_native
#ifdef MM_NOTIFICATION_TEST
extern void *mm_notification_function(uintptr_t);
extern void *mm_notification_registry(void);
#define FN(a,t) ((t)mm_notification_function(a))
#else
#define FN(a,t) ((t)(uintptr_t)(a))
#endif
#define MAGIC UINT32_C(0x414e4331)
#define ACTION_EVENT 0x280u
#define REPLY_BYTES 1536u
typedef struct {
    mm_notifications relay;
    mm_ancs_ingress ingress;
    uint8_t ring[4096],scratch[1024];
    char *reply;size_t used;unsigned records;
    uint32_t action_uid,action_generation,action_serial;
    uint8_t action_peer[6],action_kind,action_pending,action_result;
} owner;
typedef struct {uint32_t magic,state;owner *context;} registry;
_Static_assert(sizeof(registry)<=128,"ANCS registry fits reserved tail");
static volatile registry *reg(void){
#ifdef MM_NOTIFICATION_TEST
    return mm_notification_registry();
#else
    return (volatile registry *)(uintptr_t)(MM_CANARY_REGISTRY+128);
#endif
}
static void lock(void){glassly_canary_enter();}
static void unlock(void){glassly_canary_leave();}
static void noop(void *p){(void)p;}
static void *allocate(void *p,size_t n){owner *o=p;return n==4096?o->ring:n<=1024?o->scratch:0;}
static void deallocate(void *p,void *b){(void)p;(void)b;}
static uint32_t now(void *p){(void)p;return P.now();}
static uint32_t side(void *p){(void)p;return 1;}
static uintptr_t timer_new(void *p,void (*cb)(void *),void *arg){(void)p;(void)cb;(void)arg;return 1;}
static int timer_start(void *p,uintptr_t timer,uint32_t ms){(void)p;(void)timer;(void)ms;return 0;}
static int timer_stop(void *p,uintptr_t timer){(void)p;(void)timer;return 0;}
static void text(owner *o,const char *s){while(*s && o->used+1<REPLY_BYTES)o->reply[o->used++]=*s++;}
static void number(owner *o,uint32_t n){char b[10];unsigned at=0;do{b[at++]=(char)('0'+n%10);n/=10;}while(n);while(at && o->used+1<REPLY_BYTES)o->reply[o->used++]=b[--at];}
static int send(void *p,const uint8_t *b,uint32_t n){
    owner *o=p;
    if(!o->reply || n<7 || b[4]!=0xea || b[5]!=7)return -1;
    unsigned off=(b[6]&128)?8:7;
    unsigned length=(b[6]&127u)|(off==8?(unsigned)b[7]<<7:0);
    if(n!=off+length || length>150 || o->used+2*length+4>=REPLY_BYTES)return -1;
    if(o->records++){text(o,",");}text(o,"\"");
    static const char hex[]="0123456789abcdef";
    for(unsigned i=off;i<n;i++){o->reply[o->used++]=hex[b[i]>>4];o->reply[o->used++]=hex[b[i]&15];}
    text(o,"\"");return 0;
}
static void action(void *p,uint32_t uid,uint32_t kind){
    owner *o=p;
    if(o->action_pending || o->action_serial==UINT32_MAX){o->action_result=3;return;}
    if(!o->relay.ancs_lease_deadline || (int32_t)(o->relay.ancs_lease_deadline-P.now())<=0 ||
       !mm_ancs_ingress_action(&o->ingress,uid,(uint8_t)kind,o->action_peer,&o->action_generation)){
        o->action_result=4;return;
    }
    o->action_uid=uid;o->action_kind=(uint8_t)kind;o->action_pending=1;
    o->action_serial++;o->action_result=1;
}
static owner *get(int create){
    if(!glassly_canary_layout_valid())return 0;
    volatile registry *r=reg();owner *o=0;int start=0;
    lock();
    if(r->magic==MAGIC && r->state==2)o=r->context;
    else if(create && !r->magic){r->magic=MAGIC;r->state=1;start=1;}
    unlock();if(!start)return o;
    if(P.free_bytes()<MM_CANARY_HEADROOM+sizeof(owner))goto fail;
    o=P.alloc(sizeof(*o));if(!o)goto fail;
    for(size_t i=0;i<sizeof(*o);i++)((uint8_t *)o)[i]=0;
    mm_notifications_platform platform={o,allocate,deallocate,now,side,timer_new,timer_start,timer_stop,timer_stop,send,action,noop,noop};
    if(!mm_notifications_init(&o->relay,&platform)){P.free(o);goto fail;}
    mm_ancs_ingress_init(&o->ingress,&o->relay);
    lock();r->context=o;r->state=2;unlock();return o;
fail:
    lock();r->state=3;unlock();return 0;
}
static int valid(const uint8_t *p,size_t n){
    return p && n>=4 && p[0]=='A' && p[1]=='N' && p[2]==1 && p[3]<=5 &&
        (p[3]==4?(n==9 && p[8]<=1):n==4);
}
void glassly_notification_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t control[9];
    *response=0;
    if(!P.request_bytes(request,&p,&n) || !valid(p,n)){
        if(request){P.release(&request);}*response=P.status(2,0);return;
    }
    for(size_t i=0;i<n;i++)control[i]=p[i];
    if(request)P.release(&request);
    owner *o=get(control[3]==1);
    if(!o){*response=P.json("{\"glassly\":\"notifications\",\"abi\":1,\"result\":\"unavailable\",\"records\":[]}");return;}
    char *reply=P.alloc(REPLY_BYTES);if(!reply){*response=P.status(4,0);return;}
    uint32_t serial=0;
    lock();o->reply=reply;o->used=0;o->records=0;
    text(o,"{\"glassly\":\"notifications\",\"abi\":1,\"result\":\"ok\",\"records\":[");
    if(control[3]==2){mm_ancs_ingress_reset(&o->ingress);o->action_pending=0;o->action_result=0;}
    uint8_t was_pending=o->action_pending;
    mm_notifications_control(&o->relay,control,n);
    mm_notifications_tick(&o->relay);
    if(!was_pending && o->action_pending)serial=o->action_serial;
    text(o,"],\"generation\":");number(o,o->ingress.generation);
    text(o,",\"session\":");number(o,o->ingress.session);
    text(o,",\"rejected\":");number(o,o->ingress.rejected);
    text(o,",\"drops\":");number(o,o->relay.ancs_drops);
    text(o,",\"active\":");number(o,o->relay.ancs_lease_deadline && (int32_t)(o->relay.ancs_lease_deadline-P.now())>0);
    text(o,",\"connected\":");number(o,o->ingress.connected);
    text(o,",\"actionSerial\":");number(o,o->action_serial);
    text(o,",\"actionResult\":");number(o,o->action_result);text(o,"}");reply[o->used]=0;o->reply=0;
    unlock();
    if(serial){
        uint32_t job[2]={MAGIC,serial};
        typedef uint32_t (*post_fn)(uint32_t,uint32_t,const void *,uint32_t);
        uint32_t rc=P.free_bytes()<MM_CANARY_HEADROOM?11:FN(0x042361b8u,post_fn)(0,ACTION_EVENT,job,sizeof(job));
        if(rc){lock();if(o->action_serial==serial){o->action_pending=0;o->action_result=5;}unlock();}
    }
    *response=P.json(reply);P.free(reply);
}
static uint32_t u32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void apply_action(owner *o,const uint8_t *p,uint32_t n){
    if(!p || n!=8 || u32(p)!=MAGIC)return;
    uint32_t serial=u32(p+4),uid=0,generation=0;uint8_t peer[6],kind=0;int accepted=0;
    lock();
    if(o->action_pending && serial==o->action_serial){
        kind=o->action_kind;uid=o->action_uid;
        accepted=o->relay.ancs_lease_deadline && (int32_t)(o->relay.ancs_lease_deadline-P.now())>0 &&
            mm_ancs_ingress_action(&o->ingress,uid,kind,peer,&generation) && generation==o->action_generation;
        if(!accepted){o->action_pending=0;o->action_result=4;}
    }
    unlock();if(!accepted)return;
    /* This branch runs only for our command on the stock app worker. Never
     * issue a new control transaction while the stock peer is busy. */
    typedef uint8_t *(*peer_fn)(const uint8_t *);
    uint8_t *state=FN(0x042113ceu,peer_fn)(peer);
    uint32_t result=3;
    if(state && !state[12] && P.free_bytes()>=MM_CANARY_HEADROOM){
        uint8_t bytes[4]={(uint8_t)uid,(uint8_t)(uid>>8),(uint8_t)(uid>>16),(uint8_t)(uid>>24)};
        typedef uint32_t (*action_fn)(const uint8_t *,const uint8_t *,uint8_t);
        result=FN(0x04318ee6u,action_fn)(peer,bytes,kind)?5:2;
        if(result==2)state[12]=1;
    }
    lock();if(o->action_serial==serial){o->action_pending=0;o->action_result=(uint8_t)result;}unlock();
}
void glassly_notification_observe(uint32_t event,const uint8_t *p,uint32_t n){
    owner *o=get(0);if(!o)return;
    if(event==ACTION_EVENT){apply_action(o,p,n);return;}
    if(event!=0x258 && event!=0x25a && event!=0x25b)return;
    const uint8_t *body=0;size_t length=0;
    if(event==0x25b && p && n==16){
        length=p[12]|((size_t)p[13]<<8);
        uintptr_t ptr=u32(p+8);
        /* Native ANCS body is app SRAM; reject unbounded or wrapping spans. */
        if(length>MM_ANCS_BODY_MAX || ptr<0x02000000u || ptr>0x020fedc0u || length>0x020fedc0u-ptr)return;
        body=(const uint8_t *)ptr;
    }
    lock();
    if(o->relay.ancs_lease_deadline && (int32_t)(o->relay.ancs_lease_deadline-P.now())>0)
        mm_ancs_ingress_event(&o->ingress,(uint16_t)event,p,n,body,length);
    else {mm_ancs_ingress_reset(&o->ingress);o->action_pending=0;}
    unlock();
}
void glassly_notification_cleanup(void){
    owner *o=get(0);if(!o)return;
    lock();mm_notifications_cleanup(&o->relay);mm_ancs_ingress_reset(&o->ingress);o->action_pending=0;unlock();
}
