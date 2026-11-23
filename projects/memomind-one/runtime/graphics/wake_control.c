#include "wake_control.h"
#include "input.h"
#include "wake.h"
#define P mm_graphics_native
#define WAKE_MAGIC UINT32_C(0x474c5731)
typedef struct {
    uint32_t magic;
    void *parent,*image,*timer;
    mm_wake state;
} wake_owner;
static void wake_deleted(void *event) {
    wake_owner *o=P.event_userdata(event);
    if(!o || o->magic!=WAKE_MAGIC)return;
    o->magic=0;
    if(o->timer)P.timer_delete(o->timer);
    P.free(o);
}
static wake_owner *wake_find(void *parent) {
    wake_owner *o=parent?P.find_owner(parent,wake_deleted):0;
    return o && o->magic==WAKE_MAGIC?o:0;
}
static void wake_effects(wake_owner *o,unsigned flags) {
    if(flags&MM_WAKE_DROP_FRAME)glassly_graphics_drop_frame(o->parent);
}
static void wake_tick(void *timer) {
    wake_owner *o=P.timer_userdata(timer);
    if(!o || o->magic!=WAKE_MAGIC)return;
    if(P.screen()!=o->parent || !P.launcher_active()){
        glassly_graphics_drop_frame(o->parent);P.image_delete(o->image);return;
    }
    wake_effects(o,mm_wake_update(&o->state,P.now()));
    if(!o->state.wake && !o->state.frame)P.image_delete(o->image);
}
static wake_owner *wake_create(void *parent) {
    if(!parent || !P.launcher_active() || P.free_bytes()<65536u+sizeof(wake_owner))return 0;
    wake_owner *o=P.alloc(sizeof(*o));if(!o)return 0;
    for(size_t i=0;i<sizeof(*o);i++)((uint8_t *)o)[i]=0;
    o->magic=WAKE_MAGIC;o->parent=parent;
    o->image=P.image_create(parent);
    if(!o->image){P.free(o);return 0;}
    glassly_input_hide(o->image);
    if(!P.on_delete(o->image,wake_deleted,o)){P.image_delete(o->image);P.free(o);return 0;}
    o->timer=P.timer_create(wake_tick,20,o);
    if(!o->timer){P.image_delete(o->image);return 0;}
    return o;
}
static void *wake_snapshot(const wake_owner *o,const char *result,unsigned event) {
    char text[160];size_t at=0;
    const char *prefix="{\"glassly\":\"ownership\",\"abi\":1,\"result\":\"";
    while(*prefix)text[at++]=*prefix++;
    while(*result)text[at++]=*result++;
    const char *middle="\",\"stateHex\":\"";
    while(*middle)text[at++]=*middle++;
    uint8_t state[9]={0};
    if(o){state[0]=o->state.wake;state[1]=o->state.frame;state[2]=o->state.pending;
        state[3]=(uint8_t)o->state.nonce;state[4]=(uint8_t)(o->state.nonce>>8);state[7]=o->state.presented;}
    state[5]=(uint8_t)glassly_wake_native_on_state();state[6]=(uint8_t)glassly_wake_native_blocked();state[8]=(uint8_t)event;
    static const char hex[]="0123456789abcdef";
    for(size_t i=0;i<sizeof(state);i++){text[at++]=hex[state[i]>>4];text[at++]=hex[state[i]&15];}
    text[at++]='"';text[at++]='}';text[at]=0;
    void *r=P.json(text);return r?r:P.status(4,0);
}
static int wake_valid(const uint8_t *data,size_t n) {
    return data && n==6 && data[0]=='F' && data[1]=='C' && data[2]==1 && data[3]<=6;
}
void glassly_wake_command(uint32_t command,void *request,const uint8_t *event,void **response) {
    (void)command;const uint8_t *data=0;size_t n=0;*response=0;
    if(!event || !P.request_bytes(request,&data,&n) || !wake_valid(data,n)){
        if(request){P.release(&request);}
        *response=P.json("{\"glassly\":\"ownership\",\"abi\":1,\"result\":\"invalid\"}");return;
    }
    uint8_t job[10]={3,*event,6,0};
    for(unsigned i=0;i<6;i++)job[i+4]=data[i];
    if(request)P.release(&request);
    P.post(job,sizeof(job));
}
void glassly_wake_display(const void *envelope) {
    const uint8_t *e=envelope;
    if(!e || (e[1]&63)!=63 || e[4]!=0x4c || e[5]!=0x47 || e[6]!=10 || e[7] ||
       e[8]!=3 || e[10]!=6 || e[11] || !wake_valid(e+12,6))return;
    void *parent=P.screen();wake_owner *o=wake_find(parent);const char *result="ok";
    if(o)wake_effects(o,mm_wake_update(&o->state,P.now()));
    unsigned op=e[15];
    if(op==1 || op==5){
        if(!P.launcher_active() || glassly_wake_native_blocked())result="busy";
        else {
            if(!o)o=wake_create(parent);
            if(!o)result="allocation-failed";
        }
    }
    if(o && result[0]=='o'){
        wake_effects(o,mm_wake_control(&o->state,e+12,6,P.now()));
        if(op==5)glassly_wake_native_on();
    }else if(!o && op==6)glassly_graphics_drop_frame(parent);
    void *r=wake_snapshot(o,result,0);
    if(r){glassly_wake_send(e[9],r);P.release(&r);}
}
void glassly_wake_observe(uint16_t id) {
    wake_owner *o=wake_find(P.screen());
    if(!o || !P.launcher_active())return;
    unsigned flags=mm_wake_button(&o->state,id,P.now());wake_effects(o,flags);
    if(flags&MM_WAKE_NOTIFY){
        if(o->state.event==1)glassly_wake_native_on();
        void *r=wake_snapshot(o,"event",o->state.event);
        if(r){glassly_wake_send(0,r);P.release(&r);}
    }
}
void glassly_wake_cleanup(void *parent) {wake_owner *o=wake_find(parent);if(o)P.image_delete(o->image);}
int glassly_wake_frame_active(void *parent) {
    wake_owner *o=wake_find(parent);
    return o && o->state.frame && (uint32_t)(P.now()-o->state.frame_started)<MM_WAKE_LEASE_MS;
}
void glassly_wake_presented(void *parent) {wake_owner *o=wake_find(parent);if(o && glassly_wake_frame_active(parent))o->state.presented=1;}
