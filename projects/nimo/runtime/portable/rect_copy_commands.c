/* Adapted from pinned G2 draw.c rect_copy_4bpp and zlib_glue.c mode9.
 * Explicit byte memmove avoids a freestanding libc dependency. MIT. */
#include "rect_copy_commands.h"
typedef struct {uint32_t sx,sy,dx,dy,w,h;} copy_rect;
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return an && bn && (x<=y?y-x<an:x-y<bn);
}
static uint32_t rd16(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8);}
static int parse(const mm_raster *r,const uint8_t *p,size_t n,copy_rect *c) {
    if(!r || sizeof(*r)>UINTPTR_MAX-(uintptr_t)r || mm_raster_validate(r) ||
       r->bytes>UINTPTR_MAX-(uintptr_t)r->pixels || !p || n<17 || n>65535u ||
       n>UINTPTR_MAX-(uintptr_t)p || overlap(r,sizeof(*r),p,n) ||
       overlap(r->pixels,r->bytes,r,sizeof(*r)) || overlap(r->pixels,r->bytes,p,n))return -1;
    if((p[0]&127u)!=9 || ((p[0]&128u) && n<33))return -1;
    c->sx=rd16(p+1);c->sy=rd16(p+3);c->w=rd16(p+5);c->h=rd16(p+7);
    c->dx=rd16(p+9);c->dy=rd16(p+11);
    if(!c->w || !c->h || c->w!=rd16(p+13) || c->h!=rd16(p+15) ||
       c->sx>r->width || c->w>r->width-c->sx || c->dx>r->width || c->w>r->width-c->dx ||
       c->sy>r->height || c->h>r->height-c->sy || c->dy>r->height || c->h>r->height-c->dy)return -1;
    return 0;
}
int mm_rect_copy_validate(const mm_raster *r,const uint8_t *p,size_t n){copy_rect c;return parse(r,p,n,&c);}
int mm_rect_copy_draw(const mm_raster *r,const uint8_t *p,size_t n) {
    copy_rect c;if(parse(r,p,n,&c))return -1;
    int rev_y=c.dy>c.sy,rev_x=c.dx>c.sx;
    for(uint32_t i=0;i<c.h;i++){
        uint32_t y=rev_y?c.h-1u-i:i;
        uint8_t *src=r->pixels+(size_t)(c.sy+y)*r->stride;
        uint8_t *dst=r->pixels+(size_t)(c.dy+y)*r->stride;
        if(!((c.sx|c.dx|c.w)&1u)){
            uint32_t bytes=c.w/2u;
            for(uint32_t j=0;j<bytes;j++){
                uint32_t x=rev_x?bytes-1u-j:j;
                dst[c.dx/2u+x]=src[c.sx/2u+x];
            }
        }else{
            for(uint32_t j=0;j<c.w;j++){
                uint32_t x=rev_x?c.w-1u-j:j,sx=c.sx+x,dx=c.dx+x;
                uint8_t value=(sx&1u)?src[sx/2u]&15u:src[sx/2u]>>4;
                uint8_t *out=dst+dx/2u;
                *out=(dx&1u)?(uint8_t)((*out&0xf0u)|value):(uint8_t)((*out&15u)|(value<<4));
            }
        }
    }
    return 0;
}
