#ifndef MEMOMIND_GRAPHICS_H
#define MEMOMIND_GRAPHICS_H
#include <stddef.h>
#include <stdint.h>
#include "geometry.h"

#define MM_GRAPHICS_WIDTH 600u
#define MM_GRAPHICS_HEIGHT 350u
#define MM_GRAPHICS_STRIDE 300u
#define MM_GRAPHICS_PIXELS (MM_GRAPHICS_STRIDE * MM_GRAPHICS_HEIGHT)
#define MM_GRAPHICS_QUEUE_EVENT 0x474cu
#define MM_GRAPHICS_COMMAND 0x7du
#define MM_GRAPHICS_JOB_HEADER 4u
#ifdef MM_GRAPHICS_SCENE
#define MM_GRAPHICS_MAX_MESSAGE 8192u
#define MM_GRAPHICS_QUEUE_HEADROOM (32u * 1024u)
#else
#define MM_GRAPHICS_MAX_MESSAGE MM_GEOMETRY_MAX_MESSAGE
#endif
/* Native scheduler ticks: exact profile configures1000Hz (one millisecond). */
#define MM_GRAPHICS_LEASE_TICKS 1000u
#define MM_GRAPHICS_TIMER_TICKS 20u
#define MM_GRAPHICS_METADATA_MARGIN 65536u

typedef void (*mm_callback)(void *);
typedef struct {
    uint32_t header, data_size;
    const uint8_t *data;
} mm_native_image;

/* The display worker serializes all object/timer operations. Request extraction
 * borrows until release(); post() synchronously copies its input. send() borrows
 * its TLV list and copies before returning. No function owns passed heap memory
 * unless stated below. Host tests substitute this table, not firmware addresses.
 */
typedef struct {
    int (*request_bytes)(void *, const uint8_t **, size_t *);
    void (*release)(void **);
    void *(*json)(const char *);
    void *(*status)(uint32_t, const char *);
    void *(*alloc)(size_t);
    void (*free)(void *);
    void (*post)(const void *, size_t);
    void (*send)(uint8_t event, void *response);
    void *(*screen)(void);
    int (*launcher_active)(void);
    void *(*find_owner)(void *parent, mm_callback delete_callback);
    void *(*image_create)(void *parent);
    int (*on_delete)(void *image, mm_callback callback, void *owner);
    void (*image_source)(void *image, const mm_native_image *source);
    void (*image_delete)(void *image); /* invokes attached DELETE callback */
    void (*cache_invalidate)(const mm_native_image *);
    void *(*event_userdata)(void *);
    void *(*timer_create)(mm_callback, uint32_t period, void *owner);
    void (*timer_delete)(void *);
    void *(*timer_userdata)(void *);
    uint32_t (*now)(void);
    uint32_t (*free_bytes)(void);
    uint32_t (*low_water_bytes)(void);
} mm_graphics_platform;
extern const mm_graphics_platform mm_graphics_native;

void glassly_graphics_probe(uint32_t, void *, const uint8_t *, void **);
void glassly_graphics_command(uint32_t, void *, const uint8_t *, void **);
void glassly_graphics_display(void *envelope);
#endif
