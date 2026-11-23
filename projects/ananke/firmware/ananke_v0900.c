/* Experimental binding to the hash-pinned Purple/Gray/Cream Yellow V0900.
 * Addresses are supplied by ananke_v0900.ld, independently traced in this app.
 * Never link this binding against a different application or another controller.
 */
#include "button_stream.h"

struct ag_binding {
    struct ag_stream stream;
    volatile ag_u32 epoch;
    ag_u32 sending_epoch;
    ag_u8 packet[AG_PACKET_SIZE];
};
_Static_assert(sizeof(struct ag_binding) == 96, "Update the state allocation audit");

extern struct ag_binding ag_state;
extern volatile ag_u16 stock_connection;
extern volatile ag_u32 stock_keys;
extern void stock_scan(void);
extern ag_u16 stock_ccc_get(ag_u16 connection, ag_u16 handle);
extern void stock_ccc_set(ag_u16 connection, ag_u16 handle, ag_u16 value);
extern ag_u16 stock_ccc_clear(ag_u16 connection);
extern void stock_critical_enter(void);
extern void stock_critical_exit(void);
extern void stock_bt_wake(void);
extern int stock_att_queue(ag_u16 connection, ag_u16 handle, const ag_u8 *packet,
                          ag_u16 length, unsigned operation, unsigned buffer);

static int send_packet(void *context, ag_u16 connection,
                       const ag_u8 *packet, ag_u16 length) {
    struct ag_binding *s = context;
    int result = -1;
    int attempted = 0;
    stock_critical_enter();
    if (length != AG_PACKET_SIZE || s->epoch != s->sending_epoch ||
        stock_connection != connection || !(stock_ccc_get(connection, 0x55) & 1))
        goto done;
    /* Persistent staging also avoids passing a stack pointer to OEM code.
     * Reuse still requires the traced ATT queue's synchronous-copy contract.
     */
    for (unsigned i = 0; i < AG_PACKET_SIZE; ++i) s->packet[i] = packet[i];
    /* The same bounded copying queue reached by the OEM AE42 wrapper. Avoid
     * its error-logging wrapper while holding the OEM nested critical section.
     */
    attempted = 1;
    result = stock_att_queue(connection, 0x54, s->packet, length, 0, 0);
done:
    stock_critical_exit();
    /* OEM dispatcher 0x1e16cfe calls this after queue insertion. The queue
     * alone does not schedule transmission. Wake outside our critical section,
     * including on backpressure so previously queued packets can drain. */
    if (attempted) stock_bt_wake();
    return result;
}

void ag_scan_hook(void) {
    stock_scan();
    stock_critical_enter();
    ag_u32 epoch = ag_state.epoch;
    ag_u16 connection = stock_connection;
    int subscribed = connection && (stock_ccc_get(connection, 0x55) & 1);
    ag_u32 keys = stock_keys;
    int coherent = epoch == ag_state.epoch && connection == stock_connection;
    stock_critical_exit();
    if (!coherent) return;
    ag_state.sending_epoch = epoch;
    ag_stream_poll(&ag_state.stream, connection, epoch, subscribed, keys,
                   send_packet, &ag_state);
}

void ag_ccc_set_hook(ag_u16 connection, ag_u16 handle, ag_u16 value) {
    stock_critical_enter();
    stock_ccc_set(connection, handle, value);
    if (handle == 0x55) ++ag_state.epoch;
    stock_critical_exit();
}

ag_u16 ag_ccc_clear_hook(ag_u16 connection) {
    stock_critical_enter();
    ag_u16 result = stock_ccc_clear(connection);
    ++ag_state.epoch;
    stock_critical_exit();
    /* The OEM caller reuses r0 immediately after this call. */
    return result;
}
