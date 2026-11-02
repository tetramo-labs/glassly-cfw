/* MIT. G2 record/ACK algorithms adapted with explicit context.
 * Source pin, platform boundaries and deliberate hardening: TRANSPORT.md. */
#include "transport.h"
static void copy(void *dst, const void *src, size_t n) {
    uint8_t *d=dst; const uint8_t *s=src; while(n--) *d++=*s++;
}
static void zero(void *dst, size_t n) { uint8_t *d=dst; while(n--) *d++=0; }
static void inflate_reset(mm_transport *ctx, mm_transport_stream *s) {
    if (s->inflater && ctx->platform.end) ctx->platform.end(ctx->platform.user,&s->inflater);
    s->inflater=0;
}
static int inflate_message(mm_transport *ctx, mm_transport_stream *s, uint8_t *out, uint32_t *size) {
    uint16_t n=s->size; const uint8_t *p=s->buffer;
    if (!ctx->platform.decode || n<4 || p[n-4] || p[n-3] || p[n-2]!=255 || p[n-1]!=255) return 0;
    uint32_t decoded=0;
    int status=ctx->platform.decode(ctx->platform.user,&s->inflater,p,n,out,(uint32_t)ctx->max_record+1u,&decoded);
    if (status || decoded>ctx->max_record) return 0;
    *size=decoded; return 1;
}
uint16_t mm_transport_crc(const uint8_t *data, uint16_t size) {
    uint16_t crc = 0xffffu;
    for (uint16_t i = 0; i < size; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000u) ? 0x1021u : 0));
    }
    return crc;
}

static void message_discard(mm_transport *ctx, mm_transport_stream *stream) {
    if (stream->buffer) ctx->platform.release(ctx->platform.user, stream->buffer);
    stream->buffer = 0;
    stream->size = stream->used = 0;
    stream->length_bytes = stream->active = 0;
}

static int message_reply(mm_transport *ctx, mm_transport_stream *stream, uint8_t here,
                             uint8_t origin, uint8_t kind, uint16_t size) {
    uint8_t reply[MM_ACK_MAX_SIZE];
    reply[0]=kind; reply[1]=stream->stream_id;
    reply[2]=(uint8_t)stream->message_id; reply[3]=(uint8_t)(stream->message_id>>8);
    reply[4]=here; reply[5]=(uint8_t)size; reply[6]=(uint8_t)(size>>8);
    reply[7]=(uint8_t)stream->checksum; reply[8]=(uint8_t)(stream->checksum>>8);
    uint16_t length = MM_ACK_SIZE;
    if (kind == MM_MESSAGE_ACK) {
        /* Explicit successes, newest first; never imply success across a gap.
         * Remember processing even if enqueueing this reply fails, so a later
         * reply can repair that loss without executing the command again. */
        unsigned count = (stream->ack_capacity - MM_ACK_SIZE) / MM_ACK_ENTRY_SIZE;
        if (count > stream->ack_count) count = stream->ack_count;
        length += count * MM_ACK_ENTRY_SIZE;
        copy(reply + MM_ACK_SIZE, stream->ack_history,
               count * MM_ACK_ENTRY_SIZE);
        for (unsigned i = MM_ACK_HISTORY - 1; i > 0; --i)
            copy(stream->ack_history[i], stream->ack_history[i - 1], MM_ACK_ENTRY_SIZE);
        copy(stream->ack_history[0], reply + 1, 3);
        copy(stream->ack_history[0] + 3, reply + 5, 4);
        if (stream->ack_count < MM_ACK_HISTORY) ++stream->ack_count;
    } else {
        stream->ack_count = 0;
    }
    return ctx->platform.send(ctx->platform.user, origin, reply, length);
}

/* A RESET may declare the link's notification capacity (scene.c); the streams
 * otherwise learn it from the request packets they see. */
void mm_transport_reply_capacity_hint(mm_transport *ctx, uint8_t capacity) {
    if (!ctx || !ctx->ready) return;
    for (uint8_t origin = MM_MESSAGE_LEFT; origin <= MM_MESSAGE_RIGHT; origin++) {
        mm_transport_stream *stream = &ctx->message_streams[origin - 1];
        if (stream && stream->reply_capacity < capacity) stream->reply_capacity = capacity;
    }
}

/* Kind-5 reply: [5][stream][ordinal LE16][lens][payload], the payload already
 * in place in stream->reply. Same route as the ACK. */
static int message_send_reply(mm_transport *ctx, mm_transport_stream *stream, uint8_t here, uint8_t origin,
                                  uint8_t length) {
    uint8_t *reply = stream->reply;
    if (length == 0 || (unsigned)length + MM_REPLY_HDR_SIZE > stream->reply_capacity) return -1;
    reply[0] = MM_MESSAGE_REPLY;
    reply[1] = stream->stream_id;
    reply[2] = (uint8_t)stream->message_id;
    reply[3] = (uint8_t)(stream->message_id >> 8);
    reply[4] = here;
    uint16_t total = (uint16_t)(MM_REPLY_HDR_SIZE + length);
    return ctx->platform.send(ctx->platform.user, origin, reply, total);
}

/* An incomplete record will never reach the decoded-CRC check. Report the
 * original attempt before discarding it, otherwise the phone waits 3.5 seconds
 * for an ACK while later messages fill its window. Only report once per abort. */
static void message_abort(mm_transport *ctx, mm_transport_stream *stream, uint8_t here, uint8_t origin) {
    if (!stream || !stream->active) return;
    message_reply(ctx, stream, here, origin, MM_MESSAGE_NACK, 0);
    inflate_reset(ctx, stream);
    stream->context_valid = 0;
    message_discard(ctx, stream);
}

static void message_consumed(mm_transport *ctx, mm_transport_stream *stream) {
    if (stream->buffer) ctx->platform.release(ctx->platform.user, stream->buffer);
    stream->buffer = 0;
    stream->size = stream->used = stream->length_bytes = 0;
    ++stream->message_id;
}

/* ACK identifies the stream and message ordinal, independent of packet splits.
 * Several messages ending in one packet must still have distinct ACKs.
 *
 * Revision 41: a record may address a subset of the stream's lenses, so a
 * frame's left and right SHOWs travel as the records of one stream and both
 * lenses apply them on the same packet arrival. A lens the record does not
 * address consumes it without inflating, running or answering it; its
 * inflate context is untouched (the phone brackets exclusive records with
 * RESET_CONTEXT). The ordinal still counts every record of the stream. */
static uint32_t message_complete(mm_transport *ctx, mm_transport_stream *stream, uint8_t here,
                                     uint8_t origin) {
    uint8_t empty = 0;
    const uint8_t *data = stream->buffer ? stream->buffer : &empty;
    uint8_t *decoded = 0;
    uint32_t size = stream->size;
    uint8_t reason = 0;
    int reply_failed = 0;
    uint8_t lenses = stream->flags & MM_MESSAGE_BOTH;
    int valid = !(stream->flags & ~(MM_MESSAGE_BOTH | MM_MESSAGE_COMPRESSED | MM_MESSAGE_RESET_CONTEXT))
        && lenses != 0 && (lenses & ~stream->options) == 0;
    if (!valid) reason = MM_NACK_FLAGS;
    if (valid && !(lenses & here)) {
        message_consumed(ctx, stream);
        return 0;
    }
    if (stream->flags & MM_MESSAGE_RESET_CONTEXT) {
        inflate_reset(ctx, stream);
        /* Also bounds history across reconnects, retries and target changes. */
        stream->ack_count = 0;
        stream->ack_capacity = stream->packet_capacity;
        stream->context_valid = 1;
    }
    if (stream->ack_capacity < stream->packet_capacity)
        stream->ack_capacity = stream->packet_capacity;
    if (valid && !stream->context_valid) { valid = 0; reason = MM_NACK_CONTEXT; }
    if (stream->flags & MM_MESSAGE_COMPRESSED) {
        decoded = ctx->platform.allocate(ctx->platform.user, (uint32_t)ctx->max_record + 1u);
        if (valid && !(decoded && inflate_message(ctx, stream, decoded, &size))) { valid = 0; reason = MM_NACK_INFLATE; }
        data = decoded;
    }
    uint16_t crc = valid ? mm_transport_crc(data, (uint16_t)size) : 0;
    if (valid && crc != stream->checksum) { valid = 0; reason = MM_NACK_CRC; }
    if (valid) {
        uint8_t reply_len = 0;
        uint8_t reply_cap = stream->reply_capacity > MM_REPLY_HDR_SIZE ?
            (uint8_t)(stream->reply_capacity - MM_REPLY_HDR_SIZE) : 0;
        if (ctx->platform.handle(ctx->platform.user, data, (uint16_t)size, crc, reply_cap,
                                 stream->reply + MM_REPLY_HDR_SIZE, &reply_len) != 0) { valid = 0; reason = MM_NACK_HANDLER; }
        else if (reply_len > reply_cap) { valid = 0; reason = MM_NACK_HANDLER; }
        else if (reply_len) reply_failed = message_send_reply(ctx, stream, here, origin, reply_len) != 0;
    }
    if (!valid) {
        ++ctx->nack_count; ctx->nack_reason = reason;
        inflate_reset(ctx, stream);
        stream->context_valid = 0; /* only an explicit record reset can recover */
    }
    int result = message_reply(ctx, stream, here, origin,
        valid ? MM_MESSAGE_ACK : MM_MESSAGE_NACK, (uint16_t)size);
    if (decoded) ctx->platform.release(ctx->platform.user, decoded);
    message_consumed(ctx, stream);
    return result == 0 && !reply_failed ? 0 : 6;
}

int mm_transport_init(mm_transport *ctx, const mm_transport_platform *p,
                      uint8_t endpoint, uint16_t max_record) {
    if (!ctx || !p || !p->allocate || !p->release || !p->send || !p->handle ||
        (!!p->decode != !!p->end) || (endpoint!=1 && endpoint!=2) || !max_record) return -1;
    /* Copy platform before clearing ctx: caller may pass &ctx->platform. */
    mm_transport_platform platform;
    copy(&platform,p,sizeof platform);
    zero(ctx,sizeof *ctx);
    copy(&ctx->platform,&platform,sizeof platform);
    ctx->endpoint=endpoint; ctx->max_record=max_record; ctx->ready=1;
    return 0;
}
void mm_transport_dispose(mm_transport *ctx) {
    if (!ctx || !ctx->ready) return;
    for (unsigned i=0;i<2;i++) {
        inflate_reset(ctx,&ctx->message_streams[i]);
        message_discard(ctx,&ctx->message_streams[i]);
    }
    zero(ctx,sizeof *ctx);
}
void mm_transport_abort(mm_transport *ctx,uint8_t origin) {
    if (!ctx || !ctx->ready || origin<1 || origin>2) return;
    message_abort(ctx,&ctx->message_streams[origin-1],ctx->endpoint,origin);
}
uint32_t mm_transport_receive(mm_transport *ctx,uint8_t origin,uint8_t sequence,
                              uint8_t flags,const uint8_t *data,uint16_t bytes,
                              uint8_t reply_capacity) {
    if (!ctx || !ctx->ready || origin<1 || origin>2) return 10;
    mm_transport_stream *s=&ctx->message_streams[origin-1];
    if ((!data && bytes) || reply_capacity<MM_ACK_SIZE ||
        (flags & ~(MM_MESSAGE_BOTH|MM_MESSAGE_RESET|MM_MESSAGE_END))) {
        mm_transport_abort(ctx,origin); return 10;
    }
    uint8_t options=flags & MM_MESSAGE_BOTH, here=ctx->endpoint;
    if (!(options & here)) return 0; /* caller delivers only selected endpoints */
    if (flags & MM_MESSAGE_RESET) {
        if (s->length_bytes) message_abort(ctx,s,here,origin);
        message_discard(ctx,s);
        s->active=1; s->next_sequence=s->stream_id=sequence;
        s->message_id=0; s->options=options; s->packet_capacity=MM_ACK_SIZE;
    }
    if (!s->active || s->next_sequence!=sequence || s->options!=options) {
        message_abort(ctx,s,here,origin); message_discard(ctx,s); return 10;
    }
    ++s->next_sequence; /* uint8 wrap is intentional. */
    if (reply_capacity>s->reply_capacity) s->reply_capacity=reply_capacity;
    if (reply_capacity>MM_ACK_MAX_SIZE) reply_capacity=MM_ACK_MAX_SIZE;
    if (reply_capacity>s->packet_capacity) s->packet_capacity=reply_capacity;
    uint32_t status=0;
    uint16_t cursor=0;
    while (cursor<bytes) {
        if (s->length_bytes<5) {
            uint8_t byte=data[cursor++];
            switch(s->length_bytes++) {
            case 0:s->flags=byte;break;
            case 1:s->size=byte;break;
            case 2:s->size|=(uint16_t)byte<<8;break;
            case 3:s->checksum=byte;break;
            case 4:s->checksum|=(uint16_t)byte<<8;break;
            }
            if (s->length_bytes<5) continue;
            if (s->size>ctx->max_record) {
                ++ctx->nack_count; ctx->nack_reason=MM_NACK_LIMIT;
                message_abort(ctx,s,here,origin); return 6;
            }
            if (s->size) {
                s->buffer=ctx->platform.allocate(ctx->platform.user,s->size);
                if (!s->buffer) {message_abort(ctx,s,here,origin);return 6;}
            }
        }
        uint16_t count=s->size-s->used;
        if (count>bytes-cursor) count=bytes-cursor;
        if (count) copy(s->buffer+s->used,data+cursor,count);
        s->used+=count; cursor+=count;
        if (s->used==s->size) {
            uint32_t result=message_complete(ctx,s,here,origin);
            if (result) status=result;
        }
    }
    if (flags & MM_MESSAGE_END) {
        if (s->length_bytes) {message_abort(ctx,s,here,origin);status=11;}
        message_discard(ctx,s);
    }
    return status;
}
