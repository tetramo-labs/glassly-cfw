#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../firmware/ananke_v0900.c"

struct ag_binding ag_state;
volatile ag_u16 stock_connection;
volatile ag_u32 stock_keys;
static ag_u16 ccc;
static unsigned scans, sent, setters, clears;
static unsigned queue_attempts, wakes;
static int blocked, change_during_get;
static unsigned lock_depth, enters, exits;
static int defer_disconnect;
static ag_u8 last[8];

void stock_scan(void) { ++scans; }
void stock_critical_enter(void) { ++lock_depth; ++enters; }
void stock_critical_exit(void) {
    assert(lock_depth); --lock_depth; ++exits;
    if (!lock_depth && defer_disconnect) {
        defer_disconnect = 0;
        assert(ag_ccc_clear_hook(stock_connection) == stock_connection);
        ag_ccc_set_hook(stock_connection, 0x55, 1);
    }
}
ag_u16 stock_ccc_get(ag_u16 connection, ag_u16 handle) {
    assert(lock_depth);
    assert(connection == stock_connection && handle == 0x55);
    if (change_during_get) { ++ag_state.epoch; change_during_get = 0; }
    return ccc;
}
void stock_ccc_set(ag_u16 connection, ag_u16 handle, ag_u16 value) {
    assert(lock_depth);
    assert(connection == stock_connection);
    ++setters;
    if (handle == 0x55) ccc = value;
}
ag_u16 stock_ccc_clear(ag_u16 connection) {
    assert(lock_depth);
    assert(connection == stock_connection);
    ++clears;
    ccc = 0;
    return connection;
}
int stock_att_queue(ag_u16 connection, ag_u16 handle, const ag_u8 *packet,
                    ag_u16 length, unsigned operation, unsigned buffer) {
    assert(lock_depth && connection == stock_connection && handle == 0x54);
    assert(operation == 0 && buffer == 0);
    assert(packet == ag_state.packet && length == 8);
    ++queue_attempts;
    if (blocked) return -97;
    memcpy(last, packet, 8);
    ++sent;
    return 0;
}
void stock_bt_wake(void) {
    assert(lock_depth == 0);
    assert(queue_attempts == wakes + 1);
    ++wakes;
}
static ag_u32 mask(void) {
    return (ag_u32)last[4] | ((ag_u32)last[5] << 8) |
           ((ag_u32)last[6] << 16) | ((ag_u32)last[7] << 24);
}
int main(void) {
    /* Simulate the reserved page's startup clear. */
    memset(&ag_state, 0, sizeof ag_state);
    ag_scan_hook(); assert(scans == 1 && sent == 0 && wakes == 0);
    stock_connection = 7;
    stock_keys = 0x80000001;
    ag_scan_hook(); assert(sent == 0);
    ag_ccc_set_hook(7, 0x28, 1); assert(ag_state.epoch == 0);
    ag_ccc_set_hook(7, 0x55, 1);
    ag_scan_hook();
    assert(sent == 1 && mask() == 0x80000001 && last[3] == AG_FLAG_BASELINE);
    assert(last[0] == 0x47 && last[1] == 2);
    ag_scan_hook(); assert(sent == 1);
    blocked = 1;
    stock_keys = 0; ag_scan_hook();
    stock_keys = 2; ag_scan_hook();
    assert(sent == 1 && ag_state.stream.count == 2);
    assert(wakes == 3); /* Accepted baseline plus two backpressure attempts. */
    /* Disconnect and same-handle reconnect between polls must drop old events. */
    assert(ag_ccc_clear_hook(7) == 7);
    ag_ccc_set_hook(7, 0x55, 1);
    blocked = 0; stock_keys = 4; ag_scan_hook();
    assert(sent == 2 && mask() == 4 && last[3] == AG_FLAG_BASELINE);
    assert(ag_state.stream.count == 0 && clears == 1);
    ag_ccc_set_hook(7, 0x55, 0); ag_scan_hook(); assert(sent == 2);
    /* Indications-only must not turn on our notification stream. */
    ag_ccc_set_hook(7, 0x55, 2); ag_scan_hook(); assert(sent == 2);
    ag_ccc_set_hook(7, 0x55, 1);
    change_during_get = 1; ag_scan_hook(); assert(sent == 2);
    ag_scan_hook(); assert(sent == 3 && last[3] == AG_FLAG_BASELINE);
    assert(setters == 6);
    /* A disconnect requested during the snapshot is deferred until unlock;
     * the old epoch then prevents a stale send in this same scan iteration. */
    stock_keys = 16; defer_disconnect = 1; ag_scan_hook();
    assert(sent == 3 && !defer_disconnect);
    ag_scan_hook(); assert(sent == 4 && mask() == 16 && last[3] == AG_FLAG_BASELINE);
    assert(lock_depth == 0 && enters == exits);
    assert(wakes == queue_attempts && wakes == sent + 2);
    puts("Ananke binding tests passed");
}
