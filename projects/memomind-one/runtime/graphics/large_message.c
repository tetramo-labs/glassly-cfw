#include "large_message.h"
static uint16_t u16(const uint8_t *p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t u32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint32_t crc(const uint8_t *p,size_t n){uint32_t c=UINT32_MAX;while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;}
void mm_large_clear(mm_large_message *s,void (*release)(void *)){
    if(s->data)release(s->data);
    s->data=0;s->length=s->used=0;s->token=0;
}
int mm_large_accept(mm_large_message *s,const uint8_t *p,size_t n,void *(*alloc)(size_t),void (*release)(void *),uint8_t **out,size_t *length){
    *out=0;*length=0;
    if(!p || n<6 || p[0]!=MM_LARGE_WIRE_MODE)return MM_LARGE_INVALID;
    uint32_t token=u32(p+2);if(!token)return MM_LARGE_INVALID;
    if(!p[1]){
        if(n!=8 || !u16(p+6))return MM_LARGE_INVALID;
        if(token==s->consumed)return MM_LARGE_STALE;
        if(s->data)return s->token==token && s->length==u16(p+6)?MM_LARGE_OK:MM_LARGE_BUSY;
        uint8_t *data=alloc(u16(p+6));if(!data)return MM_LARGE_MEMORY;
        s->data=data;s->token=token;s->length=u16(p+6);s->used=0;return MM_LARGE_OK;
    }
    if(!s->data || token!=s->token)return MM_LARGE_STALE;
    if(p[1]==1){
        if(n<=8 || n>8+MM_LARGE_CHUNK)return MM_LARGE_INVALID;
        size_t offset=u16(p+6),bytes=n-8;
        if(offset>s->used || bytes>s->length-offset)return MM_LARGE_INVALID;
        if(offset<s->used){
            if(bytes>s->used-offset)return MM_LARGE_INVALID;
            for(size_t i=0;i<bytes;i++)if(s->data[offset+i]!=p[8+i])return MM_LARGE_INVALID;
            return MM_LARGE_OK;
        }
        for(size_t i=0;i<bytes;i++)s->data[offset+i]=p[8+i];
        s->used+=bytes;return MM_LARGE_OK;
    }
    if(p[1]==2){
        if(n!=10 || s->used!=s->length)return MM_LARGE_INVALID;
        if(crc(s->data,s->length)!=u32(p+6))return MM_LARGE_CRC;
        *out=s->data;*length=s->length;s->consumed=s->token;
        s->data=0;s->token=0;s->used=s->length=0;return MM_LARGE_DONE;
    }
    if(p[1]==3 && n==6){mm_large_clear(s,release);return MM_LARGE_OK;}
    return MM_LARGE_INVALID;
}
