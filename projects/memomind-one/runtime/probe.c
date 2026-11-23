/* First opt-in executable extension for the exact MemoMind 1.0.3.127 profile.
 * No static writable state, startup work, display changes or owned heap.
 * See analysis/ghidra/append-hook/report.md for the stock ABI witnesses.
 */
#include <stdint.h>

typedef void (*release_fn)(void **);
typedef void *(*json_fn)(const char *);
typedef void *(*status_fn)(uint32_t, const char *);

#define RELEASE_TLVS ((release_fn)(uintptr_t)0x042eff8eu)
#define JSON_RESPONSE ((json_fn)(uintptr_t)0x042ef9f6u)
#define STATUS_RESPONSE ((status_fn)(uintptr_t)0x042ef924u)

void glassly_probe(uint32_t command, void *request,
                   const uint8_t *sequence, void **response)
{
    (void)command;
    (void)sequence;
    if (request != 0)
        RELEASE_TLVS(&request);
    void *reply = JSON_RESPONSE(
        "{\"glassly\":\"runtime-probe\",\"abi\":1,\"profile\":\"H001Y-1.0.3.127\","
        "\"entry\":\"0439bea0\",\"writableStaticBytes\":0}");
    if (reply == 0)
        reply = STATUS_RESPONSE(4, 0);
    *response = reply;
}
