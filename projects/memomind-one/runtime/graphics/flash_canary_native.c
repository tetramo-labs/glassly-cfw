/* Hardware bindings only. Never called while a custom critical section is held. */
#include "flash_canary.h"
#define FN(a,t) ((t)(uintptr_t)(a))
_Static_assert(sizeof(void *)==4,"Pinned RV32 ABI only");
int glassly_canary_layout_valid(void) {
    volatile const uint32_t *p=(const volatile uint32_t *)(uintptr_t)0x0205d5f8u;
    return p[0]==2 && p[1]==0x0205e228u && p[2]==0x020fedc0u && p[3]==0x0205e228u;
}
volatile mm_canary_registry *glassly_canary_registry(void) {return (volatile mm_canary_registry *)(uintptr_t)MM_CANARY_REGISTRY;}
void glassly_canary_enter(void) {typedef void (*f)(void);FN(0x0200a23au,f)();}
void glassly_canary_leave(void) {typedef void (*f)(void);FN(0x0200a264u,f)();}
int glassly_canary_create(void *job) {
    typedef uintptr_t (*f)(mm_callback,void *,uint32_t,uint32_t,const char *);
    return FN(0x0200f168u,f)(glassly_flash_canary_entry,job,5,0x800,"glassly_canary")!=0;
}
