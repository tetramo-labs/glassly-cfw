#include "flash_store_native.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned checks,reads,programs,erases,caches,sequence,fail_read_at;
#define CHECK(x) do{++checks;assert(x);}while(0)
static uint8_t flash[0x100000],map[32],data[256],output[256];
static mm_flash_native ctx;
static int read_status,program_status,erase_status,corrupt,reenter;
static uint32_t last_cache_off,last_cache_len;
static void reset_calls(void){reads=programs=erases=caches=sequence=fail_read_at=0;read_status=program_status=erase_status=corrupt=reenter=0;}
static void bounds(uint32_t d,uint32_t off,uint32_t n){CHECK(d==1);CHECK(off>=MM_FLASH_NATIVE_BASE && off<MM_FLASH_NATIVE_END && n<=MM_FLASH_NATIVE_END-off);}
int mm_flash_test_read(uint32_t d,uint32_t off,void *out,uint32_t n){
 bounds(d,off,n);CHECK(n>0 && n<=256 && n<=256-(off&255));reads++;sequence++;
 if(programs||erases)CHECK(caches==1);
 memcpy(out,flash+(off-MM_FLASH_NATIVE_BASE),n);
 if(corrupt)((uint8_t *)out)[n-1]^=1;
 return !fail_read_at||reads==fail_read_at?read_status:0;
}
int mm_flash_test_program(uint32_t d,uint32_t off,const void *src,uint32_t n){
 bounds(d,off,n);CHECK(n==256 && !(off&255));CHECK(!sequence++);programs++;
 if(reenter){
  CHECK(mm_flash_native_read(&ctx,off,output,256)==MM_FLASH_NATIVE_BUSY);
  CHECK(mm_flash_native_init(&ctx,map)==MM_FLASH_NATIVE_BUSY);
 }
 for(unsigned i=0;i<n;i++)flash[off-MM_FLASH_NATIVE_BASE+i]&=((const uint8_t *)src)[i];
 return program_status;
}
int mm_flash_test_erase(uint32_t d,uint32_t off,uint32_t n){bounds(d,off,n);CHECK(n==4096 && !(off&4095));CHECK(!sequence++);erases++;memset(flash+(off-MM_FLASH_NATIVE_BASE),255,n);return erase_status;}
void mm_flash_test_cache(uint32_t index,uint32_t address,uint32_t n){CHECK(index==0 && address>=0x05700000 && address+n<=0x05800000);CHECK(sequence++==1);CHECK(programs+erases==1);caches++;last_cache_off=address;last_cache_len=n;}
static void initialize(void){memset(&ctx,0,sizeof(ctx));memset(map,0,sizeof(map));CHECK(mm_flash_native_init(&ctx,map)==0);reset_calls();}
static void invalid(void){
 initialize();mm_flash_callbacks cb;CHECK(mm_flash_native_callbacks(&ctx,&cb)==0);CHECK(cb.user==&ctx && cb.read==mm_flash_native_read && cb.erase==mm_flash_native_erase && cb.program==mm_flash_native_program);
 mm_flash_native before=ctx;CHECK(mm_flash_native_init(&ctx,ctx.real_unavailable)==MM_FLASH_NATIVE_ALIAS);CHECK(!memcmp(&ctx,&before,sizeof(ctx)));
 CHECK(mm_flash_native_init(0,map)==MM_FLASH_NATIVE_ARGUMENT);CHECK(mm_flash_native_init(&ctx,0)==MM_FLASH_NATIVE_ARGUMENT);
 CHECK(mm_flash_native_callbacks(&ctx,(mm_flash_callbacks *)(void *)&ctx)==MM_FLASH_NATIVE_ALIAS);
 CHECK(mm_flash_native_callbacks(&ctx,0)==MM_FLASH_NATIVE_ARGUMENT);
 CHECK(mm_flash_native_read(0,MM_FLASH_NATIVE_BASE,output,1)==MM_FLASH_NATIVE_STATE);
 uint32_t off[]={0,0x6fffff,0x800000,0xffffffff};
 for(unsigned i=0;i<4;i++){CHECK(mm_flash_native_read(&ctx,off[i],output,1)==MM_FLASH_NATIVE_RANGE);CHECK(mm_flash_native_program(&ctx,off[i],data,256)==MM_FLASH_NATIVE_RANGE);CHECK(mm_flash_native_erase(&ctx,off[i],4096)==MM_FLASH_NATIVE_RANGE);}
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,output,0)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,output,257)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE+255,output,2)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,output,SIZE_MAX)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE+1,data,256)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,data,255)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_erase(&ctx,MM_FLASH_NATIVE_BASE+256,4096)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_erase(&ctx,MM_FLASH_NATIVE_BASE,8192)==MM_FLASH_NATIVE_RANGE);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,ctx.verification,1)==MM_FLASH_NATIVE_ALIAS);
 CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,&ctx,256)==MM_FLASH_NATIVE_ALIAS);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,0,1)==MM_FLASH_NATIVE_ARGUMENT);
 CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,0,256)==MM_FLASH_NATIVE_ARGUMENT);
 CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,(void *)(UINTPTR_MAX-3),8)==MM_FLASH_NATIVE_ARGUMENT);
 CHECK(!(reads+programs+erases+caches));
}
static void badbits(void){
 for(unsigned bit=0;bit<256;bit++){
  initialize();map[bit>>3]=(uint8_t)(1u<<(bit&7));CHECK(mm_flash_native_init(&ctx,map)==0);memset(map,0,32);
  uint32_t off=MM_FLASH_NATIVE_BASE+bit*4096;
  CHECK(mm_flash_native_read(&ctx,off,output,1)==MM_FLASH_NATIVE_BAD_SECTOR);
  CHECK(mm_flash_native_program(&ctx,off,data,256)==MM_FLASH_NATIVE_BAD_SECTOR);
  CHECK(mm_flash_native_erase(&ctx,off,4096)==MM_FLASH_NATIVE_BAD_SECTOR);
  CHECK(!(reads+programs+erases+caches));
 }
}
static void successful(void){
 initialize();for(unsigned i=0;i<256;i++)data[i]=(uint8_t)i;
 for(unsigned sector=0;sector<256;sector++){
  uint32_t off=MM_FLASH_NATIVE_BASE+sector*4096;reset_calls();
  CHECK(mm_flash_native_erase(&ctx,off,4096)==0);CHECK(erases==1 && caches==1 && reads==16);CHECK(last_cache_off==0x05000000+off && last_cache_len==4096);
  for(unsigned page=0;page<16;page++){
   reset_calls();CHECK(mm_flash_native_program(&ctx,off+page*256,data,256)==0);CHECK(programs==1 && caches==1 && reads==1);CHECK(last_cache_off==0x05000000+off+page*256 && last_cache_len==256);
  }
 }
 reset_calls();CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_END-1,output,1)==0);CHECK(output[0]==255 && reads==1 && !caches);
}
static void failures(void){
 initialize();memset(data,0x55,256);
 for(int status=-7;status<=7;status+=14){
  reset_calls();program_status=status;CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,data,256)==status);CHECK(programs==1 && caches==1 && reads==0 && ctx.last_native_status==status && !ctx.busy);
  reset_calls();erase_status=status;CHECK(mm_flash_native_erase(&ctx,MM_FLASH_NATIVE_BASE,4096)==status);CHECK(erases==1 && caches==1 && reads==0 && ctx.last_native_status==status && !ctx.busy);
  reset_calls();read_status=status;CHECK(mm_flash_native_read(&ctx,MM_FLASH_NATIVE_BASE,output,256)==status);CHECK(reads==1 && !caches && ctx.phase==MM_FLASH_NATIVE_READ);
 }
 for(unsigned page=1;page<=16;page++){
  reset_calls();read_status=19;fail_read_at=page;CHECK(mm_flash_native_erase(&ctx,MM_FLASH_NATIVE_BASE,4096)==19);CHECK(reads==page && caches==1 && ctx.phase==MM_FLASH_NATIVE_READBACK && ctx.last_native_status==19 && !ctx.busy);
 }
 reset_calls();read_status=-23;CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,data,256)==-23);CHECK(reads==1 && caches==1 && !ctx.busy);
 reset_calls();corrupt=1;CHECK(mm_flash_native_erase(&ctx,MM_FLASH_NATIVE_BASE,4096)==MM_FLASH_NATIVE_VERIFY);CHECK(reads==1 && !ctx.last_native_status && !ctx.busy);
 reset_calls();corrupt=1;CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,data,256)==MM_FLASH_NATIVE_VERIFY);CHECK(reads==1 && !ctx.busy);
 reset_calls();reenter=1;CHECK(mm_flash_native_program(&ctx,MM_FLASH_NATIVE_BASE,data,256)==0);CHECK(programs==1 && reads==1 && caches==1);
}
int main(void){invalid();badbits();successful();failures();printf("PASS checks=%u sectors=256 pages=4096 badbits=256 erase_readback_faults=16 context_bytes=%zu\n",checks,sizeof(ctx));return 0;}
