/* Offline portable transactional cache backend. See FLASH_STORE.md. */
#ifndef MM_PORTABLE_FLASH_STORE_H
#define MM_PORTABLE_FLASH_STORE_H
#include <stddef.h>
#include <stdint.h>
#define MM_FLASH_LOGICAL_BYTES UINT32_C(262144)
#define MM_FLASH_PHYSICAL_BYTES UINT32_C(1048576)
#define MM_FLASH_SECTOR_BYTES UINT32_C(4096)
#define MM_FLASH_PAGE_BYTES UINT32_C(256)
#define MM_FLASH_LOGICAL_SECTORS 64u
#define MM_FLASH_PHYSICAL_SECTORS 256u
#define MM_FLASH_UNAVAILABLE_BYTES 32u
#define MM_FLASH_MIN_USABLE_SECTORS 129u
#define MM_FLASH_UNMAPPED UINT16_MAX

enum { MM_FLASH_OK=0, MM_FLASH_ARGUMENT=-1, MM_FLASH_GEOMETRY=-2,
       MM_FLASH_STATE=-3, MM_FLASH_RANGE=-4, MM_FLASH_IO=-5,
       MM_FLASH_POISONED=-6, MM_FLASH_NO_SPACE=-7, MM_FLASH_ALIAS=-8 };
typedef struct {
    uint32_t physical_base,physical_bytes,logical_bytes,sector_bytes,page_bytes;
} mm_flash_geometry;
typedef struct {
    void *user;
    /* Zero success, nonzero failure. Callbacks are synchronous, non-reentrant.
     * Physical offsets include geometry.physical_base. read<=256, erase4096,
     * program256; no callback call crosses its physical page/sector boundary.
     * A failure may have partially changed destination/new physical sector. */
    int (*read)(void *,uint32_t,void *,size_t);
    int (*erase)(void *,uint32_t,size_t);
    int (*program)(void *,uint32_t,const void *,size_t);
} mm_flash_callbacks;
/* Caller-owned; internal fields must not be modified after init. At most512B.
 * A single serialized owner must call every function, including read/view. */
typedef struct {
    mm_flash_callbacks io;
    uint8_t *workspace;
    uint32_t base,magic;
    uint16_t active[MM_FLASH_LOGICAL_SECTORS],staged[MM_FLASH_LOGICAL_SECTORS];
    uint8_t unavailable[MM_FLASH_UNAVAILABLE_BYTES];
    uint8_t next_sector,open_sector,transaction,poisoned;
} mm_flash_store;

/* Exactly4096 bytes of nonaliasing workspace. Init never calls flash callbacks;
 * logical bytes start zero regardless of previous flash contents. Reinit loses
 * every logical byte intentionally. Mandatory unavailable bitmap: bitN means
 * physical sectorN cannot be touched. Copy requires>=129 usable sectors.
 * No null/default bitmap, reboot durability or physical reservation here. */
int mm_flash_store_init(mm_flash_store *,const mm_flash_geometry *,
                        const mm_flash_callbacks *,const uint8_t unavailable[MM_FLASH_UNAVAILABLE_BYTES],
                        void *workspace,size_t workspace_bytes);
int mm_flash_store_begin(mm_flash_store *);
int mm_flash_store_read(mm_flash_store *,uint32_t offset,void *out,size_t length);
int mm_flash_store_write(mm_flash_store *,uint32_t offset,const void *data,size_t length);
int mm_flash_store_commit(mm_flash_store *);
int mm_flash_store_abort(mm_flash_store *);
/* Writes collect one logical sector in the workspace; touching another sector,
 * commit, or a view of another sector inside a transaction copies it to flash.
 * Returns a borrowed const scratch view, up to one logical sector boundary,
 * <=max_length. Invalid after any next store operation. No writable XIP alias. */
int mm_flash_store_view(mm_flash_store *,uint32_t offset,size_t max_length,
                        const uint8_t **view,size_t *length);
#endif
