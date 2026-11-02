/* Actual broker/COW/native binding with pthread queue/task and flash mocks. */
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../flash_broker.c"
typedef struct {pthread_mutex_t mutex;pthread_cond_t wake;size_t size;unsigned count;uint8_t bytes[32];} q;
static registry registry_memory;static mm_canary_registry canary;
static pthread_t thread,display;static int critical,created,failed,queue_count,fault;static unsigned flash_calls,erases,programs;
static uint8_t flash[1048576];static uint32_t free_value=1000000;
void *mm_broker_test_registry(void){return &registry_memory;}
volatile mm_canary_registry *glassly_canary_registry(void){return &canary;}
int glassly_canary_layout_valid(void){return failed!=1;}
void glassly_canary_enter(void){assert(!critical);critical=1;}
void glassly_canary_leave(void){assert(critical);critical=0;}
static void *new_queue(uint32_t count,uint32_t size){assert(!critical&&count==1&&size<=32);if(++queue_count==failed-10)return 0;q *v=calloc(1,sizeof(*v));assert(v);pthread_mutex_init(&v->mutex,0);pthread_cond_init(&v->wake,0);v->size=size;return v;}
static int send_queue(void *arg,const void *p){assert(!critical);q *v=arg;pthread_mutex_lock(&v->mutex);int ok=!v->count;if(ok){memcpy(v->bytes,p,v->size);v->count=1;pthread_cond_signal(&v->wake);}pthread_mutex_unlock(&v->mutex);return ok;}
static void unlock(void *p){pthread_mutex_unlock(p);}
static int get_queue(void *arg,void *p,uint32_t timeout){assert(!critical&&timeout==UINT32_MAX);q *v=arg;pthread_mutex_lock(&v->mutex);pthread_cleanup_push(unlock,&v->mutex);while(!v->count)pthread_cond_wait(&v->wake,&v->mutex);memcpy(p,v->bytes,v->size);v->count=0;pthread_cleanup_pop(1);return 1;}
static void delete_queue(void *arg){q *v=arg;pthread_mutex_destroy(&v->mutex);pthread_cond_destroy(&v->wake);free(v);}
static void *run_worker(void *p){glassly_flash_broker_worker(p);return 0;}
void glassly_flash_broker_entry(void *p){glassly_flash_broker_worker(p);}
static uintptr_t create_task(mm_callback fn,void *arg,uint32_t priority,uint32_t words,const char *name){assert(!critical&&fn==glassly_flash_broker_entry&&priority==5&&words==0x800&&!strcmp(name,"glassly_flash"));if(failed==2)return 0;assert(!created);created=1;assert(!pthread_create(&thread,0,run_worker,arg));return 1;}
void *mm_broker_test_function(uintptr_t a){switch(a){case 0x0200ee6a:return new_queue;case 0x0200ee8c:return send_queue;case 0x0200ef7a:return get_queue;case 0x0200f08c:return delete_queue;case 0x0200f168:return create_task;default:abort();}}
static void worker_only(void){assert(!critical&&!pthread_equal(display,pthread_self()));}
int glassly_storage_badmap_read(uint8_t *p,uint32_t *n){worker_only();(void)p;*n=0;return failed==3?8:7;}
uint32_t glassly_storage_badmap_crc(const uint8_t *p){(void)p;abort();}
int glassly_storage_badmap_valid(const uint8_t *p){(void)p;abort();}
int mm_flash_test_read(uint32_t d,uint32_t o,void *p,uint32_t n){worker_only();assert(d==1&&o>=0x700000&&o+n<=0x800000);if(++flash_calls==(unsigned)fault)return 9;memcpy(p,flash+(o-0x700000),n);return 0;}
int mm_flash_test_program(uint32_t d,uint32_t o,const void *p,uint32_t n){worker_only();assert(d==1&&n==256);if(++flash_calls==(unsigned)fault)return 9;programs++;for(unsigned i=0;i<n;i++){unsigned off=o-0x700000+i;assert((flash[off]&((const uint8_t *)p)[i])==((const uint8_t *)p)[i]);flash[off]=((const uint8_t *)p)[i];}return 0;}
int mm_flash_test_erase(uint32_t d,uint32_t o,uint32_t n){worker_only();assert(d==1&&n==4096&&o>=0x700000&&o+n<=0x800000);if(++flash_calls==(unsigned)fault)return 9;erases++;memset(flash+(o-0x700000),255,n);return 0;}
void mm_flash_test_cache(uint32_t d,uint32_t o,uint32_t n){worker_only();assert(d==0&&o>=0x05700000&&o+n<=0x05800000);}
static uint32_t free_bytes(void){return free_value;}
const mm_graphics_platform mm_graphics_native={.alloc=malloc,.free=free,.free_bytes=free_bytes};
int main(int argc,char **argv){
 display=pthread_self();failed=argc>1?atoi(argv[1]):0;if(failed==4)free_value=0;
 memset(flash,255,sizeof flash);mm_flash_callbacks io;uint8_t bad[32];int rc=glassly_flash_broker_bind(&io,bad);
 if(failed)assert(rc);else{
  assert(!rc&&created&&registry_memory.state==READY&&canary.state==MM_CANARY_FAILED);
  mm_flash_callbacks again;assert(!glassly_flash_broker_bind(&again,bad)&&again.user==io.user&&queue_count==2);
  mm_flash_store store;uint8_t scratch[4096],input[65535],output[65535];
  mm_flash_geometry geometry={0x700000,1048576,262144,4096,256};
  assert(!mm_flash_store_init(&store,&geometry,&io,bad,scratch,sizeof scratch));
  for(unsigned i=0;i<sizeof input;i++)input[i]=(uint8_t)(i*31);
  assert(!mm_flash_store_begin(&store));
  for(unsigned off=0;off<262144;){unsigned n=262144-off;if(n>sizeof input)n=sizeof input;assert(!mm_flash_store_write(&store,off,input,n));off+=n;}
  assert(!mm_flash_store_commit(&store));
  for(unsigned off=0;off<262144;){unsigned n=262144-off;if(n>sizeof output)n=sizeof output;assert(!mm_flash_store_read(&store,off,output,n));assert(!memcmp(output,input,n));off+=n;}
  assert(!mm_flash_store_begin(&store));fault=flash_calls+1;assert(mm_flash_store_write(&store,0,input,4096));assert(!mm_flash_store_abort(&store));fault=0;
  assert(!mm_flash_store_read(&store,0,output,sizeof output)&&!memcmp(output,input,sizeof input));
  printf("PASS persistent worker:262144 asset bytes,65535-byte operations, rollback/readback; %u calls,%u erases,%u programs; all driver calls off display task\n",flash_calls,erases,programs);
 }
 if(created){assert(!pthread_cancel(thread));assert(!pthread_join(thread,0));broker *b=registry_memory.context;delete_queue(b->requests);delete_queue(b->completions);free(b);}
 if(failed)printf("PASS broker failure %d; no flash mutation\n",failed);
}
