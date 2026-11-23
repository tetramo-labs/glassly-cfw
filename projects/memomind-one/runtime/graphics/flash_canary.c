/* One-shot normal-task canary. No automatic retry/restore after any error.
 * Status polling never owns worker memory and cannot cancel/restart the worker. */
#include "flash_canary.h"
#include "flash_store_native.h"
#include "storage_diag.h"
#define P mm_graphics_native
typedef struct {mm_flash_native native;uint8_t bytes[256],record[116];uint32_t operation;} job;
_Static_assert(sizeof(job)<1024,"Bounded private job");
static uint32_t le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void zero(void *p,size_t n){uint8_t *b=p;while(n--)*b++=0;}
static void snapshot(mm_canary_registry *s) {
    glassly_canary_enter();volatile mm_canary_registry *r=glassly_canary_registry();
    s->magic=r->magic;s->state=r->state;s->operation=r->operation;s->phase=r->phase;
    s->error=r->error;s->native_status=r->native_status;s->map_source=r->map_source;
    s->mutation=r->mutation;s->restored=r->restored;s->neighbor=r->neighbor;
    glassly_canary_leave();
}
static int coherent(const mm_canary_registry *s) {
    if(!s->magic)return !(s->state|s->operation|s->phase|(uint32_t)s->error|(uint32_t)s->native_status|s->map_source|s->mutation|s->restored|s->neighbor);
    return s->magic==MM_CANARY_MAGIC && s->state>=1 && s->state<=4 && s->operation>=1 && s->operation<=2 && s->phase>=1 && s->phase<=8 && s->map_source<=2 && s->mutation<=1 && s->restored<=1 && s->neighbor<=1;
}
static void publish(const mm_canary_registry *s) {
    glassly_canary_enter();volatile mm_canary_registry *r=glassly_canary_registry();
    r->phase=s->phase;r->error=s->error;r->native_status=s->native_status;r->map_source=s->map_source;
    r->mutation=s->mutation;r->restored=s->restored;r->neighbor=s->neighbor;r->state=s->state;
    glassly_canary_leave();
}
static void *response(const char *s){void *p=P.json(s);return p?p:P.status(4,0);}
static char *text(char *p,const char *s){while(*s)*p++=*s++;return p;}
static char *number(char *p,uint32_t n){char d[10];unsigned k=0;do{d[k++]=(char)('0'+n%10u);n/=10u;}while(n);while(k)*p++=d[--k];return p;}
static char *signed_number(char *p,int32_t n){if(n<0){*p++='-';return number(p,0u-(uint32_t)n);}return number(p,(uint32_t)n);}
static const char invalid[]="{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"invalid\"}";
static const char wrong[]="{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"wrong-image\"}";
static const char corrupt[]="{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"registry-invalid\"}";
static const char used[]="{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"already-used\"}";
static const char nomem[]="{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"allocation-failed\"}";
static void *status_reply(void) {
    mm_canary_registry s;snapshot(&s);if(!coherent(&s))return response(corrupt);
    char *out=P.alloc(768);if(!out)return response(nomem);
    static const char *const states[]={"idle","starting","running","passed","failed"};
    char *p=text(out,"{\"glassly\":\"flash-canary\",\"abi\":1,\"result\":\"ok\",\"state\":\"");
    p=text(p,states[s.state]);p=text(p,"\",\"operation\":");p=number(p,s.operation);
    p=text(p,",\"phase\":");p=number(p,s.phase);p=text(p,",\"error\":");p=signed_number(p,s.error);
    p=text(p,",\"nativeStatus\":");p=signed_number(p,s.native_status);p=text(p,",\"mapSource\":");p=number(p,s.map_source);
    p=text(p,",\"mutationStarted\":");p=text(p,s.mutation?"true":"false");
    p=text(p,",\"restored\":");p=text(p,s.restored?"true":"false");p=text(p,",\"neighborVerified\":");p=text(p,s.neighbor?"true":"false");
    p=text(p,",\"device\":1,\"offset\":8384512,\"neighbor\":8380416,\"sectorBytes\":4096}");*p=0;
    void *r=response(out);P.free(out);return r;
}
static int all_erased(job *j,uint32_t base) {
    for(uint32_t off=0;off<4096;off+=256){
        int rc=mm_flash_native_read(&j->native,base+off,j->bytes,256);if(rc)return rc;
        for(unsigned i=0;i<256;i++)if(j->bytes[i]!=255)return MM_CANARY_NOT_ERASED;
    }return 0;
}
static int verify_program(job *j) {
    for(uint32_t off=0;off<4096;off+=256){
        int rc=mm_flash_native_read(&j->native,MM_CANARY_TARGET+off,j->bytes,256);if(rc)return rc;
        for(unsigned i=0;i<256;i++){
            uint8_t expected=off?255u:(uint8_t)((i*37u)^0xa5u);
            if(j->bytes[i]!=expected)return MM_FLASH_NATIVE_VERIFY;
        }
    }return 0;
}
static int acquire_map(job *j,mm_canary_registry *s) {
    uint32_t actual=0;int rc=glassly_storage_badmap_read(j->record,&actual);s->native_status=rc;
    if(rc==7 && actual==0){zero(j->record,116);s->map_source=2;}
    else if(rc==0 && actual==116 && le32(j->record)==0x474d4231u && le32(j->record+4)==1 &&
        le32(j->record+8)==0x01500000u && le32(j->record+12)==0x00300000u &&
        le32(j->record+112)==glassly_storage_badmap_crc(j->record) && glassly_storage_badmap_valid(j->record+16))s->map_source=1;
    else return MM_CANARY_MAP;
    if(j->record[111]&0xc0u)return MM_FLASH_NATIVE_BAD_SECTOR;
    return mm_flash_native_init(&j->native,j->record+80);
}
void glassly_flash_canary_worker(void *owned) {
    job *j=owned;mm_canary_registry s;snapshot(&s);s.state=MM_CANARY_RUNNING;s.phase=MM_CANARY_BADMAP;publish(&s);
    int rc=acquire_map(j,&s);if(rc)goto done;
    s.phase=MM_CANARY_PRECHECK;publish(&s);
    rc=all_erased(j,MM_CANARY_TARGET);if(rc)goto native_done;
    rc=all_erased(j,MM_CANARY_NEIGHBOR);if(rc)goto native_done;
    if(j->operation==1){s.neighbor=1;goto native_done;}
    s.phase=MM_CANARY_ERASE;s.mutation=1;publish(&s);
    rc=mm_flash_native_erase(&j->native,MM_CANARY_TARGET,4096);if(rc)goto native_done;
    s.phase=MM_CANARY_PROGRAM;publish(&s);
    for(unsigned i=0;i<256;i++)j->bytes[i]=(uint8_t)((i*37u)^0xa5u);
    rc=mm_flash_native_program(&j->native,MM_CANARY_TARGET,j->bytes,256);if(rc)goto native_done;
    rc=verify_program(j);if(rc)goto native_done;
    s.phase=MM_CANARY_RESTORE;publish(&s);
    rc=mm_flash_native_erase(&j->native,MM_CANARY_TARGET,4096);if(rc)goto native_done;
    s.restored=1;s.phase=MM_CANARY_NEIGHBOR_CHECK;publish(&s);
    rc=all_erased(j,MM_CANARY_NEIGHBOR);if(!rc)s.neighbor=1;
native_done:s.native_status=j->native.last_native_status;
done:s.error=rc;s.state=rc?MM_CANARY_FAILED:MM_CANARY_PASSED;if(!rc)s.phase=MM_CANARY_COMPLETE;
    /* Native trampoline frees its wrapper, not this argument. No access to j
     * after free, including when completion precedes creator return. */
    P.free(j);publish(&s);
}
void glassly_flash_canary_command(uint32_t command,void *request,const uint8_t *event,void **out) {
    (void)command;const uint8_t *p=0;size_t n=0;unsigned op=255;
    if(event && P.request_bytes(request,&p,&n) && p){if(n==1 && p[0]==0)op=0;else if(n==5 && (p[0]==1||p[0]==2) && le32(p+1)==MM_CANARY_TOKEN)op=p[0];}
    if(request)P.release(&request);
    *out=0;
    if(op==255){*out=response(invalid);return;}
    /* The uncarved image still owns this address as heap. Do not even inspect
     * registry bytes before proving the active native allocator descriptor. */
    if(!glassly_canary_layout_valid()){*out=response(wrong);return;}
    mm_canary_registry s;snapshot(&s);if(!coherent(&s)){*out=response(corrupt);return;}
    if(!op){*out=status_reply();return;}
    glassly_canary_enter();volatile mm_canary_registry *r=glassly_canary_registry();
    if(r->magic || r->state){glassly_canary_leave();*out=response(used);return;}
    r->operation=op;r->phase=MM_CANARY_ADMISSION;r->magic=MM_CANARY_MAGIC;r->state=MM_CANARY_STARTING;
    glassly_canary_leave();snapshot(&s);
    job *j=0;
    /*96KiB includes the private job, 8192 stack +124 TCB +12 wrapper, reply and
     * >64KiB margin. This is a free-space snapshot, not a contiguous reservation. */
    if(P.free_bytes()>=MM_CANARY_HEADROOM)j=P.alloc(sizeof(*j));
    if(!j){s.state=MM_CANARY_FAILED;s.error=MM_CANARY_ALLOC;publish(&s);*out=status_reply();return;}
    zero(j,sizeof(*j));j->operation=op;
    if(!glassly_canary_create(j)){P.free(j);s.state=MM_CANARY_FAILED;s.error=MM_CANARY_TASK;publish(&s);}
    /* On success j and native returned wrapper may both already be freed. */
    *out=status_reply();
}
