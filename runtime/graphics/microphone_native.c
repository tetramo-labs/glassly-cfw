/* MIT. Native calls that change recording state run only on the app worker. */
#include "microphone_native.h"
#include "flash_canary.h"
#define P mm_graphics_native
#ifdef MM_MICROPHONE_TEST
extern void *mm_microphone_function(uintptr_t);
extern void *mm_microphone_memory(uintptr_t);
#define FN(a,t) ((t)mm_microphone_function(a))
#define MEM(a) ((volatile uint8_t *)mm_microphone_memory(a))
#else
#define FN(a,t) ((t)(uintptr_t)(a))
#define MEM(a) ((volatile uint8_t *)(uintptr_t)(a))
#endif
#define MAGIC UINT32_C(0x4d494331)
#define CONTROL_EVENT 0x290u
#define WATCH_EVENT 0x291u
#define LEASE 90000u
#define PERIOD 1000u
enum { IDLE,CONFIGURED,STARTING,STREAMING,STOPPING,FAULT };
enum { OK,BUSY,NO_LINK,UNSUPPORTED,QUEUE,NATIVE,EXPIRED,DISCONNECTED,CANCELLED,START_TIMEOUT,OWNER_CHANGED,SCHEDULE };
typedef struct {
    uint32_t magic,serial,completed,generation,deadline,started,frames,native_status;
    uint8_t peer[6];uint16_t channel;
    uint8_t pending,active,owned,phase,error,flags,transport,cancelled;
} owner;
_Static_assert(sizeof(owner)<=48,"Microphone registry fits slot160..207");
static owner *get(void){
    if(!glassly_canary_layout_valid())return 0;
    owner *o=(owner *)(void *)MEM(MM_CANARY_REGISTRY+160);
    return o->magic==0 || o->magic==MAGIC?o:0;
}
static void lock(void){glassly_canary_enter();}
static void unlock(void){glassly_canary_leave();}
static uint32_t now(void){typedef uint32_t (*f)(void);return FN(0x0200f6e8u,f)();}
static int equal(const volatile uint8_t *a,const volatile uint8_t *b){if(!a || !b)return 0;for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;return 1;}
static uint16_t half(uintptr_t a){volatile uint8_t *p=MEM(a);return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t word(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static int live(const owner *o,uint32_t t){return o->active && (int32_t)(o->deadline-t)>0;}
static int connected(const owner *o){
    return (*MEM(0x02013c7c)&(1u<<o->transport)) &&
        equal(o->peer,MEM(o->transport?0x02013c8f:0x02013c83)) &&
        o->channel==half(o->transport?0x02013c80:0x02013c7e);
}
static int native_owned(const owner *o){return o->owned && equal(o->peer,MEM(0x020127e0));}
static uint32_t post(uint32_t event,const void *p,uint32_t n){typedef uint32_t (*f)(uint32_t,uint32_t,const void *,uint32_t);return FN(0x042361b8u,f)(0x13,event,p,n);}
static void cancel_start(void){typedef uint32_t (*f)(uint32_t,uint32_t);FN(0x04236404u,f)(0x13,1);}
static uint32_t watch(uint32_t generation){
    typedef uint32_t (*f)(uint32_t,uint32_t,const void *,uint32_t,uint32_t);
    uint32_t job[2]={MAGIC,generation};return FN(0x042363f4u,f)(0x13,WATCH_EVENT,job,sizeof(job),PERIOD);
}
static void stop(owner *o){
    if(*MEM(0x0201196c) && !native_owned(o)){lock();o->owned=0;o->phase=FAULT;o->error=OWNER_CHANGED;unlock();return;}
    cancel_start();
    uint32_t rc=0;
    if(*MEM(0x0201196c)){
        typedef uint32_t (*f)(void);rc=FN(0x0420a232u,f)();
    }
    if(!*MEM(0x0201196c) && *MEM(0x02011968)==1 && native_owned(o)){
        typedef void (*f)(const char *);FN(0x04209998u,f)("glassly_microphone_stop");
    }
    lock();o->native_status=rc;
    if(!*MEM(0x0201196c)){o->owned=0;o->phase=IDLE;}
    else {o->phase=STOPPING;if(rc)o->error=NATIVE;}
    unlock();
}
static void update(owner *o,uint32_t t){
    lock();
    if(o->active && !live(o,t)){o->active=0;o->error=EXPIRED;}
    if(o->owned && !connected(o)){o->active=0;o->error=DISCONNECTED;}
    if(o->owned && o->phase==STARTING && (uint32_t)(t-o->started)>=5000u){o->active=0;o->error=START_TIMEOUT;}
    if(o->owned && o->phase==STREAMING && !*MEM(0x0201196c)){o->active=0;o->error=NATIVE;}
    if(o->owned && *MEM(0x0201196c)){
        if(!native_owned(o)){o->active=0;o->owned=0;o->phase=FAULT;o->error=OWNER_CHANGED;}
        else if(o->active)o->phase=STREAMING;
    }
    int stopping=o->owned && !o->active;
    if(!o->owned && !o->active && o->phase!=FAULT)o->phase=IDLE;
    unlock();if(stopping)stop(o);
}
static int supported(const uint8_t *p){
    static const uint8_t config[8]={0,1,3,0,160,0,160,0};
    for(unsigned i=0;i<8;i++)if(p[4+i]!=config[i])return 0;
    return p[12]==0 || p[12]==2;
}
static int valid(const uint8_t *p,size_t n){return p && n>=4 && p[0]=='M' && p[1]=='C' && p[2]==1 && p[3]>=1 && p[3]<=4 && n==(p[3]==1?13u:4u);}
static char *text(char *p,const char *s){while(*s)*p++=*s++;return p;}
static char *number(char *p,uint32_t n){char b[10];unsigned k=0;do{b[k++]=(char)('0'+n%10);n/=10;}while(n);while(k)*p++=b[--k];return p;}
static void *reply(const char *result){
    owner *o=get();owner s;for(size_t i=0;i<sizeof(s);i++)((uint8_t *)&s)[i]=0;uint32_t t=now();
    if(o){lock();s=*o;unlock();}
    uint8_t body[21]={'M','C',1,0,0,1,3,0,160,0,160,0,0,0,1,0,0,0,0,160,0};
    body[3]=(uint8_t)live(&s,t);body[12]=s.flags;
    body[13]=(uint8_t)(body[3] && native_owned(&s) && *MEM(0x0201196c));
    for(unsigned i=0;i<4;i++)body[15+i]=(uint8_t)(s.frames>>(8*i));
    char *out=P.alloc(320);if(!out)return P.status(4,0);
    char *p=text(out,"{\"glassly\":\"microphone\",\"abi\":1,\"result\":\"");p=text(p,result);p=text(p,"\",\"stateHex\":\"");
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<sizeof(body);i++){*p++=hex[body[i]>>4];*p++=hex[body[i]&15];}
    p=text(p,"\",\"serial\":");p=number(p,s.serial);p=text(p,",\"completed\":");p=number(p,s.completed);
    p=text(p,",\"pending\":");p=number(p,s.pending);p=text(p,",\"phase\":");p=number(p,s.phase);
    p=text(p,",\"error\":");p=number(p,s.error);p=text(p,",\"nativeStatus\":");p=number(p,s.native_status);
    p=text(p,",\"nativeActive\":");p=number(p,*MEM(0x0201196c)!=0);p=text(p,"}");*p=0;
    void *r=P.json(out);P.free(out);return r;
}
void glassly_microphone_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t control[13];
    if(!P.request_bytes(request,&p,&n) || !valid(p,n)){if(request)P.release(&request);*response=reply("invalid");return;}
    for(size_t i=0;i<n;i++)control[i]=p[i];
    if(request)P.release(&request);
    if(control[3]==1 && !supported(control)){*response=reply("unsupported");return;}
    owner *o=get();if(!o){*response=reply("unavailable");return;}
    if(control[3]==2){*response=reply("ok");return;}
    uint32_t serial=0;
    lock();if(!o->magic)o->magic=MAGIC;
    if(!o->pending && o->serial!=UINT32_MAX){serial=++o->serial;o->pending=1;o->cancelled=0;}
    if(control[3]==3){o->active=0;o->cancelled=1;}
    unlock();
    if(!serial){*response=reply("busy");return;}
    uint8_t job[21]={(uint8_t)MAGIC,(uint8_t)(MAGIC>>8),(uint8_t)(MAGIC>>16),(uint8_t)(MAGIC>>24)};
    for(unsigned i=0;i<4;i++)job[4+i]=(uint8_t)(serial>>(8*i));
    for(size_t i=0;i<n;i++)job[8+i]=control[i];
    uint32_t rc=post(CONTROL_EVENT,job,(uint32_t)n+8);
    if(rc){lock();o->pending=0;o->completed=serial;o->error=QUEUE;o->native_status=rc;unlock();}
    *response=reply(rc?"queue-failed":"queued");
}
static void configure(owner *o,const uint8_t *p){
    uint32_t t=now();update(o,t);
    lock();
    if(o->cancelled){o->error=CANCELLED;unlock();return;}
    if(o->active){
        if(o->flags==p[12]){o->deadline=t+LEASE;o->error=OK;}
        else o->error=BUSY;
        unlock();return;
    }
    if(o->owned || (p[12] && (*MEM(0x0201196c) || *MEM(0x02011968)))){o->error=BUSY;unlock();return;}
    unsigned links=*MEM(0x02013c7c)&3u;
    if(p[12] && links!=1 && links!=2){o->error=NO_LINK;unlock();return;}
    if(o->generation==UINT32_MAX){o->error=SCHEDULE;unlock();return;}
    o->generation++;o->flags=p[12];o->error=OK;o->native_status=0;o->frames=0;o->started=t;
    o->deadline=t+LEASE;o->active=1;o->owned=p[12]!=0;o->phase=o->owned?STARTING:CONFIGURED;
    if(o->owned){o->transport=links==2;for(unsigned i=0;i<6;i++)o->peer[i]=MEM(o->transport?0x02013c8f:0x02013c83)[i];o->channel=half(o->transport?0x02013c80:0x02013c7e);}
    uint32_t generation=o->generation;unlock();
    if(watch(generation)){lock();o->active=0;o->owned=0;o->phase=FAULT;o->error=SCHEDULE;unlock();return;}
    if(!o->owned)return;
    typedef void (*format_fn)(uint32_t);FN(0x04209de8u,format_fn)(0);
    uint8_t start[7];for(unsigned i=0;i<6;i++)start[i]=o->peer[i];start[6]=5;
    t=now();lock();int allowed=live(o,t);unlock();
    if(allowed){typedef void (*f)(uint32_t,const void *,uint32_t);FN(0x0420a316u,f)(1,start,sizeof(start));}
    update(o,now());
}
void glassly_microphone_task(uint32_t event,const uint8_t *p,uint32_t n){
    owner *o=get();if(!o)return;
    if(event==WATCH_EVENT){
        if(!p || n!=8 || word(p)!=MAGIC || word(p+4)!=o->generation)return;
        update(o,now());
        if(o->active || o->owned){
            if(watch(o->generation)){lock();o->active=0;o->error=SCHEDULE;unlock();if(o->owned)stop(o);}
        }
        return;
    }
    if(event==CONTROL_EVENT){
        if(!p || n<12 || word(p)!=MAGIC || !valid(p+8,n-8))return;
        uint32_t serial=word(p+4);if(!o->pending || serial!=o->serial)return;
        unsigned op=p[11];
        if(op==1)configure(o,p+8);
        else if(op==3){lock();o->active=0;unlock();if(o->owned)stop(o);else {lock();o->phase=IDLE;o->error=OK;unlock();}}
        else if(op==4){uint32_t t=now();update(o,t);lock();if(o->active && !o->cancelled){o->deadline=t+LEASE;o->error=OK;}unlock();}
        lock();o->pending=0;o->completed=serial;unlock();return;
    }
    if(!p || n<6 || !o->owned || !equal(o->peer,p))return;
    if(event==1 && o->phase==STARTING && live(o,now()) && n==7 && p[6]==5){
        typedef void (*f)(uint32_t,const void *,uint32_t);FN(0x0420a316u,f)(event,p,n);update(o,now());
    }else if(event==2){lock();o->active=0;unlock();stop(o);}
}
void glassly_microphone_cleanup(void){owner *o=get();if(o){lock();o->active=0;o->cancelled=1;if(!o->owned)o->phase=IDLE;unlock();}}
void glassly_microphone_link(uint32_t transport,uint32_t up,const uint8_t *peer){
    owner *o=get();if(!o || up || !peer)return;
    lock();if(o->owned && transport==o->transport && equal(o->peer,peer)){o->active=0;o->error=DISCONNECTED;}unlock();
}
static int allow(const uint8_t *peer,unsigned transport,uint32_t channel,const uint8_t *data,uint32_t n){
    owner *o=get();if(!o)return 0;
    uint32_t t=now();int result;
    lock();result=o->magic==MAGIC && o->owned && live(o,t) && o->transport==transport &&
        o->channel==channel && equal(o->peer,peer) && native_owned(o) && *MEM(0x0201196c);
    if(result && data && n>=12 && data[0]==0x52 && data[1]>=0x90 && data[1]<=0x94 && !data[2] && !data[3] && data[11]==255 && data[6]>=1 && data[6]<=8 && n==12u+49u*data[6]){
        if(o->frames<=UINT32_MAX-data[6])o->frames+=data[6];
    }
    unlock();return result;
}
int glassly_microphone_spp(const uint8_t *peer,const uint8_t *uuid,const uint8_t *data,uint32_t n){
    static const uint8_t recording[20]={4,0,0,0,0,0,0x20,0x24,0,0,0x10,0,0x80,0,0,0x80,0x5f,0x9b,0x34,0xfb};
    if(!uuid)return 1;
    for(unsigned i=0;i<sizeof(recording);i++)if(uuid[i]!=recording[i])return 1;
    return allow(peer,0,half(0x02013c7e),data,n);
}
int glassly_microphone_iap2(const uint8_t *peer,uint32_t channel,const uint8_t *data,uint32_t n){
    channel&=65535u;n&=65535u;
    owner *o=get();
    int recording=((*MEM(0x02013c7c)&2u) && channel==half(0x02013c80) && equal(peer,MEM(0x02013c8f)));
    if(o){lock();recording|=o->owned && o->transport==1 && channel==o->channel && equal(o->peer,peer);unlock();}
    return recording?allow(peer,1,channel,data,n):1;
}
