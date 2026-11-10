/* Retained scene/cache port; no firmware imports or singleton context. MIT. */
#include "scene_internal.h"
static void bzero(uint8_t *p,uint32_t n) { volatile uint8_t *v=p;while(n--)*v++=0; }
static void *mm_scene_memcpy(void *d,const void *s,size_t n) {
    /* The 45 KiB rollback snapshot runs through here on every transaction:
     * copy words while both sides are aligned, bytes for the rest. */
    volatile uint8_t *a=d;const uint8_t *b=s;      /* volatile: no memcpy idiom in a freestanding build */
    if(!(((uintptr_t)a|(uintptr_t)b)&3u)){
        volatile uint32_t *wa=(volatile uint32_t *)a;const uint32_t *wb=(const uint32_t *)(const void *)b;
        for(;n>=4;n-=4)*wa++=*wb++;
        a=(volatile uint8_t *)wa;b=(const uint8_t *)wb;
    }
    while(n--)*a++=*b++;
    return d;
}
#define memcpy mm_scene_memcpy
static uint32_t rd16(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8);}
static uint32_t rd32(const uint8_t *p) {return rd16(p)|(rd16(p+2)<<16);}
static void rl_add(cfw_rectlist *rl,uint32_t l,uint32_t t,uint32_t w,uint32_t h) {
    if(rl && rl->n<CFW_RECT_MAX)rl->r[rl->n++]=(mm_scene_rect){(uint16_t)l,(uint16_t)t,(uint16_t)w,(uint16_t)h};
}
static void *mm_scene_allocate(mm_scene_context *ctx,unsigned kind,size_t n) {
    return ctx->platform.allocate(ctx->platform.user,kind,n);
}
static void mm_scene_deallocate(mm_scene_context *ctx,unsigned kind,void *p) {
    if(p)ctx->platform.deallocate(ctx->platform.user,kind,p);
}
static uint32_t mm_scene_now(mm_scene_context *ctx) {return ctx->platform.now_ms(ctx->platform.user);}
static int mm_scene_lease(mm_scene_context *ctx) {return ctx->platform.lease_active(ctx->platform.user);}
static uint8_t *mm_scene_shadow(mm_scene_context *ctx) {
    mm_raster r;
    if(!ctx->platform.shadow(ctx->platform.user,&r) || mm_raster_validate(&r) ||
        r.width>MM_VECTOR_MAX_DIMENSION || r.height>MM_VECTOR_MAX_DIMENSION)return 0;
    mm_scene_memcpy(&ctx->raster,&r,sizeof(r));return r.pixels;
}
static uintptr_t mm_scene_timer_new(mm_scene_context *ctx) {
    return ctx->platform.timer_new ? ctx->platform.timer_new(ctx->platform.user,mm_scene_tick,ctx):0;
}
static void mm_scene_timer_start(mm_scene_context *ctx,uint32_t ms) {
    if(ctx->platform.timer_start)ctx->platform.timer_start(ctx->platform.user,ctx->scene_timer,ms);
}
static void mm_scene_timer_stop(mm_scene_context *ctx) {
    if(ctx->platform.timer_stop)ctx->platform.timer_stop(ctx->platform.user,ctx->scene_timer);
}
static void mm_scene_gate_wait(mm_scene_context *ctx) {if(ctx->platform.gate_wait)ctx->platform.gate_wait(ctx->platform.user);}
static void mm_scene_gate_signal(mm_scene_context *ctx) {if(ctx->platform.gate_signal)ctx->platform.gate_signal(ctx->platform.user);}
static void mm_scene_reply_capacity_hint(mm_scene_context *ctx,uint8_t capacity) {
    if(ctx->platform.reply_capacity_hint)ctx->platform.reply_capacity_hint(ctx->platform.user,capacity);
}
static void cfw_scene_notify_settled(mm_scene_context *ctx,uint16_t tag) {
    if(ctx->platform.settled)ctx->platform.settled(ctx->platform.user,tag);
}
static cfw_cache *cfw_cache_peek(customCfwContext *ctx);
static void cfw_scene_render(customCfwContext *ctx,cfw_cache *sc,uint8_t *fb,cfw_rectlist *rl);
/* A due deferred render draws into fb and reports its box on rl (a null rl
 * discards it, as the generated cfw_scene_render_if_due does). */
static void render_due_into(mm_scene_context *ctx,uint8_t *fb,cfw_rectlist *rl) {
    cfw_cache *sc=cfw_cache_peek(ctx);
    if(sc==0 || !sc->render_due || fb==0 || fb!=sc->fb)return;
    sc->render_due=0;
    cfw_rectlist scratch;
    if(!rl){rl=&scratch;rl->n=0;rl->direct_submitted=0;rl->direct_failed=0;}
    cfw_scene_render(ctx,sc,fb,rl);
}
#ifdef MM_SCENE_STEREO_EYES
/* A scene holding eye-tagged objects is presented once per eye: the box of
 * every tagged object plus what this render changed is redrawn with the other
 * eye's objects skipped and presented with ctx->eye naming the panel. The
 * shared raster ends holding the right eye; outside the box both eyes agree. */
static int stereo_present(mm_scene_context *ctx,uint8_t *fb,const mm_raster *target,cfw_rectlist *rl) {
    cfw_cache *sc=cfw_cache_peek(ctx);
    if(!sc || !ctx->platform.present)return 0;
    int16_t box[4]={32767,32767,-32768,-32768};unsigned tagged=0;
    for(uint32_t i=0;i<sc->active_count;i++){
        const cfw_object *o=&sc->objects[sc->active[i]];
        if(!(o->id>>31) || !(o->draw&CFW_DRAW_VALID))continue;
        tagged=1;
        for(unsigned k=0;k<4;k++)if(k<2 ? o->drawn[k]<box[k]:o->drawn[k]>box[k])box[k]=o->drawn[k];
    }
    if(!tagged)return 0;
    for(uint32_t i=0;rl && i<rl->n && i<CFW_RECT_MAX;i++){
        int16_t r[4]={(int16_t)rl->r[i].l,(int16_t)rl->r[i].t,(int16_t)(rl->r[i].l+rl->r[i].w),(int16_t)(rl->r[i].t+rl->r[i].h)};
        for(unsigned k=0;k<4;k++)if(k<2 ? r[k]<box[k]:r[k]>box[k])box[k]=r[k];
    }
    for(uint8_t eye=1;eye<=2;eye++){
        for(unsigned k=0;k<4;k++)sc->stale[k]=box[k];
        cfw_rectlist pass;pass.n=0;pass.direct_submitted=0;pass.direct_failed=0;
        ctx->eye=eye;cfw_scene_render(ctx,sc,fb,&pass);
        ctx->platform.present(ctx->platform.user,ctx,target,&pass);
    }
    ctx->eye=0;
    if(rl)rl->direct_submitted=1;
    return 1;
}
#endif
static void present_buffer(mm_scene_context *ctx,const uint8_t *fb,cfw_rectlist *rl) {
#ifdef MM_SCENE_EXTERNAL_STORE
    if(ctx->external_ready){
        render_due_into(ctx,(uint8_t *)(uintptr_t)fb,rl);
        if(ctx->shadow_invalid){cfw_scene_stop(ctx);return;}
    }
#endif
    mm_raster target;mm_scene_memcpy(&target,&ctx->raster,sizeof(target));target.pixels=(uint8_t *)(uintptr_t)fb;
#ifdef MM_SCENE_STEREO_EYES
    if(stereo_present(ctx,(uint8_t *)(uintptr_t)fb,&target,rl))return;
#endif
    if(ctx->platform.present)ctx->platform.present(ctx->platform.user,ctx,&target,rl);
}
#include "scene_assets.inc"
#include "scene_shapes.inc"
#ifdef MM_SCENE_EXTERNAL_STORE
#include "scene_assets_external.inc"
#endif
static mm_raster mm_scene_raster(const cfw_raster *r) {
    return (mm_raster){r->buf,(size_t)r->stride*(uint32_t)r->h,(uint32_t)r->w,(uint32_t)r->h,r->stride};
}
static void cfw_raster_clear(const cfw_raster *r,uint8_t color) {
    mm_raster target=mm_scene_raster(r);(void)mm_raster_clear(&target,color);
}
static void mm_scene_path_draw(const cfw_raster *r,cfw_vector_work *work,const cfw_path *path,
                               const int16_t *p,const cfw_rotation *rot,uint8_t color) {
    mm_raster target=mm_scene_raster(r);
    mm_vector_transform transform={p[0],p[1],(uint16_t)p[2],{rot->angle,rot->px,rot->py}};
    (void)mm_vector_draw_path(&target,work,sizeof(*work),path,mm_vector_path_bytes(path->count),&transform,color&15u);
}
static void mm_scene_shape_draw(mm_scene_context *ctx,const cfw_raster *r,cfw_vector_work *work,
                                const cfw_shape *s,const cfw_rotation *rotation,cfw_rectlist *rl) {
    mm_raster target=mm_scene_raster(r);
    if(s->type<=13) {
        uint8_t message[22];message[0]=36;message[1]=1;message[2]=s->type;message[3]=s->flags;message[4]=s->color;message[5]=s->width;
        for(unsigned i=0;i<8;i++){uint16_t v=(uint16_t)s->p[i];message[6+2*i]=(uint8_t)v;message[7+2*i]=(uint8_t)(v>>8);}
        if(work && rotation) {mm_vector_rotation rot={rotation->angle,rotation->px,rotation->py};(void)mm_vector_draw_shape(&target,work,sizeof(*work),message+2,20,&rot);}
        else (void)mm_geometry_mode36(&target,message,sizeof(message));
        return;
    }
#ifdef MM_SCENE_EXTERNAL_STORE
    if(ctx->external_ready && (s->type==CFW_SHAPE_IMAGE||s->type==CFW_SHAPE_TEXT_CACHED)) {
        int rc=s->type==CFW_SHAPE_IMAGE ? mm_external_image_draw(ctx,r,&s->asset_region,s->p[0],s->p[1],s->color,rl):
            mm_external_string_draw(ctx,r,&s->font_region,&s->asset_region,s->p[0],s->p[1],s->color,rl);
        if(rc)ctx->shadow_invalid=1;
        return;
    }
#endif
    if(s->type==CFW_SHAPE_IMAGE) {
        if(s->asset && s->asset_len)(void)cfw_texture_draw_image_region(r->buf,r->stride,r->w,r->h,s->asset,s->asset_len,s->p[0],s->p[1],s->color,rl);
        return;
    }
    if(s->type==CFW_SHAPE_TEXT_CACHED) {
        if(s->asset && s->font)(void)cfw_texture_draw_string_region(r->buf,r->stride,r->w,r->h,s->font,s->font_len,s->p[0],s->p[1],s->color,s->asset,s->asset_len,rl);
        return;
    }
    if(s->type!=CFW_SHAPE_TEXT && s->type!=CFW_SHAPE_TEXT_INLINE)return;
    const uint8_t *string=s->type==CFW_SHAPE_TEXT ? s->asset:s->text;
    uint32_t len=s->type==CFW_SHAPE_TEXT ? s->asset_len:(uint16_t)s->p[4];
#ifdef MM_SCENE_EXTERNAL_STORE
    uint8_t stored_string[128];
    if(ctx->external_ready && (s->type==CFW_SHAPE_TEXT || (s->type==CFW_SHAPE_TEXT_INLINE&&s->asset_region.store))) {
        len=s->asset_region.length;
        if(len>128||mm_external_read(ctx,&s->asset_region,0,stored_string,len)){ctx->shadow_invalid=1;return;}
        string=stored_string;
    }
#endif
    if(!string || !len || len>CFW_SHAPE_TEXT_MAX || !ctx->platform.builtin_text)return;
    int32_t clip_w=r->w,clip_h=r->h;
    if(s->type==CFW_SHAPE_TEXT_INLINE) {
        if(s->p[2]>0 && s->p[0]+s->p[2]<clip_w)clip_w=s->p[0]+s->p[2];
        if(s->p[3]>0 && s->p[1]+s->p[3]<clip_h)clip_h=s->p[1]+s->p[3];
        if(clip_w<=0 || clip_h<=0)return;
    }
    target.width=(uint32_t)clip_w;target.height=(uint32_t)clip_h;
    uint8_t *buf=ctx->shape_text_buf;
    buf[0]=(uint8_t)s->p[0];buf[1]=(uint8_t)((uint16_t)s->p[0]>>8);
    buf[2]=(uint8_t)s->p[1];buf[3]=(uint8_t)((uint16_t)s->p[1]>>8);buf[4]=s->color;buf[5]=(uint8_t)len;
    for(uint32_t i=0;i<len;i++)buf[6+i]=string[i];
    (void)ctx->platform.builtin_text(ctx->platform.user,&target,buf,len+6,rl,ctx->shape_tokens,CFW_SHAPE_TEXT_MAX);
}
#include "scene_cache.inc"
static int mm_scene_shapes_immediate(mm_scene_context *ctx,const mm_raster *target,const uint8_t *src,uint32_t len,cfw_rectlist *rl) {
    if(!src || len<1)return -1;
    uint32_t count=src[0],pos=1;
    for(uint32_t i=0;i<count;i++) {
        uint32_t n=cfw_shape_record_len(src+pos,len-pos);if(!n)return -1;
        cfw_shape s;cfw_shape_decode(src+pos,&s);
        if(!cfw_shape_valid(&s,0) || (s.asset_id && !cfw_shape_resolve(ctx,&s)))return -1;
        pos+=n;
    }
    if(pos!=len)return -1;
    cfw_raster r={target->pixels,target->stride,(int32_t)target->width,(int32_t)target->height};pos=1;
    for(uint32_t i=0;i<count;i++) {
        cfw_shape s;cfw_shape_decode(src+pos,&s);if(s.asset_id)cfw_shape_resolve(ctx,&s);
        mm_scene_shape_draw(ctx,&r,0,&s,0,rl);pos+=cfw_shape_record_len(src+pos,len-pos);
    }
    rl_add(rl,0,0,target->width,target->height);return 0;
}
static int mm_scene_overlap(const void *a,size_t an,const void *b,size_t bn) {
    if(!an || !bn)return 0;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y ? y-x<an : x-y<bn;
}
static int mm_scene_input_valid(mm_scene_context *ctx,const uint8_t *src,size_t len) {
    if(!ctx || ctx->magic!=MM_SCENE_MAGIC || !src || len>MM_SCENE_MAX_MESSAGE)return 0;
    if(mm_scene_overlap(src,len,ctx,sizeof(*ctx)) ||
       mm_scene_overlap(src,len,ctx->texture_cache,ctx->texture_cache_size) ||
       mm_scene_overlap(src,len,ctx->raster.pixels,ctx->raster.bytes))return 0;
#ifdef MM_SCENE_EXTERNAL_STORE
    if(ctx->external_store.read&&ctx->external_store.aliases(ctx->external_store.user,src,len))return 0;
#endif
    cfw_cache *sc=ctx->scene;
    if(sc && (mm_scene_overlap(src,len,sc,sizeof(*sc)) ||
       (sc->vector_work && mm_scene_overlap(src,len,sc->vector_work,sizeof(*sc->vector_work))) ||
       (sc->undo && mm_scene_overlap(src,len,sc->undo,sizeof(cfw_undo)+(size_t)sc->undo_capacity*20u))))return 0;
    return 1;
}
#ifdef MM_RASTER_COMMANDS
int mm_scene_raster_input_valid(mm_scene_context *ctx,const uint8_t *src,size_t len) {
    return src && len && len<=UINTPTR_MAX-(uintptr_t)src && mm_scene_input_valid(ctx,src,len);
}
#endif
int mm_scene_init(mm_scene_context *ctx,const mm_scene_platform *p,uint32_t limit) {
    if(!ctx || !p || !p->allocate || !p->deallocate || !p->now_ms || !p->lease_active || !p->shadow ||
       limit<MM_SCENE_MIN_STORE || limit>MM_SCENE_MAX_STORE)return -1;
    if(mm_scene_overlap(ctx,sizeof(*ctx),p,sizeof(*p)))return -1;
    bzero((uint8_t *)ctx,sizeof(*ctx));mm_scene_memcpy(&ctx->platform,p,sizeof(*p));ctx->store_limit=limit;ctx->magic=MM_SCENE_MAGIC;return 0;
}
#ifdef MM_SCENE_EXTERNAL_STORE
int mm_scene_init_with_store(mm_scene_context *ctx,const mm_scene_platform *p,const mm_scene_store *store) {
    if(!store||store->capacity!=MM_SCENE_MAX_STORE||!store->read||!store->write||!store->begin||!store->commit||!store->abort||!store->reset||!store->aliases)return -1;
    mm_scene_store saved=*store;
    if(!ctx||sizeof(*ctx)>UINTPTR_MAX-(uintptr_t)ctx||saved.aliases(saved.user,ctx,sizeof(*ctx)))return -1;
    int rc=mm_scene_init(ctx,p,saved.capacity);if(rc)return rc;ctx->external_store=saved;return 0;
}
#endif
void mm_scene_prepare(mm_scene_context *ctx,uint8_t mode,const uint8_t *src,size_t len) {
    if(mm_scene_input_valid(ctx,src,len))cfw_cache_prepare(ctx,mode,src,(uint32_t)len);
}
#ifdef MM_SCENE_RESET_UNDO_TRIM
size_t mm_scene_trim_reset_undo(mm_scene_context *ctx) {
    if (!ctx || ctx->magic!=MM_SCENE_MAGIC || ctx->cache_lost ||
        !mm_scene_lease(ctx) || ctx->cache_reply_len!=CFW_CACHE_REPLY_HDR+3u ||
        ctx->cache_reply[0]!=41 || ctx->cache_reply[3]!=CFW_CACHE_REPLY_APPLIED ||
        rd16(ctx->cache_reply+4)!=ctx->cache_epoch || rd32(ctx->cache_reply+6) ||
        ctx->cache_reply[10]) return 0;
    cfw_cache *sc=cfw_cache_peek(ctx);
    if (!sc || sc->owner!=ctx || !sc->undo || sc->fb || sc->bg ||
        sc->anim_active || sc->render_due || sc->settle_pending || sc->last_show_valid ||
        sc->tag || sc->last_show_request || sc->active_count || sc->revision ||
        sc->use_clock || sc->journal_lost_rev || sc->journal_head || sc->journal_count)
        return 0;
    /* RESET zeros the entire transaction, bitmap, descriptors and journal.
     * Check in place: no large stack snapshot and no allocator calls. */
    const uint8_t *tail=(const uint8_t *)&sc->txn;
    size_t tail_bytes=sizeof(*sc)-offsetof(cfw_cache,txn);
    for (size_t i=0;i<tail_bytes;i++) if (tail[i]) return 0;
    cfw_undo *old=sc->undo;
    size_t bytes=sizeof(*old)+(size_t)sc->undo_capacity*sizeof(old->granules[0]);
    sc->undo=0;sc->undo_capacity=0;
    mm_scene_deallocate(ctx,MM_SCENE_PERSISTENT,old);
    return bytes;
}
#endif
int mm_scene_dispatch(mm_scene_context *ctx,uint8_t mode,const uint8_t *src,size_t len,int present,mm_scene_dirty *dirty) {
    if(!mm_scene_input_valid(ctx,src,len))return -1;
#ifdef MM_SCENE_EXTERNAL_STORE
    ctx->storage_io=0;
    int rc=cfw_scene_dispatch(ctx,mode,src,(uint32_t)len,present,dirty);
    if(ctx->storage_io){ctx->cache_reply_len=0;return MM_SCENE_STORAGE_IO;}return rc;
#else
    return cfw_scene_dispatch(ctx,mode,src,(uint32_t)len,present,dirty);
#endif
}
#ifdef MM_COMMAND_BUNDLES
int mm_scene_immediate_mode(mm_scene_context *ctx,const mm_raster *target,const uint8_t *src,size_t len,uint8_t mode,mm_scene_dirty *dirty) {
    if(!ctx || ctx->magic!=MM_SCENE_MAGIC || mm_raster_validate(target) || target->width>1024 || target->height>1024 ||
       !src || !len || !mm_scene_input_valid(ctx,src,len) || !mm_scene_lease(ctx) ||
       mm_scene_overlap(src,len,target->pixels,target->bytes))return -1;
#ifdef MM_SCENE_EXTERNAL_STORE
    if(ctx->external_ready){
        if(ctx->shadow_invalid)return MM_SCENE_STORAGE_IO;
        ctx->storage_io=0;
        int rc=mode==36?mm_scene_shapes_immediate(ctx,target,src+1,(uint32_t)len-1,dirty):
            cfw_cache_immediate(ctx,mode,target->pixels,target->stride,target->width,target->height,src+1,(uint32_t)len-1,dirty);
        if(ctx->storage_io){ctx->shadow_invalid=1;return MM_SCENE_STORAGE_IO;}
        return ctx->shadow_invalid?-1:rc;
    }
#endif
    if(mode==36)return mm_scene_shapes_immediate(ctx,target,src+1,(uint32_t)len-1,dirty);
    return cfw_cache_immediate(ctx,mode,target->pixels,target->stride,target->width,target->height,src+1,(uint32_t)len-1,dirty);
}
int mm_scene_immediate(mm_scene_context *ctx,const mm_raster *target,const uint8_t *src,size_t len,mm_scene_dirty *dirty) {
    if(!src || !len)return -1;
    return mm_scene_immediate_mode(ctx,target,src,len,src[0]&127u,dirty);
}
#else
int mm_scene_immediate(mm_scene_context *ctx,const mm_raster *target,const uint8_t *src,size_t len,mm_scene_dirty *dirty) {
    if(!ctx || ctx->magic!=MM_SCENE_MAGIC || mm_raster_validate(target) || target->width>1024 || target->height>1024 ||
       !src || !len || !mm_scene_input_valid(ctx,src,len) || !mm_scene_lease(ctx) ||
       mm_scene_overlap(src,len,target->pixels,target->bytes))return -1;
#ifdef MM_SCENE_EXTERNAL_STORE
    if(ctx->external_ready){
        if(ctx->shadow_invalid)return MM_SCENE_STORAGE_IO;
        ctx->storage_io=0;
        int rc=(src[0]&127u)==36?mm_scene_shapes_immediate(ctx,target,src+1,(uint32_t)len-1,dirty):
            cfw_cache_immediate(ctx,src[0]&127u,target->pixels,target->stride,target->width,target->height,src+1,(uint32_t)len-1,dirty);
        if(ctx->storage_io){ctx->shadow_invalid=1;return MM_SCENE_STORAGE_IO;}
        return ctx->shadow_invalid?-1:rc;
    }
#endif
    if((src[0]&127u)==36)return mm_scene_shapes_immediate(ctx,target,src+1,(uint32_t)len-1,dirty);
    return cfw_cache_immediate(ctx,src[0]&127u,target->pixels,target->stride,target->width,target->height,src+1,(uint32_t)len-1,dirty);
}
#endif
void mm_scene_tick(void *ctx) {scene_tick(ctx);}
void mm_scene_render_if_due(mm_scene_context *ctx,uint8_t *fb) {if(ctx && ctx->magic==MM_SCENE_MAGIC)cfw_scene_render_if_due(ctx,fb);}
void mm_scene_render_if_due_rects(mm_scene_context *ctx,uint8_t *fb,mm_scene_dirty *dirty) {
    if(!ctx || ctx->magic!=MM_SCENE_MAGIC)return;
    uint32_t before=dirty?dirty->n:0;
    render_due_into(ctx,fb,dirty);
    /* rl_add drops boxes past capacity: a full list means "everything" to callers. */
    if(dirty && dirty->n>=CFW_RECT_MAX && before<CFW_RECT_MAX)dirty->n=CFW_RECT_MAX;
}
void mm_scene_takeover(mm_scene_context *ctx) {if(ctx && ctx->magic==MM_SCENE_MAGIC)cfw_scene_takeover(ctx);}
void mm_scene_lose(mm_scene_context *ctx) {if(ctx && ctx->magic==MM_SCENE_MAGIC)cfw_cache_lose(ctx);}
void mm_scene_reap(mm_scene_context *ctx) {if(ctx && ctx->magic==MM_SCENE_MAGIC)cfw_cache_reap(ctx);}
void mm_scene_release(mm_scene_context *ctx) {if(ctx && ctx->magic==MM_SCENE_MAGIC)cfw_scene_release(ctx);}
