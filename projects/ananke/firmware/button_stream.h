#ifndef ANANKE_BUTTON_STREAM_H
#define ANANKE_BUTTON_STREAM_H

/* Proposed custom protocol v2, NOT a claim about any stock BLE packet.
 * 0: 'G'; 1: 2; 2: sequence; 3: flags; 4..7: raw key mask, little endian.
 * Bit 0 of flags means dropped transitions; bit 1 marks a new-session snapshot.
 * Physical key names are deliberately outside this transport component.
 */
typedef unsigned char ag_u8;
typedef unsigned short ag_u16;
typedef unsigned int ag_u32;
#define AG_QUEUE_CAPACITY 16u
#define AG_PACKET_SIZE 8u
#define AG_FLAG_OVERFLOW 1u
#define AG_FLAG_BASELINE 2u

struct ag_stream {
    ag_u32 queue[AG_QUEUE_CAPACITY];
    ag_u32 observed;
    ag_u32 epoch;
    ag_u16 connection;
    ag_u8 head, count, sequence, flags, ready;
};

/* Must copy packet before returning; zero means accepted, nonzero means retry.
 * No actual firmware addresses or handles are bound by this interface.
 */
typedef int (*ag_send_fn)(void *context, ag_u16 connection, const ag_u8 *packet, ag_u16 length);

void ag_stream_init(struct ag_stream *stream);
/* Caller supplies a coherent connection/subscription/epoch/key snapshot and
 * invokes only from the chosen input task. CCC/disconnect callbacks must only
 * advance the epoch. This queue itself has a single owner.
 * Returns 1 on accepted packet, 0 if idle/unsubscribed, -1 for backpressure.
 */
int ag_stream_poll(struct ag_stream *stream, ag_u16 connection, ag_u32 epoch,
                   int subscribed, ag_u32 keys, ag_send_fn send, void *context);

#endif
