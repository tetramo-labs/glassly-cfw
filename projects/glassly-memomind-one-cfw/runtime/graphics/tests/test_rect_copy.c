/* Actual mode9/session/native queue plus exact pinned G2 copy reference. */
#define main legacy_geometry_main
#include "test_graphics.c"
#undef main
#include "rect_copy_commands.h"
void g2_rect_copy_reference(uint8_t *,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
static unsigned cases;
static void put16(uint8_t *p,unsigned v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void packet(uint8_t *p,unsigned sx,unsigned sy,unsigned dx,unsigned dy,unsigned w,unsigned h){
    p[0]=9;unsigned v[]={sx,sy,w,h,dx,dy,w,h};for(unsigned i=0;i<8;i++)put16(p+1+2*i,v[i]);
}
static uint8_t get(const uint8_t *p,unsigned stride,unsigned x,unsigned y){uint8_t b=p[y*stride+x/2];return x&1?b&15:b>>4;}
static void set(uint8_t *p,unsigned stride,unsigned x,unsigned y,uint8_t v){uint8_t *b=p+y*stride+x/2;*b=x&1?(*b&0xf0)|v:(*b&15)|(v<<4);}
static void snapshot_copy(uint8_t *p,unsigned stride,unsigned sx,unsigned sy,unsigned dx,unsigned dy,unsigned w,unsigned h){
    uint8_t *old=malloc((size_t)w*h);assert(old);
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)old[y*w+x]=get(p,stride,sx+x,sy+y);
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)set(p,stride,dx+x,dy+y,old[y*w+x]);free(old);
}
static void one(unsigned width,unsigned height,unsigned stride,unsigned sx,unsigned sy,unsigned dx,unsigned dy,unsigned w,unsigned h){
    size_t n=(size_t)stride*height;uint8_t *a=malloc(n+32),*b=malloc(n+32),*c=malloc(n+32);assert(a&&b&&c);
    for(size_t i=0;i<n+32;i++)a[i]=(uint8_t)(i*73u+(i/stride)*19u);memcpy(b,a,n+32);memcpy(c,a,n+32);
    uint8_t p[33];packet(p,sx,sy,dx,dy,w,h);mm_raster r={a+16,n,width,height,stride};
    assert(!mm_rect_copy_validate(&r,p,17) && !mm_rect_copy_draw(&r,p,17));
    g2_rect_copy_reference(b+16,stride,sx,sy,dx,dy,w,h);snapshot_copy(c+16,stride,sx,sy,dx,dy,w,h);
    assert(!memcmp(a,b,n+32) && !memcmp(a,c,n+32));cases++;free(a);free(b);free(c);
}
static void differential(void){
    for(unsigned sx=0;sx<6;sx++)for(unsigned dx=0;dx<6;dx++)
    for(unsigned sy=0;sy<4;sy++)for(unsigned dy=0;dy<4;dy++)
    for(unsigned w=1;w<=9;w++)for(unsigned h=1;h<=5;h++)one(17,9,13,sx,sy,dx,dy,w,h);
    one(600,350,300,0,0,0,0,600,350);one(600,350,300,0,0,1,1,599,349);one(600,350,320,1,1,0,0,599,349);
    one(600,350,300,99,99,301,99,129,115);one(600,350,300,100,180,101,181,63,31);
    one(601,351,320,599,349,0,0,2,2);one(601,351,320,0,0,600,350,1,1);
}
static void bad(mm_raster *r,const uint8_t *p,size_t n){
    uint8_t old[16*8];assert(r->bytes==sizeof old);memcpy(old,r->pixels,sizeof old);
    assert(mm_rect_copy_validate(r,p,n) && mm_rect_copy_draw(r,p,n));assert(!memcmp(old,r->pixels,sizeof old));cases++;
}
static void boundaries(void){
    uint8_t pixels[128],p[40];for(unsigned i=0;i<sizeof pixels;i++)pixels[i]=(uint8_t)i;
    mm_raster r={pixels,sizeof pixels,25,8,16};packet(p,1,1,2,2,7,3);
    for(unsigned n=0;n<17;n++)bad(&r,p,n);p[0]=0x89;for(unsigned n=17;n<33;n++)bad(&r,p,n);
    /* Unused second pair deliberately invalid; trailing bytes retain upstream behavior. */
    memset(p+17,255,23);uint8_t ref[128];memcpy(ref,pixels,128);g2_rect_copy_reference(ref,16,1,1,2,2,7,3);
    assert(!mm_rect_copy_draw(&r,p,sizeof p) && !memcmp(ref,pixels,128));
    for(unsigned field=0;field<8;field++){
        packet(p,1,1,2,2,7,3);put16(p+1+field*2,65535);bad(&r,p,17);
    }
    for(unsigned field=2;field<=3;field++){packet(p,1,1,2,2,7,3);put16(p+1+field*2,0);bad(&r,p,17);}
    for(unsigned m=0;m<256;m++)if((m&127)!=9){packet(p,1,1,2,2,7,3);p[0]=(uint8_t)m;bad(&r,p,17);}
    bad(&r,pixels,33);bad(&r,(const uint8_t *)&r,sizeof r);bad(&r,0,17);
    assert(mm_rect_copy_validate(&r,(const uint8_t *)(UINTPTR_MAX-2),17));
    mm_raster overflow=r;overflow.pixels=(uint8_t *)(UINTPTR_MAX-4);assert(mm_rect_copy_draw(&overflow,p,17));
    union {mm_raster align;uint8_t data[128];} alias;alias.align=(mm_raster){alias.data,128,25,8,16};
    assert(mm_rect_copy_draw(&alias.align,p,17));
}
static void send_copy(const uint8_t *p,size_t n){uint8_t e=52;assert(!command(p,n,1,&e));assert(queued && !request_live);deliver();assert(last_event==e);}
static void native(void){
    uint8_t key[1401];key[0]=6;for(unsigned y=0;y<350;y++){key[1+4*y]=(uint8_t)(y%16);key[2+4*y]=0;put16(key+3+4*y,600);}
    send_copy(key,sizeof key);assert(images && images->source);uint8_t p[33];packet(p,99,99,301,99,129,115);
    uint8_t *expected=malloc(105000);assert(expected);memcpy(expected,images->source->data+64,105000);
    snapshot_copy(expected,300,99,99,301,99,129,115);unsigned before=source_calls;int alloc=own_allocations;
    send_copy(p,17);assert(source_calls==before+1 && own_allocations==alloc && !memcmp(expected,images->source->data+64,105000));
    packet(p,100,180,101,181,63,31);snapshot_copy(expected,300,100,180,101,181,63,31);send_copy(p,17);
    assert(!memcmp(expected,images->source->data+64,105000));
    packet(p,599,349,0,0,2,2);before=source_calls;send_copy(p,17);assert(strstr(last_response,"invalid") && source_calls==before && !memcmp(expected,images->source->data+64,105000));
    free(expected);clear_all();
    packet(p,0,0,1,1,3,3);free_value=32000;uint8_t e=0;void *v=command(p,17,1,&e);assert(v && strstr(v,"allocation-failed") && !queued);release(&v);clear_all();
    drop=1;assert(!command(p,17,1,&e) && !queued && !own_allocations);clear_all();
    send_copy(p,17);assert(source_calls && images);delete_image(images);assert(!own_allocations && !timers);clear_all();
}
int main(void){differential();boundaries();native();printf("mode9: %u reference/snapshot/invalid cases; padded/odd pixels/all overlap directions, native queue/present/cleanup passed\n",cases);return 0;}
