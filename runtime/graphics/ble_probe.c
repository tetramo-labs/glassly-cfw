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
typedef uint32_t (*run_registration_fn)(void);
typedef uint32_t (*adv_enable_fn)(uint32_t);
typedef int (*notify_fn)(const uint8_t *,void *,const uint8_t *,uint16_t);
#define REGISTER_SERVICE FN(0x0431a7feu,register_service_fn)
#define REGISTER_CHARA FN(0x0431a93au,register_chara_fn)
#define RUN_REGISTRATION FN(0x0431a42eu,run_registration_fn)
typedef void (*adv_resume_fn)(int);
typedef void (*registration_failed_fn)(int);
#define ADV_RESUME FN(0x043179c2u,adv_resume_fn)
#define REGISTRATION_FAILED FN(0x0431a6a8u,registration_failed_fn)
#define CURSOR_CHARA (*(volatile uint8_t **)(uintptr_t)0x02012228u)
#define CURSOR_SERVICE (*(volatile uint8_t **)(uintptr_t)0x0201222cu)
#define ADV_ENABLE FN(0x04317164u,adv_enable_fn)
typedef uint8_t *(*find_slot_fn)(uint32_t);
#define FIND_SLOT FN(0x04316df8u,find_slot_fn)
#define LINK_FLAGS ((const volatile uint8_t *)(uintptr_t)0x02012218u)
#define NOTIFY FN(0x0431a712u,notify_fn)
typedef void *(*tlv_append_fn)(void **,uint32_t,uint32_t,const void *);
#define TLV_APPEND FN(0x042efe44u,tlv_append_fn)
extern void service_entry(uint32_t,void *,const uint8_t *,void **);
#define BLE_CHUNK 500u
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
    /* The spare bytes travel inside the characteristic registration message, so
     * they stay zero until the BT core has assigned the value handle. */
    if(*(uint16_t *)(node+0x18)==0xffffu)return 0;
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
/* BLE command frame: 'G','M',command,TLV bytes. The command runs through the same
 * service entry the Classic link uses (a kind-1 request node built by the stock
 * TLV constructor); every reply node's bytes are notified in MTU-sized chunks. */
static void ble_command(const uint8_t *msg,uint8_t *chr,state *s,const uint8_t *data,uint32_t len){
    void *request=0,*response=0;
    if(len>3 && !TLV_APPEND(&request,1,len-3,data+3)){s->notify_failed++;return;}
    service_entry(data[2],request,msg,&response); /* handlers release the request */
    for(uint8_t *node=response;node;node=*(uint8_t **)node){
        const uint8_t *h=*(const uint8_t **)(node+4);if(!h)continue;
        uint32_t n=h[1]|((uint32_t)h[2]<<8)|((uint32_t)h[3]<<16);const uint8_t *p=*(const uint8_t **)(h+4);
        while(p && n){uint32_t c=n<BLE_CHUNK?n:BLE_CHUNK;
            if(NOTIFY(msg,chr,p,(uint16_t)c))s->notified++;else s->notify_failed++;p+=c;n-=c;}
    }
    if(response)P.release(&response);
}
void glassly_ble_on_write(const uint8_t *msg,void *desc,const uint8_t *data,uint32_t len){
    state *s=state_of(desc);if(!s || !msg)return;
    if(len>=3 && data && data[0]=='G' && data[1]=='M'){
        s->writes++;for(unsigned i=0;i<6;i++)s->peer[i]=msg[i];
        ble_command(msg,(uint8_t *)desc-4,s,data,len);return;
    }
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
    char *out=P.alloc(2u*n+96u);if(!out)return P.status(4,0); /* prefix + result (<=24) + hex + close */
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
    uint8_t b[128]={'B','P',1};uint8_t *svc=find_service(),*chr=find_chara();
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
    /* Stock advertising slot (0x38 bytes: +8 configured, +9 enabled, +0xb state,
     * +0xd id, +0x10/+0x12 interval) and the BT link flags that gate posts. */
    uint8_t *slot=ADV_SLOTS?FIND_SLOT((uint32_t)ADV_SLOTS-1u):0;
    for(unsigned i=0;i<0x38;i++)b[64+i]=slot?slot[i]:0;
    for(unsigned i=0;i<4;i++)b[120+i]=LINK_FLAGS[i];
    return json_hex(result,b,sizeof(b));
}
/* Appends the Glassly service and characteristic nodes to the stock list (idempotent).
 * Returns the service node, or 0 when either allocation failed. */
static void *register_nodes(void){
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
    if(!service)return 0;
    if(!find_chara() && !REGISTER_CHARA(service,chr))return 0;
    return service;
}
/* Boot hook: runs right after the stock app_ble_adv init (042d58cc) registers
 * 0x9200/0x9300, so the Glassly service sits in the same list the stock registers,
 * re-registers after a BT restart (0431b592) and exposes before any phone connects.
 * The pending flag is left alone: whatever kick the stock uses for its own nodes
 * covers ours. */
void glassly_ble_boot_register(void){
    (void)register_nodes();
}
/* Request: 'B','P',1,op[,arg...]. op1 register (idempotent), op2 enable adv slot
 * arg, op3 status, op4 notify the last peer with the remaining bytes, op5 restart
 * every enabled advertising slot (the stock resume). */
void glassly_ble_probe_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t op=255,arg=0;uint8_t payload[20];unsigned plen=0;
    if(P.request_bytes(request,&p,&n) && p && n>=4 && p[0]=='B' && p[1]=='P' && p[2]==1 && p[3]>=1 && p[3]<=5){
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
            PENDING=0;
            void *service=register_nodes();
            if(!service)result=find_service()?"chara-failed":"service-failed";
            else {
                /* Handle replies (0x15f/0x160 service, 0x162/0x163 chara) are only
                 * accepted while registering is set and the cursors point at the
                 * entry in flight; the reply handler re-enters the machine until
                 * every handle is assigned, then the stock done callback posts
                 * register_done (0x213). */
                ADV_RESUME(0);REGISTERING=1;CURSOR_CHARA=0;CURSOR_SERVICE=(uint8_t *)service;
                rc=RUN_REGISTRATION();
                if(rc){REGISTRATION_FAILED(1);result="registration-refused";}
            }
        }
    } else if(op==2){
        rc=ADV_ENABLE(arg);if(rc)result="adv-refused";
    } else if(op==5){
        ADV_RESUME(0);
    } else if(op==4){
        uint8_t *chr=find_chara();state *s=chr?state_of(chr+4):0;
        if(!s || !s->writes)result="no-peer";
        else if(NOTIFY(s->peer,chr,payload,(uint16_t)plen))s->notified++;else {s->notify_failed++;result="notify-failed";}
    }
    *response=status(result,rc);
}
