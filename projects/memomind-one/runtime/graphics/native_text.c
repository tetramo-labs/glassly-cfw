/* Resource-backed native glyphs; do not use the incompatible G2 bitmap ABI. */
#include "native_text.h"
_Static_assert(sizeof(mm_native_text_glyph)==16,"Native glyph descriptor layout");
_Static_assert(offsetof(mm_native_text_glyph,bpp_flags)==14,"Native glyph bpp offset");
#define CONTROL UINT32_C(0x80000000)
static uint32_t rd16(const uint8_t *p) {return p[0]|((uint32_t)p[1]<<8);}
static int32_t s16(const uint8_t *p) {uint32_t n=rd16(p);return n<32768u?(int32_t)n:(int32_t)n-65536;}
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    if(!an || !bn)return 0;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;
}
static unsigned font_bpp(uint32_t f) {
    if(f==MM_NATIVE_TEXT_DEFAULT_FONT || f==MM_NATIVE_TEXT_LARGE_FONT)return 2;
    return f==MM_NATIVE_TEXT_EMOJI_FONT?1:0;
}
static int utf8(const uint8_t *p,size_t n,size_t *used,uint32_t *cp) {
    if(!n)return 0;
    uint32_t a=p[0];
    if(a>=0x20 && a<=0x7f){*used=1;*cp=a;return 1;}
    if(a>=0xc2 && a<=0xdf){
        if(n<2 || (p[1]&0xc0)!=0x80)return 0;
        *used=2;*cp=((a&31)<<6)|(p[1]&63);return 1;
    }
    if(a>=0xe0 && a<=0xef){
        if(n<3 || (p[1]&0xc0)!=0x80 || (p[2]&0xc0)!=0x80 ||
           (a==0xe0 && p[1]<0xa0) || (a==0xed && p[1]>=0xa0))return 0;
        *used=3;*cp=((a&15)<<12)|((uint32_t)(p[1]&63)<<6)|(p[2]&63);return 1;
    }
    if(a>=0xf0 && a<=0xf4){
        if(n<4 || (p[1]&0xc0)!=0x80 || (p[2]&0xc0)!=0x80 ||
           (p[3]&0xc0)!=0x80 || (a==0xf0 && p[1]<0x90) ||
           (a==0xf4 && p[1]>=0x90))return 0;
        *used=4;*cp=((a&7)<<18)|((uint32_t)(p[1]&63)<<12)|
                   ((uint32_t)(p[2]&63)<<6)|(p[3]&63);return 1;
    }
    return 0;
}
static uint32_t next_cp(const uint32_t *tokens,size_t count,size_t i) {
    while(++i<count)if(!(tokens[i]&CONTROL))return tokens[i];
    return 0;
}
static int glyph(const mm_native_text_api *api,uint32_t cp,uint32_t next,
                 mm_native_text_glyph *g,const uint8_t **bits,int32_t *baseline) {
    *g=(mm_native_text_glyph){0};*bits=0;
    if(!api->metrics(api->context,api->root_font,g,cp,next))return 0;
    unsigned bpp=font_bpp(g->font);
    int32_t height;uint8_t flags;
    if(!bpp || !api->font_info(api->context,g->font,&height,baseline,&flags) ||
       height<=0 || height>128 || *baseline< -128 || *baseline>128 || (flags&3) ||
       (g->bpp_flags&16) || g->box_w>255 || g->box_h>255)return 0;
    /* Native zero-area spacing glyphs may advertise1bpp on the default font. */
    if(!g->box_w || !g->box_h)return 1;
    if((g->bpp_flags&15)!=bpp ||
       ((uint32_t)g->box_w*g->box_h*bpp+7u)/8u>1000u)return 0;
    *bits=api->bitmap(api->context,g->font,cp);return *bits!=0;
}
static uint32_t scaled_u(uint32_t v,unsigned num,unsigned den) {return (v*num+den/2u)/den;}
static int32_t scaled_s(int32_t v,unsigned num,unsigned den) {
    return v<0?-(int32_t)scaled_u((uint32_t)-v,num,den):(int32_t)scaled_u((uint32_t)v,num,den);
}
static int32_t floor_div(int32_t v,unsigned den) {
    return v<0?-(int32_t)(((uint32_t)-v+den-1u)/den):(int32_t)((uint32_t)v/den);
}
static void dirty_rect(mm_scene_dirty *dirty,int32_t l,int32_t t,int32_t r,int32_t b) {
    if(!dirty || l>=r || t>=b)return;
    if(dirty->n<MM_SCENE_RECT_MAX){
        dirty->r[dirty->n++]=(mm_scene_rect){(uint16_t)l,(uint16_t)t,(uint16_t)(r-l),(uint16_t)(b-t)};
    } else {
        /* Keep all earlier coverage and include this glyph when capacity fills. */
        mm_scene_rect *p=&dirty->r[MM_SCENE_RECT_MAX-1];
        int32_t old_r=(int32_t)p->l+p->w,old_b=(int32_t)p->t+p->h;
        if(p->l<l)l=p->l;
        if(p->t<t)t=p->t;
        if(old_r>r)r=old_r;
        if(old_b>b)b=old_b;
        *p=(mm_scene_rect){(uint16_t)l,(uint16_t)t,(uint16_t)(r-l),(uint16_t)(b-t)};
    }
}
int mm_native_builtin_text(void *user,const mm_raster *target,const uint8_t *src,size_t len,
                           mm_scene_dirty *dirty,uint32_t *tokens,size_t cap) {
    const mm_native_text_api *api=user;
#ifdef MM_NATIVE_TEXT_FIRMWARE
    if(!api)api=&mm_native_text_firmware_api;
#endif
    if(!target || !src || !tokens || !api || len<6 || len>6+MM_NATIVE_TEXT_MAX_BYTES ||
       mm_raster_validate(target) || len!=6u+src[5] ||
#ifndef MM_TEXT_COMMANDS
       src[5]>MM_NATIVE_TEXT_MAX_BYTES ||
#endif
       (dirty && dirty->n>MM_SCENE_RECT_MAX) || !font_bpp(api->root_font) ||
       !api->ready || !api->font_info || !api->metrics || !api->bitmap)return -1;
    /* Scratch uses at most one entry per byte. Restrict alias checks to storage
     * this call may access; do not multiply untrusted cap. */
    size_t token_bytes=(cap<src[5]?cap:(size_t)src[5])*sizeof(*tokens);
    if(overlap(target->pixels,target->bytes,src,len) ||
       overlap(target->pixels,target->bytes,target,sizeof(*target)) ||
       overlap(target->pixels,target->bytes,api,sizeof(*api)) ||
       overlap(target->pixels,target->bytes,tokens,token_bytes) ||
       overlap(src,len,tokens,token_bytes) || overlap(api,sizeof(*api),tokens,token_bytes) ||
       overlap(target,sizeof(*target),tokens,token_bytes) ||
       (dirty && (overlap(target->pixels,target->bytes,dirty,sizeof(*dirty)) ||
                  overlap(dirty,sizeof(*dirty),src,len) || overlap(dirty,sizeof(*dirty),tokens,token_bytes) ||
                  overlap(dirty,sizeof(*dirty),api,sizeof(*api)) || overlap(dirty,sizeof(*dirty),target,sizeof(*target)))))return -1;
    size_t count=0,pos=0;
    while(pos<src[5]){
        if(count>=cap)return -1;
        uint32_t b=src[6+pos];
        if(b>=1 && b<=31){tokens[count++]=CONTROL|b;pos++;continue;}
        size_t used;uint32_t cp;
        if(!utf8(src+6+pos,src[5]-pos,&used,&cp))return -1;
        tokens[count++]=cp;pos+=used;
    }
    int32_t height,root_baseline;uint8_t flags;
    if(!api->ready(api->context) ||
       !api->font_info(api->context,api->root_font,&height,&root_baseline,&flags) ||
       height<=0 || height>128 || root_baseline< -128 || root_baseline>128 || (flags&3))return -1;
    mm_native_text_glyph g;const uint8_t *bits;int32_t baseline;
    for(size_t i=0;i<count;i++)if(!(tokens[i]&CONTROL))
        if(!glyph(api,tokens[i],next_cp(tokens,count,i),&g,&bits,&baseline))return -1;
    unsigned num=api->scale_num?api->scale_num:1u,den=api->scale_den?api->scale_den:1u;
    /* The cursor keeps 1/den px so scaled advances do not drift along a line. */
    int32_t xf=s16(src)*(int32_t)den,y=s16(src+2);unsigned options=src[4],top=options&15u;
    uint8_t level[16];
    for(unsigned v=0;v<16;v++)level[v]=(uint8_t)(v*top/15u);
    for(size_t i=0;i<count;i++){
        if(tokens[i]&CONTROL){xf+=((int32_t)(tokens[i]&31u)-11)*(int32_t)den;continue;}
        /* Stable synchronous resource callbacks make this identical to preflight. */
        if(!glyph(api,tokens[i],next_cp(tokens,count,i),&g,&bits,&baseline))return -1;
        if(bits){
            uint32_t w=scaled_u(g.box_w,num,den),h=scaled_u(g.box_h,num,den);
            if(!w)w=1u;
            if(!h)h=1u;
            /* Every glyph's bottom rounds from the same baseline row, so a line stays level. */
            int32_t gx=floor_div(xf,den)+scaled_s(g.ofs_x,num,den);
            int32_t gy=y+scaled_s(height-baseline-g.ofs_y,num,den)-(int32_t)h;
            int32_t l=gx<0?0:gx,t=gy<0?0:gy,r=gx+(int32_t)w,b=gy+(int32_t)h;
            if(r>(int32_t)target->width)r=(int32_t)target->width;
            if(b>(int32_t)target->height)b=(int32_t)target->height;
            unsigned bpp=g.bpp_flags&15u,mask=(1u<<bpp)-1u,weight=bpp==1?15u:5u;
            if(l<r && t<b){
                /* The 2x2 sample of output pixel o stays ((4o+1)*box)/(4*size) and
                 * ((4o+3)*box)/(4*size) on each axis; columns are stepped, not divided. */
                uint32_t xd=4u*w,yd=4u*h,xq=g.box_w/w,xr=4u*(g.box_w%w),n0=(4u*(uint32_t)(l-gx)+1u)*g.box_w,n1=n0+2u*g.box_w;
                uint32_t q0s=n0/xd,r0s=n0%xd,q1s=n1/xd,r1s=n1%xd;
                for(int32_t py=t;py<b;py++){
                    uint32_t oy=(uint32_t)(py-gy),row0=((4u*oy+1u)*g.box_h)/yd*g.box_w,row1=((4u*oy+3u)*g.box_h)/yd*g.box_w;
                    uint32_t q0=q0s,r0=r0s,q1=q1s,r1=r1s;
                    for(int32_t px=l;px<r;px++){
                        uint32_t s00=(row0+q0)*bpp,s01=(row0+q1)*bpp,s10=(row1+q0)*bpp,s11=(row1+q1)*bpp;
                        unsigned sum=(((bits[s00>>3]>>(8u-bpp-(s00&7u)))&mask)+((bits[s01>>3]>>(8u-bpp-(s01&7u)))&mask)+
                                      ((bits[s10>>3]>>(8u-bpp-(s10&7u)))&mask)+((bits[s11>>3]>>(8u-bpp-(s11&7u)))&mask))*weight;
                        q0+=xq;r0+=xr;if(r0>=xd){r0-=xd;q0++;}
                        q1+=xq;r1+=xr;if(r1>=xd){r1-=xd;q1++;}
                        unsigned value=(sum+2u)>>2;
                        if(!value && (options&16u))continue;
                        if(options&32u)value=15u-value;
                        value=level[value];
                        size_t at=(size_t)py*target->stride+(uint32_t)px/2u;
                        unsigned shift=(px&1)?0:4;
                        target->pixels[at]=(uint8_t)((target->pixels[at]&~(15u<<shift))|(value<<shift));
                    }
                }
            }
            dirty_rect(dirty,l,t,r,b);
        }
        xf+=(int32_t)((uint32_t)g.advance*num);
    }
    return 0;
}
#ifdef MM_NATIVE_TEXT_FIRMWARE
_Static_assert(sizeof(void *)==4,"Native API requires RV32");
static uint32_t native_word(uint32_t f,unsigned offset) {
    const uint8_t *p=(const uint8_t *)(uintptr_t)f+offset;
    return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static int native_ready(void *context) {
    (void)context;return *(const volatile uint8_t *)(uintptr_t)0x0205a048u!=0;
}
static int native_info(void *context,uint32_t f,int32_t *h,int32_t *b,uint8_t *flags) {
    (void)context;if(!font_bpp(f))return 0;
    *h=(int32_t)native_word(f,8);*b=(int32_t)native_word(f,12);*flags=(uint8_t)native_word(f,16);return 1;
}
static int native_metrics(void *context,uint32_t font,mm_native_text_glyph *g,uint32_t cp,uint32_t next) {
    (void)context;
    typedef int (*fn)(const void *,mm_native_text_glyph *,uint32_t,uint32_t);
    return ((fn)(uintptr_t)0x042d153cu)((const void *)(uintptr_t)font,g,cp,next);
}
static const uint8_t *native_bitmap(void *context,uint32_t font,uint32_t cp) {
    (void)context;
    typedef const uint8_t *(*fn)(const void *,uint32_t);
    return ((fn)(uintptr_t)0x042d14beu)((const void *)(uintptr_t)font,cp);
}
const mm_native_text_api mm_native_text_firmware_api={
    0,MM_NATIVE_TEXT_DEFAULT_FONT,native_ready,native_info,native_metrics,native_bitmap,
    MM_NATIVE_TEXT_SCALE_NUM,MM_NATIVE_TEXT_SCALE_DEN
};
#endif
