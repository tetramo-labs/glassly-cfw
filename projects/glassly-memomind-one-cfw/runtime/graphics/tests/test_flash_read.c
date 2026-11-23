#include "flash_read.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {uint8_t *data;size_t length;int valid;} request;
#ifdef MM_FULL_STORE_READ
/* These diagnostic serializers are tested separately with actual RV32 code.
 * The exhaustive flash-range host test must never dispatch either one. */
int mm_storage_topology_json(char *p,size_t n){(void)p;(void)n;abort();}
int mm_storage_badmap_json(char *p,size_t n,uint8_t *b){(void)p;(void)n;(void)b;abort();}
#endif
static char copied[1024];static void *workspace;
static unsigned released,allocated,freed,read_calls,json_calls,status_calls;
static int fail_alloc,fail_json,fail_status,native_result;
static uint32_t available=0x80000,expect_device,expect_offset,expect_length;
static int extract(void *p,const uint8_t **b,size_t *n){request *r=p;if(!r||!r->valid)return 0;*b=r->data;*n=r->length;return 1;}
static void release(void **p){assert(p&&*p);request *r=*p;memset(r->data,0xdd,r->length);free(r->data);free(r);*p=0;released++;}
static void *json(const char *text){json_calls++;assert(strlen(text)<sizeof(copied));strcpy(copied,text);return fail_json?0:(void *)1;}
static void *status(uint32_t value,const char *text){assert(value==4&&!text);status_calls++;return fail_status?0:(void *)2;}
static void *alloc(size_t size){assert(released==1&&size==1024&&!workspace);allocated++;if(fail_alloc)return 0;workspace=malloc(size);assert(workspace);memset(workspace,0xa5,size);return workspace;}
static void free_workspace(void *p){assert(p==workspace&&p);memset(p,0xdd,1024);free(p);workspace=0;freed++;}
static uint32_t free_bytes(void){assert(released==1);return available;}
const mm_graphics_platform mm_graphics_native={.request_bytes=extract,.release=release,.json=json,.status=status,.alloc=alloc,.free=free_workspace,.free_bytes=free_bytes};
int glassly_flash_read_native(uint32_t device,uint32_t offset,void *destination,uint32_t length){
 assert(released==1&&allocated==1&&freed==0&&destination==workspace);
 assert(device==expect_device&&offset==expect_offset&&length==expect_length);read_calls++;
 for(unsigned i=0;i<256;i++)assert(((uint8_t *)destination)[i]==0);
 for(unsigned i=0;i<length;i++)((uint8_t *)destination)[i]=(uint8_t)(offset+i+device*17u);
 return native_result;
}
static void reset(void){assert(!workspace);released=allocated=freed=read_calls=json_calls=status_calls=0;copied[0]=0;fail_alloc=fail_json=fail_status=native_result=0;available=0x80000;}
static void *invoke(const uint8_t *bytes,size_t n,int valid,int event){
 request *r=malloc(sizeof(*r));assert(r);r->data=malloc(n?n:1);assert(r->data);memcpy(r->data,bytes,n);r->length=n;r->valid=valid;
 uint8_t seq=0xa4;void *response=(void *)0xdeadbeef;
 glassly_flash_read_command(0x7b,r,event?&seq:0,&response);assert(released==1&&!workspace);return response;
}
static void packet(uint8_t p[8],unsigned d,uint32_t off,unsigned n){p[0]=1;p[1]=(uint8_t)d;for(unsigned i=0;i<4;i++)p[2+i]=(uint8_t)(off>>(i*8));p[6]=(uint8_t)n;p[7]=(uint8_t)(n>>8);expect_device=d;expect_offset=off;expect_length=n;}
static void valid_read(unsigned d,uint32_t off,unsigned n){uint8_t p[8];reset();packet(p,d,off,n);assert(invoke(p,8,1,1)==(void *)1);assert(read_calls==1&&allocated==1&&freed==1);assert(strstr(copied,"\"result\":\"ok\"")&&strstr(copied,"\"hex\":\""));const char *h=strstr(copied,"\"hex\":\"")+7;assert(strlen(h)==n*2+2);for(unsigned i=0;i<n;i++){char x[3];snprintf(x,3,"%02x",(unsigned)(uint8_t)(off+i+d*17));assert(h[2*i]==x[0]&&h[2*i+1]==x[1]);}}
static void invalid_read(unsigned d,uint32_t off,unsigned n){uint8_t p[8];reset();packet(p,d,off,n);invoke(p,8,1,1);assert(!allocated&&!read_calls&&!freed);assert(strstr(copied,"\"invalid\""));}
int main(void){
 const uint32_t ranges[][3]={{0,0,0x10000},{0,0x1eb000,0x1eb100},{0,0x7fc000,0x7fe000}
#ifdef MM_FULL_STORE_READ
 ,{1,0x500000,0x800000}
#else
 ,{1,0x500000,0x510000}
#ifdef MM_EXTERNAL_TAIL_READ
 ,{1,0x700000,0x800000}
#endif
#endif
 };
 reset();uint8_t q=0;invoke(&q,1,1,1);assert(!read_calls&&!allocated&&!freed);puts(copied);
 unsigned cases=1;
 for(unsigned r=0;r<sizeof(ranges)/sizeof(ranges[0]);r++){
  unsigned d=ranges[r][0];uint32_t begin=ranges[r][1],end=ranges[r][2];
  for(uint32_t off=begin;off<end;off+=256){valid_read(d,off,1);valid_read(d,off,256);cases+=2;}
  if(begin){invalid_read(d,begin-256,256);cases++;}invalid_read(d,end,1);cases++;
  for(unsigned i=1;i<256;i++){invalid_read(d,begin+i,1);cases++;}
  invalid_read(d,begin,0);invalid_read(d,begin,257);invalid_read(d,begin,65535);cases+=3;
 }
 for(unsigned d=2;d<256;d++){invalid_read(d,0,1);cases++;}
 invalid_read(1,0,256);invalid_read(0,0x500000,256);invalid_read(0,0xffffff00,256);invalid_read(1,0xffffff00,65535);invalid_read(0,0xffffffff,1);cases+=5;
 for(unsigned n=0;n<12;n++){if(n==8)continue;uint8_t bad[12]={1};reset();invoke(bad,n,1,1);assert(!read_calls&&strstr(copied,"\"invalid\""));cases++;}
 uint8_t p[8];reset();packet(p,1,0x50ff00,256);invoke(p,8,1,1);puts(copied);
 reset();packet(p,0,0x1eb000,256);native_result=-1;invoke(p,8,1,1);assert(read_calls==1&&freed==1&&!strstr(copied,"\"hex\""));puts(copied);
 reset();packet(p,0,0,256);native_result=1;invoke(p,8,1,1);assert(read_calls==1&&freed==1&&strstr(copied,"read-failed"));
 reset();packet(p,0,0,1);fail_alloc=1;invoke(p,8,1,1);assert(allocated==1&&!read_calls&&!freed);puts(copied);
 reset();packet(p,0,0,256);available=32768+2048-1;invoke(p,8,1,1);assert(!allocated&&!read_calls&&strstr(copied,"allocation-failed"));
 reset();packet(p,0,0,256);available=32768+2048;invoke(p,8,1,1);assert(read_calls==1&&freed==1);
 reset();available=32768+1024-1;invoke(&q,1,1,1);assert(!allocated&&!read_calls&&strstr(copied,"allocation-failed"));
 reset();packet(p,0,0,1);fail_json=1;assert(invoke(p,8,1,1)==(void *)2);assert(status_calls==1&&freed==1);
 reset();packet(p,0,0,1);fail_json=fail_status=1;assert(!invoke(p,8,1,1));assert(status_calls==1&&freed==1);
 reset();invoke(&q,1,0,1);assert(!read_calls&&strstr(copied,"invalid"));puts(copied);
 reset();invoke(&q,1,1,0);assert(!read_calls&&strstr(copied,"invalid"));
 reset();void *response=(void *)1;glassly_flash_read_command(0x7b,0,0,&response);assert(!released&&!read_calls&&response==(void *)1);
 printf("PASS flash-reader range/ownership cases=%u plus failure paths; no write/erase/display APIs provided\n",cases);
 return 0;
}
