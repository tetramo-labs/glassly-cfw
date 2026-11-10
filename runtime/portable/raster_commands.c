#include "raster_commands.h"
#include "rle.h"
static int overlap(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return an && bn && (x<=y?y-x<an:x-y<bn);
}
static int parse(const mm_raster *r,const uint8_t *p,size_t n,
                 uint32_t *x,uint32_t *y,uint32_t *w,uint32_t *h,size_t *off) {
    if(!r || sizeof(*r)>UINTPTR_MAX-(uintptr_t)r || mm_raster_validate(r) ||
       r->bytes>UINTPTR_MAX-(uintptr_t)r->pixels || !p || n<3 || n>65535u ||
       n>UINTPTR_MAX-(uintptr_t)p || overlap(r,sizeof(*r),p,n) ||
       overlap(r->pixels,r->bytes,r,sizeof(*r)) || overlap(r->pixels,r->bytes,p,n))return -1;
    unsigned mode=p[0]&127u;
    *x=*y=0;*w=(r->width+1u)/2u;*h=r->height;*off=1;
    if(mode==3){
        if(p[0]&128u){
            if(n<12 || p[3]!=p[7] || p[4]!=p[8])return -1;
            *off=11;
        }else{if(n<8)return -1;*off=7;}
        uint32_t left=(uint32_t)p[1]*4u,top=(uint32_t)p[2]*2u;
        uint32_t width=(uint32_t)p[3]*4u,height=(uint32_t)p[4]*2u;
        if(!width || !height || left>r->width || width>r->width-left ||
           top>r->height || height>r->height-top)return -1;
        *x=left/2u;*y=top;*w=width/2u;*h=height;
    }else if(mode!=6)return -1;
    if(*w>UINT32_MAX/2u/ *h || mm_rle_validate(p+*off,n-*off,*w* *h*2u))return -1;
    return 0;
}
int mm_raster_command_validate(const mm_raster *r,const uint8_t *p,size_t n) {
    uint32_t x,y,w,h;size_t off;return parse(r,p,n,&x,&y,&w,&h,&off);
}
int mm_raster_command_draw(const mm_raster *r,const uint8_t *p,size_t n) {
    uint32_t x,y,w,h;size_t off;if(parse(r,p,n,&x,&y,&w,&h,&off))return -1;
    mm_rle_surface s={r->pixels,r->bytes,(r->width+1u)/2u,r->height,r->stride};
    return mm_rle_decode_window(&s,x,y,w,h,p+off,n-off);
}
