#ifndef MM_LARGE_MESSAGE_H
#define MM_LARGE_MESSAGE_H
#include <stddef.h>
#include <stdint.h>
#define MM_LARGE_WIRE_MODE 127u
#define MM_LARGE_CHUNK 1024u
#define MM_LARGE_MAX 65535u
/* Single display-task owner. Incomplete records never reach a command parser.
 * Token, exact offsets and final CRC protect reconnection/replay and mixing.
 * Cleanup/lease expiry frees assembly; taking a record transfers its buffer. */
typedef struct {uint8_t *data;uint32_t token,consumed;size_t length,used;} mm_large_message;
enum {MM_LARGE_OK=0,MM_LARGE_INVALID=-1,MM_LARGE_MEMORY=-2,MM_LARGE_STALE=-3,MM_LARGE_CRC=-4,MM_LARGE_BUSY=-5,MM_LARGE_DONE=1};
int mm_large_accept(mm_large_message *,const uint8_t *,size_t,void *(*)(size_t),void (*)(void *),uint8_t **,size_t *);
void mm_large_clear(mm_large_message *,void (*)(void *));
#endif
