#include "button_input.h"
#include "button_stream.h"
#include <assert.h>
#include <stdio.h>

static uint32_t expand(unsigned combination) {
    static const unsigned bits[] = {0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};
    uint32_t mask = 0;
    for (unsigned i = 0; i < 12; ++i)
        if (combination & (1u << i)) mask |= UINT32_C(1) << bits[i];
    return mask;
}

static void combinations(void) {
    struct z2_input s;
    for (unsigned combination = 0; combination < 4096; ++combination) {
        uint32_t mask = expand(combination);
        z2_input_reset(&s);
        assert(z2_input_poll(&s, mask, 100) == 0);
        assert(z2_input_poll(&s, mask, 107) == 0);
        assert(z2_input_poll(&s, mask, 108) == mask);
        assert(z2_input_poll(&s, mask, 200) == mask);
        assert(z2_input_poll(&s, 0, 201) == mask);
        assert(z2_input_poll(&s, 0, 208) == mask);
        assert(z2_input_poll(&s, 0, 209) == 0);
    }
}

static void bounce_and_independence(void) {
    struct z2_input s;
    z2_input_reset(&s);
    assert(z2_input_poll(&s, 1, 0) == 0);
    assert(z2_input_poll(&s, 0, 7) == 0); /* short pulse */
    assert(z2_input_poll(&s, 0, 15) == 0);
    for (uint32_t t = 20; t < 40; ++t) {
        uint32_t raw = 1u | ((t & 1u) ? 8u : 0u);
        assert(z2_input_poll(&s, raw, t) == (t >= 28 ? 1u : 0u));
    }
    assert(z2_input_poll(&s, 9, 40) == 1);
    assert(z2_input_poll(&s, 9, 47) == 9);
    assert(z2_input_poll(&s, 8, 48) == 9);
    assert(z2_input_poll(&s, 9, 55) == 9); /* release bounce */
    assert(z2_input_poll(&s, 9, 63) == 9);
    assert(z2_input_poll(&s, ~Z2_INPUT_MASK, 64) == 9);
    assert(z2_input_poll(&s, ~Z2_INPUT_MASK, 72) == 0);
}

static void clock_wrap_and_reset(void) {
    struct z2_input s;
    z2_input_reset(&s);
    assert(z2_input_poll(&s, 1, UINT32_MAX - 4) == 0);
    assert(z2_input_poll(&s, 1, 2) == 0);
    assert(z2_input_poll(&s, 1, 3) == 1);
    z2_input_reset(&s); /* resume/clock reset must not inherit pending state */
    assert(z2_input_poll(&s, 1, 0) == 0);
    assert(z2_input_poll(&s, 1, 8) == 1);
}

struct sink { int blocked; unsigned count; uint32_t masks[4]; uint8_t sequence[4]; };
static int send_packet(void *context, uint16_t connection, const uint8_t *p, uint16_t length) {
    struct sink *sink = context;
    assert(connection == 0 && length == Z2_PACKET_SIZE);
    if (sink->blocked) return 1;
    assert(sink->count < 4);
    sink->masks[sink->count] = p[4] | (uint32_t)p[5] << 8 | (uint32_t)p[6] << 16 | (uint32_t)p[7] << 24;
    sink->sequence[sink->count++] = p[2];
    return 0;
}

static void stream_integration(void) {
    struct z2_input input;
    struct z2_stream stream;
    struct sink sink = {0};
    z2_input_reset(&input);
    z2_stream_init(&stream);
    for (uint32_t t = 0; t <= 31; ++t) {
        /* Qualified press/release while radio is blocked; chatter is filtered. */
        uint32_t raw = (t >= 2 && t < 14) ? 1 : 0;
        if (t == 1 || t == 15) raw = 1;
        if (t == 1) sink.blocked = 1;
        if (t == 29) sink.blocked = 0;
        uint32_t keys = z2_input_poll(&input, raw, t);
        z2_stream_poll(&stream, 1, 0, 1, 1, keys, send_packet, &sink);
    }
    assert(sink.count == 3);
    assert(sink.masks[0] == 0 && sink.masks[1] == 1 && sink.masks[2] == 0);
    assert(sink.sequence[0] == 0 && sink.sequence[1] == 1 && sink.sequence[2] == 2);
}

int main(void) {
    combinations();
    bounce_and_independence();
    clock_wrap_and_reset();
    stream_integration();
    puts("Input debounce: 4096 combinations, independent bounce, clock wrap, reset and queued press/release passed");
}
