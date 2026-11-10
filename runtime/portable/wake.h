/* MIT. G2 settings_ext.c ownership policy, adapted to explicit state. */
#ifndef MM_WAKE_H
#define MM_WAKE_H
#include <stdint.h>
#include <stddef.h>
#define MM_WAKE_LEASE_MS 90000u
enum { MM_WAKE_DROP_FRAME=1, MM_WAKE_FALLBACK=2, MM_WAKE_NOTIFY=4, MM_WAKE_INVALID=8 };
typedef struct {
    uint32_t wake_started,frame_started,pending_started,pending_ms;
    uint16_t nonce;
    uint8_t wake,frame,pending,presented,event;
} mm_wake;
unsigned mm_wake_update(mm_wake *,uint32_t now);
unsigned mm_wake_control(mm_wake *,const uint8_t *,size_t,uint32_t now);
unsigned mm_wake_button(mm_wake *,uint16_t id,uint32_t now);
#endif
