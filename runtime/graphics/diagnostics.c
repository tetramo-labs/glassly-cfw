/* Optional current-screen diagnostics, not a G2 transport/timing emulator. */
#include "diagnostics.h"
#define P mm_graphics_native
#define WIDTH 80u
#define HEIGHT 18u
#define PIXELS (WIDTH*HEIGHT/2u)
typedef struct {
    void *image,*overlay;
    mm_native_image source;
    uint32_t worker,allocation;
    uint16_t recent[16],last,high,epoch;
    uint8_t flags,hidden,seen,resync,pos,failed_mode;
    uint32_t palette[16];
    uint8_t pixels[PIXELS];
} diagnostic_owner;
static void overlay_deleted(void *event) {diagnostic_owner *d=P.event_userdata(event);d->overlay=0;}
static void diagnostic_deleted(void *event) {
    diagnostic_owner *d=P.event_userdata(event);
    if(d->overlay)P.image_delete(d->overlay);
    P.cache_invalidate(&d->source);P.free(d);
}
static diagnostic_owner *diagnostic_find(void *parent) {return parent?P.find_owner(parent,diagnostic_deleted):0;}
static diagnostic_owner *diagnostic_get(void *parent) {
    diagnostic_owner *d=diagnostic_find(parent);if(d || !parent)return d;
    if(P.free_bytes()<65536u+sizeof(*d))return 0;
    d=P.alloc(sizeof(*d));if(!d)return 0;
    for(size_t i=0;i<sizeof(*d);i++)((uint8_t *)d)[i]=0;
    d->hidden=1;for(unsigned i=0;i<16;i++){d->recent[i]=65535;d->palette[i]=0xff000000u|i*0x111111u;}
    d->source=(mm_native_image){(HEIGHT<<21)|(WIDTH<<10)|9u,64u+PIXELS,(const uint8_t *)d->palette};
    d->image=P.image_create(parent);if(!d->image){P.free(d);return 0;}
    glassly_diagnostics_hidden(d->image,1);
    if(!P.on_delete(d->image,diagnostic_deleted,d)){P.image_delete(d->image);P.free(d);return 0;}
    return d;
}
/* Exact original16-bit ring/sentinel/resync behavior; never suppress drawing. */
static void diagnostic_frame(diagnostic_owner *d,int has,uint16_t fid) {
    d->seen=1;if(!has){d->resync=1;return;}
    for(unsigned i=0;i<16;i++)if(d->recent[i]==fid){d->flags|=4;return;}
    if(!d->resync){uint16_t n=(uint16_t)(fid-d->last);if(!n || n>0x8000)d->flags|=1;else if(n>1)d->flags|=2;}
    d->resync=0;d->last=fid;if(fid>d->high)d->high=fid;
    d->recent[d->pos]=fid;d->pos=(uint8_t)((d->pos+1)&15u);
}
void mm_diagnostics_frame(void *parent,const uint8_t *p,size_t n) {
    if(n<3)return;
    unsigned mode=p[0]&127u;uint16_t fid=0;
    if(mode==3){
        unsigned off=(p[0]&128u)?9u:5u;
        if(n<off+3u || ((p[0]&128u)&&(p[3]!=p[7]||p[4]!=p[8])) ||
           !p[3]||!p[4]||((unsigned)p[1]+p[3])*4u>600u||((unsigned)p[2]+p[4])*2u>350u)return;
        fid=(uint16_t)(p[off]|((unsigned)p[off+1]<<8));
    }else if(mode!=6)return;
    diagnostic_owner *d=diagnostic_get(parent);if(d)diagnostic_frame(d,mode==3,fid);
}
void *mm_diagnostics_control(void *parent,unsigned sub) {
    diagnostic_owner *d=diagnostic_get(parent);if(!d)return P.json("{\"glassly\":\"diagnostics\",\"abi\":1,\"result\":\"allocation-failed\"}");
    if(!sub){d->flags=d->seen=d->resync=d->pos=d->failed_mode=0;d->last=d->high=0;d->worker=d->allocation=0;for(unsigned i=0;i<16;i++)d->recent[i]=65535;}
    else if(sub==1)d->hidden=1;else if(sub==2)d->hidden=0;
    uint8_t state[20]={d->flags,d->hidden,d->seen,d->resync};
    uint32_t words[4]={d->last|((uint32_t)d->high<<16),d->worker,d->allocation,d->failed_mode|((uint32_t)d->epoch<<16)};
    for(unsigned i=0;i<16;i++)state[i+4]=(uint8_t)(words[i/4]>>(8*(i&3)));
    static const char pattern[]="{\"glassly\":\"diagnostics\",\"abi\":1,\"result\":\"ok\",\"presentation\":\"unchanged\",\"stateHex\":\"0000000000000000000000000000000000000000\"}";
    char text[sizeof(pattern)];for(unsigned i=0;i<sizeof(pattern);i++)text[i]=pattern[i];
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<20;i++){text[sizeof(text)-43+2*i]=hex[state[i]>>4];text[sizeof(text)-42+2*i]=hex[state[i]&15];}
    return P.json(text);
}
/* Compact3x5 glyph subset:0..9,A..F,R,S,W,H,-. Pixels remain private. */
static void diagnostic_glyph(diagnostic_owner *d,unsigned x,unsigned y,unsigned ch) {
    static const uint16_t font[]={0x7b6f,0x2492,0x73e7,0x73cf,0x5bc9,0x79cf,0x79ef,0x7249,0x7bef,0x7bcf,0x7bed,0x6bae,0x7927,0x6b6e,0x79a7,0x79a4,0x6bad,0x79cf,0x5b7d,0x5bed,0x01c0};
    uint16_t bits=font[ch];for(unsigned row=0;row<5;row++)for(unsigned col=0;col<3;col++)if(bits&(1u<<(14-row*3-col))){unsigned px=x+col,at=(y+row)*WIDTH/2+px/2;d->pixels[at]|=(uint8_t)(15u<<((px&1)?0:4));}
}
static void diagnostic_number(diagnostic_owner *d,unsigned x,unsigned y,uint32_t n,unsigned digits) {while(digits){digits--;diagnostic_glyph(d,x+digits*4,y,n&15u);n>>=4;}}
void mm_diagnostics_present(void *parent,void *graphics_image) {
    diagnostic_owner *d=diagnostic_find(parent);if(!d)return;
    if(d->overlay)glassly_diagnostics_hidden(d->overlay,d->hidden);
    if(d->hidden)return;
    if(!d->overlay){
        d->overlay=P.image_create(graphics_image);if(!d->overlay)return;
        if(!P.on_delete(d->overlay,overlay_deleted,d)){void *image=d->overlay;d->overlay=0;P.image_delete(image);return;}
    }
    for(unsigned i=0;i<PIXELS;i++)d->pixels[i]=0;
    diagnostic_glyph(d,0,0,d->flags&1?16:20);diagnostic_glyph(d,4,0,d->flags&2?17:20);diagnostic_glyph(d,8,0,d->flags&4?13:20);
    diagnostic_glyph(d,0,6,15);diagnostic_number(d,4,6,d->last,4);diagnostic_glyph(d,24,6,19);diagnostic_number(d,28,6,d->high,4);
    diagnostic_glyph(d,0,12,18);diagnostic_number(d,4,12,d->worker,8);diagnostic_glyph(d,40,12,10);diagnostic_number(d,44,12,d->allocation,8);
    P.cache_invalidate(&d->source);glassly_diagnostics_source(d->overlay,&d->source);
}
void mm_diagnostics_failure(void *parent,unsigned mode,int allocation) {diagnostic_owner *d=diagnostic_find(parent);if(d){d->worker++;d->failed_mode=(uint8_t)mode;if(allocation)d->allocation++;}}
void mm_diagnostics_cleanup(void *parent,uint16_t epoch) {diagnostic_owner *d=epoch?diagnostic_get(parent):diagnostic_find(parent);if(d){d->hidden=1;if(epoch)d->epoch=epoch;if(d->overlay)glassly_diagnostics_hidden(d->overlay,1);}}
uint16_t mm_diagnostics_epoch(void *parent) {diagnostic_owner *d=diagnostic_find(parent);return d?d->epoch:0;}
