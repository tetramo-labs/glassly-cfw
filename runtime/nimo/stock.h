/* Stock 1.1.5.1 app entry points the runtime calls (XIP addresses, app load
 * 0x041b4020). Found in Ghidra; see docs/runtime.md. Rebuild against another
 * firmware only after re-finding every one. With NIMO_HOST the same names are
 * plain functions and variables a host test provides. */
#ifndef NIMO_STOCK_H
#define NIMO_STOCK_H

#include <stdint.h>
#include "ram.h"

#define NIMO_PANEL_W 540u
#define NIMO_PANEL_H 280u
#define NIMO_PANEL_STRIDE 270u

typedef void (*nimo_ui_fn)(void *arg);
typedef void (*nimo_timer_fn)(void *timer);

/* LVGL 9.3 font records as far as the runtime reads them: lv_font_t,
 * lv_font_fmt_txt_dsc_t (its first two fields), lv_font_fmt_txt_glyph_dsc_t
 * and the lv_font_glyph_dsc_t the font's get_glyph_dsc fills in. */
typedef struct {
    uint32_t index_adv;  /* glyph_bitmap byte offset (20 bits), advance in 1/16 px (12 bits) */
    uint8_t box_w, box_h;
    int8_t ofs_x, ofs_y;
} nimo_glyph_record;
typedef struct {
    const uint8_t *glyph_bitmap;
    const nimo_glyph_record *glyph_dsc;
} nimo_font_dsc;
typedef struct {
    const void *get_glyph_dsc, *get_glyph_bitmap, *release_glyph;
    int32_t line_height, base_line;
    uint8_t flags;
    int8_t underline_position, underline_thickness;
    const nimo_font_dsc *dsc;
} nimo_font;
typedef struct {
    const void *resolved_font;
    uint16_t adv_w, box_w, box_h;
    int16_t ofs_x, ofs_y;
    uint16_t stride;
    uint32_t format;     /* bits per pixel for a plain bitmap font */
    uint8_t flags;
    int32_t outline_stroke_width;
    uint32_t gid;
    const void *entry, *spare[3];
} nimo_glyph_dsc;

#ifdef NIMO_HOST
int nimo_send_response(uint32_t cmd, uint32_t key, const void *data, uint32_t len);
int nimo_is_master(void);
int nimo_peer_ui(uint32_t id, const void *data, uint32_t len);
void nimo_still_reset(void);
int nimo_gui_post_async(nimo_ui_fn fn, void *arg);
void *nimo_malloc(uint32_t size);
void nimo_free(void *ptr);
uint32_t nimo_heap_free(void);
uint32_t nimo_heap_largest(uint32_t caps);
uint32_t nimo_now_ms(void);
void *nimo_display_mutex(void);
void nimo_os_lock(void *mutex);
void nimo_os_unlock(void *mutex);
int nimo_panel_flush(const uint8_t *fb, uint32_t x, uint32_t row0, uint32_t w, uint32_t nrows);
int nimo_set_brightness(uint32_t level);
void nimo_repaint_all(void);
void nimo_cancel_auto_off(uint32_t reason);
void *nimo_lv_screen_active(void);
void nimo_lv_obj_invalidate(void *obj);
void *nimo_lv_timer_create(nimo_timer_fn fn, uint32_t period_ms, void *user);
void nimo_lv_timer_delete(void *timer);
void nimo_critical_enter(void);
void nimo_critical_exit(void);
int nimo_font_glyph(const nimo_font *font, nimo_glyph_dsc *dsc, uint32_t letter, uint32_t next);
extern const nimo_font nimo_host_text_font;
#define NIMO_TEXT_FONT (&nimo_host_text_font)
extern volatile uint8_t nimo_host_panel_up, nimo_host_left, nimo_host_display_on, nimo_host_lit;
extern volatile uint16_t nimo_host_panel_brightness;
extern volatile uint32_t nimo_host_blank_ticks;
extern uint8_t nimo_host_fb[2][NIMO_PANEL_STRIDE * NIMO_PANEL_H];
extern volatile uint8_t nimo_host_fb_back, nimo_host_fb_front;
#define NIMO_FB(i) (nimo_host_fb[(i)])
#define NIMO_FB_BACK nimo_host_fb_back
#define NIMO_FB_FRONT nimo_host_fb_front
#define NIMO_PANEL_UP nimo_host_panel_up
#define NIMO_IS_LEFT nimo_host_left
#define NIMO_DISPLAY_ON nimo_host_display_on
#define NIMO_LIT nimo_host_lit
#define NIMO_BLANK nimo_host_blank_ticks
#define NIMO_PANEL_BRIGHTNESS nimo_host_panel_brightness
#else
/* send_response(cmd, key, data, len): frames [cmd][key][len LE16][data] on the
 * 0xBF channel; data[0] is the status byte. The slave arm skips the send. */
typedef int (*nimo_send_response_fn)(uint32_t cmd, uint32_t key, const void *data, uint32_t len);
#define nimo_send_response ((nimo_send_response_fn)0x0426e2d6u)

/* Copies a UI message (up to 512 bytes) through the stock inter-arm transport. */
typedef int (*nimo_peer_ui_fn)(uint32_t id, const void *data, uint32_t len);
#define nimo_peer_ui ((nimo_peer_ui_fn)0x041fc078u)

/* Zeroes the head task's stillness time, which enters wake-on-motion (and
 * stops the accelerometer FIFO) after 120 s without movement. */
typedef void (*nimo_still_reset_fn)(void);
#define nimo_still_reset ((nimo_still_reset_fn)0x04277b18u)

/* Nonzero on the arm that talks to the phone. */
typedef int (*nimo_is_master_fn)(void);
#define nimo_is_master ((nimo_is_master_fn)0x041fc24eu)

/* gui_post_async(fn, arg): run fn(arg) on the UI (LVGL) task; nonzero when queued
 * (48-entry ring, no copy). Safe from the router context. */
typedef int (*nimo_gui_post_async_fn)(nimo_ui_fn fn, void *arg);
#define nimo_gui_post_async ((nimo_gui_post_async_fn)0x04206cf2u)

/* Heap (wq_heap_caps_malloc behind a thunk); malloc returns 0 on failure.
 * heap_free sums the free bytes of every registered region and heap_largest
 * returns the largest free block (caps 0 = any), both under a critical
 * section; the stock DIAGHEAPCHK boot trace prints exactly these two. */
typedef void *(*nimo_malloc_fn)(uint32_t size);
typedef void (*nimo_free_fn)(void *ptr);
typedef uint32_t (*nimo_heap_free_fn)(void);
typedef uint32_t (*nimo_heap_largest_fn)(uint32_t caps);
#define nimo_malloc ((nimo_malloc_fn)0x041fa772u)
#define nimo_free ((nimo_free_fn)0x041fa784u)
#define nimo_heap_free ((nimo_heap_free_fn)0x042f7aeau)
#define nimo_heap_largest ((nimo_heap_largest_fn)0x042f7a38u)

/* Milliseconds: the FreeRTOS tick count (1 kHz), the clock the GUI task times
 * lv_timer_handler with. */
typedef uint32_t (*nimo_now_fn)(void);
#define nimo_now_ms ((nimo_now_fn)0x041fa73cu)

/* Display mutex (created on first use) and the OS lock wrappers. os_lock waits
 * up to 60 s and asserts (resets) on failure or from an interrupt. */
typedef void *(*nimo_display_mutex_fn)(void);
typedef void (*nimo_lock_fn)(void *mutex);
#define nimo_display_mutex ((nimo_display_mutex_fn)0x041fc706u)
#define nimo_os_lock ((nimo_lock_fn)0x0200ed06u)
#define nimo_os_unlock ((nimo_lock_fn)0x0200ed7eu)

/* Panel: 540x280, 4-bit gray, 270-byte rows, high nibble = even x.
 * flush(fb, x, row0, w, nrows) sends rows row0.. of the full-frame buffer fb over
 * SPI (DMA, blocking); x and w are ignored. 0 = sent, 1 = panel down. */
typedef int (*nimo_panel_flush_fn)(const uint8_t *fb, uint32_t x, uint32_t row0, uint32_t w, uint32_t nrows);
#define nimo_panel_flush ((nimo_panel_flush_fn)0x04200db2u)

/* Brightness 0..32, not persisted; takes the display mutex itself. Returns the
 * panel op's result (0x04202646): 0 set, 1 panel down or level out of range;
 * 3/7 when the panel has no op. The op keeps the level it set (u16 below). */
typedef int (*nimo_set_brightness_fn)(uint32_t level);
#define nimo_set_brightness ((nimo_set_brightness_fn)0x041fec90u)

/* Marks every stock framebuffer row dirty so the next stock frame resends all. */
typedef void (*nimo_void_fn)(void);
#define nimo_repaint_all ((nimo_void_fn)0x041fe71au)

/* Cancels an armed display auto-off (reason 2 is the quiet one). */
typedef void (*nimo_cancel_auto_off_fn)(uint32_t reason);
#define nimo_cancel_auto_off ((nimo_cancel_auto_off_fn)0x04268164u)

/* LVGL 9.3: lv_screen_active, lv_obj_invalidate, lv_timer_create(cb, period,
 * user_data) (asserts forever on out of memory), lv_timer_delete. UI task only. */
typedef void *(*nimo_screen_fn)(void);
typedef void (*nimo_obj_fn)(void *obj);
typedef void *(*nimo_timer_create_fn)(nimo_timer_fn fn, uint32_t period_ms, void *user);
#define nimo_lv_screen_active ((nimo_screen_fn)0x0424143cu)
#define nimo_lv_obj_invalidate ((nimo_obj_fn)0x04233f3au)
#define nimo_lv_timer_create ((nimo_timer_create_fn)0x0423f7f8u)
#define nimo_lv_timer_delete ((nimo_obj_fn)0x0423f89eu)

/* Critical section: masks interrupts (csrrci mstatus, MIE) with a nesting
 * count; the OS wrappers the GUI task guards its own async ring with
 * (0x041fa74e -> 0x0200a432, 0x041fa760 -> 0x0200a45c). The core has no A
 * extension: shared read-modify-writes go through these, never AMOs. Keep
 * sections a few instructions long, with no call inside. */
#define nimo_critical_enter ((nimo_void_fn)0x041fa74eu)
#define nimo_critical_exit ((nimo_void_fn)0x041fa760u)

/* LVGL's default face, Montserrat 16 (lv_font_montserrat_16 layout): 4 bpp,
 * 18 px line, baseline 3, U+0020..U+007E, U+00B0, U+2022 and the LVGL symbol
 * icons; no fallback. Its get_glyph_dsc (lv_font_get_glyph_dsc_fmt_txt) only
 * reads the font's const tables and writes dsc; with next = 0 it skips kerning
 * and the advance is the glyph's own, rounded to whole pixels. */
typedef int (*nimo_font_glyph_fn)(const nimo_font *font, nimo_glyph_dsc *dsc, uint32_t letter, uint32_t next);
#define nimo_font_glyph ((nimo_font_glyph_fn)0x04243e8au)
#define NIMO_TEXT_FONT ((const nimo_font *)0x0431ee44u)
_Static_assert(__builtin_offsetof(nimo_font, line_height) == 12 && __builtin_offsetof(nimo_font, dsc) == 24,
               "lv_font_t layout");
_Static_assert(__builtin_offsetof(nimo_glyph_dsc, adv_w) == 4 && __builtin_offsetof(nimo_glyph_dsc, format) == 16 &&
               __builtin_offsetof(nimo_glyph_dsc, gid) == 28, "lv_font_glyph_dsc_t layout");
_Static_assert(sizeof(nimo_glyph_record) == 8, "lv_font_fmt_txt_glyph_dsc_t layout");

#define NIMO_PANEL_UP (*(volatile const uint8_t *)0x020121beu)
#define NIMO_IS_LEFT (*(volatile const uint8_t *)0x02011b18u)
#define NIMO_DISPLAY_ON (*(volatile const uint8_t *)0x02011fa6u)
#define NIMO_LIT (*(volatile uint8_t *)NIMO_LIT_FLAG)
#define NIMO_BLANK (*(volatile uint32_t *)NIMO_BLANK_TICKS)
#define NIMO_PANEL_BRIGHTNESS (*(volatile const uint16_t *)0x0201198eu)

/* The two stock framebuffers, 75,600 bytes each (540x280 GRAY4, stride 270).
 * LVGL's flush, the frame task, the scroller and the clear routine write the
 * back one (index byte 0x020120fb); the frame commit 0x041fdb08 copies back to
 * front (index 0x0201198a) and is the only code that writes either index. It
 * runs only through the frame kick 0x041f703c, which the kick gate skips while
 * the runtime owns the panel. The build re-checks both claims. */
#define NIMO_FB(i) ((uint8_t *)(0x0202f064u + (uint32_t)(i) * 0x12750u))
#define NIMO_FB_BACK (*(volatile uint8_t *)0x020120fbu)
#define NIMO_FB_FRONT (*(volatile uint8_t *)0x0201198au)
#endif

#endif
