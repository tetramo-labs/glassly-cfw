/* MIT. Lease/claim/ready behavior from pinned G2 settings_ext.c. */
#include "wake.h"
static unsigned fallback(mm_wake *s) {
    if(!s->pending)return 0;
    s->pending=0;s->nonce=0;s->presented=0;
    return MM_WAKE_FALLBACK|MM_WAKE_DROP_FRAME;
}
unsigned mm_wake_update(mm_wake *s,uint32_t now) {
    unsigned effects=0;
    if(s->wake && (uint32_t)(now-s->wake_started)>=MM_WAKE_LEASE_MS){
        s->wake=0;effects|=fallback(s);
    }
    if(s->frame && (uint32_t)(now-s->frame_started)>=MM_WAKE_LEASE_MS){
        s->frame=0;s->presented=0;effects|=MM_WAKE_DROP_FRAME;
    }
    if(s->pending && (uint32_t)(now-s->pending_started)>=s->pending_ms)effects|=fallback(s);
    return effects;
}
unsigned mm_wake_control(mm_wake *s,const uint8_t *p,size_t n,uint32_t now) {
    if(!s || !p || n!=6 || p[0]!='F' || p[1]!='C' || p[2]!=1 || p[3]>6)return MM_WAKE_INVALID;
    unsigned effects=mm_wake_update(s,now);
    uint16_t nonce=(uint16_t)p[4]|((uint16_t)p[5]<<8);
    switch(p[3]) {
    case 0:break;
    case 1:s->wake=1;s->wake_started=now;break;
    case 2:s->wake=0;effects|=fallback(s);break;
    case 3:
        if(s->wake && s->pending){s->nonce=nonce;s->pending_started=now;s->pending_ms=5000;}
        break;
    case 4:
        if(s->wake && s->pending && s->nonce==nonce){s->pending=0;s->nonce=0;}
        break;
    case 5:
        if(!s->frame){s->presented=0;effects|=MM_WAKE_DROP_FRAME;}
        s->frame=1;s->frame_started=now;break;
    case 6:s->frame=0;s->presented=0;effects|=MM_WAKE_DROP_FRAME;break;
    }
    return effects;
}
unsigned mm_wake_button(mm_wake *s,uint16_t id,uint32_t now) {
    unsigned effects=mm_wake_update(s,now);
    s->event=0;
    if(!s->wake)return effects;
    if(id==0x1f7c){
        if(s->pending)return effects|fallback(s);
        if(++s->nonce==0)s->nonce=1;
        s->pending=1;s->pending_started=now;s->pending_ms=400;s->event=1;
    }else if(id==0x1f7b)s->event=2;
    else if(id==0x1f7d)s->event=3;
    else if(id==0x1f7f)s->event=4;
    return effects|(s->event?MM_WAKE_NOTIFY:0);
}
