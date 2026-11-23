/* Original compiler/drawing reference only; pinned unchanged host source. MIT. */
#include <assert.h>
#define main original_unused_shape_main
#include G2_REFERENCE_SOURCE
#undef main
#include "../vector.h"
int g2_vector_compile_reference(mm_vector_work *w,const uint8_t *src,uint32_t len) {
    cfw_vector_work *old=calloc(1,sizeof(*old));assert(old);
    int n=cv_compile(old,src,len);
    if(n>=0)for(int i=0;i<n;i++)w->edges[i]=(mm_vector_edge){old->edges[i].x0,old->edges[i].y0,old->edges[i].x1,old->edges[i].y1};
    free(old);return n;
}
void g2_vector_path_reference(const mm_raster *t,const mm_vector_path *path,
                              const mm_vector_transform *transform,uint8_t color) {
    cfw_vector_work *old=calloc(1,sizeof(*old));assert(old);
    cfw_path *p=malloc(sizeof(*p)+path->count*sizeof(cfw_edge));assert(p);
    p->count=path->count;p->rule=path->rule;p->pad=0;
    for(unsigned i=0;i<p->count;i++)p->edges[i]=(cfw_edge){path->edges[i].x0,path->edges[i].y0,path->edges[i].x1,path->edges[i].y1};
    cfw_rotation rotation={0};rotation.angle=transform->rotation.angle;rotation.px=transform->rotation.px;rotation.py=transform->rotation.py;
    cfw_raster target={t->pixels,t->stride,(int32_t)t->width,(int32_t)t->height};
    int16_t params[3]={transform->x,transform->y,(int16_t)transform->scale};
    cv_path_draw(&target,old,p,params,&rotation,color);
    free(p);free(old);
}
void g2_vector_shape_reference(const mm_raster *t,const uint8_t *record,const mm_vector_rotation *rotation) {
    cfw_vector_work *old=calloc(1,sizeof(*old));assert(old);
    cfw_shape shape={0};shape.type=record[0];shape.flags=record[1];shape.color=record[2];shape.width=record[3];
    for(unsigned i=0;i<8;i++)shape.p[i]=(int16_t)rd16(record+4+2*i);
    cfw_rotation rot={0};rot.angle=rotation->angle;rot.px=rotation->px;rot.py=rotation->py;
    cfw_raster target={t->pixels,t->stride,(int32_t)t->width,(int32_t)t->height};
    cv_shape_draw(&target,old,&shape,&rot,0);free(old);
}
