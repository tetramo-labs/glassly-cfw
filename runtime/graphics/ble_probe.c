/* MIT. Glassly BLE link: service 0x9400 carries the stock GM stream on 0x9401
 * and the stock OTA stream on 0x9402 for the bonded phone. */
#include "ble_probe.h"
#define P mm_graphics_native
#define FN(address,type) ((type)(uintptr_t)(address))
#define BLE_SERVICE_UUID 0x9400u
#define BLE_GM_UUID 0x9401u
#define BLE_OTA_UUID 0x9402u
typedef void *(*register_service_fn)(const uint8_t *);
typedef void *(*register_chara_fn)(void *,const uint8_t *);
typedef uint32_t (*run_registration_fn)(void);
typedef uint32_t (*adv_enable_fn)(uint32_t);
typedef int (*notify_fn)(const uint8_t *,void *,const uint8_t *,uint16_t);
typedef void (*adv_resume_fn)(int);
typedef void (*registration_failed_fn)(int);
typedef uint8_t *(*find_slot_fn)(uint32_t);
typedef void (*void_fn)(void);
typedef void (*add_listener_fn)(void (*)(const uint8_t *,uint32_t,uint32_t));
typedef uint32_t (*post_fn)(uint32_t,uint32_t,const void *,uint32_t);
typedef void (*ota_rx_fn)(uint32_t,const uint8_t *,uint32_t);
typedef void (*ota_drop_fn)(uint32_t);
typedef int (*ring_fn)(const uint8_t *);
typedef uint32_t (*bt_send_fn)(uint32_t,const void *,uint32_t);
typedef uint32_t (*peer_fn)(const uint8_t *);
#define REGISTER_SERVICE FN(0x0431a7feu,register_service_fn)
#define REGISTER_CHARA FN(0x0431a93au,register_chara_fn)
#define RUN_REGISTRATION FN(0x0431a42eu,run_registration_fn)
#define ADV_RESUME FN(0x043179c2u,adv_resume_fn)
#define REGISTRATION_FAILED FN(0x0431a6a8u,registration_failed_fn)
#define ADV_ENABLE FN(0x04317164u,adv_enable_fn)
#define FIND_SLOT FN(0x04316df8u,find_slot_fn)
#define NOTIFY FN(0x0431a712u,notify_fn)
#define ADD_LISTENER FN(0x04319adcu,add_listener_fn)
#define ADV_START FN(0x042d52bcu,void_fn)
#define ADV_STOP FN(0x042d556au,void_fn)
#define POST FN(0x042361b8u,post_fn)
#define OTA_RX FN(0x0423cc32u,ota_rx_fn)
#define OTA_DROP FN(0x042388e0u,ota_drop_fn)
#define KNOWN_RING FN(0x0424eef2u,ring_fn)
#define BT_SEND FN(0x043199d2u,bt_send_fn)
#define IS_PHONE FN(0x042133e2u,peer_fn)
#define IS_BONDED_ADDR FN(0x04212eecu,peer_fn)
#define BT_CONN_UPDATE 0x27au
#define BT_SECURITY_REQUEST 0x2bcu
#define CONN_INTERVAL_MIN 12u
#define CONN_INTERVAL_MAX 24u
#define CONN_LATENCY 0u
#define CONN_TIMEOUT 400u
#define CURSOR_CHARA (*(volatile uint8_t **)(uintptr_t)0x02012228u)
#define CURSOR_SERVICE (*(volatile uint8_t **)(uintptr_t)0x0201222cu)
#define SERVICE_LIST (*(uint8_t **)(uintptr_t)0x0201223cu)
#define PENDING (*(volatile uint8_t *)(uintptr_t)0x02012230u)
#define REGISTERING (*(volatile uint8_t *)(uintptr_t)0x02012231u)
#define ADV_SLOTS (*(volatile uint8_t *)(uintptr_t)0x0201220au)
#define ADVERTISING (*(const volatile uint8_t *)(uintptr_t)0x02011ffcu)
#define LE_CONNECTED (*(const volatile uint8_t *)(uintptr_t)0x02012004u)
#define LINK_FLAGS ((const volatile uint8_t *)(uintptr_t)0x02012218u)
#define GM_BLE_LINK (*(volatile uint8_t *)(uintptr_t)0x02012077u)
#define GM_PHONE ((volatile uint8_t *)(uintptr_t)0x02012088u)
#define BT_APP_TASK 0xdu
#define GM_RX_MESSAGE 0x3au
#define ACCEPT_AFTER_MS 10000u
#define FRAME_LIMIT 2048u
#define NOTIFY_MIN 20u
#define NOTIFY_MAX 512u
#define FLAG_FIRST 1u
#define FLAG_LAST 2u
#define FLAG_CONTROL 0x80u
#define CONTROL_HELLO 1u
#define CONTROL_PARAMS 2u
#define CONTROL_SECURITY 3u
#define LINK_NONE 0u
#define LINK_PENDING 1u
#define LINK_ACCEPTED 2u
#define STATE_MAGIC 0x4b4c4247u
typedef struct {
    uint32_t magic,writes,notified,notify_failed,connected_at;
    uint8_t peer[6];uint8_t cccd,link;
    uint16_t notify_max,frag_len,frag_total,rejected;
    uint8_t *frag;
    uint8_t peer_type,peer_kind,bonded,param_rc,security_rc,requests;
} state;
_Static_assert(sizeof(state)<=0x34,"Link state fits the spare descriptor bytes");
static void put16(uint8_t *p,uint32_t v);
static uint32_t conn_update(state *g,uint32_t min,uint32_t max,uint32_t latency,uint32_t timeout);
static uint8_t *find_service(void){
    for(uint8_t *s=SERVICE_LIST;s;s=*(uint8_t **)s)
        if(*(uint16_t *)(s+8)==BLE_SERVICE_UUID)return s;
    return 0;
}
static uint8_t *find_chara(uint16_t uuid){
    uint8_t *s=find_service();if(!s)return 0;
    for(uint8_t *c=*(uint8_t **)(s+0x20);c;c=*(uint8_t **)c)
        if(*(uint16_t *)(c+8)==uuid)return c;
    return 0;
}
static state *state_of(void *desc){
    if(!desc)return 0;
    uint8_t *node=(uint8_t *)desc-4;uint16_t uuid=*(uint16_t *)(node+8);
    if(uuid!=BLE_GM_UUID && uuid!=BLE_OTA_UUID)return 0;
    if(*(uint16_t *)(node+0x18)==0xffffu)return 0;
    state *s=(state *)(node+0x24);
    if(s->magic!=STATE_MAGIC){
        for(unsigned i=0;i<sizeof(*s);i++)((uint8_t *)s)[i]=0;
        s->magic=STATE_MAGIC;s->notify_max=NOTIFY_MIN;
    }
    return s;
}
static state *chara_state(uint16_t uuid){
    uint8_t *c=find_chara(uuid);return c?state_of(c+4):0;
}
static int same_peer(const uint8_t *a,const volatile uint8_t *b){
    for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;
    return 1;
}
static void drop_fragment(state *s){
    if(s->frag)P.free(s->frag);
    s->frag=0;s->frag_len=s->frag_total=0;
}
static int notify_bytes(const uint8_t *peer,uint8_t *chr,state *s,uint16_t limit,const uint8_t *data,uint32_t n){
    int ok=1;
    while(n){
        uint32_t c=n<limit?n:limit;
        if(NOTIFY(peer,chr,data,(uint16_t)c))s->notified++;else {s->notify_failed++;ok=0;}
        data+=c;n-=c;
    }
    return ok;
}
static state *accepted(void){
    state *g=chara_state(BLE_GM_UUID);
    return g && g->link==LINK_ACCEPTED && g->cccd ? g : 0;
}
static void release_link(state *g){
    if(g->link==LINK_ACCEPTED)GM_BLE_LINK=0;
    g->link=LINK_NONE;g->cccd=0;drop_fragment(g);
}
uint32_t glassly_ble_on_read(const uint8_t *msg,void *desc,uint8_t *buf,uint32_t len){
    (void)msg;state *s=state_of(desc);if(!s || !buf || len<4)return 0;
    for(unsigned i=0;i<4;i++)buf[i]=(uint8_t)(s->writes>>(i*8));
    return 4;
}
void glassly_ble_on_cccd(const uint8_t *msg,void *desc,uint32_t enabled){
    (void)msg;state *s=state_of(desc);if(!s)return;
    s->cccd=enabled?1:0;
    state *g=chara_state(BLE_GM_UUID);
    if(!enabled && s==g && g->link==LINK_ACCEPTED){GM_BLE_LINK=0;g->link=LINK_PENDING;}
}
void glassly_ble_on_link(const uint8_t *conn,uint32_t peripheral,uint32_t connected){
    if(!conn || !peripheral || KNOWN_RING(conn))return;
    state *g=chara_state(BLE_GM_UUID),*o=chara_state(BLE_OTA_UUID);
    if(connected){
        if(g){
            release_link(g);
            for(unsigned i=0;i<6;i++)g->peer[i]=conn[i];
            g->peer_type=conn[6];g->peer_kind=conn[7];
            g->link=LINK_PENDING;g->connected_at=P.now();g->notify_max=NOTIFY_MIN;
            g->bonded=0;g->param_rc=0xff;g->security_rc=0xff;g->requests=0;
            conn_update(g,CONN_INTERVAL_MIN,CONN_INTERVAL_MAX,CONN_LATENCY,CONN_TIMEOUT);
        }
        if(o){o->cccd=0;o->link=LINK_NONE;drop_fragment(o);}
        return;
    }
    if(!g || !same_peer(conn,g->peer))return;
    release_link(g);
    if(o){
        if(o->link)OTA_DROP(0);
        o->cccd=0;o->link=LINK_NONE;drop_fragment(o);
    }
    ADV_START();
}
static uint32_t conn_update(state *g,uint32_t min,uint32_t max,uint32_t latency,uint32_t timeout){
    uint8_t req[18];
    for(unsigned i=0;i<6;i++)req[i]=g->peer[i];
    put16(req+6,min);put16(req+8,max);put16(req+10,latency);put16(req+12,timeout);put16(req+14,0);put16(req+16,0);
    g->requests++;
    return g->param_rc=(uint8_t)BT_SEND(BT_CONN_UPDATE,req,sizeof req);
}
static uint32_t security_request(state *g){
    uint8_t req[8];
    for(unsigned i=0;i<6;i++)req[i]=g->peer[i];
    req[6]=g->peer_type;req[7]=g->peer_kind;
    return g->security_rc=(uint8_t)BT_SEND(BT_SECURITY_REQUEST,req,sizeof req);
}
static void reply_control(const uint8_t *msg,uint8_t *chr,state *g,uint8_t op,uint8_t status,uint8_t detail){
    if(!g->cccd)return;
    uint8_t reply[6]={FLAG_CONTROL,op,status,(uint8_t)MM_CFW_REVISION,
        (uint8_t)((g->bonded?1:0)|(g->requests?2:0)|(g->param_rc==0?4:0)),detail};
    (void)notify_bytes(msg,chr,g,g->notify_max,reply,sizeof(reply));
}
/* The stock classifies the bonded phone when the link comes up, so its peer
 * is accepted at the first hello; anyone else waits out the window the stock
 * uses to drop unbonded centrals. */
static void hello(const uint8_t *msg,uint8_t *chr,state *g,const uint8_t *data,uint32_t len){
    if(len<4)return;
    uint32_t limit=data[2]|((uint32_t)data[3]<<8);
    g->notify_max=(uint16_t)(limit<NOTIFY_MIN?NOTIFY_MIN:limit>NOTIFY_MAX?NOTIFY_MAX:limit);
    uint8_t status=0;
    if(g->link==LINK_PENDING){
        int bonded=IS_PHONE(g->peer) || IS_BONDED_ADDR(g->peer);
        if(bonded || P.now()-g->connected_at>=ACCEPT_AFTER_MS){
            for(unsigned i=0;i<6;i++)GM_PHONE[i]=g->peer[i];
            g->link=LINK_ACCEPTED;GM_BLE_LINK=1;g->bonded=bonded?1:0;
        } else status=1;
    }
    reply_control(msg,chr,g,CONTROL_HELLO,status,g->param_rc);
}
static void control(const uint8_t *msg,uint8_t *chr,state *g,const uint8_t *data,uint32_t len){
    if(len<2)return;
    if(data[1]==CONTROL_HELLO){hello(msg,chr,g,data,len);return;}
    if(data[1]!=CONTROL_PARAMS && data[1]!=CONTROL_SECURITY)return;
    uint8_t status=1,detail=0xff;
    if(g->link==LINK_ACCEPTED){
        if(data[1]==CONTROL_PARAMS){
            if(len!=10)return;
            detail=(uint8_t)conn_update(g,data[2]|((uint32_t)data[3]<<8),data[4]|((uint32_t)data[5]<<8),
                                        data[6]|((uint32_t)data[7]<<8),data[8]|((uint32_t)data[9]<<8));
        } else detail=(uint8_t)security_request(g);
        status=detail?2:0;
    }
    reply_control(msg,chr,g,data[1],status,detail);
}
static uint8_t *assemble(state *s,const uint8_t *data,uint32_t len,uint32_t *out){
    unsigned flags=data[0];const uint8_t *p=data+1;uint32_t n=len-1;
    if(flags&FLAG_FIRST){
        drop_fragment(s);
        if(n<2)return 0;
        uint32_t total=p[0]|((uint32_t)p[1]<<8);p+=2;n-=2;
        if(!total || total>FRAME_LIMIT || !(s->frag=P.alloc(total)))return 0;
        s->frag_total=(uint16_t)total;
    }
    if(!s->frag || n>(uint32_t)(s->frag_total-s->frag_len)){drop_fragment(s);return 0;}
    for(uint32_t i=0;i<n;i++)s->frag[s->frag_len+i]=p[i];
    s->frag_len=(uint16_t)(s->frag_len+n);
    if(!(flags&FLAG_LAST))return 0;
    if(s->frag_len!=s->frag_total){drop_fragment(s);return 0;}
    uint8_t *whole=s->frag;*out=s->frag_len;
    s->frag=0;s->frag_len=s->frag_total=0;
    return whole;
}
void glassly_ble_on_write(const uint8_t *msg,void *desc,const uint8_t *data,uint32_t len){
    state *s=state_of(desc),*g=chara_state(BLE_GM_UUID);
    if(!s || !g || !msg || !data || !len || g->link==LINK_NONE || !same_peer(msg,g->peer))return;
    uint8_t *node=(uint8_t *)desc-4;int gm=*(uint16_t *)(node+8)==BLE_GM_UUID;
    s->writes++;
    if(data[0]&FLAG_CONTROL){if(gm)control(msg,node,g,data,len);return;}
    if(g->link!=LINK_ACCEPTED){s->rejected++;return;}
    uint32_t n=0;uint8_t *whole=assemble(s,data,len,&n);
    if(!whole)return;
    if(gm)(void)POST(BT_APP_TASK,GM_RX_MESSAGE,whole,n);
    else {s->link=1;OTA_RX(0,whole,n);}
    P.free(whole);
}
uint32_t glassly_gm_write(const uint8_t *data,uint32_t len){
    state *g=accepted();uint8_t *chr=find_chara(BLE_GM_UUID);
    if(!g || !chr)return 0;
    return notify_bytes(g->peer,chr,g,g->notify_max,data,len)?1:2;
}
uint32_t glassly_ota_ble_send(uint32_t conn,const uint8_t *data,uint32_t len){
    (void)conn;state *g=accepted();uint8_t *chr=find_chara(BLE_OTA_UUID);state *o=chr?state_of(chr+4):0;
    if(!g || !o || !o->cccd || !data)return 1;
    return notify_bytes(g->peer,chr,o,g->notify_max,data,len)?0:1;
}
void glassly_adv_stop(void){
    if(find_chara(BLE_GM_UUID))return;
    ADV_STOP();
}
static void put16(uint8_t *p,uint32_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static void *json_hex(const char *result,const uint8_t *b,unsigned n){
    char *out=P.alloc(2u*n+96u);if(!out)return P.status(4,0);
    char *p=out;const char *s="{\"glassly\":\"ble-probe\",\"abi\":2,\"result\":\"";while(*s)*p++=*s++;
    while(*result)*p++=*result++;
    s="\",\"stateHex\":\"";while(*s)*p++=*s++;
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<n;i++){*p++=hex[b[i]>>4];*p++=hex[b[i]&15];}
    *p++='"';*p++='}';*p=0;void *r=P.json(out);P.free(out);return r;
}
static void *status(const char *result,uint32_t rc){
    uint8_t b[136]={'B','P',2};uint8_t *svc=find_service(),*gc=find_chara(BLE_GM_UUID),*oc=find_chara(BLE_OTA_UUID);
    b[3]=svc?1:0;b[4]=gc?1:0;b[5]=REGISTERING;b[6]=PENDING;b[7]=ADV_SLOTS;
    put16(b+8,svc?*(uint16_t *)(svc+0x1c):0xffffu);
    put16(b+10,gc?*(uint16_t *)(gc+0x18):0xffffu);put16(b+12,gc?*(uint16_t *)(gc+0x1a):0xffffu);
    put16(b+14,oc?*(uint16_t *)(oc+0x18):0xffffu);put16(b+16,oc?*(uint16_t *)(oc+0x1a):0xffffu);
    b[18]=gc?gc[0x1e]:0;b[19]=oc?1:0;
    state *g=gc?state_of(gc+4):0,*o=oc?state_of(oc+4):0;
    if(g){
        put32(b+20,g->writes);put32(b+24,g->notified);put32(b+28,g->notify_failed);
        put16(b+32,g->notify_max);b[34]=g->cccd;b[35]=g->link;
        for(unsigned i=0;i<6;i++)b[36+i]=g->peer[i];
        put32(b+56,g->link?P.now()-g->connected_at:0);put16(b+60,g->rejected);
    }
    if(o){put32(b+42,o->writes);put32(b+46,o->notified);put32(b+50,o->notify_failed);b[54]=o->cccd;}
    b[55]=GM_BLE_LINK;
    put16(b+62,rc);
    uint8_t *slot=ADV_SLOTS?FIND_SLOT((uint32_t)ADV_SLOTS-1u):0;
    for(unsigned i=0;i<0x38;i++)b[64+i]=slot?slot[i]:0;
    for(unsigned i=0;i<4;i++)b[120+i]=LINK_FLAGS[i];
    b[124]=ADVERTISING;b[125]=LE_CONNECTED;
    if(g){b[126]=g->peer_type;b[127]=g->peer_kind;b[128]=g->bonded;b[129]=g->param_rc;b[130]=g->security_rc;b[131]=g->requests;}
    return json_hex(result,b,sizeof(b));
}
static void chara_desc(uint8_t *chr,uint16_t uuid){
    for(unsigned i=0;i<0x68;i++)chr[i]=0;
    chr[4]=1;put16(chr+8,uuid);put32(chr+0x18,0xffffffffu);chr[0x1e]=0x1eu;
    *(uintptr_t *)(chr+0x58)=(uintptr_t)glassly_ble_on_read;
    *(uintptr_t *)(chr+0x5c)=(uintptr_t)glassly_ble_on_write;
    *(uintptr_t *)(chr+0x60)=(uintptr_t)glassly_ble_on_cccd;
}
static void *register_nodes(void){
    uint8_t svc[0x24],chr[0x68];
    for(unsigned i=0;i<sizeof(svc);i++)svc[i]=0;
    svc[4]=1;put16(svc+8,BLE_SERVICE_UUID);put32(svc+0x18,0xf0000000u);put32(svc+0x1c,0xffffu);
    void *service=find_service();
    if(!service)service=REGISTER_SERVICE(svc);
    if(!service)return 0;
    if(!find_chara(BLE_GM_UUID)){chara_desc(chr,BLE_GM_UUID);if(!REGISTER_CHARA(service,chr))return 0;}
    if(!find_chara(BLE_OTA_UUID)){chara_desc(chr,BLE_OTA_UUID);if(!REGISTER_CHARA(service,chr))return 0;}
    return service;
}
void glassly_ble_boot_register(void){
    (void)register_nodes();
    ADD_LISTENER(glassly_ble_on_link);
}
void glassly_ble_probe_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;(void)event;const uint8_t *p=0;size_t n=0;uint8_t op=255,arg=0;
    if(P.request_bytes(request,&p,&n) && p && n>=4 && p[0]=='B' && p[1]=='P' && p[2]==1 && p[3]>=1 && p[3]<=6 && p[3]!=4){
        op=p[3];
        if(op==2){if(n==5)arg=p[4];else op=255;}
        else if(n!=4)op=255;
    }
    if(request)P.release(&request);
    if(op==255){*response=status("invalid",0);return;}
    uint32_t rc=0;const char *result="ok";
    if(op==1){
        if(find_chara(BLE_GM_UUID) && find_chara(BLE_OTA_UUID))result="exists";
        else if(REGISTERING)result="busy";
        else {
            PENDING=0;
            void *service=register_nodes();
            if(!service)result=find_service()?"chara-failed":"service-failed";
            else {
                ADV_RESUME(0);REGISTERING=1;CURSOR_CHARA=0;CURSOR_SERVICE=(uint8_t *)service;
                rc=RUN_REGISTRATION();
                if(rc){REGISTRATION_FAILED(1);result="registration-refused";}
            }
        }
        ADD_LISTENER(glassly_ble_on_link);
    } else if(op==2){
        rc=ADV_ENABLE(arg);if(rc)result="adv-refused";
    } else if(op==5){
        ADV_RESUME(0);
    } else if(op==6){
        ADV_START();
    }
    *response=status(result,rc);
}
