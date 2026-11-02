/* Execute the real native-font adapter, scene/session and queued graphics C. */
#define main native_font_baseline_main
#include "test_native_text.c"
#undef main
#define main graphics_baseline_main
#include "test_graphics.c"
#undef main
static fixture native_fixture;
const mm_native_text_api mm_text_test_api={&native_fixture,MM_NATIVE_TEXT_DEFAULT_FONT,ready,info,metrics,bitmap};
int g2_text_reference(uint8_t *,uint32_t,uint32_t,uint32_t,const uint8_t *,uint32_t);
static unsigned reference_cases;
static void compare(const uint8_t *text,size_t length,int x,int y,unsigned options){
    uint8_t a[240],b[240],payload[261];uint32_t tokens[255];
    memset(a,0x9a,sizeof a);memcpy(b,a,sizeof a);native_fixture=fresh();
    mm_raster r={a,sizeof a,31,12,20};mm_scene_dirty d={0};
    size_t n=message(payload,x,y,options,text,length);
    int want=g2_text_reference(b,20,31,12,payload,(uint32_t)n);
    int got=mm_native_builtin_text((void *)&mm_text_test_api,&r,payload,n,&d,tokens,255);
    assert(got==want && !memcmp(a,b,sizeof a));reference_cases++;
}
static void differential(void){
    const uint8_t text[]={'A',12,'B',1,'A',31,'B'};
    int xy[]={-32768,-3,-1,0,1,29,32767};
    for(unsigned opt=0;opt<256;opt++)for(unsigned i=0;i<7;i++)compare(text,sizeof text,xy[i],xy[(i+2)%7],opt);
    uint8_t bytes[255];for(unsigned n=0;n<=255;n++){memset(bytes,'A',n);compare(bytes,n,0,0,15);}
    for(unsigned c=1;c<=31;c++){bytes[0]='A';bytes[1]=(uint8_t)c;bytes[2]='B';compare(bytes,3,10,0,15);}
    const uint8_t valid[]={0x7f,0xc2,0x80,0xdf,0xbf,0xe0,0xa0,0x80,0xed,0x9f,0xbf,0xf0,0x90,0x80,0x80,0xf4,0x8f,0xbf,0xbf};compare(valid,sizeof valid,0,0,15);
    /* Compare exact declared-length rejection against the original function,
     * including otherwise valid prefixes followed by extra bytes. */
    for(unsigned declared=0;declared<=255;declared++){
        uint8_t payload[262]={0},a[32],b[32];uint32_t tokens[255];
        payload[4]=15;payload[5]=(uint8_t)declared;memset(payload+6,'A',declared);
        for(int delta=-1;delta<=1;delta+=2){
            memset(a,0x9a,sizeof a);memcpy(b,a,sizeof a);mm_raster r={a,sizeof a,8,8,4};mm_scene_dirty d={0};
            size_t n=(size_t)(6+(int)declared+delta);native_fixture=fresh();
            assert(g2_text_reference(b,4,8,8,payload,(uint32_t)n)==-1);
            assert(mm_native_builtin_text((void *)&mm_text_test_api,&r,payload,n,&d,tokens,255)==-1);
            assert(!memcmp(a,b,sizeof a));reference_cases++;
        }
    }
    const uint8_t bad[][4]={{0},{0xc0,0xaf},{0xed,0xa0,0x80},{0xf4,0x90,0x80,0x80},{0x80},{0xe2,0x82}};
    const unsigned lens[]={1,2,3,4,1,2};for(unsigned i=0;i<6;i++)compare(bad[i],lens[i],0,0,15);
}
static size_t packet(uint8_t *p,unsigned mode,const uint8_t *text,size_t n){p[0]=(uint8_t)mode;return 1+message(p+1,10,10,15,text,n);}
static void submit_text(const uint8_t *p,size_t n){uint8_t event=52;assert(!command(p,n,1,&event));assert(queued&&!request_live);deliver();}
static void native_queue(void){
    native_fixture=fresh();uint8_t p[263],text[255];memset(text,'A',255);size_t n=packet(p,0x8f,text,255);
    unsigned before=source_calls;submit_text(p,n);assert(strstr(last_response,"\"ok\"") && source_calls==before+1);
    int owned=own_allocations;uint8_t *frame=(uint8_t *)images->source->data+64;uint8_t *snapshot=malloc(105000);assert(snapshot);memcpy(snapshot,frame,105000);
    /* Failure on the last glyph preflights all bytes; no partial pixels. */
    text[254]='B';native_fixture.fail_metrics='B';n=packet(p,15,text,255);before=source_calls;submit_text(p,n);
    assert(strstr(last_response,"invalid") && source_calls==before && !memcmp(snapshot,frame,105000) && own_allocations==owned);
    native_fixture=fresh();n=packet(p,15,text,255);fail_alloc_number=alloc_attempts+2;submit_text(p,n);fail_alloc_number=0;
    assert(strstr(last_response,"allocation-failed") && !memcmp(snapshot,frame,105000) && own_allocations==owned);
    /* Exact request length is rejected on BT before copying to display. */
    uint8_t event=52;void *response=command(p,n+1,1,&event);assert(response && !queued && !request_live);release(&response);
    response=command(p,n-1,1,&event);assert(response && !queued && !request_live);release(&response);
    /* Successful empty/control-only text still presents and frees scratch. */
    n=packet(p,15,text,0);before=source_calls;submit_text(p,n);assert(source_calls==before+1 && own_allocations==owned);
    memset(text,11,255);n=packet(p,15,text,255);submit_text(p,n);assert(own_allocations==owned);
    free(snapshot);clear_all();assert(!own_allocations);
}
int main(void){native_font_baseline_main();differential();native_queue();printf("text commands: %u actual G2 builtin differential cases; queued255-byte text, missing glyph preflight, scratchOOM, exactlength and cleanup passed\n",reference_cases);return 0;}
