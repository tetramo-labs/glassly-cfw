/* Stock ABI for the pinned G1 1.6.3 application (2025-06-28 17:28:42).
 * Addresses and instruction guards: cfw/targets/g1-1.6.3.json.
 * Port evidence and memory ownership: docs/G1_CFW_163_PORT.md.
 * Thumb function addresses carry bit 0. Never use these with a 1.5.60 base.
 * Host tests override calls/pointers, not the target's structure offsets.
 */
#pragma once
#include <stdint.h>

#define FW_BASE_MAJOR 1
#define FW_BASE_MINOR 6
#define FW_BASE_PATCH 3

typedef uint8_t *(*fw_get_ctx_fn)(void);
#ifndef FW_GET_CTX
#define FW_GET_CTX ((fw_get_ctx_fn)0x00018321)
#endif

typedef int (*fw_send_fn)(const void *data, uint32_t len);
#define FW_CTX_SEND_OFFSET 0x0c
#ifndef FW_SEND_OF
#define FW_SEND_OF(ctx) (*(fw_send_fn *)((ctx) + FW_CTX_SEND_OFFSET))
#endif

typedef int (*fw_hook_fn)(const void *data, uint32_t len);
#ifndef FW_SPEC_BLE_COMMAND_HOOK
#define FW_SPEC_BLE_COMMAND_HOOK ((fw_hook_fn)0x0000ef29)
#endif

typedef uint8_t *(*fw_get_state_fn)(void);
#ifndef FW_GET_STATE
#define FW_GET_STATE ((fw_get_state_fn)0x0001681d)
#endif

/* sys_clock_tick_get_32: kernel ticks at 32768 Hz (k_msleep at 0x7fef6
 * converts ms << 15 / 1000). Wraps after 36 hours. */
typedef uint32_t (*fw_ticks_fn)(void);
#ifndef FW_TICKS32
#define FW_TICKS32 ((fw_ticks_fn)0x00089e41)
#endif

/* Panel context inside GlassesState; a 640x200 frame buffer on a 640x480
 * panel. The CFW canvas is taller and is composed through the buffer in
 * bands of at most FW_FRAME_HEIGHT rows. */
#define FW_PANEL_OFFSET      0xb6c
#define FW_PANEL_FRAME       0x344
#define FW_PANEL_COL_OFFSET  0x348
#define FW_PANEL_ROW_OFFSET  0x34c
#define FW_PANEL_POWERED     0x35c
#define FW_PANEL_HEIGHT_GEAR 0x354
#define FW_PANEL_DEPTH_GEAR  0x355
#define FW_FRAME_WIDTH       640
#define FW_FRAME_HEIGHT      200
#define FW_FRAME_STRIDE      320

#define FW_PANEL_MEM_ROWS    480
#ifndef FW_FRAME_OF
#define FW_FRAME_OF(panel) ((uint8_t *)(uintptr_t)(*(uint32_t *)((panel) + FW_PANEL_FRAME)))
#endif

/* x1 exclusive, y1 inclusive. Caller holds the recursive LCD mutex across
 * header writes, temporary frame shifts, SPI transfers, and restoration. */
typedef int (*fw_reflash_fn)(int col_off, int row_off, int x0, int y0, int x1, int y1);
#ifndef FW_REFLASH_FB
#define FW_REFLASH_FB ((fw_reflash_fn)0x0004abd1)
#endif

typedef int (*fw_lcd_lock_fn)(int64_t timeout);
typedef int (*fw_lcd_unlock_fn)(void);
#ifndef FW_LCD_LOCK
#define FW_LCD_LOCK ((fw_lcd_lock_fn)0x0004af51)
#define FW_LCD_UNLOCK ((fw_lcd_unlock_fn)0x0004af61)
#endif

#define FW_MAX_PACKET 256

typedef int (*fw_system_power_fn)(uint8_t *state);
#ifndef FW_SYSTEM_SUSPEND
#define FW_SYSTEM_SUSPEND ((fw_system_power_fn)0x0002d8f9)
#endif
#ifndef FW_SYSTEM_RESUME
#define FW_SYSTEM_RESUME ((fw_system_power_fn)0x0002d975)
#endif
#define FW_STATE_POWER_OFFSET 0xfea

typedef int (*fw_panel_cb_fn)(uint8_t *panel);
#define FW_PANEL_CB_SUSPEND 0x04
#define FW_PANEL_CB_RESUME  0x08
#define FW_PANEL_CB_OFF 0x0c
#define FW_PANEL_CB_ON  0x10

typedef int (*fw_panel_drv_fn)(uint8_t *panel);
#ifndef FW_JBD_PANEL_SUSPEND
#define FW_JBD_PANEL_SUSPEND ((fw_panel_drv_fn)0x0004aea9)
#endif
#ifndef FW_JBD_PANEL_RESUME
#define FW_JBD_PANEL_RESUME ((fw_panel_drv_fn)0x0004aef1)
#endif

#define FW_PANEL_BRIGHTNESS_LEVEL 0x369
typedef int (*fw_level_fn)(uint32_t level);
#ifndef FW_PANEL_WRITE_BRIGHTNESS
#define FW_PANEL_WRITE_BRIGHTNESS ((fw_level_fn)0x0004a831)
#endif
#ifndef FW_PANEL_CB_OF
#define FW_PANEL_CB_OF(panel, slot) ((fw_panel_cb_fn)(uintptr_t)(*(uint32_t *)((panel) + (slot))))
#endif

/* BMP staging [0x20017d30,0x20019130): stock 15/16/20 uploads are swallowed. */
#define FW_CFW_RAM_BASE 0x20017d30u
#define FW_CFW_RAM_SIZE 0x1400u
#ifndef FW_CFW_RAM
#define FW_CFW_RAM ((uint8_t *)FW_CFW_RAM_BASE)
#endif

typedef int (*fw_utf_draw_fn)(int unused, const char *utf8, unsigned font, int x0, int y0, int x1, int y1,
                              unsigned max_lines, unsigned dim_glyphs, int p10, void *effect_cb, int p12);
#ifndef FW_GUI_UTF_DRAW
#define FW_GUI_UTF_DRAW ((fw_utf_draw_fn)0x000462e9)
#endif

typedef int (*fw_set_rows_fn)(void *rows);
#ifndef FW_GUI_SET_ROWS
#define FW_GUI_SET_ROWS ((fw_set_rows_fn)0x000452f1)
#endif

typedef int (*fw_void_fn)(void);
#ifndef FW_GUI_MANUAL_FLUSH
#define FW_GUI_MANUAL_FLUSH ((fw_void_fn)0x00045429)
#endif
#define FW_PANEL_ROWS 0x24

typedef void *(*fw_malloc_fn)(uint32_t size);
#ifndef FW_MALLOC
#define FW_MALLOC ((fw_malloc_fn)0x0007a015)
#endif

#ifndef FW_ADDR_OF
#define FW_ADDR_OF(ptr) ((uint32_t)(uintptr_t)(ptr))
#define FW_PTR_OF(addr) ((uint8_t *)(uintptr_t)(addr))
#endif

#ifndef FW_PEEK_PTR
#define FW_PEEK_PTR(addr) ((const uint8_t *)(uintptr_t)(addr))
#endif

/* Navigation/translation scratch ends BEFORE the live word at 0x2001db40.
 * The display dispatch is replaced; this region has 328 spare bytes. */
#define FW_CFW_RAM2_BASE 0x2001c750u
#define FW_CFW_RAM2_SIZE 0x13f0u
#ifndef FW_CFW_RAM2
#define FW_CFW_RAM2 ((uint8_t *)FW_CFW_RAM2_BASE)
#endif

/* Dashboard/navigation scratch: depth-shift edges or physical clear packet,
 * always held under the LCD mutex. */
#define FW_CFW_RAM3_BASE 0x200143d0u
#define FW_CFW_RAM3_SIZE 0x13a4u
#ifndef FW_CFW_RAM3
#define FW_CFW_RAM3 ((uint8_t *)FW_CFW_RAM3_BASE)
#endif

typedef int (*fw_display_post_fn)(uint8_t screen, uint32_t p2, uint32_t p3);
#ifndef FW_DISPLAY_POST
#define FW_DISPLAY_POST ((fw_display_post_fn)0x00080fcb)
#endif
typedef int (*fw_msleep_fn)(int ms);
#ifndef FW_K_MSLEEP
#define FW_K_MSLEEP ((fw_msleep_fn)0x0007fef7)
#endif
#define FW_SCREEN_CFW 0x10

#ifndef FW_TOUCH_EVENT
#define FW_TOUCH_EVENT ((volatile uint32_t *)0x200084f8u)
#define FW_KEY_EVENT_SEM ((void *)0x200084fcu)
#define FW_KEY_EVENT_SEM_READY ((volatile uint8_t *)0x20019a58u)
#endif
typedef void (*fw_sem_give_fn)(void *sem);
#ifndef FW_K_SEM_GIVE
#define FW_K_SEM_GIVE ((fw_sem_give_fn)0x0007fecb)
#endif

#ifndef FW_EVENT_PENDING
#define FW_EVENT_PENDING ((volatile uint8_t *)0x20003051u)
#endif
#define FW_CTX_EVENT_SEM    0x218
#define FW_CTX_EVENT_READY  0x220
#define FW_CTX_EVENT_DIRECT 0x248
typedef int (*fw_enqueue_fn)(const void *data, uint32_t len);
#ifndef FW_ENQUEUE_BT_DATA
#define FW_ENQUEUE_BT_DATA ((fw_enqueue_fn)0x00017fed)
#endif

#define FW_STATE_WORK_MODE 0x1
/* Resume after the exact displaced instructions; see the naked detours. */
#define FW_CHANGE_WORK_MODE_RESUME_LO 0x69c5
#define FW_CHANGE_WORK_MODE_RESUME_HI 0x0001

#define FW_CHECK_WORK_MODE_RESUME_LO 0x97e5
#define FW_CHECK_WORK_MODE_RESUME_HI 0x0002

#define FW_STATE_WEAR_DETECT 0x10d4
#define FW_WEAR_WORD_ADDR 0x20006bc8
#ifndef FW_WEAR_WORD
#define FW_WEAR_WORD() (*(volatile uint32_t *)FW_WEAR_WORD_ADDR)
#endif

#define FW_SYSTEM_SUSPEND_RESUME_LO 0xd8ff
#define FW_SYSTEM_SUSPEND_RESUME_HI 0x0002

#ifndef FW_IMU_ATTITUDE
#define FW_IMU_ATTITUDE ((volatile int32_t *)0x20008484u)
#endif

/* Main-thread PDM capture request bit 2; mode 0 streams, 1 stops, 2 captures. */
#define FW_STATE_MIC_ARM    0x106d
#define FW_STATE_MAIN_SEM   0x68
#ifndef FW_MIC_MODE
#define FW_MIC_MODE ((volatile uint8_t *)0x20003052u)
#define FW_MIC_TO_FLASH ((volatile uint32_t *)0x20008558u)
#endif

/* Stock SPI helpers, valid during panel_init before the powered flag is set.
 * WRITE_DATA takes a RAM packet (EasyDMA) and preserves its CS framing. */
typedef void (*fw_panel_write_fn)(const void *data, uint32_t len);
typedef void (*fw_panel_command_fn)(uint32_t command);
typedef void (*fw_panel_wait_fn)(uint32_t ms);
#ifndef FW_PANEL_WRITE_DATA
#define FW_PANEL_WRITE_DATA ((fw_panel_write_fn)0x00080f09)
#endif
#ifndef FW_PANEL_COMMAND
#define FW_PANEL_COMMAND ((fw_panel_command_fn)0x00080ecf)
#endif
#ifndef FW_PANEL_WAIT_MS
#define FW_PANEL_WAIT_MS ((fw_panel_wait_fn)0x00080ec5)
#endif

/* Stock ANCS client, on the temple whose state byte 0 reads 2. Its request
 * thread fetches one notification into a 0x1b4-byte record: [time:u32]
 * [incall:u32][uid:u32, set only for a removal][u32], NUL-terminated
 * strings (app id 0x10, display name 0x30, title 0x50, subtitle 0x70: 32
 * bytes each; message 0x90: 256; ANCS date 0x190: 32) and the event id as
 * the u32 at 0x1b0. dequeue_ancs
 * copies the next queued record out and returns 0. The uid-queue entry the
 * thread last took, [uid:u32][event][flags][category][count], sits at
 * 0x20006c8c. */
typedef int (*fw_dequeue_fn)(void *record);
#ifndef FW_DEQUEUE_ANCS
#define FW_DEQUEUE_ANCS ((fw_dequeue_fn)0x00018ee9)
#endif
#define FW_ANCS_RECORD_BYTES  0x1b4u
#define FW_ANCS_REC_UID       0x08u
#define FW_ANCS_REC_APP_ID    0x10u
#define FW_ANCS_REC_APP_NAME  0x30u
#define FW_ANCS_REC_TITLE     0x50u
#define FW_ANCS_REC_SUBTITLE  0x70u
#define FW_ANCS_REC_MESSAGE   0x90u
#define FW_ANCS_REC_DATE      0x190u
#define FW_ANCS_REC_EVENT     0x1b0u
#define FW_ANCS_SHORT_FIELD   32u
#define FW_ANCS_MESSAGE_FIELD 256u
#ifndef FW_ANCS_UID_ENTRY
#define FW_ANCS_UID_ENTRY ((const volatile uint8_t *)0x20006c8cu)
#endif

/* The stock client subscribes to ANCS only after discover_gattp on a link
 * at security level 2 (ancs_security_changed, 0x185f4), and the stock asks
 * for that level itself only from low_speed_peripheral_dispatch_thread
 * (0x2cd70) behind state flags the Even app sets. The CFW does both when
 * the host arms the lease. FUN_00019cec returns the phone connection the
 * ANCS client works on (DAT_20007ef4), NULL while none. discover_gattp's
 * second argument supplies the uuid type in its high byte: pass 0.
 * bt_conn_get_security is the two-instruction reader of conn->sec_level
 * (byte 9: ldrb r0,[r0,#9]; bx lr) that ancs_security_changed calls; the
 * neighbouring 0x84cde (adds r0,#0x90) is bt_conn_get_dst and returns a
 * pointer, which G1CFW/52 mistook for a level and so never asked for 2. */
typedef void *(*fw_ancs_conn_fn)(void);
#ifndef FW_ANCS_CONN
#define FW_ANCS_CONN ((fw_ancs_conn_fn)0x00019ced)
#endif
typedef int (*fw_conn_get_security_fn)(void *conn);
#ifndef FW_CONN_GET_SECURITY
#define FW_CONN_GET_SECURITY ((fw_conn_get_security_fn)0x00084c9b)
#endif
typedef int (*fw_conn_set_security_fn)(void *conn, int level);
#ifndef FW_CONN_SET_SECURITY
#define FW_CONN_SET_SECURITY ((fw_conn_set_security_fn)0x00084c53)
#endif
typedef void (*fw_discover_gattp_fn)(void *conn, uint32_t uuid_type, uint32_t unused);
#ifndef FW_DISCOVER_GATTP
#define FW_DISCOVER_GATTP ((fw_discover_gattp_fn)0x000183ed)
#endif
/* ancs_discovery_flags: bit 0 a discovery is running, bit 1 the ANCS
 * handles are assigned (discover_ancs_completed_cb). */
#ifndef FW_ANCS_DISCOVERY_FLAGS
#define FW_ANCS_DISCOVERY_FLAGS ((volatile uint32_t *)0x20006c94u)
#endif
/* ancs_security_changed's count of failed security changes in a row: it
 * re-requests level 2 after each failure, reboots once the count reaches 10
 * and clears it on any successful change (its only reference, literal at
 * 0x1871c; increment and compare at 0x186ae). Not cleared on disconnect. */
#ifndef FW_ANCS_SECURITY_FAILS
#define FW_ANCS_SECURITY_FAILS ((volatile uint32_t *)0x20006c14u)
#endif
/* Persisted user settings in GlassesState: 0x1088 is the Even app's
 * notify-enable (14 01), 0x1089 the force-bind mode. */
#define FW_STATE_NOTIFY_ENABLED 0x1088u
#define FW_STATE_FORCE_BIND     0x1089u
#define FW_STATE_SIDE 0x0
