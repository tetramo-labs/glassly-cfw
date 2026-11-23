#ifndef MM_STORAGE_DIAG_H
#define MM_STORAGE_DIAG_H
#include <stddef.h>
#include <stdint.h>
/* Fixed passive snapshot only. No address, key, bus-command or pointer input.
 * Raw native values stay internal; JSON contains normalized state and a legacy
 * manufacturer/device ID, never pointers or UID bytes. */
typedef struct { uint32_t v[22]; } mm_storage_snapshot;
void glassly_storage_snapshot(mm_storage_snapshot *owned);
int mm_storage_topology_json(char *out, size_t capacity);
/* One initialized-only KV read, fixed key0x6009/capacity116. Native helpers
 * compute CRC32(first112) and validate the physical96-byte bitmap. */
int glassly_storage_badmap_read(uint8_t *owned116, uint32_t *actual_length);
uint32_t glassly_storage_badmap_crc(const uint8_t *record116);
int glassly_storage_badmap_valid(const uint8_t *bitmap96);
int mm_storage_badmap_json(char *out,size_t capacity,uint8_t *owned116);
#endif
