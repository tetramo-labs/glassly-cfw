#include "button_stream.h"

_Static_assert(sizeof(ag_u32) == 4 && sizeof(ag_u16) == 2 && sizeof(ag_u8) == 1,
               "Protocol requires 8/16/32-bit integer types");
_Static_assert(sizeof(struct ag_stream) == 80, "Review state allocation if layout changes");
_Static_assert((AG_QUEUE_CAPACITY & (AG_QUEUE_CAPACITY - 1u)) == 0,
               "Queue capacity must be a power of two");

void ag_stream_init(struct ag_stream *s) {
    s->observed = 0;
    s->epoch = 0;
    s->connection = 0;
    s->head = s->count = s->sequence = s->flags = s->ready = 0;
}

int ag_stream_poll(struct ag_stream *s, ag_u16 connection, ag_u32 epoch,
                   int subscribed, ag_u32 keys, ag_send_fn send, void *context) {
    ag_u8 packet[AG_PACKET_SIZE];
    ag_u32 next;
    if (!connection || !subscribed) {
        s->ready = 0;
        s->count = 0;
        return 0;
    }
    if (!s->ready || s->connection != connection || s->epoch != epoch) {
        s->connection = connection;
        s->epoch = epoch;
        s->head = 0;
        s->count = 1;
        s->queue[0] = keys;
        s->observed = keys;
        s->flags = AG_FLAG_BASELINE;
        s->ready = 1;
    } else if (s->observed != keys) {
        s->observed = keys;
        if (s->count == AG_QUEUE_CAPACITY) {
            s->head = (s->head + 1u) & (AG_QUEUE_CAPACITY - 1u);
            s->count--;
            /* A pending baseline may have been dropped: overflow requires the
             * receiver to resynchronize from the next complete state instead.
             */
            s->flags = AG_FLAG_OVERFLOW;
        }
        s->queue[(s->head + s->count) & (AG_QUEUE_CAPACITY - 1u)] = keys;
        s->count++;
    }
    if (!s->count) return 0;
    next = s->queue[s->head];
    packet[0] = 0x47;
    packet[1] = 2;
    packet[2] = s->sequence;
    packet[3] = s->flags;
    packet[4] = (ag_u8)next;
    packet[5] = (ag_u8)(next >> 8);
    packet[6] = (ag_u8)(next >> 16);
    packet[7] = (ag_u8)(next >> 24);
    if (send(context, connection, packet, sizeof packet)) return -1;
    s->head = (s->head + 1u) & (AG_QUEUE_CAPACITY - 1u);
    s->count--;
    s->flags = 0;
    s->sequence++;
    return 1;
}
