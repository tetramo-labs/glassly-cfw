/* Ambient light readings for the phone (GLASSLYCFW/13). The sensor, a TI
 * OPT3001, sits on the left arm only and the stock firmware powers it just
 * while its auto-brightness wants it. While the phone holds the 90 s lease it
 * renews with 0x7E/0x2C, the left arm reads the sensor from an LVGL timer at
 * the phone's interval, powering it if the stock has it off, and each reading
 * leaves the master as 0x7E/0x2D: sent directly when the left arm is the
 * master, else handed over through the stock inter-arm UI transport. The
 * timer is created and deleted only by a UI job, never from its own
 * callback. No heap. MIT. */
#include "glassly.h"

#define LIGHT_MIN_MS 200u
#define LIGHT_MAX_MS 5000u
#define LIGHT_RECORD 11u
enum { LIGHT_FORCED = 1, LIGHT_STOCK_AUTO = 2 };

static int leased(const nimo_ram *ram, uint32_t now)
{
    return ram->light_lease_until != 0 && (int32_t)(ram->light_lease_until - now) > 0;
}

static void put16(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void light_job(void *arg);

static void post(nimo_ram *ram)
{
    if (ram->light_posted) return;
    ram->light_posted = 1;
    if (!nimo_gui_post_async(light_job, 0)) {
        ram->light_posted = 0;
        ram->busy++;
    }
}

/* UI task, every interval: [status][sample u16][flags][lux u16][ms tick u32]
 * [panel level]. A sensor found off is powered and read on the next tick,
 * once its first 100 ms conversion is done. */
static void light_tick(void *timer)
{
    (void)timer;
    nimo_ram *ram = NIMO_RAM;
    uint32_t now = nimo_now_ms();
    if (!leased(ram, now)) {
        post(ram);
        return;
    }
    if (!NIMO_LIGHT_POWERED) {
        if (nimo_light_power(1) == 0) ram->light_forced = 1;
        else ram->light_failures++;
        return;
    }
    uint16_t lux = 0;
    if (nimo_light_read(&lux) != 0) {
        ram->light_failures++;
        return;
    }
    uint8_t out[LIGHT_RECORD];
    out[0] = STATUS_OK;
    put16(out + 1, (uint32_t)ram->light_samples + 1u);
    out[3] = (uint8_t)((ram->light_forced ? LIGHT_FORCED : 0) | (NIMO_LIGHT_WANTED ? LIGHT_STOCK_AUTO : 0));
    put16(out + 4, lux);
    put16(out + 6, now);
    put16(out + 8, now >> 16);
    out[10] = (uint8_t)NIMO_PANEL_BRIGHTNESS;
    int rc = nimo_is_master() ? nimo_send_response(GLASSLY_CMD, KEY_LIGHT, out, sizeof out)
                              : nimo_peer_ui(NIMO_MSG_LIGHT_RELAY, out, sizeof out);
    if (rc == 0) ram->light_samples++;
    else ram->light_failures++;
}

/* UI task: brings the timer in line with the lease. When the lease is over
 * the sensor goes back to the power the stock last asked for. */
static void light_job(void *arg)
{
    (void)arg;
    nimo_ram *ram = NIMO_RAM;
    ram->light_posted = 0;
    int want = NIMO_IS_LEFT && leased(ram, nimo_now_ms());
    if (ram->light_timer != 0 && (!want || ram->light_period != ram->light_interval)) {
        nimo_lv_timer_delete(ram->light_timer);
        ram->light_timer = 0;
    }
    if (!want) {
        if (ram->light_forced && !NIMO_LIGHT_WANTED && !NIMO_LIGHT_FACTORY) nimo_light_power(0);
        ram->light_forced = 0;
        return;
    }
    if (ram->light_timer == 0) {
        ram->light_period = ram->light_interval;
        ram->light_timer = nimo_lv_timer_create(light_tick, ram->light_period, 0);
    }
}

/* The master, UI task: a reading the left arm handed over. Always kept from
 * the stock dispatcher. */
int glassly_light_forwarded(const uint8_t *data, uint32_t len)
{
    nimo_ram *ram = NIMO_RAM;
    if (!nimo_is_master() || !leased(ram, nimo_now_ms())) return 1;
    if (data == 0 || len != LIGHT_RECORD || data[0] != STATUS_OK) return 1;
    if (nimo_send_response(GLASSLY_CMD, KEY_LIGHT, data, len) == 0) ram->light_samples++;
    else ram->light_failures++;
    return 1;
}

/* [1][interval ms u16] arms or renews a 90 s lease (interval held to
 * 200..5000), [0] drops it. Reply [status][leased][1 when this arm has the
 * sensor][interval u16][samples u16][failures u16]. */
uint32_t glassly_light_control(const uint8_t *payload, uint32_t len, uint8_t *out)
{
    nimo_ram *ram = NIMO_RAM;
    uint32_t now = nimo_now_ms();
    if (len == 3 && payload[0] == 1u) {
        uint32_t interval = (uint32_t)payload[1] | ((uint32_t)payload[2] << 8);
        if (interval < LIGHT_MIN_MS) interval = LIGHT_MIN_MS;
        if (interval > LIGHT_MAX_MS) interval = LIGHT_MAX_MS;
        ram->light_interval = (uint16_t)interval;
        ram->light_lease_until = now + NIMO_LIGHT_LEASE_MS;
        if (ram->light_lease_until == 0) ram->light_lease_until = 1;
    } else if (len == 1 && payload[0] == 0) {
        ram->light_lease_until = 0;
    } else {
        out[0] = STATUS_INVALID;
        return 1;
    }
    if (NIMO_IS_LEFT) post(ram);
    out[0] = STATUS_OK;
    out[1] = (uint8_t)leased(ram, now);
    out[2] = NIMO_IS_LEFT ? 1u : 0u;
    put16(out + 3, ram->light_interval);
    put16(out + 5, ram->light_samples);
    put16(out + 7, ram->light_failures);
    return 9;
}
