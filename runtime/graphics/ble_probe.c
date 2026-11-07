/* MIT. Registers a Glassly GATT service after boot through the stock app-side
 * server (app_gatts.c / wq_gatts.c), enables an advertising slot, counts writes
 * and echoes them back as notifications. A probe for the BLE command channel:
 * it proves post-boot registration, the write path and the notify path on the
 * glasses before any transport code is written. No writable globals: the
 * probe's state lives in the unused descriptor bytes of its own characteristic
 * node, found by walking the stock service list for UUID 0x9400. */
#include "ble_probe.h"
#define P mm_graphics_native
#define FN(address,type) ((type)(uintptr_t)(address))
#define BLE_SERVICE_UUID 0x9400u
#define BLE_CHARA_UUID 0x9401u
/* Stock app-side GATT server (segment-3 body, see analysis/ghidra/ble-survey). */
typedef void *(*register_service_fn)(const uint8_t *);
typedef void *(*register_chara_fn)(void *,const uint8_t *);
typedef void (*arm_pending_fn)(int);
typedef uint32_t (*run_registration_fn)(void);
typedef uint32_t (*adv_enable_fn)(uint32_t);
typedef int (*notify_fn)(const uint8_t *,void *,const uint8_t *,uint16_t);
#define REGISTER_SERVICE FN(0x0431a7feu,register_service_fn)
#define REGISTER_CHARA FN(0x0431a93au,register_chara_fn)
#define ARM_PENDING FN(0x0431b504u,arm_pending_fn)
#define RUN_REGISTRATION FN(0x0431a42eu,run_registration_fn)
#define ADV_ENABLE FN(0x04317164u,adv_enable_fn)
#define NOTIFY FN(0x0431a712u,notify_fn)
#define SERVICE_LIST (*(uint8_t **)(uintptr_t)0x0201223cu)
#define PENDING (*(volatile uint8_t *)(uintptr_t)0x02012230u)
#define REGISTERING (*(volatile uint8_t *)(uintptr_t)0x02012231u)
#define ADV_SLOTS (*(volatile uint8_t *)(uintptr_t)0x0201220au)
/* Node layouts: service {next, desc[0x20]} with uuid16 at +8 and start handle
 * at +0x1c; chara {next, desc[0x64]} with uuid16 at +8, value/cccd handles at
 * +0x18/+0x1a, more handles at +0x20/+0x22, properties at +0x1e, callbacks at
 * +0x58 read, +0x5c write, +0x60 cccd, +0x64 read-multiple. Bytes +0x24..+0x57
 * are copied into the registration message (zero then) and are free afterwards. */
#define STATE_MAGIC 0x4c424c47u
typedef struct {
    uint32_t magic,writes,notified,notify_failed,last_rc;
    uint16_t last_len;uint8_t cccd,pad;
    uint8_t peer[6];uint8_t last[22];
} state;
_Static_assert(sizeof(state)<=0x34,"Probe state fits the spare descriptor bytes");
static uint8_t *find_service(void){
    for(uint8_t *s=SERVICE_LIST;s;s=*(uint8_t **)s)
        if(*(uint16_t *)(s+8)==BLE_SERVICE_UUID)return s;
    return 0;
}
static uint8_t *find_chara(void){
    uint8_t *s=find_service();if(!s)return 0;
    for(uint8_t *c=*(uint8_t **)(s+0x20);c;c=*(uint8_t **)c)
        if(*(uint16_t *)(c+8)==BLE_CHARA_UUID)return c;
    return 0;
}
static state *state_of(void *desc){
    if(!desc)return 0;
    uint8_t *node=(uint8_t *)desc-4;
    if(*(uint16_t *)(node+8)!=BLE_CHARA_UUID)return 0;
    state *s=(state *)(node+0x24);
    if(s->magic!=STATE_MAGIC){
        for(unsigned i=0;i<sizeof(*s);i++)((uint8_t *)s)[i]=0;
        s->magic=STATE_MAGIC;
    }
    return s;
}
uint32_t glassly_ble_on_read(const uint8_t *msg,void *desc,uint8_t *buf,uint32_t len){
    (void)msg;state *s=state_of(desc);if(!s || !buf || len<4)return 0;
    buf[0]=(uint8_t)s->writes;buf[1]=(uint8_t)(s->writes>>8);buf[2]=(uint8_t)(s->writes>>16);buf[3]=(uint8_t)(s->writes>>24);
    return 4;
}
void glassly_ble_on_write(const uint8_t *msg,void *desc,const uint8_t *data,uint32_t len){
    state *s=state_of(desc);if(!s || !msg)return;
    s->writes++;s->last_len=(uint16_t)len;
    for(unsigned i=0;i<6;i++)s->peer[i]=msg[i];
    for(unsigned i=0;i<sizeof(s->last);i++)s->last[i]=data && i<len?data[i]:0;
    if(s->cccd && data && len && len<=512){
        /* Echo through the stock notify path (opcode 0x210). */
        if(NOTIFY(msg,(uint8_t *)desc-4,data,(uint16_t)len))s->notified++;else s->notify_failed++;
    }
}
void glassly_ble_on_cccd(const uint8_t *msg,void *desc,uint32_t enabled){
    (void)msg;state *s=state_of(desc);if(s)s->cccd=enabled?1:0;
}
static void *json_hex(const char *result,const uint8_t *b,unsigned n){
    char *out=P.alloc(208);if(!out)return P.status(4,0);
    char *p=out;const char *s="{\"glassly\":\"ble-probe\",\"abi\":1,\"result\":\"";while(*s)*p++=*s++;
    while(*result)*p++=*result++;
    s="\",\"stateHex\":\"";while(*s)*p++=*s++;
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<n;i++){*p++=hex[b[i]>>4];*p++=hex[b[i]&15];}
    *p++='"';*p++='}';*p=0;void *r=P.json(out);P.free(out);return r;
}
static void put16(uint8_t *p,uint32_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static void *status(const char *result,uint32_t rc){
    uint8_t b[64]={'B','P',1};uint8_t *svc=find_service(),*chr=find_chara();
    b[3]=svc?1:0;b[4]=chr?1:0;b[5]=REGISTERING;b[6]=PENDING;b[7]=ADV_SLOTS;
    put16(b+8,svc?*(uint16_t *)(svc+0x1c):0xffffu);
    put16(b+10,chr?*(uint16_t *)(chr+0x18):0xffffu);put16(b+12,chr?*(uint16_t *)(chr+0x1a):0xffffu);
    put16(b+14,chr?*(uint16_t *)(chr+0x20):0xffffu);put16(b+16,chr?*(uint16_t *)(chr+0x22):0xffffu);
    b[18]=chr?chr[0x1e]:0;b[19]=0;
    state *s=chr?state_of(chr+4):0;
    put32(b+20,s?s->writes:0);put32(b+24,s?s->notified:0);put32(b+28,s?s->notify_failed:0);
    put16(b+32,s?s->last_len:0);b[34]=s?s->cccd:0;b[35]=0;
    for(unsigned i=0;i<6;i++)b[36+i]=s?s->peer[i]:0;
    for(unsigned i=0;i<18;i++)b[42+i]=s?s->last[i]:0;
    put32(b+60,rc);
    return json_hex(result,b,sizeof(b));
}
/* Request: 'B','P',1,op[,arg...]. op1 register (idempotent), op2 enable adv slot
 * arg, op3 status, op4 notify the last peer with the remaining bytes. */
void glassly_ble_probe_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t op=255,arg=0;uint8_t payload[20];unsigned plen=0;
    if(P.request_bytes(request,&p,&n) && p && n>=4 && p[0]=='B' && p[1]=='P' && p[2]==1 && p[3]>=1 && p[3]<=4){
        op=p[3];
        if(op==2){if(n==5)arg=p[4];else op=255;}
        else if(op==4){if(n>4 && n<=4+sizeof(payload)){plen=(unsigned)n-4;for(unsigned i=0;i<plen;i++)payload[i]=p[4+i];}else op=255;}
        else if(n!=4)op=255;
    }
    if(request)P.release(&request);
    if(op==255){*response=status("invalid",0);return;}
    uint32_t rc=0;const char *result="ok";
    if(op==1){
        if(find_chara())result="exists";
        else if(REGISTERING)result="busy";
        else {
            uint8_t svc[0x24],chr[0x68];
            for(unsigned i=0;i<sizeof(svc);i++)svc[i]=0;
            for(unsigned i=0;i<sizeof(chr);i++)chr[i]=0;
            svc[4]=1;put16(svc+8,BLE_SERVICE_UUID);put32(svc+0x18,0xf0000000u);put32(svc+0x1c,0xffffu);
            chr[4]=1;put16(chr+8,BLE_CHARA_UUID);put32(chr+0x18,0xffffffffu);chr[0x1e]=0x1eu; /* read|write-no-rsp|write|notify */
            *(uintptr_t *)(chr+0x58)=(uintptr_t)glassly_ble_on_read;
            *(uintptr_t *)(chr+0x5c)=(uintptr_t)glassly_ble_on_write;
            *(uintptr_t *)(chr+0x60)=(uintptr_t)glassly_ble_on_cccd;
            void *service=find_service();
            if(!service)service=REGISTER_SERVICE(svc);
            if(!service)result="service-failed";
            else if(!REGISTER_CHARA(service,chr))result="chara-failed";
            else {ARM_PENDING(1);rc=RUN_REGISTRATION();}
        }
    } else if(op==2){
        rc=ADV_ENABLE(arg);if(rc)result="adv-refused";
    } else if(op==4){
        uint8_t *chr=find_chara();state *s=chr?state_of(chr+4):0;
        if(!s || !s->writes)result="no-peer";
        else if(NOTIFY(s->peer,chr,payload,(uint16_t)plen))s->notified++;else {s->notify_failed++;result="notify-failed";}
    }
    *response=status(result,rc);
}
