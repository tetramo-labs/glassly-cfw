/* MIT; adapted from G2 ancs_relay.c, pinned in UPSTREAM.json. */
#ifndef MM_PORTABLE_NOTIFICATIONS_H
#define MM_PORTABLE_NOTIFICATIONS_H
#include <stdint.h>
#include <stddef.h>
#define MM_NOTIFICATIONS_MAGIC 0x4e4f5446u
#define MM_NOTIFICATIONS_RING_BYTES 4096u
#define MM_NOTIFICATIONS_ATTRIBUTE_MAX 1024u
typedef struct {
    void *user;
    void *(*allocate)(void *,size_t);
    void (*deallocate)(void *,void *);
    uint32_t (*now_ms)(void *);
    /* 1 = eligible relay endpoint; other values preserve disabled-side policy. */
    uint32_t (*side)(void *);
    uintptr_t (*timer_new)(void *,void (*)(void *),void *);
    int (*timer_start)(void *,uintptr_t,uint32_t);
    int (*timer_stop)(void *,uintptr_t);
    int (*timer_delete)(void *,uintptr_t);
    /* Must consume/copy synchronously. Bytes are unchanged G2 field-125 frame. */
    int (*send)(void *,const uint8_t *,uint32_t);
    /* Adapter validates connection/handle and posts action asynchronously. */
    void (*action)(void *,uint32_t,uint32_t);
    /* Required serialization around all queue/control/tick accesses. No callback
     * may synchronously reenter the core. See NOTIFICATIONS.md. */
    void (*queue_enter)(void *);
    void (*queue_leave)(void *);
} mm_notifications_platform;
typedef struct {
    uint32_t magic;
    mm_notifications_platform platform;
    uint8_t *ancs_ring;
    uint16_t ancs_head,ancs_tail;
    uint8_t ancs_idle,ancs_epoch;
    uint16_t ancs_seq,ancs_drops;
    uint8_t ancs_send_errs;
    uint32_t ancs_lease_deadline;
    uintptr_t ancs_timer;
    uint8_t ancs_notify_buf[168],ancs_status_buf[24];
} mm_notifications;
/* Init fresh uninitialized storage only. No allocations until ENABLE. */
int mm_notifications_init(mm_notifications *,const mm_notifications_platform *);
void mm_notifications_control(mm_notifications *,const uint8_t *,size_t);
void mm_notifications_source(mm_notifications *,const uint8_t *,size_t);
void mm_notifications_attribute(mm_notifications *,uint32_t uid,uint8_t id,const uint8_t *,size_t);
/* Complete/partial ANCS app-response bytes: [1][bundle-id NUL][0][LE16 length][name]. */
void mm_notifications_app_response(mm_notifications *,const uint8_t *,size_t);
void mm_notifications_tick(void *);
void mm_notifications_cleanup(mm_notifications *);
/* Only after producer is detached and timer callbacks quiesce. On timer delete
 * failure retains storage and returns 0; retry once platform can delete it. */
int mm_notifications_destroy(mm_notifications *);
#endif
