/* MIT. Native ANCS records are borrowed only for the duration of each call. */
#ifndef MM_ANCS_INGRESS_H
#define MM_ANCS_INGRESS_H
#include "notifications.h"
#define MM_ANCS_UIDS 32u
#define MM_ANCS_BODY_MAX 4096u
typedef struct { uint32_t uid; uint8_t flags,valid; } mm_ancs_uid;
typedef struct {
    mm_notifications *relay;
    uint8_t peer[6],connected,next;
    uint32_t generation,rejected;
    mm_ancs_uid uids[MM_ANCS_UIDS];
} mm_ancs_ingress;
void mm_ancs_ingress_init(mm_ancs_ingress *,mm_notifications *);
void mm_ancs_ingress_reset(mm_ancs_ingress *);
/* body is the separately resolved descriptor body, never the descriptor pointer. */
int mm_ancs_ingress_event(mm_ancs_ingress *,uint16_t,const uint8_t *,size_t,const uint8_t *,size_t);
int mm_ancs_ingress_action(const mm_ancs_ingress *,uint32_t,uint8_t,uint8_t peer[6],uint32_t *generation);
#endif
