#include "record_session.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <zlib.h>
static unsigned live,allocations,fail_at,dispatched,close_in_handler;
static uint32_t available=1000000;
static size_t owned_bytes;
static mm_record_session *session;
static void *allocate(size_t n){
    allocations++;if(allocations==fail_at)return NULL;
    size_t *p=malloc(n+sizeof(size_t));if(!p)return NULL;
    *p=n;live++;owned_bytes+=n;return p+1;
}
static void release(void *p){assert(live);size_t *base=(size_t *)p-1;owned_bytes-=*base;live--;free(base);}
static uint32_t free_bytes(void){return available;}
static int dispatch(uint8_t event,const uint8_t *p,uint16_t n,uint8_t cap,uint8_t *out,uint8_t *used){
    assert(event==17 && n==60000 && cap==59 && p[0]==8);
    for(unsigned i=1;i<n;i++)assert(!p[i]);
    dispatched++;out[0]=42;*used=1;
    if(close_in_handler)mm_record_close(session);
    return 0;
}
static mm_record_platform platform={allocate,release,free_bytes,dispatch};
static uint16_t crc(const uint8_t *p,size_t n){
    uint16_t c=65535;
    while(n--){c^=(uint16_t)*p++<<8;for(unsigned i=0;i<8;i++)c=(uint16_t)((c<<1)^((c&32768)?0x1021:0));}
    return c;
}
static size_t fixture(uint8_t *packet){
    uint8_t *body=calloc(60000,1);assert(body);body[0]=8;
    uint16_t sum=crc(body,60000);z_stream z={0};assert(deflateInit(&z,Z_DEFAULT_COMPRESSION)==Z_OK);
    z.next_in=body;z.avail_in=60000;z.next_out=packet+9;z.avail_out=123;
    assert(deflate(&z,Z_SYNC_FLUSH)==Z_OK && !z.avail_in);
    size_t n=123-z.avail_out;assert(n<=123);deflateEnd(&z);free(body);
    packet[0]=126;packet[1]=1;packet[2]=23;packet[3]=193;
    packet[4]=13;packet[5]=(uint8_t)n;packet[6]=(uint8_t)(n>>8);
    packet[7]=(uint8_t)sum;packet[8]=(uint8_t)(sum>>8);return n+9;
}
static void reset(unsigned failure){assert(!live);fail_at=failure;allocations=dispatched=close_in_handler=0;available=1000000;}
int main(void){
    uint8_t packet[132];size_t n=fixture(packet);
    reset(0);session=mm_record_create(&platform);assert(session);
    const char *json=mm_record_process(session,17,packet,n);assert(json && strstr(json,"\"status\":0") && dispatched==1);
    unsigned total=allocations;size_t during=owned_bytes;mm_record_finish(session);
    assert(during-owned_bytes>=6144 && owned_bytes>0);mm_record_close(session);assert(!live && !owned_bytes);
    for(unsigned failure=1;failure<=total;failure++){
        reset(failure);session=mm_record_create(&platform);
        if(session){json=mm_record_process(session,17,packet,n);if(!json)assert(failure==2);mm_record_finish(session);mm_record_close(session);}
        assert(!live && !dispatched);
    }
    reset(0);session=mm_record_create(&platform);close_in_handler=1;
    json=mm_record_process(session,17,packet,n);assert(json && strstr(json,"\"closing\":1") && dispatched==1 && live);
    mm_record_finish(session);assert(!live);
    reset(0);session=mm_record_create(&platform);
    assert(!mm_record_process(session,17,packet,3));assert(!dispatched);
    assert(!mm_record_process(session,17,packet,133));assert(!dispatched);
    packet[1]=2;assert(!mm_record_process(session,17,packet,n));packet[1]=1;
    available=MM_RECORD_HEADROOM;json=mm_record_process(session,17,packet,n);assert(!json && !dispatched);
    mm_record_finish(session);mm_record_close(session);assert(!live);
    reset(0);session=mm_record_create(&platform);
    for(unsigned i=0;i<25;i++){unsigned at=4+i*5;packet[at]=9;packet[at+1]=packet[at+2]=0;packet[at+3]=packet[at+4]=255;}
    json=mm_record_process(session,17,packet,129);assert(json && strlen(json)<6144 && !dispatched);
    mm_record_finish(session);mm_record_close(session);assert(!live);
    printf("record session: maximum decode, %u OOM sites, deferred teardown, framing, headroom and reply bound passed\n",total);
    return 0;
}
