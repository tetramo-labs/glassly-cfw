/* MIT. Record parser is upstream-derived; inflater retains its zlib license. */
#include "record_session.h"
#include "transport.h"
#include "inflater.h"
#define JSON_BYTES 6144u
struct mm_record_session {
    mm_transport transport;
    mm_record_platform platform;
    size_t live,used;
    unsigned frames;
    uint8_t event,processing,closing,overflow;
    char json[JSON_BYTES];
};
typedef struct {size_t bytes;} allocation;
static void *allocate(void *user,size_t n){
    mm_record_session *s=user;
    if(n>MM_RECORD_BUDGET-sizeof(allocation))return 0;
    n+=sizeof(allocation);
    if(s->live>MM_RECORD_BUDGET-n || s->platform.free_bytes()<MM_RECORD_HEADROOM+n)return 0;
    allocation *a=s->platform.allocate(n);if(!a)return 0;
    a->bytes=n;s->live+=n;return a+1;
}
static void release(void *user,void *p){
    if(!p)return;
    mm_record_session *s=user;allocation *a=(allocation *)p-1;
    s->live-=a->bytes;s->platform.release(a);
}
static int decode(void *user,void **state,const uint8_t *p,uint16_t n,uint8_t *out,uint32_t cap,uint32_t *used){
    mm_inflater_allocator a={user,allocate,release};
    return mm_inflater_decode(&a,state,p,n,out,cap,used);
}
static void end(void *user,void **state){(void)user;mm_inflater_end(state);}
static void text(mm_record_session *s,const char *p){
    while(*p){if(s->used+1>=JSON_BYTES){s->overflow=1;return;}s->json[s->used++]=*p++;}
}
static void number(mm_record_session *s,uint32_t n){
    char digits[10];unsigned count=0;
    do{digits[count++]=(char)('0'+n%10);n/=10;}while(n);
    while(count){char one[2]={digits[--count],0};text(s,one);}
}
static int send(void *user,uint8_t origin,const uint8_t *p,uint16_t n){
    mm_record_session *s=user;
    if(origin!=1 || !n || n>MM_RECORD_REPLY_CAPACITY || s->used+2u*n+128u>=JSON_BYTES){s->overflow=1;return -1;}
    if(s->frames++)text(s,",");
    text(s,"\"");
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<n;i++){s->json[s->used++]=hex[p[i]>>4];s->json[s->used++]=hex[p[i]&15];}
    text(s,"\"");return 0;
}
static int handle(void *user,const uint8_t *p,uint16_t n,uint16_t crc,uint8_t cap,uint8_t *reply,uint8_t *count){
    (void)crc;mm_record_session *s=user;
    if(s->closing || s->overflow || !n || p[0]==MM_RECORD_MODE || p[0]==127)return -1;
    return s->platform.dispatch(s->event,p,n,cap,reply,count);
}
int mm_record_valid(const uint8_t *p,size_t n){
    return p && n>=4 && n<=4+MM_RECORD_PACKET_BYTES && p[0]==MM_RECORD_MODE && p[1]==1 &&
        !(p[3]&~(MM_MESSAGE_RESET|MM_MESSAGE_END|MM_MESSAGE_BOTH)) && (p[3]&MM_MESSAGE_LEFT);
}
mm_record_session *mm_record_create(const mm_record_platform *p){
    if(!p || !p->allocate || !p->release || !p->free_bytes || !p->dispatch ||
       p->free_bytes()<MM_RECORD_HEADROOM+sizeof(mm_record_session))return 0;
    mm_record_session *s=p->allocate(sizeof(*s));if(!s)return 0;
    for(size_t i=0;i<sizeof(*s);i++)((uint8_t *)s)[i]=0;
    s->platform=*p;s->live=sizeof(*s);
    mm_transport_platform t={s,allocate,release,send,handle,decode,end};
    if(mm_transport_init(&s->transport,&t,1,65535)){p->release(s);return 0;}
    return s;
}
void mm_record_close(mm_record_session *s){
    if(!s)return;
    if(s->processing){s->closing=1;return;}
    mm_transport_dispose(&s->transport);s->platform.release(s);
}
const char *mm_record_process(mm_record_session *s,uint8_t event,const uint8_t *p,size_t n){
    if(!s || s->processing || s->closing || !mm_record_valid(p,n))return 0;
    s->processing=1;s->event=event;s->used=0;s->frames=0;s->overflow=0;
    text(s,"{\"glassly\":\"record-transport\",\"abi\":1,\"frames\":[");
    uint32_t rc=mm_transport_receive(&s->transport,1,p[2],p[3],p+4,(uint16_t)(n-4),MM_RECORD_REPLY_CAPACITY);
    text(s,"],\"status\":");number(s,rc);text(s,",\"nackReason\":");number(s,s->transport.nack_reason);
    text(s,",\"ownedBytes\":");number(s,(uint32_t)s->live);
    text(s,",\"closing\":");number(s,s->closing);text(s,"}");s->json[s->used]=0;
    return s->overflow?0:s->json;
}
void mm_record_finish(mm_record_session *s){
    if(!s || !s->processing)return;
    s->processing=0;if(s->closing)mm_record_close(s);
}
