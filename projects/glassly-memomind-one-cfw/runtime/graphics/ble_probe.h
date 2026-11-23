/* MIT. Glassly BLE link on the stock app-side GATT server. */
#ifndef MM_BLE_PROBE_H
#define MM_BLE_PROBE_H
#include "graphics.h"
void glassly_ble_probe_command(uint32_t,void *,const uint8_t *,void **);
uint32_t glassly_ble_on_read(const uint8_t *,void *,uint8_t *,uint32_t);
void glassly_ble_on_write(const uint8_t *,void *,const uint8_t *,uint32_t);
void glassly_ble_on_cccd(const uint8_t *,void *,uint32_t);
void glassly_ble_on_link(const uint8_t *,uint32_t,uint32_t);
void glassly_ble_boot_register(void);
uint32_t glassly_gm_write(const uint8_t *,uint32_t);
uint32_t glassly_ota_ble_send(uint32_t,const uint8_t *,uint32_t);
void glassly_adv_stop(void);
#endif
