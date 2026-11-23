/* Cold-boot launcher replacement. The shared LVGL screen remains its parent;
 * no stock dashboard objects, listeners, timers or borrowed TLVs are retained. */
#include "graphics.h"
#define FN(a,t) ((t)(uintptr_t)(a))
void glassly_launcher_init(void *app) {
    (void)app;
    void *screen=mm_graphics_native.screen();
    if(screen)FN(0x042c8fe2u,void (*)(void *,uint8_t,uint32_t))(screen,0,0);
}
void glassly_launcher_destroy(void) { glassly_graphics_cleanup(); }
void glassly_launcher_tick(void) {}
int glassly_launcher_event(void *app,uint32_t kind,const void *payload) {
    (void)app;(void)kind;(void)payload;return 0;
}
void glassly_launcher_message(void *app,uint32_t event,void *payload,uint32_t flags) {
    (void)app;(void)event;(void)payload;(void)flags;
}
/* Keep the first-run welcome continuation. Removed launcher hide/show behavior
 * has no objects or deferred callback to operate on. Other apps retain routing. */
void glassly_launcher_home(uint32_t reason) {
    typedef void *(*get_fn)(void);
    typedef void (*welcome_fn)(uint32_t);
    if(FN(0x0425db22u,get_fn)()==(void *)0x0200fcf4u)
        FN(0x04274b12u,welcome_fn)(reason);
}
/* Calibration calls this before entering its independent app. The replacement
 * has no dashboard overlay or transition; retained stock flag getters read the
 * cold-zero state. No old LVGL object pointer is inspected. */
void glassly_launcher_suspend(void) {}
