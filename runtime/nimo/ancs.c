/* Notification relay for the stock ANCS client (GLASSLYCFW/10). The stock
 * 1.1.5.1 application fetches each iOS notification into its record at
 * 0x02084328, applies its app whitelist and hands a ten-word intake struct to
 * ancs_intake (0x0428c846), which queues the stock popup. While the phone
 * holds the 90 s lease it renews with 0x7E/0x27, the intake call is diverted
 * here and the notification goes to the phone as 0x7E/0x28 records in the G2
 * relay's format, which the phone decodes with its existing code; the
 * whitelist answers "allowed" under the lease so the phone's own filter
 * decides. Without a lease the stock behaviour is untouched. Runs on the
 * stock ANCS task: no heap, no UI calls. MIT. */
#include "glassly.h"

#define ANCS_LEASE_MS 90000u
#define ANCS_CHUNK 128u
#define ANCS_SHORT_FIELD 64u
#define ANCS_MESSAGE_FIELD 260u
#define ANCS_HEAD 5u /* status, 'A', 'N', version, kind */
enum { ANCS_OP_ENABLE = 1, ANCS_OP_DISABLE = 2, ANCS_OP_QUERY = 3, ANCS_OP_ACTION = 4, ANCS_OP_RENEW = 5 };
enum { ANCS_SOURCE = 1, ANCS_ATTR = 2, ANCS_APP = 3, ANCS_STATUS = 4 };
/* The stock intake struct: ten words. */
enum { INTAKE_UID, INTAKE_CATEGORY, INTAKE_ZERO, INTAKE_APP, INTAKE_TITLE, INTAKE_SUBTITLE, INTAKE_MESSAGE,
       INTAKE_ZERO2, INTAKE_ZERO3, INTAKE_DATE };

static int leased(const nimo_ram *ram, uint32_t now)
{
    return ram->ancs_lease_until != 0 && (int32_t)(ram->ancs_lease_until - now) > 0;
}

int glassly_ancs_leased(void)
{
    nimo_ram *ram = NIMO_RAM;
    if (!leased(ram, nimo_now_ms())) return 0;
    ram->ancs_allowed++;
    return 1;
}

static uint32_t text_length(const char *text, uint32_t max)
{
    uint32_t n = 0;
    if (text == 0) return 0;
    while (n < max && text[n] != 0) n++;
    return n;
}

static void put16(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void record(nimo_ram *ram, uint32_t kind, const uint8_t *body, uint32_t n)
{
    uint8_t out[ANCS_HEAD + 9 + ANCS_CHUNK];
    out[0] = STATUS_OK;
    out[1] = 'A';
    out[2] = 'N';
    out[3] = 1;
    out[4] = (uint8_t)kind;
    for (uint32_t i = 0; i < n; i++) out[ANCS_HEAD + i] = body[i];
    int rc = nimo_is_master()
        ? nimo_send_response(GLASSLY_CMD, KEY_ANCS_RECORD, out, ANCS_HEAD + n)
        : nimo_peer_ui(NIMO_MSG_ANCS_RELAY, out, ANCS_HEAD + n);
    if (rc == 0) ram->ancs_sent++;
    else { ram->ancs_send_errors++; ram->ancs_drops++; }
}

/* ATTR [uid u32][attr][total u16][offset u16][chunk]; an absent attribute is
 * one record with total 0, which completes it on the phone. */
static void attribute(nimo_ram *ram, uint32_t uid, uint32_t attr, const char *text, uint32_t max)
{
    uint8_t body[9 + ANCS_CHUNK];
    uint32_t total = text_length(text, max);
    uint32_t offset = 0;
    do {
        uint32_t chunk = total - offset < ANCS_CHUNK ? total - offset : ANCS_CHUNK;
        body[0] = (uint8_t)uid;
        body[1] = (uint8_t)(uid >> 8);
        body[2] = (uint8_t)(uid >> 16);
        body[3] = (uint8_t)(uid >> 24);
        body[4] = (uint8_t)attr;
        put16(body + 5, total);
        put16(body + 7, offset);
        for (uint32_t i = 0; i < chunk; i++) body[9 + i] = (uint8_t)text[offset + i];
        record(ram, ANCS_ATTR, body, 9 + chunk);
        offset += chunk;
    } while (offset < total);
}

int glassly_ancs_intake(const uintptr_t *intake)
{
    nimo_ram *ram = NIMO_RAM;
    if (intake == 0) return 0;
    ram->ancs_notifications++;
    if (!leased(ram, nimo_now_ms())) {
        ram->ancs_drops++;
        return 0;
    }
    uint8_t errors = ram->ancs_send_errors;
    uint32_t uid = (uint32_t)intake[INTAKE_UID];
    uint8_t source[8] = { 0, 0, (uint8_t)intake[INTAKE_CATEGORY], 0, (uint8_t)uid, (uint8_t)(uid >> 8),
                          (uint8_t)(uid >> 16), (uint8_t)(uid >> 24) };
    record(ram, ANCS_SOURCE, source, sizeof source);
    attribute(ram, uid, 0, (const char *)intake[INTAKE_APP], ANCS_SHORT_FIELD);
    attribute(ram, uid, 1, (const char *)intake[INTAKE_TITLE], ANCS_SHORT_FIELD);
    attribute(ram, uid, 2, (const char *)intake[INTAKE_SUBTITLE], ANCS_SHORT_FIELD);
    attribute(ram, uid, 3, (const char *)intake[INTAKE_MESSAGE], ANCS_MESSAGE_FIELD);
    attribute(ram, uid, 4, 0, 0);
    attribute(ram, uid, 5, (const char *)intake[INTAKE_DATE], ANCS_SHORT_FIELD);
    attribute(ram, uid, 6, 0, 0);
    attribute(ram, uid, 7, 0, 0);
    return errors == ram->ancs_send_errors;
}

/* [op] -> [status]['A','N',1,4][enabled][side][drops u16][sent u16][send errors]:
 * ENABLE arms or extends the lease, RENEW extends a live one, DISABLE drops it,
 * QUERY only answers; ACTION is refused. */
uint32_t glassly_ancs_control(const uint8_t *payload, uint32_t len, uint8_t *reply)
{
    nimo_ram *ram = NIMO_RAM;
    uint32_t now = nimo_now_ms();
    if (len != 1) {
        reply[0] = STATUS_INVALID;
        return 1;
    }
    uint32_t op = payload[0];
    if (op < ANCS_OP_ENABLE || op > ANCS_OP_RENEW || op == ANCS_OP_ACTION) {
        reply[0] = STATUS_UNSUPPORTED;
        return 1;
    }
    if (op == ANCS_OP_ENABLE || (op == ANCS_OP_RENEW && leased(ram, now))) {
        ram->ancs_lease_until = now + ANCS_LEASE_MS;
        if (ram->ancs_lease_until == 0) ram->ancs_lease_until = 1;
    } else if (op == ANCS_OP_DISABLE) {
        ram->ancs_lease_until = 0;
    }
    reply[0] = STATUS_OK;
    reply[1] = 'A';
    reply[2] = 'N';
    reply[3] = 1;
    reply[4] = ANCS_STATUS;
    reply[5] = (uint8_t)leased(ram, now);
    reply[6] = nimo_is_master() ? 1 : 2;
    put16(reply + 7, ram->ancs_drops);
    put16(reply + 9, ram->ancs_sent);
    reply[11] = ram->ancs_send_errors;
    return 12;
}

int glassly_ancs_forwarded(const uint8_t *data, uint32_t len)
{
    nimo_ram *ram = NIMO_RAM;
    if (!nimo_is_master() || !leased(ram, nimo_now_ms())) return 1;
    if (data == 0 || len < ANCS_HEAD || len > ANCS_HEAD + 9u + ANCS_CHUNK ||
        data[0] != STATUS_OK || data[1] != 'A' || data[2] != 'N' || data[3] != 1 ||
        (data[4] != ANCS_SOURCE && data[4] != ANCS_ATTR)) return 1;
    if (nimo_send_response(GLASSLY_CMD, KEY_ANCS_RECORD, data, len) == 0) ram->ancs_sent++;
    else { ram->ancs_send_errors++; ram->ancs_drops++; }
    return 1;
}
