/* MIT. Derived from G2 message_transport.c at
 * 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce. See TRANSPORT.md and LICENSE. */
#ifndef MM_TRANSPORT_H
#define MM_TRANSPORT_H
#include <stdint.h>
#include <stddef.h>
#define MM_MESSAGE_LEFT 1u /* logical endpoint bits; no physical topology implied */
#define MM_MESSAGE_RIGHT 2u
#define MM_MESSAGE_BOTH 3u
#define MM_MESSAGE_ACK 1u
#define MM_MESSAGE_NACK 3u
#define MM_MESSAGE_REPLY 5u
#define MM_MESSAGE_COMPRESSED 4u
#define MM_MESSAGE_RESET_CONTEXT 8u
#define MM_MESSAGE_MAX 65535u
#define MM_MESSAGE_RESET 0x80u
#define MM_MESSAGE_END 0x40u
#define MM_ACK_HISTORY 3u
#define MM_ACK_ENTRY_SIZE 7u
#define MM_ACK_SIZE 9u
#define MM_ACK_MAX_SIZE 30u
#define MM_REPLY_HDR_SIZE 5u
#define MM_REPLY_MAX_SIZE 255u
#define MM_NACK_FLAGS 1u
#define MM_NACK_CONTEXT 2u
#define MM_NACK_INFLATE 3u
#define MM_NACK_CRC 4u
#define MM_NACK_HANDLER 5u
#define MM_NACK_LIMIT 6u /* adapter extension: configured record bound exceeded */
typedef struct {
    uint8_t *buffer;
    void *inflater;
    uint16_t size, used, message_id, checksum;
    uint8_t length_bytes, active, next_sequence, stream_id, options;
    uint8_t flags, context_valid;
    uint8_t ack_count, ack_capacity, packet_capacity;
    uint8_t reply_capacity;
    uint8_t ack_history[MM_ACK_HISTORY][MM_ACK_ENTRY_SIZE];
    uint8_t reply[MM_REPLY_MAX_SIZE];
} mm_transport_stream;
typedef struct {
    void *user;
    void *(*allocate)(void *user, size_t bytes);
    void (*release)(void *user, void *ptr);
    /* Synchronous borrowed data; copy before return if queued. No reentry. */
    int (*send)(void *user, uint8_t origin, const uint8_t *reply, uint16_t bytes);
    int (*handle)(void *user, const uint8_t *data, uint16_t bytes, uint16_t crc,
                  uint8_t reply_capacity, uint8_t *reply, uint8_t *reply_bytes);
    /* Optional RFC1950 streaming decoder. Own *state, retain across records,
     * consume all input, output <= capacity, clear borrowed pointers on return.
     * Return0 on success, nonzero on failure; never accept Z_FINISH. Core also
     * requires SYNC_FLUSH suffix and supplies max_record+1 overflow byte.
     * end must dispose state even after a failed decode and set *state=NULL. */
    int (*decode)(void *user, void **state, const uint8_t *input, uint16_t bytes,
                  uint8_t *output, uint32_t capacity, uint32_t *output_bytes);
    void (*end)(void *user, void **state);
} mm_transport_platform;
typedef struct {
    mm_transport_platform platform;
    mm_transport_stream message_streams[2]; /* caller-designated origin 1/2 */
    uint32_t nack_count;
    uint16_t max_record;
    uint8_t nack_reason, endpoint, ready;
} mm_transport;
/* Zero/unused context only. Caller serializes ALL calls including teardown;
 * callback reentry and concurrent access are forbidden. Context/platform and
 * supplied packet bytes must remain stable and not overlap owned parser data.
 * max_record1..65535 is a policy bound on wire AND decoded record bytes.
 * Reinit a live context is invalid: dispose first. No writable globals. */
int mm_transport_init(mm_transport *, const mm_transport_platform *, uint8_t endpoint, uint16_t max_record);
void mm_transport_dispose(mm_transport *);
/* Packet outer validation/routing belongs to adapter. Deliver each selected
 * logical endpoint the identical flags/sequence/bytes in order. Return0,
 * resource/send/handler contract error6, framing/sequence10, or truncation11.
 * A NACK can be emitted with return0 (record rejected, reply sent successfully).
 * reply_capacity is verified adapter capacity INCLUDING reply envelope9/5B;
 * minimum ACK capacity9 is required, maximum255. No transport inference here. */
uint32_t mm_transport_receive(mm_transport *, uint8_t origin, uint8_t sequence,
                              uint8_t flags, const uint8_t *, uint16_t bytes,
                              uint8_t reply_capacity);
/* Outer packet failure: abort that origin's active stream, NACK partial attempt. */
void mm_transport_abort(mm_transport *, uint8_t origin);
void mm_transport_reply_capacity_hint(mm_transport *, uint8_t capacity);
uint16_t mm_transport_crc(const uint8_t *, uint16_t bytes);
#endif
