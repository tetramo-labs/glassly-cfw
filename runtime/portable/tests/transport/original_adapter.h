/* Test-only G2 outer TPL framing, two-lens bridge and native-hook replacements.
 * Production transport.c has no these envelopes, identities or stock hooks. */
static void *test_allocate(void *user,size_t n) {(void)user;return stub_malloc((uint32_t)n);}
static void test_release(void *user,void *p) {(void)user;stub_free(p);}
#include "host_zlib.h"
static int send_bridge(uint8_t kind,uint8_t origin,const uint8_t *p,uint16_t n) {
    uint8_t b[265]; if(n>263)return -1;b[0]=kind;b[1]=origin;memcpy(b+2,p,n);
    return stub_bridge_send(CFW_MESSAGE_SID,b,n+2,NULL);
}
static int test_send(void *user,uint8_t origin,const uint8_t *p,uint16_t n) {
    (void)user;return origin==g_here ? stub_ble_send(1,CFW_MESSAGE_SID,p,n):send_bridge(2,origin,p,n);
}
static int test_handle(void *user,const uint8_t *p,uint16_t n,uint16_t crc,uint8_t cap,uint8_t *r,uint8_t *rn) {
    (void)user;return cfw_message_received(p,n,crc,cap,r,rn);
}
static void initialize_context(mm_transport *ctx,uint8_t endpoint) {
    mm_transport_platform p={NULL,test_allocate,test_release,test_send,test_handle,test_decode,test_end};
    if(mm_transport_init(ctx,&p,endpoint,65535)!=0) abort();
}
static uint32_t validate(const uint8_t *p,uint16_t n) {
    if(n<11 || p[3]!=n-8)return 11;
    if(p[0]!=0xaa || p[1]!=0x21 || p[4]!=1 || p[5]!=1 || p[6]!=CFW_MESSAGE_SID || p[7] || (p[8]&~0xc3))return 10;
    return mm_transport_crc(p+8,n-10)==rd16(p+n-2)?0:10;
}
static uint32_t process(const uint8_t *p,uint16_t n,uint8_t origin) {
    unsigned cap=n-11;if(cap<9)cap=9;if(cap>255)cap=255;
    return mm_transport_receive(&g_ctx[g_here-1],origin,p[2],p[8],p+9,n-11,(uint8_t)cap);
}
static uint32_t cfw_receive_packet(uint8_t pipe,const uint8_t *p,uint16_t n) {
    if(pipe || !p || n<8 || p[0]!=0xaa || p[6]!=CFW_MESSAGE_SID)return stub_stock_receive(pipe,p,n);
    uint32_t status=validate(p,n);
    if(status){mm_transport_abort(&g_ctx[g_here-1],g_here);return status;}
    if(p[8]&(g_here^3))if(send_bridge(1,g_here,p,n))status=6;
    if(p[8]&g_here){uint32_t r=process(p,n,g_here);if(r)status=r;}
    return status;
}
static uint32_t cfw_message_bridge_received(uint32_t sid,const uint8_t *p,uint32_t n,uint16_t event) {
    if(sid!=CFW_MESSAGE_SID)return stub_stock_bridge(sid,p,n,event);
    if(!p || n<2)return 11;
    uint8_t origin=p[1];if(origin<1 || origin>2)return 10;
    if(p[0]==1){
        if(g_here==origin)return 0;if(n>265)return 11;
        uint32_t s=validate(p+2,(uint16_t)(n-2));
        if(s){mm_transport_abort(&g_ctx[g_here-1],origin);return s;}
        return p[10]&g_here?process(p+2,(uint16_t)(n-2),origin):0;
    }
    if(p[0]==2){
        if(g_here!=origin)return 0;
        if(n<3)return 11; /* harden upstream read of p[2] on a two-byte return */
        if(p[2]==CFW_MESSAGE_REPLY){
            if(n<=CFW_REPLY_HDR_SIZE+2 || n>CFW_REPLY_MAX_SIZE+2)return 11;
            if(p[6]!=(origin^3))return 10;
        }else{
            if(n<11 || n>32 || (n-11)%7)return 11;
            if((p[2]!=1 && p[2]!=3) || p[6]!=(origin^3))return 10;
            if(p[2]==3 && n!=11)return 11;
        }
        return stub_ble_send(1,CFW_MESSAGE_SID,p+2,(uint16_t)(n-2))?6:0;
    }
    return 10;
}
