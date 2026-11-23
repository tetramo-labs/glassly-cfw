/* MIT. G2 keyboard state machine port; see KEYBOARD.md. */
#ifndef MM_PORTABLE_KEYBOARD_H
#define MM_PORTABLE_KEYBOARD_H
#include <stdint.h>
#include <stddef.h>
#define KB_CHUNK 96u
#define KB_HEADER 24u
#define KB_SLOTS 32u
#define KB_CONTROL_MAX 80u

enum { KB_QUERY, KB_ENABLE, KB_DISABLE, KB_SCAN, KB_CONNECT, KB_DISCONNECT,
       KB_PAIR, KB_AUTH, KB_COMPARE, KB_FIND, KB_READ, KB_WRITE, KB_WATCH };
enum { KB_STATUS=1, KB_ATT, KB_INPUT, KB_DM, KB_ADVERT };
enum { KB_OK, KB_BAD_REQUEST, KB_OFF, KB_BUSY, KB_STALE, KB_NO_SPACE,
       KB_NOT_CONNECTED, KB_NOT_ENCRYPTED, KB_TIMEOUT, KB_NO_MEMORY };


/* Compatibility event codes retain G2 wire meaning, not native struct ABI.
 * data: ATT bytes, advertisement bytes, or auth prompt (2 bytes) / normalized
 * comparison value (4-byte little endian, already modulo 1,000,000). */
typedef struct {
    uint16_t param; uint8_t event,status;
    const uint8_t *data;
    uint16_t len,handle;
    int8_t rssi;
    uint8_t type,addr_type,addr[6];
} mm_keyboard_event;
typedef struct {
    void *user;
    uint32_t (*now_ms)(void *);
    int (*timer_start)(void *,uintptr_t,uint32_t);
    int (*post_poll)(void *);
    int (*send)(void *,const uint8_t *,uint32_t);
    int (*scan_available)(void *);
    void (*scan_start)(void *);
    int (*can_connect)(void *,uint8_t,const uint8_t *);
    uint8_t (*open)(void *,uint8_t,const uint8_t *);
    void (*close)(void *,uint8_t);
    int (*pair)(void *,uint8_t);
    void (*auth)(void *,uint8_t,const uint8_t *);
    void (*compare)(void *,uint8_t,uint8_t);
    int (*request)(void *,uint8_t,uint8_t,uint16_t,uint16_t,const uint8_t *,uint16_t);
    void (*ind_confirm)(void *,uint8_t);
    void (*master_dm)(void *,const mm_keyboard_event *);
    int (*master_security)(void *,const mm_keyboard_event *);
} mm_keyboard_platform;
typedef struct {
    uint8_t len, data[KB_HEADER + KB_CHUNK];
} mm_keyboard_record;
typedef struct {
    uint32_t head, tail;                 /* release/acquire publication */
    uint32_t sequence, drops, reported_drops, deadline, heartbeat, scan_deadline;
    uintptr_t timer;
    uint32_t poll_pending, timer_armed, active;
    uint16_t epoch, pending, pending_handle;
    uint16_t watches[16];
    uint8_t enabled, conn, connected, encrypted, scanning, closing;
    uint8_t pending_event, watch_count, auth, compare;
    uint8_t notify_buf[KB_HEADER + KB_CHUNK + 10];
    mm_keyboard_record queue[KB_SLOTS];
    mm_keyboard_platform platform;
} mm_keyboard;


/* Caller owns context and timer. Init fresh storage; no allocation by core.
 * Exactly one serialized producer calls control/event/poll/lost; one timer
 * consumer calls tick. Callbacks must obey documented non-reentrancy rules. */
int mm_keyboard_init(mm_keyboard *,const mm_keyboard_platform *,uintptr_t timer);
int mm_keyboard_validate_control(const uint8_t *,size_t);
void mm_keyboard_control(mm_keyboard *,const uint8_t *,size_t);
int mm_keyboard_handle_event(mm_keyboard *,const mm_keyboard_event *);
void mm_keyboard_poll(mm_keyboard *);
void mm_keyboard_tick(void *);
/* Owner calls when an upstream owned event is lost before the relay queue. */
void mm_keyboard_lost(mm_keyboard *);
#endif
