/* GLASSLYCFW runtime for NIMO: command keys, statuses and the UI-task side
 * shared by glassly.c (router context) and display.c (UI task). MIT. */
#ifndef NIMO_GLASSLY_H
#define NIMO_GLASSLY_H
#include <stdint.h>
#include "stock.h"
#include "scene_session.h"

enum {
    GLASSLY_CMD = 0x7E,
    KEY_IDENTITY = 0x01, KEY_ECHO = 0x02, KEY_CHECKSUM = 0x03, KEY_STATUS = 0x04, KEY_DRAW_TEST = 0x10,
    KEY_SCENE = 0x20, KEY_ACQUIRE = 0x21, KEY_RELEASE = 0x22, KEY_BRIGHTNESS = 0x23,
    KEY_SETTLED = 0x24, KEY_CANVAS = 0x25, KEY_INPUT = 0x26, KEY_ANCS_CONTROL = 0x27, KEY_ANCS_RECORD = 0x28,
};
enum {
    STATUS_OK = 0, STATUS_INVALID = 1, STATUS_NO_MEMORY = 2, STATUS_NOT_OWNED = 3,
    STATUS_TOO_LARGE = 4, STATUS_UNSUPPORTED = 5, STATUS_BUSY = 6,
};

/* The stock reassembler holds one 0x3000-byte [cmd][key][len LE16][payload]. */
#define NIMO_MAX_PAYLOAD (0x3000u - 4u)
#define NIMO_FRAME_BYTES (NIMO_PANEL_STRIDE * NIMO_PANEL_H)
#define NIMO_MAX_JOBS 4u
/* Heap left to the stock firmware when the runtime allocates a job or the
 * session; the scene's own allocations keep MM_SCENE_SESSION_HEADROOM. */
#define NIMO_JOB_HEADROOM (32u * 1024u)
#define NIMO_PUMP_MS 10u
#define NIMO_SESSION_MAGIC 0x53534e47u /* "GNSS" */
#define NIMO_SETTLED_QUEUE 8u
#define NIMO_INPUT_BYTES 16u
/* UI_MSG_ID_DISPLAY_SET_BRIGHTNESS_SYNC: the auto-brightness step from the
 * light sensor, sent to both arms. 0xa7 (a level the wearer chose) passes. */
#define NIMO_MSG_AUTO_BRIGHTNESS 0xa8u

typedef struct nimo_session {
    uint32_t magic;
    mm_scene_session scene;
    uint8_t *shadow;          /* the borrowed stock framebuffer: what this arm's panel should show */
    uint16_t pend_top, pend_bottom; /* rows the panel still lacks; empty when bottom <= top */
    uint8_t eye;              /* 1 left, 2 right: the panel this arm drives */
    uint8_t settled_count;
    uint16_t settled[NIMO_SETTLED_QUEUE];
} nimo_session;

typedef struct {
    uint32_t len;
    uint32_t seq;             /* the command's number, for the breadcrumbs */
    uint8_t data[];
} nimo_job;

/* Small UI jobs carry their argument in the low byte and the command's
 * number above it. */
#define NIMO_JOB_ARG(arg) ((uint32_t)(uintptr_t)(arg) & 0xFFu)
#define NIMO_JOB_SEQ(arg) ((uint32_t)(uintptr_t)(arg) >> 8)

/* Breadcrumbs (ram.h): a lane starts a stage with its command's identity and
 * moves through the later stages; each lane has a single writer. */
/* Notification relay (ancs.c): the router answers 0x27 with the STATUS record;
 * the stock ANCS client's completed notifications reach glassly_ancs_intake
 * through the call hook at 0x04274006 and its whitelist check asks
 * glassly_ancs_leased through the hook at 0x042767d0. */
uint32_t glassly_ancs_control(const uint8_t *payload, uint32_t len, uint8_t *reply);
int glassly_ancs_intake(const uintptr_t *intake);
int glassly_ancs_leased(void);
void nimo_crumb_start(uint32_t lane, uint32_t stage, uint32_t seq, uint32_t key, uint32_t mode, uint32_t len);
void nimo_crumb_stage(uint32_t lane, uint32_t stage);
/* One scene job fewer waiting (the UI task ran or dropped it). */
void nimo_job_finished(void);

/* UI-task jobs posted by glassly_command; each sends its own reply. */
void nimo_ui_scene(void *job);
void nimo_ui_acquire(void *unused);
void nimo_ui_release(void *unused);
void nimo_ui_brightness(void *level);
void nimo_ui_draw_test(void *pattern);
void nimo_ui_canvas(void *unused);

/* CRC-32 as zlib computes it. */
uint32_t nimo_crc32(const uint8_t *data, uint32_t len);

int glassly_command(uint32_t cmd, uint32_t key, const uint8_t *payload, uint32_t len);
/* A stock touch or auto-brightness message while owned (UI task, from the
 * input gate); nonzero when the stock dispatcher must not see it. */
int glassly_input(uint32_t id, const uint8_t *param, uint32_t len);
#endif
