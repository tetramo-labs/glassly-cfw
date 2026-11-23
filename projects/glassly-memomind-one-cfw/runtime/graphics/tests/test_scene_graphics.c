/* Native queue/object integration with actual graphics + session + scene C.
 * Reuse only the explicit firmware mocks from the geometry adapter tests. */
#define main geometry_legacy_main
#include "test_graphics.c"
#undef main

static unsigned decode_hex(char c) {
    assert((c>='0' && c<='9') || (c>='a' && c<='f'));
    return c<='9'?(unsigned)(c-'0'):(unsigned)(c-'a'+10);
}
static size_t cache_reply(uint8_t *bytes) {
    const char *p=strstr(last_response,"\"replyHex\":\"");assert(p);p+=12;
    size_t n=0;while(*p!='"') {assert(p[0] && p[1] && n<250);bytes[n++]=(uint8_t)(decode_hex(p[0])*16+decode_hex(p[1]));p+=2;}
    assert(n>=10);return n;
}
static void w16(uint8_t *p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void w32(uint8_t *p,unsigned n){w16(p,n);w16(p+2,n>>16);}
static unsigned epoch;
static uint8_t event=37;
static void scene_send(uint8_t *p,size_t n) {
    if(p[0]>=37 && p[0]<=41)w16(p+1,epoch);
    assert(!command(p,n,1,&event));assert(queued && !request_live);deliver();
    assert(!queued && last_event==event);
}
static unsigned pixel(unsigned x,unsigned y) {
    assert(images && images->source);uint8_t b=images->source->data[64+y*300+x/2];return x&1?b&15:b>>4;
}
static void smoke(void) {
    uint8_t p[34]={41,0,0,1,0,0},reply_bytes[250];
    epoch=0;scene_send(p,6);assert(cache_reply(reply_bytes)==13 && reply_bytes[3]==0);
    epoch=reply_bytes[4]|((unsigned)reply_bytes[5]<<8);assert(epoch && reply_bytes[11]==64);
    assert(images && timers && !images->source);
    memset(p,0,sizeof p);p[0]=37;p[3]=2;p[5]=1;w32(p+6,1);w32(p+10,1);
    p[14]=3;p[15]=1;p[16]=7;w16(p+18,5);w16(p+20,5);w16(p+22,10);w16(p+24,5);
    scene_send(p,sizeof p);cache_reply(reply_bytes);assert(reply_bytes[3]==0);
    memset(p,0,sizeof p);p[0]=38;p[3]=3;p[5]=1;w16(p+8,1);w32(p+10,1);w32(p+14,1);
    scene_send(p,18);cache_reply(reply_bytes);assert(reply_bytes[3]==0 && pixel(6,6)==7);
    unsigned allocations=(unsigned)own_allocations;uint8_t keep[]={36,0};now_value=500;
    scene_send(keep,sizeof keep);assert(strstr(last_response,"scheduled") && pixel(6,6)==7 && (unsigned)own_allocations==allocations);
    /* A new tagged SHOW replies first, then emits its settled notification. */
    p[3]=4;p[5]=5;unsigned sent=sends;scene_send(p,18);
    assert(sends==sent+2 && strstr(last_response,"\"settled\"") && strstr(last_response,"\"tag\":4"));
    now_value=1499;tick_once();assert(images);now_value=1500;tick_once();assert(!images && !timers && !own_allocations);
}
static void boundary_and_cleanup(void) {
    uint8_t huge[MM_GRAPHICS_MAX_MESSAGE+1]={37};void *r=command(huge,sizeof huge,1,&event);
    assert(r && strstr(r,"invalid") && !queued);release(&r);
    uint8_t reset[]={41,0,0,1,0,0};free_value=32000;
    r=command(reset,sizeof reset,1,&event);assert(r && strstr(r,"allocation-failed") && !queued);release(&r);
    free_value=1024*1024;epoch=0;scene_send(reset,sizeof reset);assert(images && own_allocations>2);
    /* Parent object deletion owns all scene storage as well as pixels/timer. */
    delete_image(images);assert(!own_allocations && !timers);
    epoch=0;scene_send(reset,sizeof reset);launcher=0;tick_once();assert(!images && !own_allocations && !timers);launcher=1;
    uint8_t clear[]={11};scene_send(clear,sizeof clear);assert(strstr(last_response,"cleared"));
}
int main(void) {
    smoke();clear_all();boundary_and_cleanup();clear_all();
    printf("scene graphics integration: copied queue, binary replies, deferred settled, retained pixels/keepalive, expiry, native admission, parent/UI cleanup passed\n");return 0;
}
