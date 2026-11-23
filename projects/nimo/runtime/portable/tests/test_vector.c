/* Applicable pinned vector_host_test predicates plus differential/bounds tests.
 * MIT. Scene/timer/lease/transaction predicates remain unimplemented. */
#include "../vector.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int g2_vector_compile_reference(mm_vector_work *,const uint8_t *,uint32_t);
void g2_vector_path_reference(const mm_raster *,const mm_vector_path *,const mm_vector_transform *,uint8_t);
void g2_vector_shape_reference(const mm_raster *,const uint8_t *,const mm_vector_rotation *);
int32_t mm_vector_test_muldiv(int32_t,int32_t,int32_t);
#define cv_muldiv mm_vector_test_muldiv
#define CFW_PATH_MAX_EDGES MM_VECTOR_MAX_EDGES
#define CHECK(c) do { assertions++;assert(c); } while(0)
static unsigned assertions,compilations,drawings;
static mm_vector_work work,reference_work;
static _Alignas(mm_vector_path) uint8_t storage[sizeof(mm_vector_path)+MM_VECTOR_MAX_EDGES*sizeof(mm_vector_edge)];
static mm_vector_path *path=(mm_vector_path *)(void *)storage;
static uint8_t commands[8192];
static void put16(uint8_t *p,int v) { p[0]=(uint8_t)v;p[1]=(uint8_t)((unsigned)v>>8); }
static uint32_t point(uint32_t at,uint8_t op,int x,int y) {
    commands[at]=op;put16(commands+at+1,x*16);put16(commands+at+3,y*16);return at+5;
}
static uint32_t boxpath(uint32_t at,int x,int y,int w,int h,int reverse) {
    at=point(at,0,x,y);
    at=point(at,1,reverse?x:x+w,reverse?y+h:y);
    at=point(at,1,x+w,y+h);
    at=point(at,1,reverse?x+w:x,reverse?y:y+h);
    commands[at++]=4;return at;
}
static int compile(uint32_t len,int rule) {
    int n=mm_vector_compile(&work,sizeof(work),commands,len,(uint8_t)rule,path,sizeof(storage));
    int old=g2_vector_compile_reference(&reference_work,commands,len);
    assert(n==old);
    if(n>=0)assert(!memcmp(path->edges,reference_work.edges,(size_t)n*sizeof(mm_vector_edge)));
    compilations++;return n;
}
static uint8_t fb[640*480/2];
static struct { uint8_t *fb; } scene={fb},*sc=&scene;
static unsigned pixel_at(const uint8_t *p,int x,int y) { uint8_t b=p[y*320+x/2];return x&1?b&15:b>>4; }
static unsigned count_color(const uint8_t *p,unsigned c) {
    unsigned n=0;for(unsigned i=0;i<sizeof(fb);i++){n+=(p[i]>>4)==c;n+=(p[i]&15)==c;}return n;
}
static void draw(mm_vector_transform t,uint8_t color) {
    memset(fb,0,sizeof(fb));mm_raster r={fb,sizeof(fb),640,480,320};
    assert(mm_vector_draw_path(&r,&work,sizeof(work),path,mm_vector_path_bytes(path->count),&t,color)==0);
}
static void original_pixels(void) {
    mm_vector_transform identity={0,0,256,{0,0,0}};
    uint32_t len=boxpath(0,20,20,120,120,0);len=boxpath(len,50,50,60,60,0);
    assert(compile(len,1)>=0);draw(identity,15);
    CHECK(pixel_at(sc->fb,30,30)==15);CHECK(pixel_at(sc->fb,80,80)==0);
    CHECK(count_color(sc->fb,15)==120*120-60*60);
    assert(compile(len,0)>=0);draw(identity,15);CHECK(pixel_at(sc->fb,80,80)==15);
    len=boxpath(0,20,20,120,120,0);len=boxpath(len,50,50,60,60,1);
    assert(compile(len,0)>=0);draw(identity,15);CHECK(pixel_at(sc->fb,80,80)==0);
    len=boxpath(0,-20,-20,50,50,0);len=boxpath(len,200,200,20,20,0);
    assert(compile(len,0)>=0);draw(identity,15);CHECK(count_color(sc->fb,15)==900+400);
    len=point(0,0,100,200);commands[len++]=3;
    int v[]={100,40,240,40,240,200};for(int i=0;i<6;i++){put16(commands+len,v[i]*16);len+=2;}
    commands[len++]=2;int q[]={170,260,100,200};for(int i=0;i<4;i++){put16(commands+len,q[i]*16);len+=2;}
    commands[len++]=4;assert(compile(len,0)>=0);draw(identity,15);
    CHECK(path->count>8);
    CHECK(pixel_at(sc->fb,170,130)==15);CHECK(pixel_at(sc->fb,170,40)==0);
    uint8_t rec[20]={3,0,15,0};put16(rec+4,100);put16(rec+6,100);put16(rec+8,80);put16(rec+10,40);
    mm_raster target={fb,sizeof(fb),640,480,320};mm_vector_rotation rot={90*256,140,120};
    memset(fb,0,sizeof fb);assert(mm_vector_draw_shape(&target,&work,sizeof(work),rec,sizeof rec,&rot)==0);
    uint32_t area=count_color(sc->fb,15);CHECK(area>=3100 && area<=3300);
    CHECK(pixel_at(sc->fb,140,85)==15);CHECK(pixel_at(sc->fb,105,120)==0);
    len=boxpath(0,0,0,40,20,0);assert(compile(len,0)>=0);
    draw((mm_vector_transform){100,100,512,{90*256,100,100}},7);
    CHECK(pixel_at(sc->fb,80,140)==7);
}
static void original_fuzz(void) {
    uint32_t seed=0x12345678;
    for(int k=0;k<10000;k++) {
        uint32_t len=(uint32_t)k%256+1;
        for(uint32_t i=0;i<len;i++){seed=seed*1664525u+1013904223u;commands[i]=(uint8_t)(seed>>24);}
        int n=compile(len,0);CHECK(n>=-1 && n<=(int)CFW_PATH_MAX_EDGES);
    }
    for(int i=0;i<10000;i++) {
        seed=seed*1664525u+1013904223u;int32_t a=(int32_t)(seed%2000000)-1000000;
        seed=seed*1664525u+1013904223u;int32_t b=(int32_t)(seed%2000000)-1000000;
        int32_t d=2000001;int64_t product=(int64_t)a*b;
        int64_t expected=product/d;if(product%d<0)expected--;
        CHECK(cv_muldiv(a,b,d)==expected);
    }
}
static uint32_t random_seed=0x973a51;
static uint32_t rnd(void) {random_seed^=random_seed<<13;random_seed^=random_seed>>17;random_seed^=random_seed<<5;return random_seed;}
static void differential(int shape,const uint8_t *record,const mm_vector_transform *t,unsigned width,unsigned height,unsigned stride) {
    size_t bytes=(size_t)stride*height;
    uint8_t *a=malloc(bytes+66),*b=malloc(bytes+66);assert(a && b);
    memset(a,0xa5,bytes+66);memset(b,0xa5,bytes+66);
    mm_raster ours={a+33,bytes,width,height,stride},original={b+33,bytes,width,height,stride};
    if(shape) {
        assert(mm_vector_draw_shape(&ours,&work,sizeof(work),record,20,&t->rotation)==0);
        g2_vector_shape_reference(&original,record,&t->rotation);
    } else {
        assert(mm_vector_draw_path(&ours,&work,sizeof(work),path,mm_vector_path_bytes(path->count),t,15)==0);
        g2_vector_path_reference(&original,path,t,15);
    }
    assert(!memcmp(a,b,bytes+66));
    for(unsigned i=0;i<33;i++)assert(a[i]==0xa5 && a[33+bytes+i]==0xa5);
    for(unsigned y=0;y<height;y++) {
        if(width&1)assert((ours.pixels[y*stride+width/2]&15)==5);
        for(unsigned x=(width+1)/2;x<stride;x++)assert(ours.pixels[y*stride+x]==0xa5);
    }
    drawings++;free(a);free(b);
}
static void renders(void) {
    uint32_t len=boxpath(0,-40,-40,180,180,0);len=boxpath(len,-10,-10,60,60,1);
    const int angles[]={0,90*256,180*256,270*256,360*256,37*256,-91*256-21,MM_VECTOR_MAX_ANGLE};
    for(unsigned rule=0;rule<2;rule++) {
        assert(compile(len,rule)>=0);
        for(unsigned a=0;a<sizeof angles/sizeof angles[0];a++)for(unsigned scale=0;scale<4;scale++) {
            mm_vector_transform t={100,150,(uint16_t)(scale==3?2048:scale*256),{angles[a],120,100}};
            differential(0,0,&t,600,350,320);differential(0,0,&t,601,175,311);
        }
    }
    for(unsigned type=1;type<=13;type++)for(unsigned a=0;a<sizeof angles/sizeof angles[0];a++) {
        int16_t p[8]={100,100,60,40,15,140,180,220};
        if(type>=6 && type<=11){int16_t pts[]={100,100,160,110,140,160,190,170};for(int i=0;i<8;i++)p[i]=pts[i];}
        if(type==12 || type==13){p[3]=0;p[4]=250;}
        uint8_t rec[20]={(uint8_t)type,0,15,3};for(unsigned i=0;i<8;i++)put16(rec+4+2*i,p[i]);
        mm_vector_transform t={0,0,256,{angles[a],140,140}};differential(1,rec,&t,600,350,320);
        if(a==5) {mm_raster target={fb,sizeof fb,640,480,320};memset(fb,0,sizeof fb);assert(mm_vector_draw_shape(&target,&work,sizeof work,rec,20,&t.rotation)==0);CHECK(count_color(sc->fb,15)>0);}
    }
    for(unsigned k=0;k<50;k++) {
        len=point(0,0,0,0);commands[len++]=3;
        for(unsigned j=0;j<6;j++){put16(commands+len,(int16_t)rnd());len+=2;}
        commands[len++]=2;for(unsigned j=0;j<4;j++){put16(commands+len,(int16_t)rnd());len+=2;}commands[len++]=4;
        int n=compile(len,k&1);
        if(n>=0) {mm_vector_transform t={(int16_t)rnd(),(int16_t)rnd(),2048,{37*256,(int16_t)rnd(),(int16_t)rnd()}};differential(0,0,&t,600,350,320);}
    }
    uint8_t wide[20]={1,0,15,255};put16(wide+4,-32768);put16(wide+6,-32768);put16(wide+8,32767);put16(wide+10,32767);
    mm_vector_transform wide_t={0,0,256,{37*256,512,512}};differential(1,wide,&wide_t,1024,1024,513);
    for(unsigned k=0;k<200;k++) {
        uint8_t rec[20]={(uint8_t)(k%13+1),0,15,255};
        for(unsigned i=0;i<8;i++)put16(rec+4+2*i,(int16_t)rnd());
        mm_vector_transform t={0,0,256,{37*256,(int16_t)rnd(),(int16_t)rnd()}};
        differential(1,rec,&t,600,350,320);
    }
}
static void limits(void) {
    uint32_t len=point(0,0,0,0);for(int i=0;i<511;i++)len=point(len,1,i%2?100:0,i+1);commands[len++]=4;
    assert(compile(len,0)==512);
    len=point(0,0,0,0);for(int i=0;i<513;i++)len=point(len,1,i%2?100:0,i+1);commands[len++]=4;
    assert(compile(len,0)==MM_VECTOR_MESSAGE);
    /* Degenerate paths hit command budget without consuming edge budget. */
    len=0;for(unsigned i=0;i<512;i++){len=point(len,0,0,0);commands[len++]=4;}
    assert(compile(len,0)==0);len=point(len,0,0,0);commands[len++]=4;
    assert(compile(len,0)==MM_VECTOR_MESSAGE);
    len=boxpath(0,10,10,30,30,0);assert(compile(len,0)==4);
    uint8_t before[sizeof storage];memcpy(before,storage,sizeof storage);
    for(unsigned n=0;n<len;n++) {assert(mm_vector_compile(&work,sizeof work,commands,n,0,path,sizeof storage)==MM_VECTOR_MESSAGE);assert(!memcmp(before,storage,sizeof storage));}
    assert(mm_vector_compile(&work,sizeof work,commands,len,0,path,mm_vector_path_bytes(4)-1)==MM_VECTOR_CAPACITY);
    assert(!memcmp(before,storage,sizeof storage));
    assert(mm_vector_compile(&work,sizeof work,commands,len,0,0,0)==4);
    assert(mm_vector_compile(&work,sizeof work,commands,len,2,path,sizeof storage)==MM_VECTOR_MESSAGE);
    assert(mm_vector_compile(&work,sizeof work-1,commands,len,0,path,sizeof storage)==MM_VECTOR_TARGET);
    assert(mm_vector_compile(&work,sizeof work,(uint8_t *)&work,len,0,path,sizeof storage)==MM_VECTOR_ALIAS);
    assert(mm_vector_compile(&work,sizeof work,commands,len,0,(mm_vector_path *)(void *)&work,sizeof work)==MM_VECTOR_ALIAS);
    assert(mm_vector_compile((mm_vector_work *)(void *)((uint8_t *)&work+1),sizeof work,commands,len,0,path,sizeof storage)==MM_VECTOR_TARGET);
    assert(mm_vector_path_bytes(513)==0);
    mm_raster target={fb,sizeof fb,640,480,320};mm_vector_transform t={0,0,256,{0,0,0}};
    memset(fb,0xa5,sizeof fb);
#define BAD_PATH(status) do { assert(mm_vector_draw_path(&target,&work,sizeof work,path,sizeof storage,&t,15)==(status));for(unsigned z=0;z<sizeof fb;z++)assert(fb[z]==0xa5); } while(0)
    path->count=513;BAD_PATH(MM_VECTOR_MESSAGE);path->count=4;
    path->rule=2;BAD_PATH(MM_VECTOR_MESSAGE);path->rule=0;
    path->pad=1;BAD_PATH(MM_VECTOR_MESSAGE);path->pad=0;
    path->edges[3].x1=32768;BAD_PATH(MM_VECTOR_MESSAGE);memcpy(storage,before,sizeof storage);
    t.scale=2049;BAD_PATH(MM_VECTOR_TRANSFORM);t.scale=256;
    t.rotation.angle=MM_VECTOR_MAX_ANGLE+1;BAD_PATH(MM_VECTOR_TRANSFORM);t.rotation.angle=0;
    assert(mm_vector_draw_path(&target,&work,sizeof work,path,3,&t,15)==MM_VECTOR_MESSAGE);
    assert(mm_vector_draw_path(&target,&work,sizeof work,path,sizeof storage,&t,16)==MM_VECTOR_TRANSFORM);
    assert(mm_vector_draw_path(&target,&work,sizeof work,(mm_vector_path *)(void *)&work,sizeof work,&t,15)<0);
    mm_raster alias={(uint8_t *)&work,sizeof work,10,10,5};assert(mm_vector_draw_path(&alias,&work,sizeof work,path,sizeof storage,&t,15)==MM_VECTOR_ALIAS);
    alias=(mm_raster){storage,sizeof storage,10,10,5};assert(mm_vector_draw_path(&alias,&work,sizeof work,path,sizeof storage,&t,15)==MM_VECTOR_ALIAS);
    assert(mm_vector_draw_path(&target,&work,sizeof work,path,sizeof storage,(mm_vector_transform *)(void *)&work,15)<0);
    uint8_t record[20]={3,0,15,0};assert(mm_vector_draw_shape(&target,&work,sizeof work,record,19,&t.rotation)==MM_VECTOR_MESSAGE);
    record[0]=14;assert(mm_vector_draw_shape(&target,&work,sizeof work,record,20,&t.rotation)==MM_VECTOR_MESSAGE);
    record[0]=3;assert(mm_vector_draw_shape(&target,&work,sizeof work,record,20,0)==MM_VECTOR_TRANSFORM);
    for(unsigned z=0;z<sizeof fb;z++)assert(fb[z]==0xa5);
#undef BAD_PATH
}
int main(void) {
    original_pixels();original_fuzz();renders();limits();
    printf("PASS: %u original vector predicate evaluations; %u original compiler comparisons; %u original raster comparisons; validation/alias/padding guards\n",assertions,compilations,drawings);
}
