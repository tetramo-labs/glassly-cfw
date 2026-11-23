#ifdef MM_WAKE_CONTROL
#include "wake_control.h"
#endif
/* Opt-in cooked input, serialized exclusively by the stock display worker.
 * A hidden source-less image child tags ownership without allocating a canvas.
 * Polling retains records until a later ACK; there are no unsolicited sends.
 */
#include "input.h"
#define IP mm_graphics_native
#define INPUT_MAGIC UINT32_C(0x474c4932)
typedef struct {
    uint32_t tick,sequence;
    uint16_t id;
    uint8_t class_id,reserved;
} input_record;
typedef struct {
    uint32_t magic,renewed,nonce,sequence,ack,drops;
    void *parent,*image,*timer;
    uint8_t head,count,mask,exhausted;
    input_record records[MM_INPUT_CAPACITY];
} input_owner;
_Static_assert(sizeof(input_record)==12,"Bounded record layout");
_Static_assert(_Alignof(input_owner)<=_Alignof(void *),"Native allocator only guarantees pointer alignment");
static const char input_invalid[]="{\"glassly\":\"input\",\"abi\":1,\"result\":\"invalid\"}";
static const char input_nomem[]="{\"glassly\":\"input\",\"abi\":1,\"result\":\"allocation-failed\"}";
static uint32_t input_u32(const uint8_t *p) {
    return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void *input_reply(const char *text) {
    void *value=IP.json(text);return value ? value:IP.status(4,0);
}
static int input_valid(const uint8_t *p,size_t n) {
    if (!p || n<2 || p[0]!=1) return 0;
    if (p[1]==0) return n==2;
    if (p[1]==1) return n==7 && p[2]>=1 && p[2]<=3 && input_u32(p+3)!=0;
    if (p[1]==2) return n==10 && input_u32(p+2)!=0;
    if (p[1]==3) return n==6 && input_u32(p+2)!=0;
    return 0;
}
static void input_deleted(void *event) {
    input_owner *o=IP.event_userdata(event);
    if (!o || o->magic!=INPUT_MAGIC) return;
    o->magic=0;
    void *timer=o->timer;o->timer=0;
    if (timer) IP.timer_delete(timer);
    IP.free(o);
}
static int input_expired(const input_owner *o,uint32_t now) {
    return (uint32_t)(now-o->renewed)>=MM_INPUT_LEASE_TICKS;
}
static void input_tick(void *timer) {
    input_owner *o=IP.timer_userdata(timer);
    if (!o || o->magic!=INPUT_MAGIC) return;
    if (IP.screen()!=o->parent || input_expired(o,IP.now())) {
        IP.image_delete(o->image); /* DELETE owns timer and owner destruction. */
        return;
    }
}
static input_owner *input_find(void *parent) {
    input_owner *o=parent ? IP.find_owner(parent,input_deleted):0;
    return o && o->magic==INPUT_MAGIC ? o:0;
}
static input_owner *input_create(void *parent,uint8_t mask,uint32_t nonce,uint32_t now) {
    if (!parent || IP.free_bytes()<65536u+sizeof(input_owner)) return 0;
    input_owner *o=IP.alloc(sizeof(*o));if (!o) return 0;
    for (size_t i=0;i<sizeof(*o);i++) ((uint8_t *)o)[i]=0;
    o->magic=INPUT_MAGIC;o->parent=parent;o->mask=mask;o->nonce=nonce;o->renewed=now;
    o->image=IP.image_create(parent);
    if (!o->image) {IP.free(o);return 0;}
    /* Hidden still participates in child ownership and can invalidate/layout.
     * Hide immediately, on the display task, without any image source/pixels. */
    glassly_input_hide(o->image);
    if (!IP.on_delete(o->image,input_deleted,o)) {
        IP.image_delete(o->image);IP.free(o);return 0;
    }
    o->timer=IP.timer_create(input_tick,20,o);
    if (!o->timer) {IP.image_delete(o->image);return 0;}
    return o;
}
static void input_drop(input_owner *o) {if (o->drops!=UINT32_MAX) o->drops++;}
void glassly_input_observe(const void *envelope) {
    const uint8_t *e=envelope;
    if (!e || e[6] || e[7]) return;
    unsigned cls=e[1]&63u,id=(unsigned)e[4]|((unsigned)e[5]<<8);
    unsigned mask;
    if (cls==2 && ((id>=0x1f7b && id<=0x1f7f) || (id>=0x1fb0 && id<=0x1fb9))) mask=1;
    else if (cls==3 && id>=1 && id<=8) mask=2;
    else return;
#ifdef MM_WAKE_CONTROL
    if(cls==2)glassly_wake_observe((uint16_t)id);
#endif
    input_owner *o=input_find(IP.screen());
    if (!o || !(o->mask&mask)) return;
    uint32_t now=IP.now();
    if (input_expired(o,now)) return; /* Observer never deletes or renews. */
    if (o->sequence==UINT32_MAX) {o->exhausted=1;input_drop(o);return;}
    if (o->count==MM_INPUT_CAPACITY) {
        o->head=(uint8_t)((o->head+1u)%MM_INPUT_CAPACITY);o->count--;input_drop(o);
    }
    input_record *r=&o->records[(o->head+o->count)%MM_INPUT_CAPACITY];
    r->tick=now;r->sequence=++o->sequence;r->id=(uint16_t)id;r->class_id=(uint8_t)cls;r->reserved=0;
    if (o->sequence==UINT32_MAX) o->exhausted=1;
    o->count++;
}
/* Bounded integer-only JSON; no printf import, no writable static storage. */
typedef struct {char *text;size_t used;int failed;} input_writer;
static void input_char(input_writer *w,char c) {
    if (w->used+1>=MM_INPUT_REPLY_BYTES) {w->failed=1;return;}
    w->text[w->used++]=c;
}
static void input_text(input_writer *w,const char *s) {while (*s) input_char(w,*s++);}
static void input_number(input_writer *w,uint32_t n) {
    char digits[10];unsigned count=0;
    do {digits[count++]=(char)('0'+n%10u);n/=10u;} while(n);
    while(count) input_char(w,digits[--count]);
}
static void input_field(input_writer *w,const char *name,uint32_t n) {
    input_text(w,name);input_number(w,n);
}
static void *input_snapshot(const input_owner *o,const char *result,int records) {
    char *text=IP.alloc(MM_INPUT_REPLY_BYTES);
    if (!text) return input_reply(input_nomem);
    input_writer w={text,0,0};
    input_text(&w,"{\"glassly\":\"input\",\"abi\":1,\"result\":\"");input_text(&w,result);
    input_text(&w,"\",\"active\":");input_text(&w,o ? "true":"false");
    input_field(&w,",\"nonce\":",o ? o->nonce:0);
    input_field(&w,",\"mask\":",o ? o->mask:0);
    input_text(&w,",\"capacity\":32,\"leaseTicks\":30000");
    input_field(&w,",\"sequence\":",o ? o->sequence:0);
    input_field(&w,",\"ack\":",o ? o->ack:0);
    input_field(&w,",\"drops\":",o ? o->drops:0);
    input_text(&w,",\"exhausted\":");input_text(&w,o && o->exhausted ? "true":"false");
    input_text(&w,",\"records\":[");
    unsigned count=o && records ? (o->count<8 ? o->count:8):0;
    for (unsigned i=0;i<count;i++) {
        const input_record *r=&o->records[(o->head+i)%MM_INPUT_CAPACITY];
        if(i) input_char(&w,',');
        input_field(&w,"{\"tick\":",r->tick);
        input_field(&w,",\"sequence\":",r->sequence);
        input_field(&w,",\"id\":",r->id);
        input_field(&w,",\"class\":",r->class_id);input_char(&w,'}');
    }
    input_text(&w,"]}");text[w.used]=0;
    void *response=input_reply(w.failed ? input_nomem:text);IP.free(text);return response;
}
void glassly_input_command(uint32_t command,void *request,const uint8_t *event,void **response) {
    (void)command;const uint8_t *data=0;size_t length=0;*response=0;
    if (!event || !IP.request_bytes(request,&data,&length) || !input_valid(data,length)) {
        if(request) IP.release(&request);
        *response=input_reply(input_invalid);return;
    }
    if (IP.free_bytes()<32768u+2u*(length+4u)+8u) {
        if(request) IP.release(&request);
        *response=input_reply(input_nomem);return;
    }
    uint8_t *job=IP.alloc(length+4u);
    if (!job) {if(request) IP.release(&request);*response=input_reply(input_nomem);return;}
    job[0]=2;job[1]=*event;job[2]=(uint8_t)length;job[3]=(uint8_t)(length>>8);
    for (size_t i=0;i<length;i++) job[4+i]=data[i];
    if(request) IP.release(&request);
    IP.post(job,length+4u);IP.free(job);
}
void glassly_input_display(const void *envelope) {
    const uint8_t *e=envelope;
    if (!e || (e[1]&63u)!=63u || e[4]!=0x4c || e[5]!=0x47) return;
    size_t size=(size_t)e[6]|((size_t)e[7]<<8);
    if (size<4 || size>14 || e[8]!=2) return;
    const uint8_t *job=e+8,*data=job+4;
    size_t length=(size_t)job[2]|((size_t)job[3]<<8);
    void *parent=IP.screen();input_owner *o=input_find(parent);
    uint32_t now=IP.now();
    if (o && input_expired(o,now)) {IP.image_delete(o->image);o=0;}
    const char *result="invalid";int records=0;
    if (length==size-4 && input_valid(data,length)) {
        unsigned op=data[1];
        uint32_t nonce=op==1 ? input_u32(data+3):op>=2 ? input_u32(data+2):0;
        if (!op) result="ok";
        else if (op==1) {
            if (o && (nonce!=o->nonce || data[2]!=o->mask)) result="session-conflict";
            else {
                if(!o) o=input_create(parent,data[2],nonce,now);
                if(o) {o->renewed=now;result="ok";} else result="allocation-failed";
            }
        } else if (!o) result="no-session";
        else if (nonce!=o->nonce) result="session-conflict";
        else if (op==3) {IP.image_delete(o->image);o=0;result="ok";}
        else {
            uint32_t ack=input_u32(data+6);
            if (ack<=o->sequence) {
                if(ack>o->ack) {
                    o->ack=ack;
                    while(o->count && o->records[o->head].sequence<=ack) {
                        o->head=(uint8_t)((o->head+1u)%MM_INPUT_CAPACITY);o->count--;
                    }
                }
                o->renewed=now;result="ok";records=1;
            }
        }
    }
    void *response=input_snapshot(o,result,records);
    if(response) {glassly_input_send(job[1],response);IP.release(&response);}
}

#ifdef MM_DIAGNOSTIC_COMMANDS
void glassly_input_cleanup(void *parent) {input_owner *o=input_find(parent);if(o)IP.image_delete(o->image);}
#endif
