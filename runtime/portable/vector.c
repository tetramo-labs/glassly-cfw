/* Derived from G2 vector.c, pinned commit 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce.
 * Modified 2026-10-31: caller-owned bounded buffers, explicit transforms/raster;
 * cache/device/timer integration absent. MIT, see PROVENANCE.md and LICENSE. */
#include "vector.h"
#include "geometry_internal.h"
typedef mm_vector_edge cfw_edge;
typedef mm_vector_path cfw_path;
typedef mm_vector_work cfw_vector_work;
typedef mm_vector_rotation cfw_rotation;
typedef mm_raster cfw_raster;
typedef struct { uint8_t type,flags,color,width; int16_t p[8]; } cfw_shape;
#define CFW_PATH_MAX_EDGES MM_VECTOR_MAX_EDGES
#define CFW_PATH_MAX_BYTES MM_VECTOR_MAX_BYTES
#define CFW_PATH_MAX_COMMANDS MM_VECTOR_MAX_COMMANDS
#define cfw_sin_deg mm_geometry_private_sin_deg
#define rs_line_q4 mm_geometry_private_line_q4
static uint16_t rd16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8)); }
static void rs_hspan(const cfw_raster *r,int32_t a,int32_t b,int32_t y,uint8_t c) {
    (void)mm_raster_span(r,a,b,y,c);
}
static void cfw_shape_draw(const cfw_raster *r,const cfw_shape *s) {
    uint8_t message[22];message[0]=36;message[1]=1;message[2]=s->type;
    message[3]=s->flags;message[4]=s->color;message[5]=s->width;
    for(unsigned i=0;i<8;i++) { uint16_t v=(uint16_t)s->p[i];message[6+2*i]=(uint8_t)v;message[7+2*i]=(uint8_t)(v>>8); }
    (void)mm_geometry_mode36(r,message,sizeof(message));
}
#define CFW_SHAPE_LINE 1u
#define CFW_SHAPE_RECT 2u
#define CFW_SHAPE_RECT_FILL 3u
#define CFW_SHAPE_CIRCLE 4u
#define CFW_SHAPE_CIRCLE_FILL 5u
#define CFW_SHAPE_TRI 6u
#define CFW_SHAPE_TRI_FILL 7u
#define CFW_SHAPE_QUAD 8u
#define CFW_SHAPE_QUAD_FILL 9u
#define CFW_SHAPE_BEZIER2 10u
#define CFW_SHAPE_BEZIER3 11u
#define CFW_SHAPE_ARC 12u
#define CFW_SHAPE_PIE 13u
static int32_t cfw_div_floor(int32_t num, int32_t den) {
    int32_t q = num / den;
    if ((num % den) != 0 && num < 0) q--;
    return q;
}
static int32_t cfw_clamp(int32_t v, int32_t lo, int32_t hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}
static int rs_span_pixels(int32_t a16, int32_t b16, int32_t *first, int32_t *last) {
    *first = cfw_div_floor(a16 + 7, 16);
    *last = cfw_div_floor(b16 + 7, 16) - 1;
    return *first <= *last;
}


/* Checked path compiler and transformed contour rasterizer. Included by scene.c
 * after shapes.c, sharing its clipped span/line primitives and trig table. */

static int32_t cv_abs(int32_t v) { return v < 0 ? -v : v; }

/* Signed floor(a*b/d), d positive. Ordinary panel geometry takes hardware
 * 32-bit division; large offscreen coordinates use bounded long division,
 * avoiding an unresolved compiler-runtime 64-bit division call. */
static int32_t cv_muldiv(int32_t a, int32_t b, int32_t d) {
    int64_t n = (int64_t)a * b;
    if (n >= -2147483647LL && n <= 2147483647LL)
        return cfw_div_floor((int32_t)n, d);
    uint64_t u = n < 0 ? (uint64_t)(-n) : (uint64_t)n;
    uint64_t q = 0, rem = 0;
    /* Constant shifts preserve the same restoring long division while avoiding
     * GCC RV32 __ashldi3/__lshrdi3 imports for variable 64-bit shifts. */
    for (int i = 0; i < 64; i++) {
        rem = (rem << 1) | (u >> 63);
        u <<= 1; q <<= 1;
        if (rem >= (uint32_t)d) { rem -= (uint32_t)d; q |= 1u; }
    }
    return n < 0 ? -(int32_t)q - (rem != 0) : (int32_t)q;
}

static int cv_edge(cfw_vector_work *w, uint32_t *n,
                   int32_t x0, int32_t y0, int32_t x1, int32_t y1) {
    if (x0 == x1 && y0 == y1) return 1;
    if (*n >= CFW_PATH_MAX_EDGES) return 0;
    w->edges[*n] = (cfw_edge){x0, y0, x1, y1};
    ++*n;
    return 1;
}

/* De Casteljau subdivision, <= 8 levels and 0.5 source pixel tolerance.
 * The compiler rejects edge overflow rather than silently dropping geometry. */
static int cv_curve(cfw_vector_work *w, uint32_t *n, const int32_t *p, uint32_t depth) {
    int32_t ux = 3*p[2]-2*p[0]-p[6], uy = 3*p[3]-2*p[1]-p[7];
    int32_t vx = 3*p[4]-2*p[6]-p[0], vy = 3*p[5]-2*p[7]-p[1];
    if (cv_abs(ux) <= 16 && cv_abs(uy) <= 16 && cv_abs(vx) <= 16 && cv_abs(vy) <= 16)
        return cv_edge(w,n,p[0],p[1],p[6],p[7]);
    if (depth == 8) return 0;
    int32_t a[8], b[8];
    for (uint32_t k=0;k<2;k++) {
        int32_t ab=(p[k]+p[k+2])/2, bc=(p[k+2]+p[k+4])/2, cd=(p[k+4]+p[k+6])/2;
        int32_t abc=(ab+bc)/2, bcd=(bc+cd)/2, mid=(abc+bcd)/2;
        a[k]=p[k]; a[k+2]=ab; a[k+4]=abc; a[k+6]=mid;
        b[k]=mid; b[k+2]=bcd; b[k+4]=cd; b[k+6]=p[k+6];
    }
    return cv_curve(w,n,a,depth+1) && cv_curve(w,n,b,depth+1);
}

/* Commands: 0 M(x,y), 1 L(x,y), 2 Q(cx,cy,x,y), 3 C(...), 4 Z.
 * Coordinates are signed int16 Q4; each subpath MUST explicitly close. */
static int cv_compile(cfw_vector_work *w, const uint8_t *src, uint32_t len) {
    uint32_t pos=0,n=0,commands=0;
    int open=0;
    int32_t x=0,y=0,sx=0,sy=0;
    if (!len || len > CFW_PATH_MAX_BYTES) return -1;
    while (pos<len) {
        uint8_t op=src[pos++];
        if (++commands > CFW_PATH_MAX_COMMANDS || op>4) return -1;
        uint32_t pairs=op==4?0:(op==2?2:(op==3?3:1));
        if (len-pos < pairs*4) return -1;
        int32_t p[8]={x,y,0,0,0,0,0,0};
        for (uint32_t k=0;k<pairs*2;k++) p[k+2]=(int16_t)rd16(src+pos+2*k);
        pos+=pairs*4;
        if (op==0) {
            if (open) return -1;
            x=sx=p[2]; y=sy=p[3]; open=1;
        } else {
            if (!open) return -1;
            if (op==4) {
                if (!cv_edge(w,&n,x,y,sx,sy)) return -1;
                x=sx; y=sy; open=0;
            } else if (op==1) {
                if (!cv_edge(w,&n,x,y,p[2],p[3])) return -1;
                x=p[2];y=p[3];
            } else {
                if (op==2) {
                    p[6]=p[4];p[7]=p[5];
                    for(uint32_t k=0;k<2;k++) {
                        p[k+4]=(p[k+6]+2*p[k+2])/3;
                        p[k+2]=(p[k]+2*p[k+2])/3;
                    }
                }
                if (!cv_curve(w,&n,p,0)) return -1;
                x=p[6];y=p[7];
            }
        }
    }
    return open ? -1 : (int)n;
}

static int32_t cv_sin(int32_t a) {
    a %= 360*256;
    if (a<0) a+=360*256;
    int32_t deg=a/256, f=a%256;
    /* Exact cardinal angles avoid a 32767/32768 shrink at 90 degrees. */
    int32_t v=deg==90?32768:(deg==270?-32768:cfw_sin_deg(deg));
    int32_t next=deg+1==90?32768:(deg+1==270?-32768:cfw_sin_deg(deg+1));
    return v+((next-v)*f)/256;
}

static void cv_rotate(int32_t *x, int32_t *y, int32_t sn,int32_t cs,int32_t px,int32_t py) {
    int32_t dx=*x-px,dy=*y-py;
    *x=px+(int32_t)(((int64_t)dx*cs-(int64_t)dy*sn+16384)>>15);
    *y=py+(int32_t)(((int64_t)dx*sn+(int64_t)dy*cs+16384)>>15);
}

static void cv_transform(cfw_vector_work *w, uint32_t n, const cfw_rotation *t) {
    if(t->angle%(360*256)==0)return;
    int32_t sn=cv_sin(t->angle),cs=cv_sin(t->angle%(360*256)+90*256);
    int32_t px=(int32_t)t->px*16,py=(int32_t)t->py*16;
    for(uint32_t i=0;i<n;i++) {
        cv_rotate(&w->edges[i].x0,&w->edges[i].y0,sn,cs,px,py);
        cv_rotate(&w->edges[i].x1,&w->edges[i].y1,sn,cs,px,py);
    }
}

static void cv_swap(cfw_vector_work *w,uint32_t a,uint32_t b) {
    int32_t x=w->xs[a];w->xs[a]=w->xs[b];w->xs[b]=x;
    int8_t wind=w->winds[a];w->winds[a]=w->winds[b];w->winds[b]=wind;
}
static void cv_sift(cfw_vector_work *w,uint32_t root,uint32_t count) {
    while(root*2+1<count) {
        uint32_t child=root*2+1;
        if(child+1<count && w->xs[child+1]>w->xs[child])child++;
        if(w->xs[root]>=w->xs[child])break;
        cv_swap(w,root,child);root=child;
    }
}
/* O(k log k), including adversarial contours with hundreds of crossings. */
static void cv_sort(cfw_vector_work *w,uint32_t count) {
    for(uint32_t i=count/2;i>0;i--)cv_sift(w,i-1,count);
    for(uint32_t i=count;i>1;i--){cv_swap(w,0,i-1);cv_sift(w,0,i-1);}
}

static void cv_fill(const cfw_raster *r, cfw_vector_work *w, uint32_t n, uint8_t rule, uint8_t color) {
    int32_t ymin=((int32_t)r->height)*16, ymax=0;
    for(uint32_t i=0;i<n;i++) {
        cfw_edge e=w->edges[i];
        if(e.y0<ymin)ymin=e.y0;
        if(e.y1<ymin)ymin=e.y1;
        if(e.y0>ymax)ymax=e.y0;
        if(e.y1>ymax)ymax=e.y1;
    }
    int32_t first=cfw_clamp(cfw_div_floor(ymin,16),0,((int32_t)r->height));
    int32_t last=cfw_clamp(cfw_div_floor(ymax,16),-1,((int32_t)r->height)-1);
    for(int32_t row=first;row<=last;row++) {
        int32_t yc=row*16+8; uint32_t k=0;
        for(uint32_t i=0;i<n;i++) {
            cfw_edge e=w->edges[i]; int8_t winding=1;
            if(e.y0==e.y1)continue;
            if(e.y0>e.y1) {int32_t v=e.x0;e.x0=e.x1;e.x1=v;v=e.y0;e.y0=e.y1;e.y1=v;winding=-1;}
            if(yc<e.y0 || yc>=e.y1)continue;
            int32_t x=e.x0+cv_muldiv(yc-e.y0,e.x1-e.x0,e.y1-e.y0);
            w->xs[k]=x;w->winds[k++]=winding;
        }
        cv_sort(w,k);
        int32_t winding=0,start=0;
        for(uint32_t i=0;i<k;) {
            int32_t x=w->xs[i], delta=0; uint32_t hits=0;
            do {delta+=w->winds[i++];hits++;} while(i<k && w->xs[i]==x);
            int before=rule?(winding&1):(winding!=0);
            winding=rule?(winding^(int32_t)(hits&1)):(winding+delta);
            int after=rule?(winding&1):(winding!=0);
            if(!before && after)start=x;
            if(before && !after) {int32_t a,b;if(rs_span_pixels(start,x,&a,&b))rs_hspan(r,a,b,row,color&15);}
        }
    }
}

static void cv_path_draw(const cfw_raster *r, cfw_vector_work *w, const cfw_path *path,
                         const int16_t *p, const cfw_rotation *t, uint8_t color) {
    int32_t scale=cfw_clamp(p[2],0,2048); /* Q8, 0..8x */
    uint32_t count=path->count;
    if(count>CFW_PATH_MAX_EDGES)count=CFW_PATH_MAX_EDGES; /* the work buffer's size; cv_compile never exceeds it */
    for(uint32_t i=0;i<count;i++) {
        cfw_edge e=path->edges[i];
        e.x0=e.x0*scale/256+(int32_t)p[0]*16;e.y0=e.y0*scale/256+(int32_t)p[1]*16;
        e.x1=e.x1*scale/256+(int32_t)p[0]*16;e.y1=e.y1*scale/256+(int32_t)p[1]*16;
        w->edges[i]=e;
    }
    cv_transform(w,count,t);
    cv_fill(r,w,count,path->rule,color);
}

/* Rotated primitives become contours. Zero/full-turn angles keep the legacy
 * renderer exactly. Rounded outlines use outer/inner even-odd contours. */
static void cv_ellipse(cfw_vector_work *w,uint32_t *n,int32_t cx,int32_t cy,int32_t rad,
                       int32_t a0,int32_t span,int pie) {
    int32_t px=cx+(int32_t)(((int64_t)rad*cv_sin((a0%360+90)*256))>>15);
    int32_t py=cy+(int32_t)(((int64_t)rad*cv_sin((a0%360)*256))>>15);
    int32_t sx=px,sy=py;
    if(pie)cv_edge(w,n,cx,cy,px,py);
    uint32_t seg=(uint32_t)cv_abs(span)/4+1;
    for(uint32_t i=1;i<=seg;i++) {
        int32_t a=(a0*256+span*256*(int32_t)i/(int32_t)seg)%(360*256);
        int32_t nx=cx+(int32_t)(((int64_t)rad*cv_sin(a+90*256))>>15);
        int32_t ny=cy+(int32_t)(((int64_t)rad*cv_sin(a))>>15);
        cv_edge(w,n,px,py,nx,ny);px=nx;py=ny;
    }
    if(pie)cv_edge(w,n,px,py,cx,cy);
    else if(cv_abs(span)==360)cv_edge(w,n,px,py,sx,sy);
}

static void cv_roundrect(cfw_vector_work *w,uint32_t *n,int32_t x,int32_t y,int32_t ww,int32_t hh,int32_t rad) {
    if(ww<=0 || hh<=0)return;
    rad=cfw_clamp(rad,0,(ww<hh?ww:hh)/2);
    int32_t cx[4]={x+ww-rad,x+ww-rad,x+rad,x+rad};
    int32_t cy[4]={y+rad,y+hh-rad,y+hh-rad,y+rad};
    int32_t px=x+ww-rad,py=y,sx=px,sy=py;
    for(int k=0;k<4;k++)for(int j=0;j<=15;j++) {
        int32_t a=(-90+k*90+j*6)*256;
        int32_t nx=cx[k]+(int32_t)(((int64_t)rad*cv_sin(a+90*256))>>15);
        int32_t ny=cy[k]+(int32_t)(((int64_t)rad*cv_sin(a))>>15);
        cv_edge(w,n,px,py,nx,ny);px=nx;py=ny;
    }
    cv_edge(w,n,px,py,sx,sy);
}

static void cv_shape_draw(const cfw_raster *r,cfw_vector_work *w,const cfw_shape *s,
                           const cfw_rotation *t) {
    if(t->angle%(360*256)==0 || s->type>CFW_SHAPE_PIE) {cfw_shape_draw(r,s);return;}
    uint32_t n=0;int fill=0;int32_t p[8];
    for(uint32_t i=0;i<8;i++)p[i]=(int32_t)s->p[i]*16+8;
    int32_t wd=s->width?s->width:1;
    switch(s->type) {
    case CFW_SHAPE_RECT: case CFW_SHAPE_RECT_FILL: {
        int32_t x=(int32_t)s->p[0]*16,y=(int32_t)s->p[1]*16;
        int32_t ww=cfw_clamp(s->p[2],0,2047)*16,hh=cfw_clamp(s->p[3],0,2047)*16;
        int32_t rad=cfw_clamp(s->p[4],0,2047)*16;
        cv_roundrect(w,&n,x,y,ww,hh,rad);
        if(s->type==CFW_SHAPE_RECT)cv_roundrect(w,&n,x+wd*16,y+wd*16,ww-wd*32,hh-wd*32,rad-wd*16);
        fill=1;break;
    }
    case CFW_SHAPE_CIRCLE:case CFW_SHAPE_CIRCLE_FILL: {
        int32_t rad=cfw_clamp(s->p[2],0,1023)*16+8;
        cv_ellipse(w,&n,p[0],p[1],rad,0,360,0);
        if(s->type==CFW_SHAPE_CIRCLE && rad>wd*16)cv_ellipse(w,&n,p[0],p[1],rad-wd*16,0,360,0);
        fill=1;break;
    }
    case CFW_SHAPE_ARC:case CFW_SHAPE_PIE: {
        int32_t span=cfw_clamp((int32_t)s->p[4]-s->p[3],-360,360);
        cv_ellipse(w,&n,p[0],p[1],cfw_clamp(s->p[2],0,1023)*16,s->p[3]%360,span,s->type==CFW_SHAPE_PIE);
        fill=s->type==CFW_SHAPE_PIE;break;
    }
    case CFW_SHAPE_BEZIER2:
        p[6]=p[4];p[7]=p[5];
        for(uint32_t k=0;k<2;k++){p[k+4]=(p[k+6]+2*p[k+2])/3;p[k+2]=(p[k]+2*p[k+2])/3;}
        /* fall through */
    case CFW_SHAPE_BEZIER3:
        /* Rendering remains bounded even for extreme legacy coordinates. */
        if(!cv_curve(w,&n,p,0))return;
        break;
    default: {
        uint32_t vertices=s->type==CFW_SHAPE_LINE?2:((s->type==CFW_SHAPE_TRI || s->type==CFW_SHAPE_TRI_FILL)?3:4);
        for(uint32_t i=1;i<vertices;i++)cv_edge(w,&n,p[2*i-2],p[2*i-1],p[2*i],p[2*i+1]);
        if(vertices>2)cv_edge(w,&n,p[2*vertices-2],p[2*vertices-1],p[0],p[1]);
        fill=s->type==CFW_SHAPE_TRI_FILL || s->type==CFW_SHAPE_QUAD_FILL;
    }}
    cv_transform(w,n,t);
    if(fill)cv_fill(r,w,n,1,s->color);
    else for(uint32_t i=0;i<n;i++) {
        cfw_edge e=w->edges[i];
        /* rs_line_q4's wide-line products require bounded deltas. Clip to
         * the panel plus stroke margin before entering the old rasterizer. */
        int32_t lo=-wd*16-16,hiX=(((int32_t)r->width)+wd+1)*16,hiY=(((int32_t)r->height)+wd+1)*16;
        for(int side=0;side<4;side++) {
            int axis=side/2;int32_t bound=(side&1)?(axis?hiY:hiX):lo;
            int32_t a=axis?e.y0:e.x0,b=axis?e.y1:e.x1;
            int outA=(side&1)?a>bound:a<bound,outB=(side&1)?b>bound:b<bound;
            if(outA && outB){e.x0=e.x1=0;e.y0=e.y1=-1000000;break;}
            if(outA!=outB) {
                int32_t den=b-a,num=bound-a,other;
                int32_t diff=axis?e.x1-e.x0:e.y1-e.y0;
                if(den<0){den=-den;num=-num;}
                other=(axis?e.x0:e.y0)+cv_muldiv(num,diff,den);
                if(outA){if(axis){e.y0=bound;e.x0=other;}else{e.x0=bound;e.y0=other;}}
                else{if(axis){e.y1=bound;e.x1=other;}else{e.x1=bound;e.y1=other;}}
            }
        }
        if(e.y0==-1000000)continue;
        rs_line_q4(r,e.x0,e.y0,e.x1,e.y1,wd,s->color&15);
    }
}

static int mmv_overlap(const void *a,size_t an,const void *b,size_t bn) {
    if(!an || !bn)return 0;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=y ? y-x<an : x-y<bn;
}
static int mmv_work(mm_vector_work *w,size_t bytes) {
    return w && bytes>=sizeof(*w) && (uintptr_t)w%_Alignof(mm_vector_work)==0;
}
size_t mm_vector_path_bytes(unsigned n) {
    return n<=MM_VECTOR_MAX_EDGES ? sizeof(mm_vector_path)+n*sizeof(mm_vector_edge) : 0;
}
int mm_vector_compile(mm_vector_work *w,size_t bytes,const uint8_t *src,size_t length,
                      uint8_t rule,mm_vector_path *out,size_t capacity) {
    if(!mmv_work(w,bytes))return MM_VECTOR_TARGET;
    if(!src || !length || length>MM_VECTOR_MAX_BYTES || rule>1)return MM_VECTOR_MESSAGE;
    if((!out && capacity) || (out && (uintptr_t)out%_Alignof(mm_vector_path)))return MM_VECTOR_TARGET;
    if(mmv_overlap(w,sizeof(*w),src,length) || (out &&
       (mmv_overlap(w,sizeof(*w),out,capacity) || mmv_overlap(src,length,out,capacity))))return MM_VECTOR_ALIAS;
    int n=cv_compile(w,src,(uint32_t)length);
    if(n<0)return MM_VECTOR_MESSAGE;
    if(!out)return n;
    size_t required=mm_vector_path_bytes((unsigned)n);
    if(capacity<required)return MM_VECTOR_CAPACITY;
    out->count=(uint16_t)n;out->rule=rule;out->pad=0;
    /* Volatile stores prevent -Os from lowering a struct copy to libc memcpy. */
    for(int i=0;i<n;i++) {
        volatile mm_vector_edge *e=&out->edges[i];
        e->x0=w->edges[i].x0;e->y0=w->edges[i].y0;
        e->x1=w->edges[i].x1;e->y1=w->edges[i].y1;
    }
    return n;
}
static int mmv_target(const mm_raster *t,mm_vector_work *w,size_t bytes) {
    if(mm_raster_validate(t) || t->width>MM_VECTOR_MAX_DIMENSION || t->height>MM_VECTOR_MAX_DIMENSION ||
       !mmv_work(w,bytes))return MM_VECTOR_TARGET;
    if(mmv_overlap(w,sizeof(*w),t->pixels,t->bytes) || mmv_overlap(w,sizeof(*w),t,sizeof(*t)) ||
       mmv_overlap(t,sizeof(*t),t->pixels,t->bytes))return MM_VECTOR_ALIAS;
    return 0;
}
static int mmv_rotation(const mm_vector_rotation *t) {
    return t && t->angle>=-MM_VECTOR_MAX_ANGLE && t->angle<=MM_VECTOR_MAX_ANGLE;
}
int mm_vector_draw_path(const mm_raster *t,mm_vector_work *w,size_t bytes,
                        const mm_vector_path *path,size_t path_bytes,
                        const mm_vector_transform *transform,uint8_t color) {
    int valid=mmv_target(t,w,bytes);if(valid)return valid;
    if(!path || (uintptr_t)path%_Alignof(mm_vector_path) || path_bytes<sizeof(*path))return MM_VECTOR_MESSAGE;
    if(path->count>MM_VECTOR_MAX_EDGES || path->rule>1 || path->pad ||
       path_bytes<mm_vector_path_bytes(path->count))return MM_VECTOR_MESSAGE;
    if(!transform || transform->scale>2048 || !mmv_rotation(&transform->rotation) || color>15)return MM_VECTOR_TRANSFORM;
    if(mmv_overlap(w,sizeof(*w),path,path_bytes) || mmv_overlap(t->pixels,t->bytes,path,path_bytes) ||
       mmv_overlap(w,sizeof(*w),transform,sizeof(*transform)) ||
       mmv_overlap(t->pixels,t->bytes,transform,sizeof(*transform)))return MM_VECTOR_ALIAS;
    for(unsigned i=0;i<path->count;i++) {
        mm_vector_edge e=path->edges[i];
        if(e.x0 < -32768 || e.x0>32767 || e.y0 < -32768 || e.y0>32767 ||
           e.x1 < -32768 || e.x1>32767 || e.y1 < -32768 || e.y1>32767)return MM_VECTOR_MESSAGE;
    }
    int16_t p[3]={transform->x,transform->y,(int16_t)transform->scale};
    cv_path_draw(t,w,path,p,&transform->rotation,color);return 0;
}
int mm_vector_draw_shape(const mm_raster *t,mm_vector_work *w,size_t bytes,
                         const uint8_t *record,size_t length,const mm_vector_rotation *rotation) {
    int valid=mmv_target(t,w,bytes);if(valid)return valid;
    if(!record || length!=20 || record[0]<1 || record[0]>13)return MM_VECTOR_MESSAGE;
    if(!mmv_rotation(rotation))return MM_VECTOR_TRANSFORM;
    if(mmv_overlap(w,sizeof(*w),record,length) || mmv_overlap(t->pixels,t->bytes,record,length) ||
       mmv_overlap(w,sizeof(*w),rotation,sizeof(*rotation)) ||
       mmv_overlap(t->pixels,t->bytes,rotation,sizeof(*rotation)))return MM_VECTOR_ALIAS;
    cfw_shape s;s.type=record[0];s.flags=record[1];s.color=record[2];s.width=record[3];
    for(unsigned i=0;i<8;i++)s.p[i]=(int16_t)rd16(record+4+2*i);
    cv_shape_draw(t,w,&s,rotation);return 0;
}
#ifdef MM_VECTOR_TESTING
int32_t mm_vector_test_muldiv(int32_t a,int32_t b,int32_t d) { return cv_muldiv(a,b,d); }
#endif

#ifdef MM_SCENE_EXTERNAL_STORE
int mm_vector_draw_path_reader(const mm_raster *t,mm_vector_work *w,size_t bytes,
                              const mm_scene_bytes *path,const mm_vector_transform *transform,uint8_t color) {
    int rc=mmv_target(t,w,bytes);if(rc)return rc;
    if(!path||!transform)return MM_VECTOR_TRANSFORM;
    if(sizeof(*path)>UINTPTR_MAX-(uintptr_t)path || sizeof(*transform)>UINTPTR_MAX-(uintptr_t)transform)return MM_VECTOR_ALIAS;
    /* Loading edges mutates work, and filling mutates pixels. Neither may
     * contain descriptors, callback tables or backend-owned state used by a
     * later read. Reject these before the first callback or workspace write. */
    if(mmv_overlap(w,sizeof(*w),path,sizeof(*path))||mmv_overlap(t->pixels,t->bytes,path,sizeof(*path))||
       mmv_overlap(w,sizeof(*w),transform,sizeof(*transform))||mmv_overlap(t->pixels,t->bytes,transform,sizeof(*transform)))return MM_VECTOR_ALIAS;
    if(mm_scene_bytes_read(path,0,0,0))return MM_VECTOR_MESSAGE;
    if(path->store && (mmv_overlap(w,sizeof(*w),path->store,sizeof(*path->store))||
       mmv_overlap(t->pixels,t->bytes,path->store,sizeof(*path->store))||
       path->store->aliases(path->store->user,w,sizeof(*w))||
       path->store->aliases(path->store->user,t->pixels,t->bytes)))return MM_VECTOR_ALIAS;
    if(path->ram&&(mmv_overlap(w,sizeof(*w),path->ram,path->length)||mmv_overlap(t->pixels,t->bytes,path->ram,path->length)))return MM_VECTOR_ALIAS;
    if(transform->scale>2048||!mmv_rotation(&transform->rotation)||color>15)return MM_VECTOR_TRANSFORM;
    uint8_t header[4];rc=mm_scene_bytes_read(path,0,header,4);if(rc)return rc==-2?-6:MM_VECTOR_MESSAGE;
    unsigned count=header[0]|((unsigned)header[1]<<8);
    if(count>MM_VECTOR_MAX_EDGES||header[2]>1||header[3]||path->length<mm_vector_path_bytes(count))return MM_VECTOR_MESSAGE;
    /* No framebuffer writes until every source edge has been read/validated. */
    for(unsigned i=0;i<count;i++) {
        uint8_t raw[16];rc=mm_scene_bytes_read(path,4+16*i,raw,16);if(rc)return rc==-2?-6:MM_VECTOR_MESSAGE;
        int32_t v[4];for(unsigned k=0;k<4;k++) {uint32_t x=(uint32_t)raw[k*4]|((uint32_t)raw[k*4+1]<<8)|((uint32_t)raw[k*4+2]<<16)|((uint32_t)raw[k*4+3]<<24);v[k]=(int32_t)x;if(v[k]<-32768||v[k]>32767)return MM_VECTOR_MESSAGE;}
        w->edges[i]=(mm_vector_edge){v[0],v[1],v[2],v[3]};
    }
    for(unsigned i=0;i<count;i++) {
        mm_vector_edge *e=&w->edges[i];int32_t scale=transform->scale;
        e->x0=e->x0*scale/256+(int32_t)transform->x*16;e->y0=e->y0*scale/256+(int32_t)transform->y*16;
        e->x1=e->x1*scale/256+(int32_t)transform->x*16;e->y1=e->y1*scale/256+(int32_t)transform->y*16;
    }
    cv_transform(w,count,&transform->rotation);cv_fill(t,w,count,header[2],color);return 0;
}
#endif
