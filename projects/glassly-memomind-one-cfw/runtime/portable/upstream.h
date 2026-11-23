/* MIT. Portable G2 compatibility protocol/policy; see UPSTREAM_PORT.md. */
#ifndef MM_PORTABLE_UPSTREAM_H
#define MM_PORTABLE_UPSTREAM_H
#include <stdint.h>
#include <stddef.h>
typedef int (*mm_upstream_send)(void *,int type,int channel,const uint8_t *,unsigned);
typedef void (*mm_upstream_control)(void *,unsigned field,const uint8_t *,unsigned);
typedef struct {unsigned field;const uint8_t *data;unsigned length;} mm_upstream_extension;
typedef struct {uint8_t connected,charging,level;} mm_upstream_battery;
typedef struct {uint32_t timestamp;uint8_t accuracy,anomalies,source,flags;} mm_upstream_sample;
typedef struct {uint32_t timestamp;uint8_t heading_valid;} mm_upstream_record;
typedef struct {uint8_t grv,gmrv,gmrv_heading,rv,rv_heading,mag_fresh,accuracy,anomalies,mag_seen,cached_accuracy,cached_anomalies;} mm_upstream_capture;
typedef struct {uint32_t prefix;uint16_t min,max,latency,timeout,retries,suffix;} mm_upstream_profile;
typedef struct {
    uint8_t ble_fast,compass_forward;
    mm_upstream_profile profile;
    mm_upstream_sample compass_samples[20];
} mm_upstream_state;
typedef struct {
    void *user;
    const mm_upstream_profile *(*profile_get)(void *);
    const mm_upstream_profile *(*stock_fast)(void *);
    void (*profile_set)(void *,const mm_upstream_profile *);
    unsigned (*wanted)(void *);
    unsigned (*applied)(void *);
    void (*clear_applied)(void *);
    void (*set_wanted)(void *,unsigned);
    unsigned (*generation)(void *);
    void (*cancel)(void *);
    void (*post)(void *,unsigned argument,unsigned milliseconds);
    int (*request)(void *,unsigned mode,void *connection);
    unsigned (*classify)(void *,const void *connection);
} mm_upstream_link;
unsigned mm_upstream_append(uint8_t *,unsigned length,unsigned capacity,unsigned field,const uint8_t *,unsigned size);
void mm_upstream_scan(const uint8_t *,unsigned,mm_upstream_control,void *);
int mm_upstream_shadow(const uint8_t *,unsigned);
unsigned mm_upstream_battery_append(uint8_t *,unsigned,unsigned,mm_upstream_battery);
int mm_upstream_battery_query(const uint8_t *,unsigned,unsigned side,mm_upstream_battery,mm_upstream_send,void *);
/* Caller supplies truthful capability/status extensions; no built-in revision claim.
 * Logical channel9 compatibility response; battery follows only successful send. */
int mm_upstream_settings_send(int type,int channel,uint8_t *,unsigned length,unsigned capacity,
    const mm_upstream_extension *,unsigned count,unsigned side,mm_upstream_battery,mm_upstream_send,void *);
void mm_upstream_capture_sample(mm_upstream_state *,unsigned index,uint32_t timestamp,const mm_upstream_capture *);
unsigned mm_upstream_heading(const mm_upstream_state *,unsigned event,int heading,unsigned side,
    const mm_upstream_record *,unsigned count,uint8_t *,unsigned capacity);
unsigned mm_upstream_filter(const mm_upstream_state *,unsigned mode);
unsigned mm_upstream_classify(const mm_upstream_state *,const mm_upstream_link *,const void *connection,
    int connected,unsigned interval,unsigned latency);
int mm_upstream_request(mm_upstream_state *,const mm_upstream_link *,unsigned mode,void *connection);
void mm_upstream_link_control(mm_upstream_state *,const mm_upstream_link *,const uint8_t *,unsigned);
void mm_upstream_link_cleanup(mm_upstream_state *,const mm_upstream_link *);
void mm_upstream_link_status(const mm_upstream_state *,const mm_upstream_link *,unsigned side,
    int connected,unsigned interval,unsigned latency,uint8_t body[17]);
#endif
