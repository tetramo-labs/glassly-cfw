/* MIT. Portable API failure, boundary and teardown tests. */
#include "transport.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <zlib.h>
typedef struct {
    int live, allocations, fail_at, sends, calls, send_fail, handler_fail;
    int reply_n, report_too_large, fail_reply_only;
    uint8_t reply_kind[256], reply[256][255], origin[256];uint16_t reply_size[256];
    uint8_t last[65535];uint16_t last_n;
} harness;
static void *test_allocate(void *user,size_t n) {
    harness *h=user;h->allocations++;if(h->fail_at==h->allocations)return NULL;
    void *p=malloc(n);if(p)h->live++;return p;
}
static void test_release(void *user,void *p) {harness *h=user;if(p){h->live--;free(p);}}
#include "host_zlib.h"
static int send_reply(void *user,uint8_t origin,const uint8_t *p,uint16_t n) {
    harness *h=user;assert(h->sends<256 && n<=255);
    int i=h->sends++;h->reply_kind[i]=p[0];h->origin[i]=origin;
    memcpy(h->reply[i],p,n);h->reply_size[i]=n;
    return h->send_fail || (h->fail_reply_only && p[0]==5);
}
static int handle(void *user,const uint8_t *p,uint16_t n,uint16_t crc,uint8_t cap,uint8_t *r,uint8_t *rn) {
    harness *h=user;h->calls++;assert(crc==mm_transport_crc(p,n));
    memcpy(h->last,p,n);h->last_n=n;
    if(h->handler_fail)return -1;
    if(h->report_too_large){*rn=(uint8_t)(cap+1);return 0;}
    assert(h->reply_n<=cap);
    for(int i=0;i<h->reply_n;i++)r[i]=(uint8_t)(0xa0+i);
    *rn=(uint8_t)h->reply_n;return 0;
}
static void setup(mm_transport *c,harness *h,uint16_t max,int compressed) {
    memset(h,0,sizeof *h);
    mm_transport_platform p={h,test_allocate,test_release,send_reply,handle,compressed?test_decode:NULL,compressed?test_end:NULL};
    assert(mm_transport_init(c,&p,1,max)==0);
}
static unsigned record(uint8_t *p,uint8_t flags,const uint8_t *data,uint16_t n) {
    uint16_t crc=mm_transport_crc(data,n);p[0]=flags;p[1]=(uint8_t)n;p[2]=(uint8_t)(n>>8);
    p[3]=(uint8_t)crc;p[4]=(uint8_t)(crc>>8);memcpy(p+5,data,n);return 5u+n;
}
static uint32_t packet(mm_transport *c,uint8_t origin,uint8_t seq,uint8_t flags,const uint8_t *p,uint16_t n) {
    return mm_transport_receive(c,origin,seq,flags,p,n,40);
}
static void finish(mm_transport *c,harness *h){mm_transport_dispose(c);assert(h->live==0);mm_transport_dispose(c);assert(h->live==0);}
static void framing(void) {
    mm_transport c;harness h;uint8_t p[64],msg[]={0,1,2,3};unsigned n=record(p,9,msg,4);
    assert(mm_transport_crc((const uint8_t *)"123456789",9)==0x29b1);
    for(unsigned cut=1;cut<n;cut++) {
        setup(&c,&h,64,0);
        assert(packet(&c,1,255,0xc1,p,(uint16_t)cut)==11);
        assert(h.calls==0 && h.sends==1 && h.reply_kind[0]==3 && !c.message_streams[0].active);
        finish(&c,&h);
    }
    for(unsigned cut=1;cut<n;cut++) {
        setup(&c,&h,64,0);
        assert(packet(&c,1,255,0x81,p,(uint16_t)cut)==0);
        assert(packet(&c,1,0,0x41,p+cut,(uint16_t)(n-cut))==0); /* sequence wrap */
        assert(h.calls==1 && h.sends==1 && h.reply_kind[0]==1 && !memcmp(h.last,msg,4));
        finish(&c,&h);
    }
    setup(&c,&h,64,0);
    assert(packet(&c,1,5,0x81,p,6)==0 && h.live==1);
    assert(packet(&c,1,7,1,p,1)==10 && h.calls==0 && h.sends==1 && h.live==0);
    assert(packet(&c,1,8,1,p,n)==10 && h.sends==1); /* abort reported once */
    assert(packet(&c,1,9,0xc1,p,n)==0 && h.calls==1);
    assert(packet(&c,1,10,0x81,p,1)==0);
    assert(packet(&c,1,11,0xc1,p,n)==0 && h.calls==2 && h.sends==4); /* partial reset NACK+ACK */
    assert(packet(&c,1,12,0x81,p,1)==0);
    assert(mm_transport_receive(&c,1,13,0x41,NULL,1,40)==10 && h.live==0);
    assert(packet(&c,0,13,0xc1,p,n)==10);
    assert(packet(&c,3,13,0xc1,p,n)==10);
    assert(packet(&c,1,13,0xc5,p,n)==10);
    assert(mm_transport_receive(&c,1,13,0xc1,p,n,8)==10);
    finish(&c,&h);
    assert(packet(&c,1,13,0xc1,p,n)==10);
}
static void limits_crc_and_recovery(void) {
    mm_transport c;harness h;uint8_t p[32],msg[]={9,8,7,6};unsigned n=record(p,9,msg,4);
    setup(&c,&h,3,0);
    assert(packet(&c,1,0,0xc1,p,n)==6 && h.calls==0 && h.live==0 && h.allocations==0);
    assert(c.nack_reason==MM_NACK_LIMIT && c.nack_count==1);finish(&c,&h);
    setup(&c,&h,64,0);h.fail_at=1;
    assert(packet(&c,1,0,0xc1,p,n)==6 && h.live==0 && !c.message_streams[0].active);
    h.fail_at=0;p[3]^=1;
    assert(packet(&c,1,1,0xc1,p,n)==0 && h.calls==0 && c.nack_reason==MM_NACK_CRC);
    p[3]^=1;p[0]=1;
    assert(packet(&c,1,2,0xc1,p,n)==0 && c.nack_reason==MM_NACK_CONTEXT && h.calls==0);
    p[0]=9;
    assert(packet(&c,1,3,0xc1,p,n)==0 && h.calls==1); /* explicit context reset recovers */
    h.handler_fail=1;
    assert(packet(&c,1,4,0xc1,p,n)==0 && c.nack_reason==MM_NACK_HANDLER);
    finish(&c,&h);
    setup(&c,&h,64,0);
    n=record(p,9,msg,0);assert(packet(&c,1,4,0xc1,p,n)==0 && h.calls==1 && h.last_n==0);
    finish(&c,&h);
}
static void replies_history_and_origins(void) {
    mm_transport c;harness h;uint8_t p[32],msg[]={3};unsigned n=record(p,9,msg,1);
    setup(&c,&h,64,0);h.reply_n=3;
    assert(packet(&c,2,7,0xc1,p,n)==0 && h.sends==2 && h.calls==1);
    assert(h.reply_kind[0]==5 && h.reply_kind[1]==1 && h.reply_size[0]==8 && h.origin[0]==2);
    assert(h.reply[0][1]==7 && h.reply[0][2]==0 && h.reply[0][4]==1 && h.reply[0][5]==0xa0);
    h.reply_n=0;h.send_fail=1;
    assert(packet(&c,1,8,0xc1,p,n)==6 && h.calls==2);
    p[0]=1;h.send_fail=0;
    assert(packet(&c,1,9,0xc1,p,n)==0 && h.calls==3);
    assert(h.reply_size[3]==16 && h.reply[3][9]==8); /* history repairs lost ACK without repeat */
    p[0]=9;h.reply_n=2;h.fail_reply_only=1;
    assert(packet(&c,1,10,0xc1,p,n)==6 && h.calls==4 && h.sends==6);
    h.fail_reply_only=0;h.reply_n=0;h.report_too_large=1;
    assert(packet(&c,1,11,0xc1,p,n)==0 && c.nack_reason==MM_NACK_HANDLER);
    assert(h.reply_kind[h.sends-1]==3);finish(&c,&h);
    setup(&c,&h,64,0);h.reply_n=250;mm_transport_reply_capacity_hint(&c,255);
    assert(packet(&c,1,1,0xc1,p,n)==0 && h.reply_size[0]==255);finish(&c,&h);
    setup(&c,&h,64,0);n=record(p,9,msg,1);
    assert(packet(&c,1,1,0x81,p,5)==0 && packet(&c,2,1,0x81,p,5)==0 && h.live==2);
    assert(packet(&c,2,2,0x41,p+5,1)==0 && packet(&c,1,2,0x41,p+5,1)==0);
    assert(h.calls==2 && h.live==0);finish(&c,&h);
    setup(&c,&h,64,0);
    for(unsigned i=0;i<5;i++) {
        p[0]=i?1:9;
        assert(packet(&c,1,(uint8_t)(20+i),0xc1,p,n)==0);
    }
    assert(h.reply_size[4]==30 && c.message_streams[0].ack_count==3);
    assert(h.reply[4][9]==23 && h.reply[4][16]==22 && h.reply[4][23]==21);
    finish(&c,&h);
}
static unsigned compressed_record(uint8_t *out,const uint8_t *msg,unsigned len,int finish_stream) {
    z_stream z={0};assert(deflateInit(&z,Z_DEFAULT_COMPRESSION)==Z_OK);
    z.next_in=(Bytef *)msg;z.avail_in=len;z.next_out=out+5;z.avail_out=1024;
    int r=deflate(&z,finish_stream?Z_FINISH:Z_SYNC_FLUSH);
    assert(r==(finish_stream?Z_STREAM_END:Z_OK) && z.avail_in==0);
    unsigned n=1024-z.avail_out;deflateEnd(&z);
    uint16_t crc=mm_transport_crc(msg,(uint16_t)len);
    out[0]=13;out[1]=(uint8_t)n;out[2]=(uint8_t)(n>>8);out[3]=(uint8_t)crc;out[4]=(uint8_t)(crc>>8);
    return n+5;
}
static void compression_and_teardown(void) {
    mm_transport c;harness h;uint8_t p[1100],msg[200];memset(msg,0x61,sizeof msg);
    unsigned n=compressed_record(p,msg,sizeof msg,0);
    setup(&c,&h,512,1);
    assert(packet(&c,1,1,0xc1,p,n)==0 && h.calls==1 && h.last_n==200 && h.live>0);
    int allocation_count=h.allocations;finish(&c,&h);
    for(int fail=1;fail<=allocation_count;fail++){
        setup(&c,&h,512,1);h.fail_at=fail;
        (void)packet(&c,1,1,0xc1,p,n);
        assert(h.calls==0);finish(&c,&h);
    }
    setup(&c,&h,64,1); /* compressed wire fits; expansion exceeds policy */
    assert(packet(&c,1,1,0xc1,p,n)==0 && h.calls==0 && c.nack_reason==MM_NACK_INFLATE && h.live==0);
    finish(&c,&h);
    setup(&c,&h,512,0);assert(packet(&c,1,1,0xc1,p,n)==0 && c.nack_reason==MM_NACK_INFLATE);finish(&c,&h);
    setup(&c,&h,512,1);p[n-1]=0;
    assert(packet(&c,1,1,0xc1,p,n)==0 && c.nack_reason==MM_NACK_INFLATE && h.live==0);finish(&c,&h);
    n=compressed_record(p,msg,sizeof msg,1);setup(&c,&h,512,1);
    assert(packet(&c,1,1,0xc1,p,n)==0 && c.nack_reason==MM_NACK_INFLATE && h.calls==0);finish(&c,&h);
    n=compressed_record(p,msg,sizeof msg,0);setup(&c,&h,512,1);
    assert(packet(&c,1,1,0xc1,p,n)==0 && h.live>0);
    assert(packet(&c,1,2,0x81,p,6)==0 && h.live>0);finish(&c,&h); /* retained decoder + partial input */
}
static void maximum_record(void) {
    mm_transport c;harness h;uint8_t *p=malloc(65540),*msg=malloc(65535);assert(p && msg);
    for(unsigned i=0;i<65535;i++)msg[i]=(uint8_t)i;
    unsigned n=record(p,9,msg,65535);setup(&c,&h,65535,0);
    assert(packet(&c,1,0,0x81,p,65535)==0 && packet(&c,1,1,0x41,p+65535,(uint16_t)(n-65535))==0);
    assert(h.calls==1 && h.last_n==65535 && !memcmp(h.last,msg,65535));finish(&c,&h);free(msg);free(p);
}
int main(void) {
    framing();limits_crc_and_recovery();replies_history_and_origins();compression_and_teardown();maximum_record();
    puts("PASS: portable framing/CRC/bounds/reset/replies/OOM/inflater/teardown/isolation");return 0;
}
