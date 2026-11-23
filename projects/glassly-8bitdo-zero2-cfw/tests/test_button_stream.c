#include "button_stream.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct sink { unsigned calls, count; int blocked; uint16_t connection; uint8_t last[8]; };
static int send_packet(void *context, uint16_t connection, const uint8_t *data, uint16_t n) {
    struct sink *out = context;
    assert(n == 8 && data[0] == 0x47 && data[1] == 3);
    out->calls++;
    if (out->blocked) return -1;
    out->count++;
    out->connection = connection;
    memcpy(out->last, data, 8);
    return 0;
}
static uint32_t mask(const struct sink *out) {
    return (uint32_t)out->last[4] | (uint32_t)out->last[5] << 8 |
           (uint32_t)out->last[6] << 16 | (uint32_t)out->last[7] << 24;
}
static void basic(void) {
    struct z2_stream s; struct sink out = {0}; z2_stream_init(&s);
    assert(z2_stream_poll(&s, 0, 0, 1, 1, 42, send_packet, &out) == 0);
    assert(z2_stream_poll(&s, 1, 0, 1, 0, 42, send_packet, &out) == 0);
    assert(out.calls == 0);
    assert(z2_stream_poll(&s, 1, 0, 1, 1, 0x87654321, send_packet, &out) == 1);
    assert(out.connection == 0 && mask(&out) == 0x87654321);
    assert(out.last[2] == 0 && out.last[3] == Z2_FLAG_BASELINE);
    assert(z2_stream_poll(&s, 1, 0, 1, 1, 0x87654321, send_packet, &out) == 0);
    assert(z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out) == 1);
    assert(mask(&out) == 0 && out.last[2] == 1 && out.last[3] == 0);
}
static void retry_and_lifecycle(void) {
    struct z2_stream s; struct sink out = {0}; z2_stream_init(&s);
    out.blocked = 1;
    for (uint32_t i = 0; i < 5; i++)
        assert(z2_stream_poll(&s, 1, 7, 1, 1, i, send_packet, &out) == -1);
    assert(s.sequence == 0 && s.count == 5);
    out.blocked = 0;
    for (uint32_t i = 0; i < 5; i++) {
        assert(z2_stream_poll(&s, 1, 7, 1, 1, 4, send_packet, &out) == 1);
        assert(mask(&out) == i && out.last[2] == i);
        assert(out.last[3] == (i == 0 ? Z2_FLAG_BASELINE : 0));
    }
    out.blocked = 1;
    z2_stream_poll(&s, 1, 7, 1, 1, 99, send_packet, &out);
    out.blocked = 0;
    z2_stream_poll(&s, 1, 7, 2, 1, 12, send_packet, &out);
    assert(mask(&out) == 12 && out.last[3] == Z2_FLAG_BASELINE && s.count == 0);
    z2_stream_poll(&s, 1, 8, 2, 1, 13, send_packet, &out);
    assert(mask(&out) == 13 && out.last[3] == Z2_FLAG_BASELINE);
    z2_stream_poll(&s, 1, 8, 2, 0, 13, send_packet, &out);
    z2_stream_poll(&s, 1, 8, 3, 1, 14, send_packet, &out);
    assert(mask(&out) == 14 && out.last[3] == Z2_FLAG_BASELINE);
    z2_stream_poll(&s, 0, 8, 4, 1, 14, send_packet, &out);
    z2_stream_poll(&s, 1, 8, 5, 1, 0, send_packet, &out);
    assert(mask(&out) == 0 && out.last[3] == Z2_FLAG_BASELINE);
}
static void quick_tap(void) {
    struct z2_stream s; struct sink out = {0}; z2_stream_init(&s);
    z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out);
    out.blocked = 1;
    z2_stream_poll(&s, 1, 0, 1, 1, 1, send_packet, &out);
    z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out);
    assert(s.count == 2);
    out.blocked = 0;
    z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out);
    assert(mask(&out) == 1 && out.last[2] == 1);
    z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out);
    assert(mask(&out) == 0 && out.last[2] == 2 && s.count == 0);
}
static void overflow_and_wrap(void) {
    struct z2_stream s; struct sink out = {0}; z2_stream_init(&s);
    z2_stream_poll(&s, 1, 0, 1, 1, 0, send_packet, &out);
    out.blocked = 1;
    for (uint32_t i = 1; i <= 17; i++)
        z2_stream_poll(&s, 1, 0, 1, 1, i, send_packet, &out);
    assert(s.count == 1 && s.sequence == 1);
    out.blocked = 0;
    z2_stream_poll(&s, 1, 0, 1, 1, 17, send_packet, &out);
    assert(mask(&out) == 17 && out.last[3] == Z2_FLAG_OVERFLOW);
    for (uint32_t i = 0; i < 1024; i++) {
        z2_stream_poll(&s, 1, 0, 1, 1, i, send_packet, &out);
        assert(mask(&out) == i && out.last[2] == (uint8_t)(i + 2));
        assert(out.last[3] == 0);
    }
    /* Overflow while the initial baseline is still waiting. */
    z2_stream_init(&s); out.blocked = 1;
    for (uint32_t i = 0; i <= 16; i++)
        z2_stream_poll(&s, 1, 0, 1, 1, i, send_packet, &out);
    out.blocked = 0;
    z2_stream_poll(&s, 1, 0, 1, 1, 16, send_packet, &out);
    assert(out.last[3] == (Z2_FLAG_BASELINE | Z2_FLAG_OVERFLOW));
    assert(mask(&out) == 16 && out.last[2] == 0);
}
static void stress(void) {
    struct z2_stream s; struct sink out = {0}; z2_stream_init(&s);
    uint32_t rng = 1;
    /* Compare every accepted packet to a separate FIFO model across random
     * input changes, backpressure, wrapping, overflow and session resets. */
    uint32_t q[16], observed = 0, epoch = 0; unsigned count = 0, seq = 0, flags = 0;
    int ready = 0;
    for (unsigned i = 0; i < 100000; i++) {
        rng = rng * 1664525u + 1013904223u;
        int connected = (rng & 0x1f) != 0, subscribed = (rng & 0x3e0) != 0;
        if ((rng & 0x7ff) == 3) { epoch++; ready = 0; }
        uint32_t keys = (rng & 3) ? observed : rng;
        out.blocked = (rng & 0xf000) != 0;
        int expected = 0; uint32_t value = 0; unsigned packet_seq = seq, packet_flags = flags;
        if (!connected || !subscribed) { ready = 0; count = 0; }
        else {
            if (!ready) {
                ready = 1; q[0] = observed = keys; count = 1; seq = 0; flags = 2;
            } else if (observed != keys) {
                observed = keys;
                if (count == 16) { count = 0; flags |= 1; }
                q[count++] = keys;
            }
            if (count) {
                expected = out.blocked ? -1 : 1;
                if (!out.blocked) {
                    value = q[0]; packet_seq = seq; packet_flags = flags;
                    memmove(q, q + 1, (--count) * sizeof(q[0]));
                    seq = (seq + 1) & 255; flags = 0;
                }
            }
        }
        int actual = z2_stream_poll(&s, connected, 0, epoch, subscribed, keys, send_packet, &out);
        assert(actual == expected && s.count == count);
        if (actual == 1) assert(mask(&out) == value && out.last[2] == packet_seq && out.last[3] == packet_flags);
    }
}
int main(void) {
    basic(); retry_and_lifecycle(); quick_tap(); overflow_and_wrap(); stress();
    puts("Stream lifecycle, retries, overflow, sequence wrap and 100000 model steps passed");
}
