#include "../native_text.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
/* Six 2bpp pixels: rows [0,1,2],[3,2,1], with no row alignment. */
static const uint8_t bits2[]={0x1b,0x90};
static const uint8_t bits1[]={0xa8}; /* [1,0,1],[0,1,0] */
typedef struct {
    int ready,fail_bitmap,fail_metrics,bad_font,bad_bpp,subpixel;
    int calls,bitmap_calls;
    uint32_t last_next,a_next;
    uint16_t w,h,advance;
    int16_t dx,dy;
    const uint8_t *custom;
} fixture;
static int ready(void *v){return ((fixture *)v)->ready;}
static int info(void *v,uint32_t font,int32_t *h,int32_t *base,uint8_t *flags){
    fixture *f=v;*h=4;*base=font==MM_NATIVE_TEXT_EMOJI_FONT?2:1;*flags=(uint8_t)f->subpixel;return 1;
}
static int metrics(void *v,uint32_t font,mm_native_text_glyph *g,uint32_t cp,uint32_t next){
    fixture *f=v;f->calls++;f->last_next=next;if(cp=='A')f->a_next=next;
    if((int)cp==f->fail_metrics)return 0;
    g->font=cp==0x2605?MM_NATIVE_TEXT_EMOJI_FONT:font;
    if(f->bad_font)g->font=(uint32_t)f->bad_font;
    g->advance=f->advance;g->box_w=f->w;g->box_h=f->h;g->ofs_x=f->dx;g->ofs_y=f->dy;
    g->bpp_flags=(uint8_t)(cp==0x2605?1:2);
    if(f->bad_bpp)g->bpp_flags=(uint8_t)f->bad_bpp;
    if(cp==' '){g->box_w=0;g->box_h=0;g->bpp_flags=1;}
    return 1;
}
static const uint8_t *bitmap(void *v,uint32_t font,uint32_t cp){
    fixture *f=v;f->bitmap_calls++;
    if((int)cp==f->fail_bitmap)return 0;
    if(f->custom)return f->custom;
    return font==MM_NATIVE_TEXT_EMOJI_FONT?bits1:bits2;
}
static fixture fresh(void){fixture f={0};f.ready=1;f.w=3;f.h=2;f.advance=3;return f;}
static mm_native_text_api api(fixture *f){return (mm_native_text_api){f,MM_NATIVE_TEXT_DEFAULT_FONT,ready,info,metrics,bitmap,0,0};}
static unsigned pixel(const mm_raster *r,unsigned x,unsigned y){return (r->pixels[y*r->stride+x/2]>>((x&1)?0:4))&15;}
static size_t message(uint8_t *out,int x,int y,unsigned options,const uint8_t *str,size_t n){
    out[0]=(uint8_t)x;out[1]=(uint8_t)((uint16_t)x>>8);out[2]=(uint8_t)y;out[3]=(uint8_t)((uint16_t)y>>8);
    out[4]=(uint8_t)options;out[5]=(uint8_t)n;memcpy(out+6,str,n);return n+6;
}
static void unchanged_failure(fixture *f,const uint8_t *text,size_t size){
    uint8_t pixels[32],before[32],msg[134];uint32_t tokens[128];
    memset(pixels,0x9a,sizeof(pixels));memcpy(before,pixels,sizeof(before));
    mm_raster r={pixels,sizeof(pixels),5,4,8};mm_scene_dirty d={0},old;
    d.n=1;d.r[0]=(mm_scene_rect){1,1,1,1};memcpy(&old,&d,sizeof(d));
    mm_native_text_api a=api(f);size_t n=message(msg,0,-1,15,text,size);
    assert(mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128)==-1);
    assert(!memcmp(pixels,before,sizeof(pixels)));assert(!memcmp(&d,&old,sizeof(d)));
}
static void packing_clipping(void){
    fixture f=fresh();mm_native_text_api a=api(&f);uint8_t pixels[20],msg[16];uint32_t tokens[128];
    memset(pixels,0xcc,sizeof(pixels));mm_raster r={pixels,sizeof(pixels),5,4,5};mm_scene_dirty d={0};
    size_t n=message(msg,0,-1,15,(const uint8_t *)"A",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    unsigned expected[6]={0,5,10,15,10,5};
    for(unsigned y=0;y<2;y++)for(unsigned x=0;x<3;x++)assert(pixel(&r,x,y)==expected[y*3+x]);
    assert(pixel(&r,3,0)==12 && pixel(&r,4,0)==12);
    for(unsigned y=0;y<4;y++){assert((pixels[y*5+2]&15)==12);assert(pixels[y*5+3]==0xcc && pixels[y*5+4]==0xcc);}
    assert(d.n==1 && d.r[0].l==0 && d.r[0].t==0 && d.r[0].w==3 && d.r[0].h==2);
    memset(pixels,0xcc,sizeof(pixels));d.n=0;n=message(msg,-1,-2,15,(const uint8_t *)"A",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    assert(pixel(&r,0,0)==10 && pixel(&r,1,0)==5 && pixel(&r,2,0)==12);
    assert(d.n==1 && d.r[0].w==2 && d.r[0].h==1);
    /* The fallback baseline is2, not the root's1: y0 is the first row. */
    const uint8_t star[]={0xe2,0x98,0x85};memset(pixels,0xcc,sizeof(pixels));d.n=0;
    n=message(msg,0,0,15,star,sizeof(star));assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,1));
    assert(pixel(&r,0,0)==15 && pixel(&r,1,0)==0 && pixel(&r,2,0)==15);
    assert(pixel(&r,0,1)==0 && pixel(&r,1,1)==15 && pixel(&r,2,1)==0);
}
static void options_and_controls(void){
    fixture f=fresh();mm_native_text_api a=api(&f);uint8_t pixels[40],msg[20];uint32_t tokens[128];
    mm_raster r={pixels,sizeof(pixels),10,4,10};mm_scene_dirty d={0};
    for(unsigned inverse=0;inverse<2;inverse++)for(unsigned transparent=0;transparent<2;transparent++)for(unsigned top=0;top<16;top++){
        memset(pixels,0xcc,sizeof(pixels));d.n=0;
        size_t n=message(msg,0,-1,top|(inverse?32:0)|(transparent?16:0),(const uint8_t *)"A",1);
        assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
        const unsigned values[]={0,5,10,15,10,5};
        for(unsigned y=0;y<2;y++)for(unsigned x=0;x<3;x++){
            unsigned v=values[y*3+x];unsigned want=!v && transparent?12:((inverse?15-v:v)*top/15);
            assert(pixel(&r,x,y)==want);
        }
    }
    /* Shift12 adds1; advance3 puts B at4. Shift1 subtracts10. */
    const uint8_t text[]={'A',12,'B',1};memset(pixels,0xcc,sizeof(pixels));d.n=0;
    size_t n=message(msg,0,-1,15,text,sizeof(text));assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    assert(d.n==2 && d.r[1].l==4 && pixel(&r,4,0)==0 && pixel(&r,6,0)==10);
    assert(f.a_next=='B');
    assert(tokens[1]==0x8000000cu && tokens[3]==0x80000001u);
    /* Next glyph skips controls during both passes. */
    f.fail_metrics='B';f.last_next=0;unchanged_failure(&f,text,sizeof(text));assert(f.calls>0);
}
static void failures(void){
    const uint8_t pair[]={'A','B'};fixture f=fresh();f.fail_bitmap='B';unchanged_failure(&f,pair,2);assert(f.calls==2);
    f=fresh();f.fail_metrics='B';unchanged_failure(&f,pair,2);
    f=fresh();f.bad_font=0x0200fb44;unchanged_failure(&f,pair,2);assert(f.bitmap_calls==0);
    f=fresh();f.bad_font=0x123456;unchanged_failure(&f,pair,2);
    f=fresh();f.bad_bpp=4;unchanged_failure(&f,pair,2);
    f=fresh();f.bad_bpp=18;unchanged_failure(&f,pair,2);
    f=fresh();f.subpixel=1;unchanged_failure(&f,pair,2);
    f=fresh();f.ready=0;unchanged_failure(&f,pair,2);assert(f.calls==0);
    f=fresh();f.w=255;f.h=255;unchanged_failure(&f,pair,2);
    static const uint8_t malformed[][4]={{0},{0xc0,0x80},{0xc1,0xbf},{0x80},{0xe0,0x80,0x80},{0xed,0xa0,0x80},{0xf0,0x80,0x80,0x80},{0xf4,0x90,0x80,0x80},{0xf5,0x80,0x80,0x80},{0xe2,0x82},{0xf0,0x90,0x80},{0xc2,0x20}};
    const size_t sizes[]={1,2,2,1,3,3,4,4,4,2,3,2};
    for(size_t i=0;i<sizeof(sizes)/sizeof(*sizes);i++){f=fresh();unchanged_failure(&f,malformed[i],sizes[i]);assert(f.calls==0);}
}
static void edges(void){
    fixture f=fresh();mm_native_text_api a=api(&f);uint8_t pixels[16],msg[134];uint32_t tokens[128];
    memset(pixels,0xcc,sizeof(pixels));mm_raster r={pixels,sizeof(pixels),4,4,4};mm_scene_dirty d={0};
    size_t n=message(msg,0,-1,15,(const uint8_t *)" ",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));assert(!f.bitmap_calls && !d.n);
    n=message(msg,0,-1,15,(const uint8_t *)"A",1);
    assert(mm_native_builtin_text(&a,&r,msg,n+1,&d,tokens,128)==-1);
    assert(mm_native_builtin_text(&a,&r,msg,n,&d,tokens,0)==-1);
    assert(mm_native_builtin_text(0,&r,msg,n,&d,tokens,128)==-1);
    assert(mm_native_builtin_text(&a,&r,msg,n,&d,(uint32_t *)(void *)pixels,128)==-1);
    memcpy(pixels,msg,n);assert(mm_native_builtin_text(&a,&r,pixels,n,&d,tokens,128)==-1);
    memset(pixels,0xcc,sizeof(pixels));d.n=MM_SCENE_RECT_MAX;d.r[MM_SCENE_RECT_MAX-1]=(mm_scene_rect){3,3,1,1};
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));assert(d.n==MM_SCENE_RECT_MAX);
    assert(d.r[MM_SCENE_RECT_MAX-1].l==0 && d.r[MM_SCENE_RECT_MAX-1].t==0 && d.r[MM_SCENE_RECT_MAX-1].w==4 && d.r[MM_SCENE_RECT_MAX-1].h==4);
    d.n=0;memset(pixels,0xcc,sizeof(pixels));n=message(msg,32767,32767,15,(const uint8_t *)"A",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));assert(!d.n);
    for(size_t i=0;i<sizeof(pixels);i++)assert(pixels[i]==0xcc);
    n=message(msg,0,0,15,(const uint8_t *)"",0);assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,0));
    /* All UTF8 scalar widths accepted, plus strict max128-byte scene text. */
    const uint8_t valid[]={0xc2,0x80,0xdf,0xbf,0xe0,0xa0,0x80,0xed,0x9f,0xbf,0xf0,0x90,0x80,0x80,0xf4,0x8f,0xbf,0xbf};
    n=message(msg,32767,0,15,valid,sizeof(valid));assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    uint8_t controls[128];memset(controls,11,sizeof(controls));n=message(msg,0,0,15,controls,sizeof(controls));
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
}
static void scaled(void){
    /* Boxes, offsets, advances and the baseline at2/3; control shifts stay in panel px. */
    fixture f=fresh();mm_native_text_api a=api(&f);a.scale_num=2;a.scale_den=3;
    uint8_t pixels[20],msg[16];uint32_t tokens[128];
    memset(pixels,0xcc,sizeof(pixels));mm_raster r={pixels,sizeof(pixels),5,4,5};mm_scene_dirty d={0};
    size_t n=message(msg,0,-1,15,(const uint8_t *)"AB",2);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    /* A3x2 glyph becomes2x1 means of2x2 samples: (0+5+15+10)/4 and (5+10+10+5)/4; B lands at advance3*2/3. */
    for(unsigned x=0;x<4;x++)assert(pixel(&r,x,0)==8);
    assert(pixel(&r,4,0)==12 && pixel(&r,0,1)==12);
    assert(d.n==2 && d.r[0].l==0 && d.r[0].t==0 && d.r[0].w==2 && d.r[0].h==1 && d.r[1].l==2 && d.r[1].w==2);
    const uint8_t shifted[]={'A',12,'B'};memset(pixels,0xcc,sizeof(pixels));d.n=0;
    n=message(msg,0,-1,32|15,shifted,sizeof(shifted));assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    assert(pixel(&r,0,0)==7 && pixel(&r,1,0)==7 && pixel(&r,2,0)==12 && pixel(&r,3,0)==7 && pixel(&r,4,0)==7);
    f.dx=-1;memset(pixels,0xcc,sizeof(pixels));d.n=0;n=message(msg,0,-1,15,(const uint8_t *)"A",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));
    assert(pixel(&r,0,0)==8 && pixel(&r,1,0)==12 && d.n==1 && d.r[0].l==0 && d.r[0].w==1);
    /* The fallback font's baseline (2) scales too: the star's single row is y itself. */
    f=fresh();const uint8_t star[]={0xe2,0x98,0x85};memset(pixels,0xcc,sizeof(pixels));d.n=0;
    n=message(msg,0,0,15,star,sizeof(star));assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,1));
    assert(pixel(&r,0,0)==8 && pixel(&r,1,0)==8 && pixel(&r,0,1)==12 && pixel(&r,2,0)==12);
    /* 1/1 and0/0 are the unscaled adapter. */
    a.scale_num=1;a.scale_den=1;memset(pixels,0xcc,sizeof(pixels));d.n=0;n=message(msg,0,-1,15,(const uint8_t *)"A",1);
    assert(!mm_native_builtin_text(&a,&r,msg,n,&d,tokens,128));assert(pixel(&r,0,1)==15 && pixel(&r,2,0)==10 && d.r[0].w==3);
}
/* The drawing loop as it was through revision 26: four divided samples per
 * output pixel and a division per level. */
static uint32_t old_scaled_u(uint32_t v,unsigned num,unsigned den){return (v*num+den/2u)/den;}
static int32_t old_scaled_s(int32_t v,unsigned num,unsigned den){
    return v<0?-(int32_t)old_scaled_u((uint32_t)-v,num,den):(int32_t)old_scaled_u((uint32_t)v,num,den);
}
static int32_t old_floor_div(int32_t v,unsigned den){
    return v<0?-(int32_t)(((uint32_t)-v+den-1u)/den):(int32_t)((uint32_t)v/den);
}
static void old_text(const mm_native_text_api *api,const mm_raster *target,int x,int y,unsigned options,const uint32_t *cps,size_t count){
    int32_t height,root_baseline;uint8_t flags;
    assert(api->font_info(api->context,api->root_font,&height,&root_baseline,&flags));
    unsigned num=api->scale_num?api->scale_num:1u,den=api->scale_den?api->scale_den:1u,top=options&15u;
    int32_t xf=x*(int32_t)den;
    for(size_t i=0;i<count;i++){
        mm_native_text_glyph g={0};int32_t font_height,baseline;
        assert(api->metrics(api->context,api->root_font,&g,cps[i],i+1<count?cps[i+1]:0));
        assert(api->font_info(api->context,g.font,&font_height,&baseline,&flags));
        const uint8_t *bits=g.box_w && g.box_h?api->bitmap(api->context,g.font,cps[i]):0;
        if(bits){
            uint32_t w=old_scaled_u(g.box_w,num,den),h=old_scaled_u(g.box_h,num,den);
            if(!w)w=1u;
            if(!h)h=1u;
            int32_t gx=old_floor_div(xf,den)+old_scaled_s(g.ofs_x,num,den);
            int32_t gy=y+old_scaled_s(height-baseline-g.ofs_y,num,den)-(int32_t)h;
            int32_t l=gx<0?0:gx,t=gy<0?0:gy,r=gx+(int32_t)w,b=gy+(int32_t)h;
            if(r>(int32_t)target->width)r=(int32_t)target->width;
            if(b>(int32_t)target->height)b=(int32_t)target->height;
            unsigned bpp=g.bpp_flags&15u,mask=(1u<<bpp)-1u;
            for(int32_t py=t;py<b;py++)for(int32_t px=l;px<r;px++){
                uint32_t ox=(uint32_t)(px-gx),oy=(uint32_t)(py-gy);unsigned sum=0;
                for(unsigned k=0;k<4;k++){
                    uint32_t sx=((4u*ox+((k&1u)?3u:1u))*g.box_w)/(4u*w);
                    uint32_t sy=((4u*oy+((k&2u)?3u:1u))*g.box_h)/(4u*h);
                    uint32_t bit=(sy*g.box_w+sx)*bpp;
                    unsigned value=(bits[bit>>3]>>(8u-bpp-(bit&7u)))&mask;
                    sum+=bpp==1?value*15u:value*5u;
                }
                unsigned value=(sum+2u)/4u;
                if(!value && (options&16u))continue;
                if(options&32u)value=15u-value;
                value=value*top/15u;
                size_t at=(size_t)py*target->stride+(uint32_t)px/2u;
                unsigned shift=(px&1)?0:4;
                target->pixels[at]=(uint8_t)((target->pixels[at]&~(15u<<shift))|(value<<shift));
            }
        }
        xf+=(int32_t)((uint32_t)g.advance*num);
    }
}
/* Random boxes, scales up and down, both depths, every option, positions on
 * and off each edge: the same bytes as the old loop. */
static void division_free_sampling(void){
    static uint8_t want[64*96],got[64*96],glyph_bits[1000];
    uint32_t seed=0x2468ace1u,cases=0;
#define RND() (seed=seed*1664525u+1013904223u,seed>>8)
    for(unsigned k=0;k<20000;k++){
        fixture f=fresh();mm_native_text_api a=api(&f);
        int star=(int)(RND()&1u);unsigned bpp=star?1u:2u,limit=8000u/bpp;
        f.w=(uint16_t)(1u+RND()%(star?120u:80u));if(f.w>limit)f.w=(uint16_t)limit;
        unsigned rows=limit/f.w;if(rows>255u)rows=255u;
        f.h=(uint16_t)(1u+RND()%rows);
        for(unsigned i=0;i<sizeof(glyph_bits);i++)glyph_bits[i]=(uint8_t)RND();
        f.custom=glyph_bits;f.dx=(int16_t)((int)(RND()%41u)-20);f.dy=(int16_t)((int)(RND()%41u)-20);f.advance=(uint16_t)(RND()%40u);
        switch(RND()%4u){
        case 0:a.scale_num=0;a.scale_den=0;break;
        case 1:a.scale_num=MM_NATIVE_TEXT_SCALE_NUM;a.scale_den=MM_NATIVE_TEXT_SCALE_DEN;break;
        default:a.scale_num=(uint8_t)(1u+RND()%12u);a.scale_den=(uint8_t)(1u+RND()%12u);break;
        }
        uint32_t width=1u+RND()%128u,height=1u+RND()%96u;
        mm_raster rw={want,sizeof(want),width,height,64},rg=rw;rg.pixels=got;
        int x=(int)(RND()%220u)-60,y=(int)(RND()%220u)-40;unsigned options=RND()&63u;
        uint32_t cps[3];size_t count=star?1u:1u+RND()%3u;uint8_t text[3];
        if(star){cps[0]=0x2605;text[0]=0xe2;text[1]=0x98;text[2]=0x85;}
        else for(size_t i=0;i<count;i++){cps[i]='A';text[i]='A';}
        for(unsigned i=0;i<sizeof(want);i++)want[i]=got[i]=(uint8_t)RND();
        uint8_t msg[16];uint32_t tokens[8];mm_scene_dirty d={0};
        size_t n=message(msg,x,y,options,text,star?3u:count);
        assert(!mm_native_builtin_text(&a,&rg,msg,n,&d,tokens,8));
        old_text(&a,&rw,x,y,options,cps,count);
        assert(!memcmp(want,got,sizeof(want)));cases++;
    }
#undef RND
    printf("division-free sampling matches the old loop in %u cases\n",(unsigned)cases);
}
int main(void){packing_clipping();options_and_controls();failures();edges();scaled();division_free_sampling();puts("native text tests passed");return 0;}
