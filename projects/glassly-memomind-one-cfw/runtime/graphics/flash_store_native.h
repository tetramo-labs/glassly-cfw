#ifndef MM_GRAPHICS_FLASH_STORE_NATIVE_H
#define MM_GRAPHICS_FLASH_STORE_NATIVE_H
#include "flash_store.h"
#define MM_FLASH_NATIVE_BASE UINT32_C(0x00700000)
#define MM_FLASH_NATIVE_END UINT32_C(0x00800000)
#define MM_FLASH_NATIVE_SRAM_BASE UINT32_C(0x02000000)
#define MM_FLASH_NATIVE_SRAM_END UINT32_C(0x02100000)
enum { MM_FLASH_NATIVE_ARGUMENT=-19713, MM_FLASH_NATIVE_STATE=-19714,
       MM_FLASH_NATIVE_RANGE=-19715, MM_FLASH_NATIVE_BAD_SECTOR=-19716,
       MM_FLASH_NATIVE_ALIAS=-19717, MM_FLASH_NATIVE_VERIFY=-19718,
       MM_FLASH_NATIVE_BUSY=-19719 };
enum { MM_FLASH_NATIVE_NONE=0, MM_FLASH_NATIVE_READ=1,
       MM_FLASH_NATIVE_PROGRAM=2, MM_FLASH_NATIVE_ERASE=3,
       MM_FLASH_NATIVE_READBACK=4 };
/* Caller-owned, stable, aligned SRAM. No writable globals or allocation.
 * real_unavailable is an acquired/validated real32B tail slice, not ownership
 * exclusions: the COW core may receive a separate OR'ed private ownership map.
 * last_native_status preserves the most recent native call result; phase names
 * that call. Readback mismatch returns VERIFY with native status0.
 * Fields are internal except read-only diagnostics after a completed call. */
typedef struct {
    uint32_t magic;
    int32_t last_native_status;
    uint8_t real_unavailable[32];
    uint8_t verification[256];
    uint8_t busy,phase;
} mm_flash_native;
/* No I/O on init/bind. Init requires zeroed or previously initialized storage.
 * Caller must supply valid nonoverlapping owned spans.
 * Reinitializing a live/in-flight context is forbidden. The API cannot prove
 * acquisition provenance, exclusive reservation or current-map freshness. */
int mm_flash_native_init(mm_flash_native *,const uint8_t acquired_real_map[32]);
int mm_flash_native_callbacks(mm_flash_native *,mm_flash_callbacks *);
/* Exact portable callback ABI; every native call uses device1 and fixed bounds.
 * SRAM source/destination must remain owned and stable through synchronous
 * completion/readback; no source XIP aliases, context overlap or raw spans.
 * Native read failure may partially change output: caller must discard it.
 * Mutations always perform correct device1 alias maintenance, including errors;
 * success requires explicit native readback. No retry or persistent badmap edit.
 * The caller serializes ALL operations/teardown on one normal worker, outside
 * ISR/LVGL/observer/critical contexts and without holding the native device lock.
 * busy is a reentry guard, NOT a cross-task lock. Binding grants no ownership.
 * Native waits/cache maintenance are uncancellable and may assert/hang. */
int mm_flash_native_read(void *,uint32_t,void *,size_t);
int mm_flash_native_erase(void *,uint32_t,size_t);
int mm_flash_native_program(void *,uint32_t,const void *,size_t);
#ifdef MM_FLASH_NATIVE_HOST_TEST
/* Test-only link seam. Production always calls the pinned addresses. */
int mm_flash_test_read(uint32_t,uint32_t,void *,uint32_t);
int mm_flash_test_program(uint32_t,uint32_t,const void *,uint32_t);
int mm_flash_test_erase(uint32_t,uint32_t,uint32_t);
void mm_flash_test_cache(uint32_t,uint32_t,uint32_t);
#endif
#endif
