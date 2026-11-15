/* Test-only platform adapters, preserving original fault injection and font stub. */
static void *test_allocate(void *u,unsigned kind,size_t bytes) {(void)u;return kind==MM_SCENE_WORKSPACE?cfw_heap13_malloc((uint32_t)bytes):cfw_malloc((uint32_t)bytes);}
static void test_deallocate(void *u,unsigned kind,void *p) {(void)u;if(kind==MM_SCENE_WORKSPACE)cfw_heap13_free(p);else free_store(p);}
static uint32_t test_now(void *u) {(void)u;return g_now;}
static int test_lease(void *u) {(void)u;return g_lease;}
static int test_shadow(void *u,mm_raster *r) {(void)u;*r=(mm_raster){cfw_shadow_buffer(),IMAGE_BYTES,IMAGE_W,IMAGE_H,IMAGE_STRIDE};return r->pixels!=0;}
static uintptr_t test_timer_new(void *u,void (*cb)(void *),void *arg) {(void)u;return stub_timer_new((void *)cb,0,arg,0);}
static void test_timer_start(void *u,uintptr_t timer,uint32_t ms) {(void)u;(void)stub_timer_start((uint32_t)timer,ms);}
static void test_timer_stop(void *u,uintptr_t timer) {(void)u;(void)stub_timer_stop((uint32_t)timer);}
static void test_wait(void *u) {(void)u;stub_gate_wait();}
static void test_signal(void *u) {(void)u;stub_gate_signal();}
static int g_present_fail,g_present_n;
static mm_scene_rect g_present_rect;
static void test_present(void *u,mm_scene_context *ctx,const mm_raster *r,mm_scene_dirty *dirty) {
    (void)u;(void)ctx;(void)r;g_presented++;
    g_present_n=dirty?(int)dirty->n:0;
    if(dirty && dirty->n)g_present_rect=dirty->r[0];
    if(dirty && !g_present_fail)dirty->direct_submitted=1;
}
static void test_settled(void *u,uint16_t tag) {(void)u;g_settled++;g_settled_tag=tag;}
static void test_hint(void *u,uint8_t capacity) {(void)u;g_hint=capacity;}
static int test_builtin(void *u,const mm_raster *r,const uint8_t *src,size_t len,mm_scene_dirty *dirty,uint32_t *tokens,size_t cap) {
    (void)u;return test_builtin_draw_string_buf(r->pixels,r->stride,r->width,r->height,src,(uint32_t)len,dirty,tokens,(uint32_t)cap);
}
static void test_bind(void) {
    const mm_scene_platform platform={0,test_allocate,test_deallocate,test_now,test_lease,test_shadow,
        test_timer_new,test_timer_start,test_timer_stop,test_wait,test_signal,test_present,test_settled,test_hint,test_builtin};
    g_ctx.platform=platform;g_ctx.store_limit=MM_SCENE_MAX_STORE;
}
#include "../../scene.c"
static uint32_t strnlen(const char *s,uint32_t limit) {uint32_t n=0;while(n<limit && s[n])n++;return n;}
static int cfw_shapes_immediate(uint8_t *p,uint32_t stride,uint32_t w,uint32_t h,const uint8_t *src,uint32_t len,cfw_rectlist *dirty) {
    mm_raster r={p,(size_t)stride*h,w,h,stride};return mm_scene_shapes_immediate(&g_ctx,&r,src,len,dirty);
}
/* Vector host white-box compiler/math predicates route to portable functions. */
static int cv_compile(cfw_vector_work *w,const uint8_t *src,uint32_t len) {return mm_vector_compile(w,sizeof(*w),src,len,0,0,0);}
int32_t mm_vector_test_muldiv(int32_t,int32_t,int32_t);
#define cv_muldiv mm_vector_test_muldiv
static int32_t cv_abs(int32_t x) {return x<0?-x:x;}
