/* MIT. Post-boot GATT service probe for a future BLE command channel. */
#ifndef MM_BLE_PROBE_H
#define MM_BLE_PROBE_H
#include "graphics.h"
void glassly_ble_probe_command(uint32_t,void *,const uint8_t *,void **);
/* Stock GATT server callbacks (exported so emulator tests can drive them). */
uint32_t glassly_ble_on_read(const uint8_t *,void *,uint8_t *,uint32_t);
void glassly_ble_on_write(const uint8_t *,void *,const uint8_t *,uint32_t);
void glassly_ble_on_cccd(const uint8_t *,void *,uint32_t);
/* Notify a reply to a request that arrived over BLE (event 0); 0 when no
 * subscribed BLE client is there to take it. */
int glassly_ble_reply(void *response);
#endif
