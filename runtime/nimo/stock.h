/* Stock 1.1.5.1 app entry points the runtime calls (XIP addresses, app load
 * 0x041b4020). Found in Ghidra; see docs/runtime.md. Rebuild against another
 * firmware only after re-finding every one. */
#ifndef NIMO_STOCK_H
#define NIMO_STOCK_H

#include <stdint.h>

/* send_response(cmd, key, data, len): frames [cmd][key][len LE16][data] on the
 * 0xBF channel; data[0] is the status byte. The slave arm skips the send. */
typedef int (*nimo_send_response_fn)(uint32_t cmd, uint32_t key, const void *data, uint32_t len);
#define nimo_send_response ((nimo_send_response_fn)0x0426e2d6u)

/* Nonzero on the arm that talks to the phone. */
typedef int (*nimo_is_master_fn)(void);
#define nimo_is_master ((nimo_is_master_fn)0x041fc24eu)

/* gui_post_async(fn, arg): run fn(arg) on the UI (LVGL) task; nonzero when queued
 * (48-entry ring, no copy). Safe from the router context. */
typedef void (*nimo_ui_fn)(void *arg);
typedef int (*nimo_gui_post_async_fn)(nimo_ui_fn fn, void *arg);
#define nimo_gui_post_async ((nimo_gui_post_async_fn)0x04206cf2u)

/* Heap (wq_heap_caps_malloc behind a thunk); malloc returns 0 on failure. */
typedef void *(*nimo_malloc_fn)(uint32_t size);
typedef void (*nimo_free_fn)(void *ptr);
#define nimo_malloc ((nimo_malloc_fn)0x041fa772u)
#define nimo_free ((nimo_free_fn)0x041fa784u)

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
#define NIMO_PANEL_W 540u
#define NIMO_PANEL_H 280u
#define NIMO_PANEL_STRIDE 270u
typedef int (*nimo_panel_flush_fn)(const uint8_t *fb, uint32_t x, uint32_t row0, uint32_t w, uint32_t nrows);
#define nimo_panel_flush ((nimo_panel_flush_fn)0x04200db2u)
#define NIMO_PANEL_UP (*(volatile const uint8_t *)0x020121beu)
#define NIMO_IS_LEFT (*(volatile const uint8_t *)0x02011b18u)

#endif
