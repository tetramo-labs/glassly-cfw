#include "wake.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned control(mm_wake *s,unsigned op,unsigned nonce,uint32_t now) {
    uint8_t p[6]={'F','C',1,(uint8_t)op,(uint8_t)nonce,(uint8_t)(nonce>>8)};
    return mm_wake_control(s,p,6,now);
}
int main(void) {
    mm_wake s={0};
    assert(mm_wake_button(&s,0x1f7c,0)==0 && !s.pending);
    assert(control(&s,1,0,100)==0 && s.wake && !s.frame);
    assert(control(&s,5,0,100)==MM_WAKE_DROP_FRAME && s.frame);
    s.presented=1;
    assert(control(&s,5,0,200)==0 && s.presented);
    assert(mm_wake_button(&s,0x1f7c,300)==MM_WAKE_NOTIFY && s.pending && s.event==1 && s.nonce==1);
    assert(mm_wake_update(&s,699)==0 && s.pending);
    assert(control(&s,3,7,699)==0 && s.nonce==7);
    assert(control(&s,4,6,700)==0 && s.pending);
    assert(control(&s,4,7,701)==0 && !s.pending && s.presented);
    assert(mm_wake_update(&s,5700)==0);
    for(unsigned i=0;i<3;i++) {
        unsigned ids[]={0x1f7b,0x1f7d,0x1f7f},events[]={2,3,4};
        assert(mm_wake_button(&s,(uint16_t)ids[i],6000)==MM_WAKE_NOTIFY && s.event==events[i]);
    }
    assert(mm_wake_button(&s,0x1f7e,6000)==0 && !s.event);
    assert(mm_wake_button(&s,0x1f7c,6100)==MM_WAKE_NOTIFY);
    assert(mm_wake_update(&s,6500)==(MM_WAKE_FALLBACK|MM_WAKE_DROP_FRAME) && !s.pending && !s.presented);
    assert(mm_wake_button(&s,0x1f7c,6600)==MM_WAKE_NOTIFY);
    assert(mm_wake_button(&s,0x1f7c,6601)==(MM_WAKE_FALLBACK|MM_WAKE_DROP_FRAME) && !s.pending);
    assert(mm_wake_button(&s,0x1f7c,6700)==MM_WAKE_NOTIFY);
    assert(control(&s,3,9,6701)==0);
    assert(mm_wake_update(&s,11700)==0 && s.pending);
    assert(mm_wake_update(&s,11701)==(MM_WAKE_FALLBACK|MM_WAKE_DROP_FRAME) && !s.pending);
    assert(mm_wake_button(&s,0x1f7c,12000)==MM_WAKE_NOTIFY);
    assert(control(&s,2,0,12001)==(MM_WAKE_FALLBACK|MM_WAKE_DROP_FRAME) && !s.wake && s.frame);
    assert(control(&s,6,0,12002)==MM_WAKE_DROP_FRAME && !s.frame);
    uint32_t start=UINT32_MAX-100;
    assert(control(&s,1,0,start)==0);
    assert(control(&s,5,0,start)==MM_WAKE_DROP_FRAME);
    s.presented=1;
    assert(mm_wake_update(&s,start+89999u)==0 && s.wake && s.frame);
    assert(mm_wake_update(&s,start+90000u)==MM_WAKE_DROP_FRAME && !s.wake && !s.frame && !s.presented);
    assert(control(&s,1,0,UINT32_MAX-89999u)==0 && s.wake);
    assert(mm_wake_update(&s,UINT32_MAX)==0 && s.wake);
    assert(mm_wake_update(&s,0)==0 && !s.wake);
    mm_wake before=s;
    for(unsigned op=7;op<256;op++)assert(control(&s,op,0,1)==MM_WAKE_INVALID && !memcmp(&s,&before,sizeof(s)));
    uint8_t p[6]={'F','C',1,1,0,0};
    for(size_t n=0;n<6;n++)assert(mm_wake_control(&s,p,n,1)==MM_WAKE_INVALID);
    p[2]=2;assert(mm_wake_control(&s,p,6,1)==MM_WAKE_INVALID);
    puts("PASS: wake/frame leases, claim/ready, fallback, button events, rollover and invalid controls");
}
