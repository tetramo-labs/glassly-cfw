#include "flash_canary.h"
#include "flash_store_native.h"
#include "storage_diag.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef struct {uint8_t *p;size_t n;} request;
static mm_canary_registry registry;
static unsigned critical,registry_access,allocs,frees,task_calls,read_calls,program_calls,erase_calls,cache_calls,native_calls,fail_at,releases,json_calls;
static int layout=1,early=1,create_fail,alloc_fail,json_fail,worker,kv_status,kv_length,kv_corrupt,dirty,collateral,interleave_alloc,interleave_free,preempted,erase_corrupt;
static unsigned foreign_json_calls;
static void query(void);static void start(unsigned);
static uint32_t available;
static uint8_t flash[8192],map[96];static void *pending;static char reply[1024];
int glassly_canary_layout_valid(void){return layout;}
volatile mm_canary_registry *glassly_canary_registry(void){assert(layout&&critical);registry_access++;return &registry;}
void glassly_canary_enter(void){assert(!critical);critical=1;}
void glassly_canary_leave(void){assert(critical==1);critical=0;}
static void execute_worker(void *p){assert(!worker&&!critical);worker=1;unsigned before=json_calls,foreign=foreign_json_calls;glassly_flash_canary_worker(p);assert(json_calls-before==foreign_json_calls-foreign);worker=0;}
int glassly_canary_create(void *p){assert(!critical&&!worker);task_calls++;if(create_fail)return 0;if(early)execute_worker(p);else pending=p;return 1;}
void glassly_flash_canary_entry(void *p){execute_worker(p);}
static int extract(void *p,const uint8_t **b,size_t *n){request *r=p;if(!r)return 0;*b=r->p;*n=r->n;return 1;}
static void release(void **p){request *r=*p;memset(r->p,0xdd,r->n);free(r->p);free(r);*p=0;releases++;}
static void *alloc(size_t n){assert(!critical&&!worker&&n<=1024);if(alloc_fail){alloc_fail=0;return 0;}if(interleave_alloc&&n!=768){interleave_alloc=0;query();assert(strstr(reply,"starting"));start(2);assert(strstr(reply,"already-used"));}void *p=malloc(n);assert(p);memset(p,0xa5,n);allocs++;return p;}
static void owned_free(void *p){assert(!critical&&p);free(p);frees++;if(worker&&interleave_free){interleave_free=0;worker=0;preempted=1;query();assert(strstr(reply,"running"));start(2);assert(strstr(reply,"already-used"));preempted=0;worker=1;}}
static void *json(const char *s){assert(!critical&&!worker&&strlen(s)<768);strcpy(reply,s);json_calls++;if(preempted)foreign_json_calls++;return json_fail?0:(void *)1;}
static void *status(uint32_t s,const char *p){assert(s==4&&!p);return (void *)2;}
static uint32_t free_bytes(void){assert(!critical);return available;}
const mm_graphics_platform mm_graphics_native={.request_bytes=extract,.release=release,.json=json,.status=status,.alloc=alloc,.free=owned_free,.free_bytes=free_bytes};
static int boundary(void){assert(worker&&!critical);native_calls++;return fail_at&&native_calls==fail_at;}
int mm_flash_test_read(uint32_t d,uint32_t off,void *p,uint32_t n){assert(d==1&&off>=MM_CANARY_NEIGHBOR&&off+n<=MM_CANARY_TARGET+4096&&n==256);read_calls++;if(boundary()){memset(p,0x77,n);return 19;}memcpy(p,flash+(off-MM_CANARY_NEIGHBOR),n);return 0;}
int mm_flash_test_erase(uint32_t d,uint32_t off,uint32_t n){assert(d==1&&off==MM_CANARY_TARGET&&n==4096);erase_calls++;dirty=1;if(boundary()){memset(flash+4096,0,128);return 23;}memset(flash+4096,255,4096);if(erase_corrupt)flash[4096]=0;return 0;}
int mm_flash_test_program(uint32_t d,uint32_t off,const void *p,uint32_t n){assert(d==1&&off==MM_CANARY_TARGET&&n==256);program_calls++;if(boundary())return 29;for(unsigned i=0;i<n;i++){assert(((const uint8_t *)p)[i]==(uint8_t)((i*37u)^0xa5u));assert(flash[4096+i]==255);flash[4096+i]=((const uint8_t *)p)[i];}if(collateral)flash[4352]=0;return 0;}
void mm_flash_test_cache(uint32_t d,uint32_t a,uint32_t n){assert(worker&&!critical&&d==0&&a==0x057ff000u&&(n==256||n==4096));cache_calls++;}
static void put32(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
int glassly_storage_badmap_read(uint8_t *p,uint32_t *n){assert(worker&&!critical);for(unsigned i=0;i<116;i++)assert(!p[i]);*n=(uint32_t)kv_length;if(!kv_status){put32(p,0x474d4231u);put32(p+4,1);put32(p+8,0x01500000u);put32(p+12,0x00300000u);memcpy(p+16,map,96);put32(p+112,0x12345678);if(kv_corrupt)p[kv_corrupt-1]^=1;}else memset(p,0xaa,116);return kv_status;}
uint32_t glassly_storage_badmap_crc(const uint8_t *p){(void)p;return 0x12345678;}
int glassly_storage_badmap_valid(const uint8_t *p){return !(p[0]|p[1]);}
static void reset(void){assert(!pending&&!critical&&allocs==frees);memset(&registry,0,sizeof(registry));memset(flash,255,sizeof(flash));memset(map,0,sizeof(map));registry_access=allocs=frees=task_calls=read_calls=program_calls=erase_calls=cache_calls=native_calls=fail_at=releases=json_calls=0;layout=early=1;create_fail=alloc_fail=json_fail=worker=kv_status=kv_corrupt=dirty=collateral=interleave_alloc=interleave_free=preempted=erase_corrupt=0;kv_length=116;available=512*1024;reply[0]=0;}
static void command(const uint8_t *p,size_t n){request *r=malloc(sizeof(*r));r->p=malloc(n?n:1);memcpy(r->p,p,n);r->n=n;uint8_t event=6;void *out=0;unsigned before=releases;glassly_flash_canary_command(0x7a,r,&event,&out);assert(releases>=before+1&&out&&!critical);}
static void start(unsigned op){uint8_t p[5]={(uint8_t)op};put32(p+1,MM_CANARY_TOKEN);command(p,5);}
static void query(void){uint8_t p=0;command(&p,1);}
static void finish(void){void *p=pending;pending=0;execute_worker(p);}
int main(void){
 reset();query();assert(strstr(reply,"\"idle\""));puts(reply);assert(!task_calls&&!registry.magic&&allocs==frees);
 unsigned accesses=registry_access;layout=0;query();assert(strstr(reply,"wrong-image"));assert(registry_access==accesses);layout=1;
 reset();start(1);assert(registry.state==MM_CANARY_PASSED&&registry.operation==1&&!dirty&&read_calls==32&&registry.neighbor&&!registry.restored&&registry.map_source==1);puts(reply);assert(allocs==frees);
 reset();interleave_alloc=interleave_free=1;start(2);assert(registry.state==MM_CANARY_PASSED&&task_calls==1&&!interleave_alloc&&!interleave_free&&allocs==frees);
 unsigned calls=task_calls;start(2);assert(strstr(reply,"already-used")&&task_calls==calls);
 reset();early=0;start(2);assert(pending&&registry.state==MM_CANARY_STARTING&&allocs==frees+1);puts(reply);query();start(1);assert(strstr(reply,"already-used")&&task_calls==1);finish();query();assert(registry.state==MM_CANARY_PASSED&&registry.restored&&registry.neighbor&&registry.mutation);puts(reply);for(unsigned i=0;i<8192;i++)assert(flash[i]==255);assert(allocs==frees&&program_calls==1&&erase_calls==2&&cache_calls==3);
 unsigned boundaries=native_calls;assert(boundaries==100);
 for(unsigned f=1;f<=boundaries;f++){reset();fail_at=f;start(2);assert(registry.state==MM_CANARY_FAILED&&native_calls==f&&allocs==frees);unsigned n=native_calls;start(2);assert(native_calls==n&&task_calls==1);}
 reset();erase_corrupt=1;start(2);assert(registry.error==MM_FLASH_NATIVE_VERIFY&&registry.phase==MM_CANARY_ERASE&&erase_calls==1&&!program_calls&&!registry.restored);
 for(unsigned corrupt_byte=1;corrupt_byte<=113;corrupt_byte+=4){reset();kv_corrupt=(int)corrupt_byte;if(corrupt_byte>13&&corrupt_byte<113)continue;start(2);assert(registry.error==MM_CANARY_MAP&&!native_calls);}
 reset();collateral=1;start(2);assert(registry.error==MM_FLASH_NATIVE_VERIFY&&registry.phase==MM_CANARY_PROGRAM&&erase_calls==1&&program_calls==1&&!registry.restored);
 reset();kv_status=7;kv_length=0;start(2);assert(registry.state==MM_CANARY_PASSED&&registry.map_source==2);puts(reply);
 for(unsigned bit=6;bit<8;bit++){reset();map[95]=(uint8_t)(1u<<bit);start(2);assert(registry.state==MM_CANARY_FAILED&&!native_calls&&!dirty);}
 for(unsigned off=0;off<8192;off+=255){reset();flash[off]=0;start(2);assert(registry.error==MM_CANARY_NOT_ERASED&&!dirty&&!erase_calls&&!program_calls);}
 for(unsigned reason=0;reason<5;reason++){reset();if(reason==0)kv_status=2;if(reason==1)kv_length=115;if(reason==2)kv_corrupt=1;if(reason==3){kv_status=7;kv_length=116;}if(reason==4)map[0]=1;start(2);assert(registry.error==MM_CANARY_MAP&&!native_calls&&!dirty);}
 reset();available=MM_CANARY_HEADROOM-1;start(2);assert(registry.state==MM_CANARY_FAILED&&registry.error==MM_CANARY_ALLOC&&!task_calls);puts(reply);
 reset();alloc_fail=1;start(2);assert(registry.error==MM_CANARY_ALLOC&&!task_calls&&allocs==frees);
 reset();create_fail=1;start(2);assert(registry.error==MM_CANARY_TASK&&!native_calls&&allocs==frees);puts(reply);
 reset();json_fail=1;start(2);assert(registry.state==MM_CANARY_PASSED&&allocs==frees);json_fail=0;query();assert(strstr(reply,"passed"));
 reset();registry.magic=123;start(2);assert(strstr(reply,"registry-invalid")&&!task_calls&&!native_calls);
 for(unsigned op=0;op<256;op++){if(op==1||op==2)continue;reset();start(op);assert(strstr(reply,"invalid")&&!task_calls&&!registry_access);}
 for(unsigned n=0;n<8;n++){if(n==5)continue;reset();uint8_t p[8]={2};command(p,n);assert(strstr(reply,"invalid")&&!task_calls&&!registry_access);}
 reset();uint8_t wrong[5]={2};command(wrong,5);assert(strstr(reply,"invalid")&&!registry_access);
 printf("PASS one-shot worker:100 native boundary failures; early completion, delayed completion, lifetime, map/preimage, allocator, token and registry guards; no worker egress\n");return 0;
}
