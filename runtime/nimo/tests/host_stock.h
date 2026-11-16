/* Host stand-ins for the stock entry points in stock.h: a recording phone
 * link, a UI-task queue run on demand, an accounted heap, the display mutex
 * and a panel that keeps what was flushed to it. Test-only. MIT. */
#ifndef NIMO_HOST_STOCK_H
#define NIMO_HOST_STOCK_H
#include <setjmp.h>
#include <stdint.h>
#include "glassly.h"

typedef struct { uint32_t cmd, key, len; uint8_t data[640]; } host_reply;
typedef struct { uint32_t row0, nrows; } host_flush;

typedef struct {
    host_reply replies[256];
    unsigned reply_count;
    host_reply peer[256];
    unsigned peer_count;
    int peer_error;
    struct { nimo_ui_fn fn; void *arg; } queue[48];
    unsigned queue_count, queue_fail;
    size_t heap_capacity, heap_used, heap_peak;
    unsigned allocations, alloc_attempts, alloc_fail_at;
    uint32_t now;
    int master;
    unsigned lock_depth, locks;
    host_flush flushes[512];
    unsigned flush_count;
    int flush_rc;
    uint8_t panel[NIMO_FRAME_BYTES];
    unsigned brightness_calls;
    uint32_t brightness;
    unsigned repaints, invalidates, cancels;
    nimo_timer_fn timer_fn;
    unsigned timers_created, timers_deleted, timer_live;
    unsigned critical, criticals;
    unsigned still_resets;
    unsigned glyph_lookups;
    jmp_buf *reset_in_flush; /* a panel flush jumps here: the device reset mid-present */
} host_state;

extern host_state host;
/* Power-on: noise where the breadcrumbs live, then a boot. */
void host_reset(int left);
/* Reset: the boot clears the RAM block and frees the heap; breadcrumbs stay. */
void host_reboot(int left);
unsigned host_run_ui(void);
void host_timer_tick(void);
#endif
