/* Native opt-in policy tests. Production core is included for allocation-size
 * and full metadata assertions; commands go through the real public session. */
#define main retained_session_main
#include "test_scene_session.c"
#undef main
#define bzero mm_test_core_bzero
#include "../../portable/scene.c"
#undef bzero
#undef memcpy

static void fixture(device *d) {
    init(d,600,350,600000,400000,MM_SCENE_MIN_STORE);
    reset(d);put(d);assert(status(d)==0);show(d);
}
static size_t undo_bytes(cfw_cache *sc) {
    return sizeof(cfw_undo)+(size_t)sc->undo_capacity*sizeof(sc->undo->granules[0]);
}
static void bundle_commands(device *d,const uint8_t **parts,const size_t *sizes,unsigned n,int expected) {
    uint8_t data[512]={8,(uint8_t)n};size_t at=2;
    for(unsigned i=0;i<n;i++) {
        assert(at+2+sizes[i]<=sizeof data);w16(data+at,(unsigned)sizes[i]);at+=2;
        memcpy(data+at,parts[i],sizes[i]);at+=sizes[i];
    }
    assert(send(d,data,at)==expected);
}
static void fill_put(uint8_t *p,unsigned id,unsigned epoch) {
    memset(p,0,34);p[0]=37;w16(p+1,epoch);w16(p+3,90);p[5]=1;
    w32(p+6,id);w32(p+10,1);p[14]=3;p[15]=1;p[16]=7;
    w16(p+18,5);w16(p+20,5);w16(p+22,10);w16(p+24,5);
}
static void lifetime(void) {
    device d;fixture(&d);cfw_cache *sc=d.session.core.scene;
    void *undo=sc->undo,*store=d.session.core.texture_cache,*work=sc->vector_work;
    size_t payload=undo_bytes(sc),before=d.used;unsigned allocations=d.allocations;
    uint8_t *pixels=malloc(d.session.raster.bytes);assert(pixels);
    memcpy(pixels,d.pixels,d.session.raster.bytes);
    animate(&d);unsigned settles=d.settled;
    reset(&d);assert(status(&d)==0 && !d.session.timer_armed && d.settled==settles+1);
    assert(!memcmp(pixels,d.pixels,d.session.raster.bytes));free(pixels);
    assert(sc==d.session.core.scene && sc->vector_work==work && d.session.core.texture_cache==store);
#ifdef MM_SCENE_RESET_UNDO_TRIM
    (void)undo;
    assert(!sc->undo && !sc->undo_capacity && d.allocations+1==allocations);
    /* Native adapter header is size_t + unsigned, padded to pointer alignment. */
    struct adapter_header {size_t bytes;unsigned kind;};
    assert(before-d.used==payload+sizeof(struct adapter_header));
    uint8_t reply[255];memcpy(reply,d.session.core.cache_reply,sizeof reply);
    size_t after=d.used;assert(!mm_scene_trim_reset_undo(&d.session.core));
    assert(!memcmp(reply,d.session.core.cache_reply,sizeof reply) && d.used==after);
    reset(&d);assert(d.used==after);
#else
    (void)payload;assert(sc->undo==undo && d.used==before && d.allocations==allocations);
#endif
    put(&d);assert(status(&d)==0 && sc->undo);unsigned attempts=d.attempts;
    show(&d);assert(d.attempts==attempts && pixel(&d,6,6)==7);
    dispose(&d);
}
#ifdef MM_SCENE_RESET_UNDO_TRIM
static void guards(void) {
    device d;fixture(&d);cfw_cache *sc=d.session.core.scene;void *undo=sc->undo;
    size_t used=d.used;assert(!mm_scene_trim_reset_undo(&d.session.core));
    uint8_t malformed[]={41,0,0,0,0};assert(send(&d,malformed,sizeof malformed)==-1);
    assert(sc->undo==undo && d.used==used);
    uint8_t stale[]={41,0xff,0xff,1,0,2,33};
    assert(!mm_scene_session_dispatch(&d.session,stale,sizeof stale));
    assert(status(&d)==1 && !mm_scene_trim_reset_undo(&d.session.core) && sc->undo==undo);
    /* Prepare genuine RESET reply without the adapter trim, then corrupt each
     * checked invariant. No mutation may free scratch until all are restored. */
    uint8_t reset_body[]={0,0,55,0,0};mm_scene_dirty dirty={0};
    assert(!mm_scene_dispatch(&d.session.core,41,reset_body,sizeof reset_body,1,&dirty));
    uint8_t *tail=(uint8_t *)&sc->txn;size_t n=sizeof(*sc)-offsetof(cfw_cache,txn);
    for(size_t i=0;i<n;i++) {tail[i]=1;assert(!mm_scene_trim_reset_undo(&d.session.core));tail[i]=0;}
    sc->owner=0;assert(!mm_scene_trim_reset_undo(&d.session.core));sc->owner=&d.session.core;
    d.session.core.cache_reply[3]=3;assert(!mm_scene_trim_reset_undo(&d.session.core));d.session.core.cache_reply[3]=0;
    d.active=0;assert(!mm_scene_trim_reset_undo(&d.session.core));d.active=1;
    assert(mm_scene_trim_reset_undo(&d.session.core)>0);dispose(&d);
}
static void reacquisition_failure(void) {
    device d;fixture(&d);reset(&d);cfw_cache *sc=d.session.core.scene;
    assert(!sc->undo);size_t used=d.used;
    /* Exhaust actual allocator headroom, covering every fallback size. */
    d.capacity=used+MM_SCENE_SESSION_HEADROOM;
    cfw_cache *snapshot=malloc(sizeof(*sc));assert(snapshot);memcpy(snapshot,sc,sizeof(*sc));
    uint8_t *store=malloc(sc->store_bytes),*pixels=malloc(d.session.raster.bytes);assert(store&&pixels);
    memcpy(store,d.session.core.texture_cache,sc->store_bytes);memcpy(pixels,d.pixels,d.session.raster.bytes);
    put(&d);assert(status(&d)==3 && !sc->undo && d.used==used && d.session.denied_allocations>=8);
    memset(&snapshot->txn,0,sizeof(snapshot->txn));cfw_txn txn=sc->txn;memset(&sc->txn,0,sizeof(sc->txn));
    assert(!memcmp(snapshot,sc,sizeof(*sc)));sc->txn=txn;
    assert(!memcmp(store,d.session.core.texture_cache,sc->store_bytes));
    assert(!memcmp(pixels,d.pixels,d.session.raster.bytes));
    /* SHOW with a PUT also refuses before pins, pixels, animation or journal. */
    uint8_t show_put[39]={38};show_put[5]=1;show_put[7]=1;uint8_t p[34];fill_put(p,7,0);memcpy(show_put+8,p+5,29);
    assert(!send(&d,show_put,sizeof show_put) && status(&d)==3 && !sc->undo && d.used==used);
    assert(!memcmp(store,d.session.core.texture_cache,sc->store_bytes));
    assert(!memcmp(pixels,d.pixels,d.session.raster.bytes));
    uint8_t r[]={41,23,0,80,0,0},bp[34];fill_put(bp,9,23);
    const uint8_t *parts[]={r,bp};size_t sizes[]={sizeof r,sizeof bp};
    bundle_commands(&d,parts,sizes,2,0);
    assert(status(&d)==3 && d.session.core.cache_epoch==23 && !sc->revision && !sc->undo);
    assert(!memcmp(store,d.session.core.texture_cache,sc->store_bytes));
    assert(!memcmp(pixels,d.pixels,d.session.raster.bytes));
    d.capacity=600000;put(&d);assert(status(&d)==0 && sc->undo);show(&d);
    free(snapshot);free(store);free(pixels);dispose(&d);
    /* All individual allocation failures, including scratch growth fallback,
     * remain reclaimable. Success may use a smaller before-image capacity. */
    for(unsigned i=1;i<=9;i++) {fixture(&d);reset(&d);d.fail_at=d.attempts+i;put(&d);dispose(&d);}
}
#endif
static void bundles(void) {
    for(unsigned variant=0;variant<3;variant++) {
        device d;fixture(&d);cfw_cache *sc=d.session.core.scene;void *undo=sc->undo;
        uint8_t r[]={41,23,0,70,0,0},p[34],p0[34],bad[]={0};
        fill_put(p,2,23);fill_put(p0,3,d.session.core.cache_epoch);
        const uint8_t *parts[]={r,p};size_t sizes[]={sizeof r,sizeof p};
        if(variant==0)bundle_commands(&d,parts,sizes,2,0);
        else if(variant==1) {const uint8_t *v[]={p0,r,p};size_t z[]={sizeof p0,sizeof r,sizeof p};bundle_commands(&d,v,z,3,0);}
        else {const uint8_t *v[]={r,p,bad};size_t z[]={sizeof r,sizeof p,sizeof bad};bundle_commands(&d,v,z,3,-1);}
        assert(sc->undo==undo && cfw_object_find(sc,2,0)>=0 && sc->revision>0);
        /* A final RESET inside a bundle deliberately retains prepared scratch. */
        const uint8_t *last[]={r};size_t len[]={sizeof r};bundle_commands(&d,last,len,1,0);
        assert(sc->undo==undo && sc->revision==0);reset(&d);
#ifdef MM_SCENE_RESET_UNDO_TRIM
        assert(!sc->undo);
#endif
        dispose(&d);
    }
}
int main(void) {
    lifetime();bundles();
#ifdef MM_SCENE_RESET_UNDO_TRIM
    guards();reacquisition_failure();
    puts("reset undo trim: lifetime, exact accounting, guards, allocation failures, bundles and cleanup passed");
#else
    puts("default RESET retention and bundle behavior unchanged");
#endif
    return 0;
}
