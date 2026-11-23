#ifndef MM_FLASH_CANARY_H
#define MM_FLASH_CANARY_H
#include "graphics.h"
#if defined(MM_FLASH_CANARY) && !defined(MM_FULL_STORE_READ)
#error "Canary requires full-store reader"
#endif
#define MM_CANARY_TOKEN UINT32_C(0x43414e31)
#define MM_CANARY_REGISTRY UINT32_C(0x0205e128)
#define MM_CANARY_TARGET UINT32_C(0x007ff000)
#define MM_CANARY_NEIGHBOR UINT32_C(0x007fe000)
#define MM_CANARY_MAGIC UINT32_C(0x434e5931)
#define MM_CANARY_HEADROOM (96u*1024u)
enum { MM_CANARY_IDLE=0,MM_CANARY_STARTING=1,MM_CANARY_RUNNING=2,MM_CANARY_PASSED=3,MM_CANARY_FAILED=4 };
enum { MM_CANARY_ADMISSION=1,MM_CANARY_BADMAP=2,MM_CANARY_PRECHECK=3,MM_CANARY_ERASE=4,MM_CANARY_PROGRAM=5,MM_CANARY_RESTORE=6,MM_CANARY_NEIGHBOR_CHECK=7,MM_CANARY_COMPLETE=8 };
enum { MM_CANARY_ALLOC=-20001,MM_CANARY_TASK=-20002,MM_CANARY_MAP=-20003,MM_CANARY_NOT_ERASED=-20004,MM_CANARY_LAYOUT=-20005 };
/* Reserved boot-zeroed SRAM, never allocator-owned. No pointer survives here.
 * Access only after layout validation and under the native short critical pair.
 * One claim per boot, including allocation/task failure. No reset/retry opcode. */
typedef struct {uint32_t magic,state,operation,phase;int32_t error,native_status;uint32_t map_source,mutation,restored,neighbor;} mm_canary_registry;
_Static_assert(sizeof(mm_canary_registry)<=256 && _Alignof(mm_canary_registry)<=8,"Registry carve bounds");
void glassly_flash_canary_command(uint32_t,void *,const uint8_t *,void **);
void glassly_flash_canary_worker(void *);
void glassly_flash_canary_entry(void *);
int glassly_canary_layout_valid(void);
volatile mm_canary_registry *glassly_canary_registry(void);
void glassly_canary_enter(void);
void glassly_canary_leave(void);
/* Only boolean success. Returned native wrapper may already have been freed. */
int glassly_canary_create(void *owned_job);
#endif
