#include "flash_store.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BASE UINT32_C(0x600000)
typedef struct {
 mm_flash_store store;
 uint8_t scratch[MM_FLASH_SECTOR_BYTES],bad[32],programmed[4096];
 uint8_t *flash;
 size_t calls,reads,erases,programs,fail_at;
 int partial;
 char failed_kind;
 unsigned touched[256];
} fixture;
static unsigned checks;
#define CHECK(x) do{checks++;assert(x);}while(0)
static unsigned offset(fixture *f,uint32_t address,size_t n){
 CHECK(address>=f->store.base);unsigned off=address-f->store.base;
 CHECK(off<MM_FLASH_PHYSICAL_BYTES&&n<=MM_FLASH_PHYSICAL_BYTES-off);
 CHECK(!(f->bad[(off/4096)>>3]&(1u<<((off/4096)&7))));return off;
}
static void unowned(fixture *f,unsigned sector){
 for(unsigned i=0;i<64;i++){CHECK(f->store.active[i]!=sector);CHECK(f->store.staged[i]!=sector);}
}
static int fails(fixture *f,char kind){f->calls++;if(f->fail_at&&f->calls==f->fail_at){f->failed_kind=kind;return 1;}return 0;}
static int read_cb(void *user,uint32_t address,void *out,size_t n){
 fixture *f=user;unsigned off=offset(f,address,n);CHECK(n&&n<=256&&(off%256)+n<=256);f->reads++;
 int failure=fails(f,'r');if(!failure||f->partial)memcpy(out,f->flash+off,failure?n/2:n);return failure?-71:0;
}
static int erase_cb(void *user,uint32_t address,size_t n){
 fixture *f=user;unsigned off=offset(f,address,n);CHECK(n==4096&&!(off%4096));unsigned sector=off/4096;unowned(f,sector);f->erases++;f->touched[sector]++;
 int failure=fails(f,'e');if(!failure||f->partial){memset(f->flash+off,255,failure?n/2:n);memset(f->programmed+off/256,0,16);}return failure?-72:0;
}
static int program_cb(void *user,uint32_t address,const void *data,size_t n){
 fixture *f=user;unsigned off=offset(f,address,n);CHECK(n==256&&!(off%256));unowned(f,off/4096);CHECK(!f->programmed[off/256]);
 const uint8_t *in=data;for(unsigned i=0;i<n;i++)CHECK(f->flash[off+i]==255);f->programmed[off/256]=1;f->programs++;
 int failure=fails(f,'p');size_t count=failure?(f->partial?n/2:0):n;
 for(size_t i=0;i<count;i++)f->flash[off+i]&=in[i];return failure?-73:0;
}
static mm_flash_geometry geometry(uint32_t base){return (mm_flash_geometry){base,1048576,262144,4096,256};}
static mm_flash_callbacks callbacks(fixture *f){return (mm_flash_callbacks){f,read_cb,erase_cb,program_cb};}
static fixture *create(const uint8_t bad[32]){
 fixture *f=calloc(1,sizeof(*f));assert(f);f->flash=malloc(1048576);assert(f->flash);memset(f->flash,0x5a,1048576);memset(f->scratch,0xa5,4096);if(bad)memcpy(f->bad,bad,32);
 mm_flash_geometry g=geometry(BASE);mm_flash_callbacks io=callbacks(f);
 CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4096)==0);CHECK(!f->calls);return f;
}
static void destroy(fixture *f){free(f->flash);free(f);}
static uint8_t *pattern(unsigned seed){uint8_t *p=malloc(262144);assert(p);for(unsigned i=0;i<262144;i++)p[i]=(uint8_t)((i*17u+(i>>8)*31u+seed)%251u);return p;}
static void verify(fixture *f,const uint8_t *expected){uint8_t *out=malloc(262144);assert(out);CHECK(mm_flash_store_read(&f->store,0,out,262144)==0);CHECK(!memcmp(out,expected,262144));free(out);}
static void commit_data(fixture *f,const uint8_t *p){CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,0,p,262144)==0);size_t calls=f->calls;CHECK(mm_flash_store_commit(&f->store)==0);CHECK(calls==f->calls);}
static void test_init_ranges_aliases(void){
 fixture *f=create(NULL);uint8_t *zero=calloc(1,262144);assert(zero);verify(f,zero);CHECK(!f->calls);for(unsigned i=0;i<4096;i++)CHECK(f->scratch[i]==0xa5);
 for(unsigned i=0;i<1048576;i++)CHECK(f->flash[i]==0x5a);
 CHECK(mm_flash_store_begin(&f->store)==0);verify(f,zero);CHECK(mm_flash_store_write(&f->store,262144,NULL,0)==0);CHECK(mm_flash_store_commit(&f->store)==0);CHECK(!f->calls);
 CHECK(mm_flash_store_read(&f->store,262144,NULL,0)==0);CHECK(mm_flash_store_write(&f->store,0,zero,1)==MM_FLASH_STATE);
 CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_STATE);CHECK(mm_flash_store_abort(&f->store)==MM_FLASH_STATE);
 for(unsigned mode=0;mode<8;mode++){
  CHECK(mm_flash_store_begin(&f->store)==0);int rc=0;
  switch(mode){
   case 0:rc=mm_flash_store_begin(&f->store);CHECK(rc==MM_FLASH_STATE);break;
   case 1:rc=mm_flash_store_write(&f->store,UINT32_MAX,zero,1);CHECK(rc==MM_FLASH_RANGE);break;
   case 2:rc=mm_flash_store_read(&f->store,1,zero,SIZE_MAX);CHECK(rc==MM_FLASH_RANGE);break;
   case 3:rc=mm_flash_store_write(&f->store,0,f->scratch,1);CHECK(rc==MM_FLASH_ALIAS);break;
   case 4:rc=mm_flash_store_read(&f->store,0,&f->store,1);CHECK(rc==MM_FLASH_ALIAS);break;
   case 5:rc=mm_flash_store_write(&f->store,0,NULL,1);CHECK(rc==MM_FLASH_ARGUMENT);break;
   case 6:rc=mm_flash_store_write(&f->store,0,(const void *)(UINTPTR_MAX-1),8);CHECK(rc==MM_FLASH_ARGUMENT);break;
   case 7:rc=mm_flash_store_read(&f->store,262144,zero,1);CHECK(rc==MM_FLASH_RANGE);break;
  }
  CHECK(rc<0&&f->store.poisoned);CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_POISONED);CHECK(mm_flash_store_read(&f->store,0,zero,1)==MM_FLASH_POISONED);CHECK(mm_flash_store_abort(&f->store)==0);CHECK(!f->calls);
 }
 mm_flash_geometry g=geometry(BASE);mm_flash_callbacks io=callbacks(f);mm_flash_store original=f->store;
 for(unsigned mode=0;mode<8;mode++){
  g=geometry(BASE);switch(mode){case 0:g.physical_base++;break;case 1:g.physical_base=0xfff00000;break;case 2:g.physical_bytes--;break;case 3:g.logical_bytes++;break;case 4:g.sector_bytes=2048;break;case 5:g.page_bytes=512;break;case 6:g.physical_base=UINT32_MAX;break;case 7:g.physical_bytes=UINT32_MAX;break;}
  CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4096)==MM_FLASH_GEOMETRY);CHECK(!memcmp(&original,&f->store,sizeof(original)));CHECK(!f->calls);
 }
 g=geometry(BASE);CHECK(mm_flash_store_init(&f->store,&g,&io,NULL,f->scratch,4096)==MM_FLASH_ARGUMENT);
 CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4095)==MM_FLASH_ARGUMENT);
 CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,&f->store,4096)==MM_FLASH_ALIAS);
 io.program=NULL;CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4096)==MM_FLASH_ARGUMENT);
 free(zero);destroy(f);
}
static void test_message_capacity_view_and_churn(void){
 fixture *f=create(NULL);uint8_t *a=pattern(1),*b=pattern(91),*expected=malloc(262144);assert(expected);memcpy(expected,a,262144);commit_data(f,a);verify(f,a);
 CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,4089,b,65535)==0);memcpy(expected+4089,b,65535);verify(f,expected);
 const uint8_t *view;size_t n;CHECK(mm_flash_store_view(&f->store,4089,65535,&view,&n)==0);CHECK(n==7&&!memcmp(view,b,7));
 CHECK(mm_flash_store_write(&f->store,0,view,n)==MM_FLASH_ALIAS);CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_POISONED);CHECK(mm_flash_store_abort(&f->store)==0);verify(f,a);
 CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,4089,b,65535)==0);CHECK(mm_flash_store_commit(&f->store)==0);verify(f,expected);
 for(unsigned off=0;off<262144;){CHECK(mm_flash_store_view(&f->store,off,262144-off,&view,&n)==0);CHECK(n&&n<=4096&&!memcmp(view,expected+off,n));off+=(unsigned)n;}
 CHECK(mm_flash_store_view(&f->store,262144,1,&view,&n)==MM_FLASH_RANGE);CHECK(!view&&!n);
 for(unsigned turn=0;turn<300;turn++){
  CHECK(mm_flash_store_begin(&f->store)==0);unsigned off=(turn*997u)%262144;uint8_t val=(uint8_t)turn;
  CHECK(mm_flash_store_write(&f->store,off,&val,1)==0);CHECK(mm_flash_store_write(&f->store,off,&val,1)==0);
  CHECK(mm_flash_store_commit(&f->store)==0);expected[off]=val;
 }
 verify(f,expected);unsigned reused=0;for(unsigned i=0;i<256;i++)reused+=f->touched[i]>1;CHECK(reused>100);
 size_t before=f->calls;mm_flash_geometry g=geometry(BASE);mm_flash_callbacks io=callbacks(f);
 CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4096)==0);CHECK(f->calls==before);memset(expected,0,262144);verify(f,expected);CHECK(f->calls==before);
 free(a);free(b);free(expected);destroy(f);
}
static void test_every_callback_failure(void){
 fixture *f=create(NULL);uint8_t *a=pattern(7),*b=pattern(23);commit_data(f,a);
 uint8_t *snapshot=malloc(1048576),*flags=malloc(4096);assert(snapshot&&flags);memcpy(snapshot,f->flash,1048576);memcpy(flags,f->programmed,4096);mm_flash_store state=f->store;
 f->calls=f->reads=f->erases=f->programs=0;CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,0,b,262144)==0);
 size_t total=f->calls;CHECK(total==64*(16+1+16));CHECK(f->reads==1024&&f->erases==64&&f->programs==1024);
 unsigned failures[3]={0};
 for(int partial=0;partial<=1;partial++)for(size_t at=1;at<=total;at++){
  memcpy(f->flash,snapshot,1048576);memcpy(f->programmed,flags,4096);f->store=state;f->calls=0;f->fail_at=at;f->partial=partial;f->failed_kind=0;
  CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,0,b,262144)==MM_FLASH_IO);CHECK(f->calls==at);
  unsigned kind=f->failed_kind=='r'?0:f->failed_kind=='e'?1:2;failures[kind]++;
  CHECK(f->store.poisoned);CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_POISONED);
  CHECK(mm_flash_store_read(&f->store,0,f->scratch,1)==MM_FLASH_POISONED);CHECK(mm_flash_store_write(&f->store,0,b,1)==MM_FLASH_POISONED);CHECK(f->calls==at);
  CHECK(mm_flash_store_abort(&f->store)==0);CHECK(f->calls==at);f->fail_at=0;verify(f,a);
 }
 CHECK(failures[0]==2048&&failures[1]==128&&failures[2]==2048);
 printf("fault_boundaries=%zu fault_runs=%zu read_faults=%u erase_faults=%u program_faults=%u\n",total,total*2,failures[0],failures[1],failures[2]);
 // A public read failure also poisons a live transaction without physical writes.
 f->calls=0;f->fail_at=1;f->partial=1;CHECK(mm_flash_store_begin(&f->store)==0);uint8_t out[17];CHECK(mm_flash_store_read(&f->store,17,out,sizeof(out))==MM_FLASH_IO);CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_POISONED);CHECK(mm_flash_store_abort(&f->store)==0);
 f->calls=0;f->fail_at=1;CHECK(mm_flash_store_read(&f->store,17,out,sizeof(out))==MM_FLASH_IO);CHECK(!f->store.poisoned);f->fail_at=0;verify(f,a);
 const uint8_t *view=(const uint8_t *)1;size_t length=99;
 f->calls=0;f->fail_at=1;CHECK(mm_flash_store_begin(&f->store)==0);
 CHECK(mm_flash_store_view(&f->store,17,33,&view,&length)==MM_FLASH_IO);CHECK(!view&&!length);
 CHECK(mm_flash_store_commit(&f->store)==MM_FLASH_POISONED);CHECK(mm_flash_store_abort(&f->store)==0);f->fail_at=0;verify(f,a);
 free(snapshot);free(flags);free(a);free(b);destroy(f);
}
static void set_bad(uint8_t *bad,unsigned sector){bad[sector>>3]|=(uint8_t)(1u<<(sector&7));}
static void test_unavailable_and_minimum_capacity(void){
 uint8_t bad[32]={0};set_bad(bad,0);set_bad(bad,255);set_bad(bad,63);set_bad(bad,128);
 fixture *f=create(bad);uint8_t *a=pattern(31),*b=pattern(71);commit_data(f,a);commit_data(f,b);verify(f,b);
 for(unsigned i=0;i<256;i++)if(bad[i>>3]&(1u<<(i&7)))CHECK(!f->touched[i]);
 CHECK(mm_flash_store_begin(&f->store)==0);f->store.staged[0]=0;uint8_t out;size_t calls=f->calls;CHECK(mm_flash_store_read(&f->store,0,&out,1)==MM_FLASH_STATE);CHECK(f->calls==calls);CHECK(mm_flash_store_abort(&f->store)==0);verify(f,b);destroy(f);
 memset(bad,0,32);for(unsigned i=129;i<256;i++)set_bad(bad,i);f=create(bad);commit_data(f,a);
 //64active+64staged+1scratch sector; repeated writes after full replacement work.
 CHECK(mm_flash_store_begin(&f->store)==0);CHECK(mm_flash_store_write(&f->store,0,b,262144)==0);
 for(unsigned i=0;i<200;i++){unsigned off=(i*4096u)%262144;CHECK(mm_flash_store_write(&f->store,off,b+off,1)==0);}
 verify(f,b);CHECK(mm_flash_store_abort(&f->store)==0);verify(f,a);
 for(unsigned i=0;i<12;i++){commit_data(f,i&1?a:b);verify(f,i&1?a:b);}
 for(unsigned i=129;i<256;i++)CHECK(!f->touched[i]);
 mm_flash_geometry g=geometry(BASE);mm_flash_callbacks io=callbacks(f);mm_flash_store original=f->store;
 set_bad(bad,128);calls=f->calls;CHECK(mm_flash_store_init(&f->store,&g,&io,bad,f->scratch,4096)==MM_FLASH_NO_SPACE);CHECK(f->calls==calls&&!memcmp(&original,&f->store,sizeof(original)));
 // Bitmap is copied from the exact input address passed to init.
 uint8_t copied[32];memcpy(copied,f->bad,32);
 CHECK(mm_flash_store_init(&f->store,&g,&io,copied,f->scratch,4096)==0);
 memset(copied,0,32);CHECK(f->store.unavailable[31]==255);commit_data(f,a);verify(f,a);
 g=geometry(0xffe00000);CHECK(mm_flash_store_init(&f->store,&g,&io,f->bad,f->scratch,4096)==0);commit_data(f,b);verify(f,b);
 free(a);free(b);destroy(f);
}
static uint32_t random_step(uint32_t *state){*state=*state*UINT32_C(1664525)+UINT32_C(1013904223);return *state;}
static void test_reference_model(void){
 fixture *f=create(NULL);uint8_t *active=calloc(1,262144),*staged=malloc(262144),*bytes=pattern(5);assert(active&&staged);
 uint32_t random=12345;
 for(unsigned turn=0;turn<240;turn++){
  memcpy(staged,active,262144);CHECK(mm_flash_store_begin(&f->store)==0);
  unsigned writes=1+random_step(&random)%7;
  for(unsigned j=0;j<writes;j++){
   unsigned off=random_step(&random)%262144,n=1+random_step(&random)%8192;if(n>262144-off)n=262144-off;
   CHECK(mm_flash_store_write(&f->store,off,bytes+turn,n)==0);memcpy(staged+off,bytes+turn,n);
   const uint8_t *view;size_t length;
   CHECK(mm_flash_store_view(&f->store,off,n,&view,&length)==0);CHECK(length&&length<=n&&!memcmp(view,staged+off,length));
  }
  verify(f,staged);size_t calls=f->calls;
  if(turn%3){CHECK(mm_flash_store_commit(&f->store)==0);memcpy(active,staged,262144);}else CHECK(mm_flash_store_abort(&f->store)==0);
  CHECK(f->calls==calls);verify(f,active);
 }
 free(active);free(staged);free(bytes);destroy(f);
}
int main(void){test_init_ranges_aliases();test_message_capacity_view_and_churn();test_every_callback_failure();test_unavailable_and_minimum_capacity();test_reference_model();printf("PASS checks=%u context_bytes=%zu workspace_bytes=4096\n",checks,sizeof(mm_flash_store));return 0;}
