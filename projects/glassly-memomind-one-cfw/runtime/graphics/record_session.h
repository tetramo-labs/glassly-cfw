/* MIT. Serialized display-worker carrier for G2 message records. */
#ifndef MM_RECORD_SESSION_H
#define MM_RECORD_SESSION_H
#include <stddef.h>
#include <stdint.h>
#define MM_RECORD_MODE 126u
#define MM_RECORD_PACKET_BYTES 128u
#define MM_RECORD_REPLY_CAPACITY 64u
#define MM_RECORD_BUDGET (180u*1024u)
#define MM_RECORD_HEADROOM (48u*1024u)
typedef struct mm_record_session mm_record_session;
typedef struct {
    void *(*allocate)(size_t);
    void (*release)(void *);
    uint32_t (*free_bytes)(void);
    int (*dispatch)(uint8_t event,const uint8_t *,uint16_t,uint8_t,uint8_t *,uint8_t *);
} mm_record_platform;
int mm_record_valid(const uint8_t *,size_t);
mm_record_session *mm_record_create(const mm_record_platform *);
/* process/finish must pair. close during dispatch defers destruction to finish;
 * callbacks must not reenter process. The returned JSON is borrowed until finish. */
const char *mm_record_process(mm_record_session *,uint8_t event,const uint8_t *,size_t);
void mm_record_finish(mm_record_session *);
void mm_record_close(mm_record_session *);
#endif
