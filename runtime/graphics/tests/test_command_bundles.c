/* Real bundle/session/core/native adapter; test-only native callbacks captured. */
#define main legacy_graphics_main
#include MM_BUNDLE_MOCKS_SOURCE
#undef main
#include "scene_session.h"
static char history[600][1024];static unsigned history_count,cases;
static void mm_bundle_test_capture(uint8_t event,const char *value){
    assert(history_count<600 && strlen(value)<1024 && event==52);strcpy(history[history_count++],value);
}
int g2_bundle_reference(const uint8_t *,uint32_t,int,unsigned *,unsigned *);
static void w16(uint8_t *p,unsigned v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void w32(uint8_t *p,unsigned v){w16(p,v);w16(p+2,v>>16);}
static void submit(const uint8_t *p,size_t n){uint8_t e=52;history_count=0;assert(!command(p,n,1,&e));assert(queued&&!request_live);deliver();assert(!queued);}
static size_t add(uint8_t *p,size_t at,const uint8_t *child,size_t n){assert(n && n<=65535 && at+n+2<=8192);w16(p+at,(unsigned)n);memcpy(p+at+2,child,n);return at+n+2;}
static void seed(void){uint8_t key[17]={6};for(unsigned i=0;i<4;i++){key[1+4*i]=(uint8_t)i;key[2+4*i]=0;w16(key+3+4*i,i<3?65535:13395);}submit(key,sizeof key);assert(images&&images->source);}
static unsigned tag(const char *p){p=strstr(p,"\"tag\":");assert(p);return (unsigned)strtoul(p+6,0,10);}
static void setup_animation(void){
    uint8_t reset[]={41,23,0,1,0,0};submit(reset,sizeof reset);
    uint8_t put[34]={37,23,0,2,0,1};w32(put+6,1);w32(put+10,1);put[14]=3;put[15]=1;put[16]=7;w16(put+18,5);w16(put+20,5);w16(put+22,10);w16(put+24,5);submit(put,sizeof put);
    uint8_t show[18]={38,23,0,3,0,1};w16(show+8,1);w32(show+10,1);w32(show+14,1);submit(show,sizeof show);
    uint8_t glide[24]={38,23,0,100,0,7};glide[10]=4;w32(glide+11,1);w16(glide+15,100);glide[19]=10;glide[22]=glide[23]=255;submit(glide,sizeof glide);assert(history_count==1);
}
static void collection(void){
    setup_animation();uint8_t p[8192]={8,255},hide[7]={39,23,0,1,0,4};size_t n=2;
    for(unsigned i=0;i<255;i++){w16(hide+3,1+i%2);n=add(p,n,hide,sizeof hide);}
    int owned=own_allocations;unsigned presents=source_calls;submit(p,n);
    assert(source_calls==presents+1 && own_allocations==owned && history_count==257);
    assert(strstr(history[0],"replyHex\":\"27") && tag(history[1])==100);
    for(unsigned i=0;i<255;i++)assert(tag(history[i+2])==1+i%2);
    /* Collector allocation failure occurs before prepare/dispatch or takeover. */
    setup_animation();owned=own_allocations;presents=source_calls;
    fail_alloc_number=alloc_attempts+2;submit(p,n);assert(history_count==1 && strstr(history[0],"allocation-failed"));
    assert(own_allocations==owned && source_calls==presents);fail_alloc_number=0;
    now_value+=400;history_count=0;tick_once();assert(history_count==1 && tag(history[0])==100);
    /* Existing display owner; fail specifically the display collector reserve. */
    setup_animation();uint8_t e=52;assert(!command(p,n,1,&e));free_value=32768+1019;history_count=0;presents=source_calls;deliver();
    assert(history_count==1 && strstr(history[0],"allocation-failed") && source_calls==presents);free_value=1024*1024;
    now_value+=400;history_count=0;tick_once();assert(history_count==1 && tag(history[0])==100);
    clear_all();
}
static void empty_pending_and_failure(void){
    setup_animation();unsigned presents=source_calls;uint8_t zero[]={0x88,0,0xff,0xff};submit(zero,sizeof zero);
    assert(source_calls==presents+1 && history_count==1 && strstr(history[0],"scheduled"));
    now_value+=400;history_count=0;tick_once();assert(history_count==1 && tag(history[0])==100);
    uint8_t hide[]={39,23,0,17,0,4,0},badrect[17]={9};uint8_t p[64]={8,2};size_t n=add(p,2,hide,sizeof hide);n=add(p,n,badrect,sizeof badrect);
    presents=source_calls;submit(p,n);assert(source_calls==presents && history_count==2 && strstr(history[0],"invalid") && tag(history[1])==17 && !strstr(history[0],"replyHex"));
    /* cache -> highbit raster preserves final scratch; count0 clears it. */
    uint8_t reset[]={0xa9,23,0,19,0,0},empty[]={0xa4,0};p[1]=2;n=add(p,2,reset,sizeof reset);n=add(p,n,empty,sizeof empty);submit(p,n);
    assert(history_count==1 && strstr(history[0],"replyHex\":\"29"));submit(zero,sizeof zero);assert(history_count==1 && !strstr(history[0],"replyHex"));
    /* Final response creation failure cannot leak the collected tag buffer. */
    int owned=own_allocations;fail_json=1;p[1]=1;n=add(p,2,hide,sizeof hide);submit(p,n);assert(own_allocations==owned);fail_json=0;
    clear_all();
}
static void reference_envelopes(void){
    seed();uint8_t geom[22]={36,1,3,1,9};w16(geom+6,3);w16(geom+8,2);w16(geom+10,5);w16(geom+12,4);
    uint8_t p[80]={8,2},empty[]={36,0};size_t n=add(p,2,geom,sizeof geom);n=add(p,n,empty,sizeof empty);
    uint8_t *frame=(uint8_t *)images->source->data+64;
    for(size_t len=2;len<=n+3;len++){
        memset(p+n,0xe1,3);memset(frame,0,105000);unsigned ran=0,presented=0;
        int rc=g2_bundle_reference(p,(uint32_t)len,-1,&ran,&presented);unsigned before=source_calls;submit(p,len);
        assert((source_calls-before)==presented && !!strstr(history[0],"invalid")==!!rc);
        for(unsigned y=0;y<350;y++)for(unsigned x=0;x<600;x++){
            unsigned expected=ran && x>=3&&x<8&&y>=2&&y<6?9:0;uint8_t b=frame[y*300+x/2];assert((x&1?b&15:b>>4)==expected);
        }
        cases++;
    }
    for(unsigned mode=0;mode<256;mode++)if((mode&127)!=3&&(mode&127)!=6&&(mode&127)!=9&&(mode&127)!=19&&(mode&127)!=20&&(mode&127)!=36&&!((mode&127)>=37&&(mode&127)<=41)){
        uint8_t child[2]={(uint8_t)mode,0};p[0]=8;p[1]=2;n=add(p,2,geom,sizeof geom);n=add(p,n,child,sizeof child);memset(frame,0,105000);unsigned before=source_calls;submit(p,n);
        assert(strstr(history[0],"invalid") && source_calls==before && (frame[2*300+1]&15)==9);cases++;
    }
    clear_all();
}
static unsigned core_allocs,core_presents;
static void *core_alloc(void *u,size_t n){(void)u;void *p=malloc(n);assert(p);core_allocs++;return p;}
static void core_free(void *u,void *p){(void)u;assert(core_allocs);core_allocs--;free(p);}
static uint32_t core_free_bytes(void *u){(void)u;return 1024*1024;}
static uint32_t core_now(void *u){(void)u;return 0;}
static int core_active(void *u){(void)u;return 1;}
static void core_present(void *u,const mm_raster *r,const mm_scene_dirty *d){(void)u;(void)d;assert(r->width==600);core_presents++;}
static void final_scratch_clear(void){
    mm_scene_session *s=calloc(1,sizeof(*s));uint8_t *frame=calloc(1,105000);assert(s&&frame);
    mm_scene_session_hooks h={0,core_alloc,core_free,core_free_bytes,core_now,core_active,core_present,0,0};
    mm_raster r={frame,105000,600,350,300};assert(!mm_scene_session_init(s,&h,&r,170*1024,48*1024,64*1024));
    uint8_t empty[]={8,0};assert(!mm_scene_session_dispatch(s,empty,2) && !core_allocs && core_presents==1);
    uint8_t reset[]={41,23,0,1,0,0};assert(!mm_scene_session_dispatch(s,reset,sizeof reset) && s->core.cache_reply_len==13);
    /* Public portable core permits a smaller link capacity. STATE cannot fit
     * a page and clears earlier RESET scratch; following raster preserves zero. */
    s->core.cache_reply_cap=20;uint8_t state[]={40,0,0,0,0,0,0,0,0},raster[]={36,0},p[64]={8,3};
    size_t n=add(p,2,reset,sizeof reset);n=add(p,n,state,sizeof state);n=add(p,n,raster,sizeof raster);
    unsigned before=core_presents;int result=mm_scene_session_dispatch(s,p,n);
    assert(!result && !s->core.cache_reply_len && core_presents==before+1);
    mm_scene_session_dispose(s);assert(!core_allocs);free(s);free(frame);
}
int main(void){final_scratch_clear();reference_envelopes();collection();empty_pending_and_failure();printf("bundles: %u envelope/reference/rejection cases;255segments+initialpending256ordered duplicate tags, finalscratch, count0, OOM, latefailure and cleanup passed\n",cases);return 0;}
