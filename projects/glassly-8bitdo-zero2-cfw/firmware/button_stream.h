#ifndef ZERO2_BUTTON_STREAM_H
#define ZERO2_BUTTON_STREAM_H

#include <stdint.h>

#define Z2_QUEUE_CAPACITY 16u
#define Z2_PACKET_SIZE 8u
#define Z2_PROTOCOL_VERSION 3u
#define Z2_FLAG_OVERFLOW 1u
#define Z2_FLAG_BASELINE 2u

/* Unbound firmware component. No Zero 2 addresses, radio commands or GPIO
 * assignments are implied by this API. Keys are an opaque 32-bit snapshot. */
struct z2_stream {
    uint32_t queue[Z2_QUEUE_CAPACITY];
    uint32_t observed, epoch;
    uint16_t connection;
    uint8_t head, count, sequence, flags, ready;
};

/* Zero = copied/accepted, nonzero = retry. Must copy before returning, must
 * not reenter the stream, and must recheck the same session/CCC under the
 * firmware's serialization mechanism before submitting to the radio. */
typedef int (*z2_send_fn)(void *context, uint16_t connection,
                          const uint8_t *packet, uint16_t length);

void z2_stream_init(struct z2_stream *stream);
/* Single task owns stream. Caller supplies coherent connection, epoch, CCC
 * and debounced key state on every poll, including when keys are unchanged.
 * Advance epoch on every connect/disconnect and CCC transition; handle reuse
 * alone cannot distinguish sessions. Connection handle zero is valid.
 * Returns 1 accepted, 0 idle, -1 retry. No sleeps, allocation or hardware I/O. */
int z2_stream_poll(struct z2_stream *stream, int connected, uint16_t connection,
                   uint32_t epoch, int subscribed, uint32_t keys,
                   z2_send_fn send, void *context);
#endif
