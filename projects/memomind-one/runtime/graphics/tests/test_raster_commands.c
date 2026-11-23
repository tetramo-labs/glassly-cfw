/* Actual optional native adapter/session/core plus explicit native mocks. */
#define main legacy_geometry_main
#include "test_graphics.c"
#undef main
#include "raster_commands.h"
#include "rle.h"
#include "scene_session.h"
int g2_rle_decode_reference(uint8_t *,uint32_t,uint32_t,uint32_t,const uint8_t *,uint32_t);
static uint8_t event=51;
static unsigned checks;
static size_t load(const char *path,uint8_t *out,size_t cap) {
    FILE *f=fopen(path,"rb");assert(f);size_t n=fread(out,1,cap,f);assert(!ferror(f) && feof(f));fclose(f);return n;
}
static void send_raster(const uint8_t *p,size_t n) {
    assert(!command(p,n,1,&event));assert(queued && !request_live);deliver();assert(!queued && last_event==event);
}
static void rejected(mm_raster *r,const uint8_t *p,size_t n) {
    uint8_t *old=malloc(r->bytes);assert(old);memcpy(old,r->pixels,r->bytes);
    assert(mm_raster_command_validate(r,p,n) && mm_raster_command_draw(r,p,n));
    assert(!memcmp(old,r->pixels,r->bytes));free(old);checks++;
}
static void malformed(mm_raster *r,const uint8_t *key,size_t kn,const uint8_t *delta,size_t dn) {
    for(size_t n=0;n<kn;n++)rejected(r,key,n);
    for(size_t n=0;n<dn;n++)rejected(r,delta,n);
    uint8_t m[8192];assert(kn+4<sizeof m && dn+4<sizeof m);
    memcpy(m,key,kn);m[kn]=0x11;rejected(r,m,kn+1);
    memcpy(m,delta,dn);m[dn]=0;rejected(r,m,dn+1);
    for(unsigned field=1;field<=4;field++){
        memcpy(m,delta,dn);m[field]=255;rejected(r,m,dn);
        if(field>=3){m[field]=0;rejected(r,m,dn);}
    }
    uint8_t zero[]={3,0,0,1,1,0,0,0,0,0,0};rejected(r,zero,sizeof zero);
    uint8_t stereo[]={0x83,149,174,1,1,0,0,2,1,0,0,0x87};rejected(r,stereo,sizeof stereo);
    for(unsigned mode=0;mode<256;mode++)if((mode&127)!=3 && (mode&127)!=6){
        memcpy(m,delta,dn);m[0]=(uint8_t)mode;rejected(r,m,dn);
    }
    rejected(r,r->pixels,kn);rejected(r,(const uint8_t *)r,sizeof(*r));
    assert(mm_raster_command_validate(r,(const uint8_t *)(UINTPTR_MAX-1),8));
    mm_raster bad=*r;bad.pixels=(uint8_t *)(UINTPTR_MAX-4);assert(mm_raster_command_validate(&bad,key,kn));
    /* Descriptor embedded in its target is rejected without being overwritten. */
    union {mm_raster align;uint8_t bytes[64];} self;
    self.align=(mm_raster){self.bytes,sizeof self.bytes,2,2,1};mm_raster saved=self.align;
    const uint8_t small[]={6,0x21,0x22};assert(mm_raster_command_draw(&self.align,small,sizeof small));
    assert(!memcmp(&self.align,&saved,sizeof saved));
}
static void windows(void) {
    uint8_t pixels[32*16+32],ref[sizeof pixels],encoded[512],raw[128];
    mm_raster r={pixels+16,32*16,31,16,32};
    for(unsigned y=0;y<8;y++)for(unsigned x=0;x<7;x++){
        unsigned left=x*4,top=y*2;uint8_t m[520]={3,(uint8_t)x,(uint8_t)y,1,1,17,0};
        for(unsigned i=0;i<4;i++)raw[i]=(uint8_t)((x+y+i)*17);
        mm_rle_surface input={raw,4,2,2,2};size_t n;
        assert(!mm_rle_encode(&input,encoded,sizeof encoded,&n));memcpy(m+7,encoded,n);
        memset(pixels,0xa5,sizeof pixels);memcpy(ref,pixels,sizeof pixels);
        assert(g2_rle_decode_reference(ref+16+top*32+left/2,32,2,2,m+7,(uint32_t)n));
        assert(!mm_raster_command_draw(&r,m,n+7) && !memcmp(pixels,ref,sizeof pixels));checks++;
    }
    /* Last physical row with nonzero x must be permitted, no padded-subview fiction. */
    uint8_t last[]={3,6,7,1,1,0,0,0x87};assert(!mm_raster_command_draw(&r,last,sizeof last));
    mm_rle_surface s={pixels+16,512,16,16,32};
    uint8_t run[]={0x87};assert(mm_rle_decode_window(&s,16,15,1,1,run,1));
    assert(mm_rle_decode_window(&s,0,16,1,1,run,1));
    assert(mm_rle_decode_window(&s,0,0,UINT32_MAX,UINT32_MAX,run,1));
    assert(mm_rle_decode_window(&s,0,0,1,1,(uint8_t *)&s,sizeof s));
}
static void native_flow(const uint8_t *key,size_t kn,const uint8_t *raw,const uint8_t *delta,size_t dn) {
    unsigned called=source_calls;send_raster(key,kn);
    assert(strstr(last_response,"scheduled") && source_calls==called+1 && images && timers);
    assert(!memcmp(images->source->data+64,raw,105000));
    uint8_t *expected=malloc(105000);assert(expected);memcpy(expected,raw,105000);
    assert(g2_rle_decode_reference(expected+348*300+298,300,2,2,delta+7,(uint32_t)dn-7));
    called=source_calls;send_raster(delta,dn);assert(source_calls==called+1);
    assert(!memcmp(images->source->data+64,expected,105000));
    /* A reused frame ID still executes; no frame-id deduplication. */
    uint8_t d[32];assert(dn<sizeof d);memcpy(d,delta,dn);d[dn-1]^=1;
    called=source_calls;send_raster(d,dn);assert(source_calls==called+1);
    uint8_t stereo[]={0x83,149,174,1,1,255,255,1,1,0,0,0x87};
    send_raster(stereo,sizeof stereo);assert(images->source->data[64+348*300+298]==0x77);
    uint8_t invalid[]={3,149,174,2,1,0,0,0x87};
    memcpy(expected,images->source->data+64,105000);called=source_calls;send_raster(invalid,sizeof invalid);
    assert(strstr(last_response,"invalid") && source_calls==called && !memcmp(expected,images->source->data+64,105000));
    uint8_t *high=malloc(kn);assert(high);memcpy(high,key,kn);high[0]=0x86;send_raster(high,kn);
    assert(!memcmp(images->source->data+64,raw,105000));free(high);free(expected);
    clear_all();
    free_value=32000;void *reply=command(key,kn,1,&event);assert(reply && strstr(reply,"allocation-failed") && !queued);release(&reply);clear_all();
    drop=1;assert(!command(key,kn,1,&event) && !queued && !own_allocations);clear_all();
    fail_alloc_number=1;reply=command(key,kn,1,&event);assert(reply && !queued && !own_allocations);release(&reply);clear_all();
    for(unsigned failure=2;failure<=3;failure++){
        fail_alloc_number=(int)failure;send_raster(key,kn);assert(strstr(last_response,"allocation-failed") && !images && !timers && !own_allocations);clear_all();
    }
    launcher=0;send_raster(key,kn);assert(strstr(last_response,"stock-ui-active") && !images);clear_all();
    send_raster(key,kn);now_value=1000;tick_once();assert(!images && !own_allocations);clear_all();
}
int main(int argc,char **argv) {
    assert(argc==4);uint8_t *key=malloc(8192),*raw=malloc(105001),*delta=malloc(8192),*frame=malloc(105000),*ref=malloc(105000);
    assert(key && raw && delta && frame && ref);
    size_t kn=load(argv[1],key,8192),rn=load(argv[2],raw,105001),dn=load(argv[3],delta,8192);assert(rn==105000);
    mm_raster r={frame,105000,600,350,300};memset(frame,0xa5,105000);memset(ref,0xa5,105000);
    assert(g2_rle_decode_reference(ref,300,300,350,key+1,(uint32_t)kn-1));
    assert(!mm_raster_command_draw(&r,key,kn) && !memcmp(frame,raw,105000) && !memcmp(frame,ref,105000));
    malformed(&r,key,kn,delta,dn);windows();native_flow(key,kn,raw,delta,dn);
    free(key);free(raw);free(delta);free(frame);free(ref);
    printf("raster commands: %u adversarial/differential cases, actual sender600x350 keyframe+bottom-right delta, highbit policy, native queue/cleanup/budget/presentation passed\n",checks);
    return 0;
}
