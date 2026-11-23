/* MIT. Adapted from G2 commit
 * 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce keyboard_core.h and keyboard.c
 * (kick/schedule/tick). Exact algorithm provenance in KEYBOARD.md.
 * Explicit platform state; normalized bounded events; no native ABI hooks. */
#include "keyboard.h"
typedef mm_keyboard mmk_state;
typedef mm_keyboard_record mmk_record;
static uint16_t mmk_u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static void mmk_w16(uint8_t *p, uint32_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void mmk_w32(uint8_t *p, uint32_t v) {
    mmk_w16(p,v); mmk_w16(p+2,v>>16);
}
static void mmk_copy(uint8_t *to, const uint8_t *from, uint32_t n) {
    for (uint32_t i=0;i<n;i++) to[i]=from[i];
}

static void mmk_kick(mmk_state *s) {
    if (!__atomic_exchange_n(&s->timer_armed,1,__ATOMIC_ACQ_REL))
        if (s->platform.timer_start(s->platform.user,s->timer,20)!=0)
            __atomic_store_n(&s->timer_armed,0,__ATOMIC_RELEASE);
}
static void mmk_schedule(mmk_state *s) {
    uint32_t active=s->enabled || s->conn || s->scanning || s->drops!=s->reported_drops;
    __atomic_store_n(&s->active,active,__ATOMIC_RELEASE);
    if (active || __atomic_load_n(&s->head,__ATOMIC_ACQUIRE)!=__atomic_load_n(&s->tail,__ATOMIC_ACQUIRE)) mmk_kick(s);
}
/* Queue an entire event or none of it. Long ATT values are fragmented without
 * truncation. A sequence is consumed even on overflow; a heartbeat exposes a
 * final lost release even when no further keys are pressed. */
static void mmk_emit(mmk_state *s, uint8_t kind, uint16_t request, uint16_t code,
                    uint16_t value, const uint8_t *data, uint16_t len) {
    uint32_t seq=++s->sequence;
    uint32_t count=len ? (len+KB_CHUNK-1)/KB_CHUNK : 1;
    uint32_t h=__atomic_load_n(&s->head,__ATOMIC_RELAXED);
    uint32_t t=__atomic_load_n(&s->tail,__ATOMIC_ACQUIRE);
    if (len>512 || count>KB_SLOTS-(h-t) || (len && !data)) { s->drops++; return; }
    uint32_t stamp=s->platform.now_ms(s->platform.user);
    for (uint32_t off=0,i=0;i<count;i++) {
        uint32_t n=len-off; if (n>KB_CHUNK) n=KB_CHUNK;
        mmk_record *r=&s->queue[(h+i)%KB_SLOTS];
        uint8_t *p=r->data;
        p[0]='K'; p[1]='B'; p[2]=1; p[3]=kind;
        mmk_w32(p+4,seq); mmk_w16(p+8,s->epoch); mmk_w16(p+10,request);
        mmk_w16(p+12,code); mmk_w16(p+14,value); mmk_w16(p+16,len);
        mmk_w16(p+18,off); mmk_w32(p+20,stamp);
        if (n) mmk_copy(p+KB_HEADER,data+off,n);
        r->len=(uint8_t)(KB_HEADER+n); off+=n;
    }
    __atomic_store_n(&s->head,h+count,__ATOMIC_RELEASE);
    mmk_kick(s);
}
static void mmk_status(mmk_state *s, uint16_t req, uint16_t error) {
    uint8_t p[10]={s->enabled,s->conn,s->connected,s->encrypted,s->scanning,s->pending_event};
    mmk_w32(p+6,s->drops);
    uint32_t before=s->drops;
    mmk_emit(s,KB_STATUS,req,error,0,p,sizeof p);
    if (s->drops==before) s->reported_drops=before;
}
static void mmk_clear_link(mmk_state *s) {
    s->conn=s->connected=s->encrypted=s->closing=0;
    s->pending=s->pending_event=s->watch_count=s->auth=s->compare=0;
    s->deadline=0;
}
static void mmk_disconnect(mmk_state *s) {
    s->watch_count=s->encrypted=s->auth=s->compare=0;
    if (s->conn && !s->closing) { s->closing=1; s->platform.close(s->platform.user,s->conn); }
}
static void mmk_poll(mmk_state *s) {
    __atomic_store_n(&s->poll_pending,0,__ATOMIC_RELEASE);
    uint32_t now=s->platform.now_ms(s->platform.user);
    if (s->deadline && (int32_t)(now-s->deadline)>=0) {
        mmk_status(s,s->pending,KB_TIMEOUT);
        s->deadline=0; s->pending=s->pending_event=0;
        /* Do not reuse the ATT transaction or connection id after a timeout.
         * Keep ownership until DM_CLOSE; a late callback stays isolated. */
        mmk_disconnect(s);
    }
    if (s->scanning && (int32_t)(now-s->scan_deadline)>=0 && s->platform.scan_available(s->platform.user)) {
        s->scanning=0; mmk_status(s,0,KB_TIMEOUT);
    }
    if ((int32_t)(now-s->heartbeat)>=1000) {
        s->heartbeat=now;
        if (s->enabled || s->conn || s->scanning || s->drops!=s->reported_drops) mmk_status(s,0,KB_OK);
    }
}
static int mmk_valid_control(const uint8_t *p, uint32_t n) {
    if (!p || n<8 || n>KB_CONTROL_MAX || p[0]!='K' || p[1]!='B' || p[2]!=1 || p[3]>KB_WATCH)
        return 0;
    uint32_t body=n-8;
    switch (p[3]) {
    case KB_CONNECT: return body==7 && p[8]<=3;
    case KB_AUTH: return body==3 && ((uint32_t)p[8]|((uint32_t)p[9]<<8)|((uint32_t)p[10]<<16))<1000000;
    case KB_COMPARE: return body==1 && p[8]<=1;
    case KB_FIND: return body==4 && mmk_u16(p+8) && mmk_u16(p+10)>=mmk_u16(p+8);
    case KB_READ: return body==4 && mmk_u16(p+8) && mmk_u16(p+10)<=512;
    case KB_WRITE: return body>=4 && body<=22 && mmk_u16(p+8) && p[10]<=1 && p[11]==body-4;
    case KB_WATCH: return body>=1 && p[8]<=16 && body==1+2u*p[8];
    default: return body==0;
    }
}
static void mmk_control(mmk_state *s, const uint8_t *p, uint32_t n) {
    if (!mmk_valid_control(p,n)) return;
    uint8_t op=p[3]; uint16_t req=mmk_u16(p+4),epoch=mmk_u16(p+6),error=KB_OK;
    const uint8_t *b=p+8;
    if (op==KB_QUERY) { mmk_status(s,req,KB_OK); return; }
    if (op==KB_ENABLE) { s->enabled=1; mmk_status(s,req,KB_OK); return; }
    if (epoch!=s->epoch) { mmk_status(s,req,KB_STALE); return; }
    if (op==KB_DISABLE) {
        s->enabled=0; mmk_disconnect(s);
        /* A bounded scan is allowed to finish; never stop somebody else's scan. */
    } else if (!s->enabled) error=KB_OFF;
    else if (op==KB_SCAN) {
        if (s->scanning || s->conn || !s->platform.scan_available(s->platform.user)) error=KB_BUSY;
        else { s->scanning=1; s->scan_deadline=s->platform.now_ms(s->platform.user)+7000; s->platform.scan_start(s->platform.user); }
    } else if (op==KB_CONNECT) {
        if (s->conn || s->scanning) error=KB_BUSY;
        else if ((error=(uint16_t)s->platform.can_connect(s->platform.user,b[0],b+1))==KB_OK) {
            uint8_t conn=s->platform.open(s->platform.user,b[0],b+1);
            if (!conn || conn>3) error=KB_NO_SPACE;
            else {
                s->conn=conn; s->epoch++; if (!s->epoch) s->epoch++;
                s->deadline=s->platform.now_ms(s->platform.user)+30000; s->pending=req;
            }
        }
    } else if (op==KB_DISCONNECT) mmk_disconnect(s);
    else if (!s->connected || s->closing) error=KB_NOT_CONNECTED;
    else if (op==KB_PAIR) {
        error=(uint16_t)s->platform.pair(s->platform.user,s->conn);
        if (!error) s->deadline=s->platform.now_ms(s->platform.user)+60000;
    } else if (op==KB_AUTH) {
        if (!s->auth) error=KB_BAD_REQUEST;
        else { s->auth=0; s->platform.auth(s->platform.user,s->conn,b); }
    } else if (op==KB_COMPARE) {
        if (!s->compare) error=KB_BAD_REQUEST;
        else { s->compare=0; s->platform.compare(s->platform.user,s->conn,b[0]); }
    } else if (!s->encrypted) error=KB_NOT_ENCRYPTED;
    else if (op==KB_WATCH) {
        for (unsigned i=0;i<b[0];i++) if (!mmk_u16(b+1+2*i)) error=KB_BAD_REQUEST;
        if (!error) {
            s->watch_count=b[0];
            for (unsigned i=0;i<s->watch_count;i++) s->watches[i]=mmk_u16(b+1+2*i);
        }
    } else if (s->pending_event) error=KB_BUSY;
    else {
        uint16_t handle=mmk_u16(b),arg=mmk_u16(b+2);
        s->pending=req; s->pending_handle=handle;
        s->pending_event=op==KB_FIND?2:op==KB_READ?(arg?6:5):(b[2]?10:9);
        s->deadline=s->platform.now_ms(s->platform.user)+30000;
        if (!s->platform.request(s->platform.user,s->conn,op,handle,arg,b+4,(uint16_t)(n-12))) {
            s->pending=s->pending_event=0; s->deadline=0; error=KB_NO_MEMORY;
        } else return; /* asynchronous ATT response, not a premature success */
    }
    mmk_status(s,req,error);
}
/* Return 1 only for events owned by the keyboard. All other links and global
 * events retain the original stock dispatch path. */
static int mmk_event(mmk_state *s, const mm_keyboard_event *h) {
    if (!s || !h) return 0;
    uint8_t e=h->event;
    if (e==0x20) {
        mmk_clear_link(s); s->scanning=s->enabled=0; s->epoch++;
        mmk_status(s,0,KB_OK); return 0;
    }
    if (s->scanning && e>=0x24 && e<=0x26) {
        if (e==0x25 || (e==0x24 && h->status)) s->scanning=0;
        if (e==0x26 && s->enabled) {
            const mm_keyboard_event *a=h;
            if (a->len<=31 && a->addr_type<=3 && a->data) {
                uint8_t b[41]; b[0]=a->addr_type; mmk_copy(b+1,a->addr,6);
                b[7]=(uint8_t)a->rssi; b[8]=a->type; b[9]=a->len;
                mmk_copy(b+10,a->data,a->len);
                mmk_emit(s,KB_ADVERT,0,0,0,b,(uint16_t)(10+a->len));
            }
        } else mmk_status(s,0,h->status);
        return 1;
    }
    if (!s->conn || h->param!=s->conn) return 0;
    if (e>=2 && e<0x19) {
        const mm_keyboard_event *a=h;
        if (e==13 || e==14) {
            if (s->enabled && s->encrypted && !s->closing)
                for (unsigned i=0;i<s->watch_count;i++) if (s->watches[i]==a->handle) {
                    mmk_emit(s,KB_INPUT,0,e,a->handle,a->data,a->len); break;
                }
            if (e==14) s->platform.ind_confirm(s->platform.user,s->conn);
        } else if (s->pending_event==e) {
            uint16_t req=s->pending;
            s->pending=s->pending_event=0; s->deadline=0;
            mmk_emit(s,KB_ATT,req,(uint16_t)(e|(h->status<<8)),a->handle,a->data,a->len);
        }
        return 1;
    }
    /* Connection-scoped DM only: don't interpret global HCI params as IDs. */
    if ((e>=0x27 && e<=0x33) || e==0x35 || e==0x36 || e==0x39 || e==0x40 || e==0x57) {
        s->platform.master_dm(s->platform.user,h);
        if (!s->platform.master_security(s->platform.user,h)) mmk_disconnect(s);
        if (e==0x27) {
            s->connected=h->status==0;
            s->deadline=0;
            if (h->status) mmk_clear_link(s);
            else if (!s->enabled || s->closing) { s->closing=0; mmk_disconnect(s); }
        } else if (e==0x28) mmk_clear_link(s);
        else if (e==0x2c) { s->encrypted=h->status==0; s->deadline=0; }
        else if (e==0x2b || e==0x2d) { s->deadline=0; mmk_disconnect(s); }
        else if (e==0x2e) {
            if (h->data[0]) mmk_disconnect(s); /* OOB is not a passkey */
            else s->auth=1;
        }
        else if (e==0x35) s->compare=1;
        /* Never relay bonding keys. Only auth prompts have payloads. */
        const uint8_t *body=h->data;
        mmk_emit(s,KB_DM,0,(uint16_t)(e|(h->status<<8)),0,body,e==0x2e?2:e==0x35?4:0);
        mmk_status(s,0,KB_OK);
        return 1;
    }
    return 0;
}

static void mmk_tick(void *arg) {
    mmk_state *s=arg;
    for (unsigned i=0;i<4;i++) {
        uint32_t t=__atomic_load_n(&s->tail,__ATOMIC_RELAXED);
        if (t==__atomic_load_n(&s->head,__ATOMIC_ACQUIRE)) break;
        mmk_record *r=&s->queue[t%KB_SLOTS];
        uint8_t *p=s->notify_buf;
        p[0]=8; p[1]=3; p[2]=16; p[3]=0;
        /* Field 131; max body120 guarantees single-byte length. */
        p[4]=0x9a;p[5]=8;p[6]=r->len;
        mmk_copy(p+7,r->data,r->len);unsigned len=7u+r->len;
        s->platform.send(s->platform.user,p,len);
        /* A failed send is a visible sequence gap; don't replay stale typing. */
        __atomic_store_n(&s->tail,t+1,__ATOMIC_RELEASE);
    }
    if (!__atomic_exchange_n(&s->poll_pending,1,__ATOMIC_ACQ_REL))
        if (!s->platform.post_poll(s->platform.user)) __atomic_store_n(&s->poll_pending,0,__ATOMIC_RELEASE);
    __atomic_store_n(&s->timer_armed,0,__ATOMIC_RELEASE);
    if (__atomic_load_n(&s->active,__ATOMIC_ACQUIRE) ||
        __atomic_load_n(&s->head,__ATOMIC_ACQUIRE)!=__atomic_load_n(&s->tail,__ATOMIC_ACQUIRE)) mmk_kick(s);
}
static int ready(const mm_keyboard *s) { return s && s->platform.now_ms; }
static int disjoint(const mm_keyboard *s,const void *p,size_t n) {
    uintptr_t a=(uintptr_t)s,b=(uintptr_t)p;
    if(!p) return n==0;
    if(n>UINTPTR_MAX-b) return 0;
    return a<=b ? b-a>=sizeof *s : a-b>=n;
}
int mm_keyboard_init(mm_keyboard *s,const mm_keyboard_platform *p,uintptr_t timer) {
    if(!s || !p || !disjoint(s,p,sizeof *p)) return 0;
#define REQUIRED(name) if(!p->name)return 0
    REQUIRED(now_ms);REQUIRED(timer_start);REQUIRED(post_poll);REQUIRED(send);
    REQUIRED(scan_available);REQUIRED(scan_start);REQUIRED(can_connect);REQUIRED(open);
    REQUIRED(close);REQUIRED(pair);REQUIRED(auth);REQUIRED(compare);REQUIRED(request);
    REQUIRED(ind_confirm);REQUIRED(master_dm);REQUIRED(master_security);
#undef REQUIRED
    volatile uint8_t *v=(volatile uint8_t *)s;
    for(size_t i=0;i<sizeof *s;i++)v[i]=0;
    s->timer=timer;s->platform.user=p->user;
#define COPY(name) s->platform.name=p->name
    COPY(now_ms);COPY(timer_start);COPY(post_poll);COPY(send);COPY(scan_available);
    COPY(scan_start);COPY(can_connect);COPY(open);COPY(close);COPY(pair);COPY(auth);
    COPY(compare);COPY(request);COPY(ind_confirm);COPY(master_dm);COPY(master_security);
#undef COPY
    return 1;
}
int mm_keyboard_validate_control(const uint8_t *p,size_t n) {
    return n<=KB_CONTROL_MAX && mmk_valid_control(p,(uint32_t)n);
}
void mm_keyboard_control(mm_keyboard *s,const uint8_t *p,size_t n) {
    if(!ready(s) || !disjoint(s,p,n) || !mm_keyboard_validate_control(p,n))return;
    mmk_control(s,p,(uint32_t)n);mmk_schedule(s);
}
int mm_keyboard_handle_event(mm_keyboard *s,const mm_keyboard_event *h) {
    if(!ready(s) || !h || !disjoint(s,h,sizeof *h))return 0;
    uint8_t e=h->event;
    /* Only data actually consumed by an owned event needs its payload checked.
     * Oversized ATT records retain upstream drop/sequence accounting. */
    if(s->conn && h->param==s->conn) {
        if(e==0x2e && (!h->data || h->len!=2))return 0;
        if(e==0x35 && (!h->data || h->len!=4))return 0;
        if(e==0x35 && ((uint32_t)mmk_u16(h->data)|((uint32_t)mmk_u16(h->data+2)<<16))>=1000000u)return 0;
        if((e>=2 && e<0x19) || e==0x2e || e==0x35) {
            if(h->data && !disjoint(s,h->data,h->len))return 0;
        }
    }
    if(s->scanning && e==0x26 && h->data && !disjoint(s,h->data,h->len))return 0;
    int handled=mmk_event(s,h);mmk_schedule(s);return handled;
}
void mm_keyboard_poll(mm_keyboard *s) {if(ready(s)){mmk_poll(s);mmk_schedule(s);}}
void mm_keyboard_tick(void *arg) {mm_keyboard *s=arg;if(ready(s))mmk_tick(s);}
void mm_keyboard_lost(mm_keyboard *s) {if(ready(s)){s->sequence++;s->drops++;mmk_schedule(s);}}
