#include <assert.h>
#include <string.h>
#include "../firmware/button_stream.h"

static ag_u8 packets[1024][AG_PACKET_SIZE];
static unsigned packet_count;
static int blocked;
static int send_packet(void *context, ag_u16 connection, const ag_u8 *data, ag_u16 size) {
    (void)context;
    assert(connection == 7 || connection == 8);
    assert(size == AG_PACKET_SIZE);
    if (blocked) return -10;
    assert(packet_count < 1024);
    memcpy(packets[packet_count++], data, size);
    return 0;
}
static ag_u32 keys(unsigned index) {
    const ag_u8 *p = packets[index];
    assert(p[0] == 0x47 && p[1] == 2);
    return (ag_u32)p[4] | ((ag_u32)p[5] << 8) | ((ag_u32)p[6] << 16) | ((ag_u32)p[7] << 24);
}
static int poll(struct ag_stream *s, ag_u32 k) {
    return ag_stream_poll(s, 7, 1, 1, k, send_packet, 0);
}
static void reset(struct ag_stream *s) {
    packet_count = 0;
    blocked = 0;
    memset(s, 0xa5, sizeof *s);
    ag_stream_init(s);
}
int main(void) {
    struct ag_stream s;
    unsigned i;
    reset(&s);
    assert(ag_stream_poll(&s, 0, 1, 1, 1, send_packet, 0) == 0);
    assert(ag_stream_poll(&s, 7, 1, 0, 1, send_packet, 0) == 0);
    assert(packet_count == 0);
    assert(poll(&s, 0) == 1);
    assert(packets[0][3] == AG_FLAG_BASELINE);
    assert(poll(&s, 0) == 0);
    for (i = 0; i < 32; i++) {
        assert(poll(&s, 1u << i) == 1);
        assert(keys(packet_count - 1) == (1u << i));
        assert(poll(&s, 0) == 1);
        assert(keys(packet_count - 1) == 0);
    }
    assert(poll(&s, 0xffffffffu) == 1);
    assert(keys(packet_count - 1) == 0xffffffffu);

    /* Backpressure retains press followed by release, including an unsent baseline. */
    reset(&s);
    blocked = 1;
    assert(poll(&s, 0) == -1);
    assert(poll(&s, 0x80000001u) == -1);
    assert(poll(&s, 0) == -1);
    assert(s.sequence == 0 && s.count == 3 && packet_count == 0);
    blocked = 0;
    for (i = 0; i < 3; i++) assert(poll(&s, 0) == 1);
    assert(keys(0) == 0 && keys(1) == 0x80000001u && keys(2) == 0);
    assert(packets[0][3] == AG_FLAG_BASELINE && packets[1][3] == 0);

    /* Overflow drops old transitions, explicitly flags loss and retains the final release. */
    reset(&s);
    blocked = 1;
    for (i = 0; i < 40; i++) assert(poll(&s, i + 1) == -1);
    assert(poll(&s, 0) == -1);
    assert(s.count == AG_QUEUE_CAPACITY);
    blocked = 0;
    for (i = 0; i < AG_QUEUE_CAPACITY; i++) assert(poll(&s, 0) == 1);
    assert(packets[0][3] == AG_FLAG_OVERFLOW);
    assert(keys(AG_QUEUE_CAPACITY - 1) == 0);
    assert(poll(&s, 0) == 0);

    /* CCC off/on, epoch changes and reused connection handles discard stale presses. */
    reset(&s);
    blocked = 1;
    assert(poll(&s, 1) == -1);
    assert(ag_stream_poll(&s, 7, 1, 0, 1, send_packet, 0) == 0);
    blocked = 0;
    assert(poll(&s, 0) == 1 && keys(0) == 0);
    blocked = 1;
    assert(poll(&s, 1) == -1);
    blocked = 0;
    assert(ag_stream_poll(&s, 7, 2, 1, 0, send_packet, 0) == 1);
    assert(keys(1) == 0 && packets[1][3] == AG_FLAG_BASELINE);
    assert(ag_stream_poll(&s, 8, 2, 1, 2, send_packet, 0) == 1);
    assert(keys(2) == 2 && packets[2][3] == AG_FLAG_BASELINE);

    reset(&s);
    for (i = 0; i < 300; i++) {
        assert(poll(&s, i) == 1);
        assert(packets[i][2] == (ag_u8)i);
    }
    return 0;
}
