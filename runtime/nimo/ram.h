/* The runtime's fixed RAM. GLASSLYCFW/6 carves 0x0209be74..0x0209cf74 off the
 * start of the only heap region (heap table entry 0x04414f5c: the region now
 * starts at 0x0209cf74) and widens the boot .bss clear (lui at 0x041c3b96) to
 * 0x0209ce74. So the 4 KB block is zero after every boot, the 256 breadcrumb
 * bytes above it keep what the previous boot left there (the record is
 * trusted only behind its two magic words), and no stock code touches either.
 * Zero is a valid state for every block field. Also included by entry.S: keep
 * the offsets below in step. MIT. */
#ifndef NIMO_RAM_H
#define NIMO_RAM_H

#define NIMO_RAM_BASE 0x0209be74
#define NIMO_RAM_BYTES 0x1000
#define NIMO_RAM_OWNED 8         /* u8: read by the flush gate */
#define NIMO_RAM_GATE_SKIPS 12   /* u32: bumped by the flush and kick gates */
#define NIMO_CRUMB_BASE 0x0209ce74
#define NIMO_CRUMB_BYTES 0x100

/* Stock auto-off state, refreshed while the runtime owns the panel: the lit
 * flag (u8, 1 = the canvas shows something) and the black-tick counter (u32;
 * three ticks of a black canvas turn the display off). */
#define NIMO_LIT_FLAG 0x02011a3a
#define NIMO_BLANK_TICKS 0x02012a38

#ifndef __ASSEMBLER__
#include <stddef.h>
#include <stdint.h>

#define NIMO_RAM_MAGIC 0x394d524eu   /* "NRM9" once a command has run this boot */
#define NIMO_CRUMB_MAGIC 0x3642434eu /* "NCB6" */

struct nimo_session;

/* Breadcrumb lanes: one writer each. The router lane is written by the
 * command router, the UI and pump lanes by the UI task. */
enum { NIMO_LANE_ROUTER, NIMO_LANE_UI, NIMO_LANE_PUMP, NIMO_LANES };
/* Stages a lane passes through; IDLE, POSTED and DONE are the resting ones. A
 * reset that leaves any other stage in a lane is reported as last_crash. */
enum {
    NIMO_STAGE_IDLE, NIMO_STAGE_ROUTER, NIMO_STAGE_POSTED, NIMO_STAGE_DISPATCH, NIMO_STAGE_RENDER,
    NIMO_STAGE_PRESENT, NIMO_STAGE_REPLY, NIMO_STAGE_DONE, NIMO_STAGE_TICK, NIMO_STAGES
};

typedef struct {
    uint32_t seq;     /* router and UI lanes: the command's number (commands); pump: tick */
    uint32_t len;     /* payload bytes */
    uint8_t stage;    /* NIMO_STAGE_*; written last when a lane starts */
    uint8_t key;      /* 0x7E key; 0 for a pump tick */
    uint8_t mode;     /* first payload byte of a scene message, else 0 */
    uint8_t reserved;
} nimo_crumb;

typedef struct {
    uint32_t magic;               /* NIMO_CRUMB_MAGIC */
    uint32_t check;               /* ~NIMO_CRUMB_MAGIC */
    uint32_t boot;                /* boots whose first command found this record valid, plus one */
    uint32_t reserved;
    nimo_crumb lane[NIMO_LANES];  /* this boot's progress */
} nimo_crumbs;

typedef struct {
    uint32_t magic;               /* 0x00 NIMO_RAM_MAGIC once a command has run */
    struct nimo_session *session; /* 0x04 heap session; UI task only */
    volatile uint8_t owned;       /* 0x08 1 while the runtime owns the panel */
    uint8_t brightness;           /* 0x09 last level set through 0x7E/0x23 */
    uint8_t brightness_set;       /* 0x0a 1 once brightness has been set */
    uint8_t eye;                  /* 0x0b 1 left, 2 right (at the last acquire) */
    volatile uint32_t gate_skips; /* 0x0c stock panel writes, frame kicks and auto-brightness steps held off while owned */
    void *timer;                  /* 0x10 lv_timer_t of the scene pump; UI task only */
    volatile uint32_t jobs;       /* 0x14 scene jobs queued and not yet run; critical section only */
    uint16_t epoch;               /* 0x18 last scene epoch; the next session starts past it */
    uint16_t reserved;
    uint32_t commands;            /* 0x1c 0x7E requests seen by the router */
    uint32_t scene_messages;      /* 0x20 scene messages dispatched */
    uint32_t scene_failures;      /* 0x24 scene messages rejected */
    uint32_t presents;            /* 0x28 panel flushes from the runtime */
    uint32_t present_rows;        /* 0x2c rows sent by those flushes */
    uint32_t presents_deferred;   /* 0x30 presents held for the other eye */
    uint32_t flush_errors;        /* 0x34 flushes the panel refused */
    uint32_t settled_sent;        /* 0x38 settled notifications sent */
    uint32_t busy;                /* 0x3c requests refused: UI queue or job limit */
    uint32_t alloc_failures;      /* 0x40 runtime allocations refused */
    uint32_t acquires;            /* 0x44 */
    uint32_t releases;            /* 0x48 */
    uint32_t pump_ticks;          /* 0x4c scene pump timer callbacks */
    uint32_t boot;                /* 0x50 the breadcrumb boot count at this boot's first command */
    uint8_t crumbs;               /* 0x54 1 record started fresh, 2 the previous boot's record was kept */
    uint8_t lane;                 /* 0x55 lane the UI task is running (UI or PUMP) */
    uint8_t reserved2[2];
    nimo_crumb last[NIMO_LANES];  /* 0x58 the previous boot's lanes as this boot found them */
    uint8_t pinned;               /* 0x7c 1 while the stock front index is pinned to the back buffer */
    uint8_t front;                /* 0x7d the stock front index the lease found, restored at release */
    uint8_t back;                 /* 0x7e the stock back index while pinned; the canvas is the other buffer */
    uint8_t reserved3;
    uint32_t repins;              /* 0x80 pump ticks that found the stock indices moved and pinned them again */
    uint32_t inputs;              /* 0x84 touch messages the input gate handed over while owned */
    uint8_t lease_brightness;     /* 0x88 the stock panel level when the lease began */
    uint8_t brightness_changed;   /* 0x89 1 once 0x7E/0x23 set a level during this lease */
    uint8_t acquired;             /* 0x8a 1 from a lease's first acquire to its release */
    uint8_t reserved4;
} nimo_ram;

_Static_assert(sizeof(nimo_ram) <= NIMO_RAM_BYTES, "RAM block layout exceeds the carve");
/* The top 16 breadcrumb bytes stay unused: a guard below the heap's first block. */
_Static_assert(sizeof(nimo_crumbs) <= NIMO_CRUMB_BYTES - 16, "breadcrumbs exceed their carve");
#ifndef NIMO_HOST
/* The offsets in the comments are the RV32 ones; host tests use wider pointers. */
_Static_assert(offsetof(nimo_ram, owned) == NIMO_RAM_OWNED, "flush gate reads the owned flag here");
_Static_assert(offsetof(nimo_ram, gate_skips) == NIMO_RAM_GATE_SKIPS, "flush gate counts here");
_Static_assert(offsetof(nimo_ram, last) == 0x58 && offsetof(nimo_ram, repins) == 0x80 &&
               offsetof(nimo_ram, inputs) == 0x84 && sizeof(nimo_ram) == 0x8c, "layout offsets documented above");
_Static_assert(NIMO_RAM_BASE + NIMO_RAM_BYTES == NIMO_CRUMB_BASE, "breadcrumbs follow the block");
#endif

#ifdef NIMO_HOST
extern unsigned char nimo_host_ram[NIMO_RAM_BYTES];
extern unsigned char nimo_host_crumbs[NIMO_CRUMB_BYTES];
#define NIMO_RAM ((nimo_ram *)(void *)nimo_host_ram)
#define NIMO_CRUMBS ((nimo_crumbs *)(void *)nimo_host_crumbs)
#else
#define NIMO_RAM ((nimo_ram *)NIMO_RAM_BASE)
#define NIMO_CRUMBS ((nimo_crumbs *)NIMO_CRUMB_BASE)
#endif
#endif
#endif
