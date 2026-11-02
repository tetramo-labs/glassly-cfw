/* Native flash calls run on a persistent ordinary task. No custom lock is held
 * during I/O or waits. Queue lifetime is the entire boot; no timed-out borrower
 * can release a buffer still used by the worker. */
#include "flash_broker.h"
#include "flash_canary.h"
#include "flash_store_native.h"
#include "storage_diag.h"
#define P mm_graphics_native
#ifdef MM_FLASH_BROKER_TEST
extern void *mm_broker_test_function(uintptr_t);
#define FN(a,t) ((t)mm_broker_test_function(a))
#else
#define FN(a,t) ((t)(uintptr_t)(a))
#endif
#define MAGIC UINT32_C(0x46425231)
enum { START=1,READY=2,FAILED=3, READ=1,ERASE=2,PROGRAM=3 };
typedef struct {uint32_t operation,offset;void *bytes;uint32_t length;} request;
typedef struct {mm_flash_native native;void *requests,*completions;uint8_t record[116];uint32_t map_source;} broker;
typedef struct {uint32_t magic,state;broker *context;int32_t error;} registry;
_Static_assert(sizeof(registry)<=64,"Broker registry fits reserved tail");
static volatile registry *reg(void){
#ifdef MM_FLASH_BROKER_TEST
    extern void *mm_broker_test_registry(void);return mm_broker_test_registry();
#else
    return (volatile registry *)(uintptr_t)(MM_CANARY_REGISTRY+64);
#endif
}
static void *queue(unsigned size){typedef void *(*f)(uint32_t,uint32_t);return FN(0x0200ee6au,f)(1,size);}
static int send(void *q,const void *p){typedef int (*f)(void *,const void *);return FN(0x0200ee8cu,f)(q,p);}
static void receive(void *q,void *p){typedef int (*f)(void *,void *,uint32_t);while(!FN(0x0200ef7au,f)(q,p,UINT32_MAX)){} }
static void remove_queue(void *q){typedef void (*f)(void *);FN(0x0200f08cu,f)(q);}
static uint32_t le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static int acquire(broker *b){
    uint32_t n=0;int rc=glassly_storage_badmap_read(b->record,&n);
    if(rc==7 && !n){for(unsigned i=0;i<116;i++)b->record[i]=0;b->map_source=2;}
    else if(!rc && n==116 && le32(b->record)==0x474d4231u && le32(b->record+4)==1 &&
            le32(b->record+8)==0x01500000u && le32(b->record+12)==0x00300000u &&
            le32(b->record+112)==glassly_storage_badmap_crc(b->record) &&
            glassly_storage_badmap_valid(b->record+16))b->map_source=1;
    else return MM_CANARY_MAP;
    return mm_flash_native_init(&b->native,b->record+80);
}
void glassly_flash_broker_worker(void *arg){
    broker *b=arg;int result=acquire(b);
    /* Completion slot is empty: exactly one producer and one outstanding RPC.
     * This worker owns b for the boot, even if initialization fails. */
    (void)send(b->completions,&result);
    for(;;){
        request r;receive(b->requests,&r);
        if(result && !b->map_source)result=MM_CANARY_MAP;
        else if(r.operation==READ)result=mm_flash_native_read(&b->native,r.offset,r.bytes,r.length);
        else if(r.operation==ERASE)result=mm_flash_native_erase(&b->native,r.offset,r.length);
        else if(r.operation==PROGRAM)result=mm_flash_native_program(&b->native,r.offset,r.bytes,r.length);
        else result=MM_FLASH_NATIVE_ARGUMENT;
        (void)send(b->completions,&result);
    }
}
static int rpc(broker *b,unsigned op,uint32_t off,void *p,size_t n){
    if(n>UINT32_MAX)return MM_FLASH_NATIVE_RANGE;
    request r={op,off,p,(uint32_t)n};int result;
    if(!send(b->requests,&r))return MM_FLASH_NATIVE_BUSY;
    receive(b->completions,&result);return result;
}
static int read_bytes(void *b,uint32_t off,void *p,size_t n){return rpc(b,READ,off,p,n);}
static int erase_bytes(void *b,uint32_t off,size_t n){return rpc(b,ERASE,off,0,n);}
static int program_bytes(void *b,uint32_t off,const void *p,size_t n){return rpc(b,PROGRAM,off,(void *)(uintptr_t)p,n);}
int glassly_flash_broker_bind(mm_flash_callbacks *out,uint8_t unavailable[32]){
    if(!out || !unavailable || !glassly_canary_layout_valid())return -1;
    volatile registry *r=reg();broker *b=0;int start=0;
    glassly_canary_enter();
    if(!r->magic){
        volatile mm_canary_registry *c=glassly_canary_registry();
        if(c->magic || c->state){glassly_canary_leave();return -1;}
        /* Exclusively reserve the same pool against the diagnostic canary. */
        c->magic=MM_CANARY_MAGIC;c->operation=1;c->phase=MM_CANARY_ADMISSION;
        c->error=MM_FLASH_NATIVE_BUSY;c->state=MM_CANARY_FAILED;
        r->magic=MAGIC;r->state=START;start=1;
    }else if(r->magic==MAGIC && r->state==READY)b=r->context;
    glassly_canary_leave();
    if(start){
        if(P.free_bytes()<MM_CANARY_HEADROOM)goto fail;
        b=P.alloc(sizeof(*b));if(!b)goto fail;
        for(size_t i=0;i<sizeof(*b);i++)((uint8_t *)b)[i]=0;
        b->requests=queue(sizeof(request));b->completions=queue(sizeof(int));
        if(!b->requests || !b->completions)goto free_failed;
        typedef uintptr_t (*create_fn)(mm_callback,void *,uint32_t,uint32_t,const char *);
        if(!FN(0x0200f168u,create_fn)(glassly_flash_broker_entry,b,5,0x800,"glassly_flash"))goto free_failed;
        int rc;receive(b->completions,&rc);
        glassly_canary_enter();r->context=b;r->error=rc;r->state=rc?FAILED:READY;glassly_canary_leave();
        if(rc)return rc;
    }
    if(!b)return -1;
    *out=(mm_flash_callbacks){b,read_bytes,erase_bytes,program_bytes};
    for(unsigned i=0;i<32;i++)unavailable[i]=b->record[80+i];
    return 0;
free_failed:
    if(b->requests)remove_queue(b->requests);
    if(b->completions)remove_queue(b->completions);
    P.free(b);
fail:
    glassly_canary_enter();r->state=FAILED;r->error=MM_CANARY_TASK;glassly_canary_leave();return -1;
}
