#include "button_stream.h"

_Static_assert(sizeof(struct z2_stream) == 80, "Review RAM reservation on layout change");
_Static_assert((Z2_QUEUE_CAPACITY & (Z2_QUEUE_CAPACITY - 1u)) == 0,
               "Queue capacity must be a power of two");

void z2_stream_init(struct z2_stream *s) {
    s->observed = s->epoch = 0;
    s->connection = 0;
    s->head = s->count = s->sequence = s->flags = s->ready = 0;
}

int z2_stream_poll(struct z2_stream *s, int connected, uint16_t connection,
                   uint32_t epoch, int subscribed, uint32_t keys,
                   z2_send_fn send, void *context) {
    uint8_t packet[Z2_PACKET_SIZE];
    uint32_t next;
    if (!connected || !subscribed) {
        s->ready = s->count = 0;
        return 0;
    }
    if (!s->ready || s->connection != connection || s->epoch != epoch) {
        s->connection = connection;
        s->epoch = epoch;
        s->head = s->sequence = 0;
        s->count = 1;
        s->queue[0] = s->observed = keys;
        s->flags = Z2_FLAG_BASELINE;
        s->ready = 1;
    } else if (s->observed != keys) {
        s->observed = keys;
        if (s->count == Z2_QUEUE_CAPACITY) {
            /* Lost edges cannot be reconstructed. Discard stale transitions,
             * then send the latest complete state with a resync marker. */
            s->head = s->count = 0;
            s->flags |= Z2_FLAG_OVERFLOW;
        }
        s->queue[(s->head + s->count) & (Z2_QUEUE_CAPACITY - 1u)] = keys;
        s->count++;
    }
    if (!s->count) return 0;
    next = s->queue[s->head];
    packet[0] = 0x47;
    packet[1] = Z2_PROTOCOL_VERSION;
    packet[2] = s->sequence;
    packet[3] = s->flags;
    packet[4] = (uint8_t)next;
    packet[5] = (uint8_t)(next >> 8);
    packet[6] = (uint8_t)(next >> 16);
    packet[7] = (uint8_t)(next >> 24);
    if (send(context, connection, packet, Z2_PACKET_SIZE)) return -1;
    s->head = (s->head + 1u) & (Z2_QUEUE_CAPACITY - 1u);
    s->count--;
    s->flags = 0;
    s->sequence++;
    return 1;
}
