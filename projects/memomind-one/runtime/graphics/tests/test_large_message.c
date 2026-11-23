#include "large_message.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static unsigned live;static int fail;
static void *alloc(size_t n){if(fail)return 0;live++;return malloc(n);}
static void release(void *p){assert(live);live--;free(p);}
static void w16(uint8_t *p,unsigned n){p[0]=n;p[1]=n>>8;}
static void w32(uint8_t *p,uint32_t n){w16(p,n);w16(p+2,n>>16);}
static uint32_t crc(const uint8_t *p,size_t n){uint32_t c=~0u;while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;}
int main(void){
 const unsigned sizes[]={1,8192,8193,32768,65534,65535};unsigned cases=0;
 for(unsigned k=0;k<sizeof(sizes)/sizeof(*sizes);k++){
  unsigned n=sizes[k];uint8_t *expected=malloc(n),p[1033]={127};for(unsigned i=0;i<n;i++)expected[i]=(uint8_t)(i*37);
  mm_large_message s={0};uint8_t *out;size_t length;w32(p+2,k+1);w16(p+6,n);
  assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==0);assert(!out&&!length);
  assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==0 && live==1);
  p[1]=2;assert(mm_large_accept(&s,p,10,alloc,release,&out,&length)==-1);
  for(unsigned offset=0;offset<n;){unsigned count=n-offset;if(count>1024)count=1024;p[1]=1;w16(p+6,offset);memcpy(p+8,expected+offset,count);
   assert(mm_large_accept(&s,p,count+8,alloc,release,&out,&length)==0);
   assert(mm_large_accept(&s,p,count+8,alloc,release,&out,&length)==0);p[8]^=1;
   assert(mm_large_accept(&s,p,count+8,alloc,release,&out,&length)==-1);p[8]^=1;offset+=count;cases+=3;
  }
  p[1]=2;w32(p+6,crc(expected,n)^1);assert(mm_large_accept(&s,p,10,alloc,release,&out,&length)==-4);assert(!out&&s.data);
  w32(p+6,crc(expected,n));assert(mm_large_accept(&s,p,10,alloc,release,&out,&length)==1);
  assert(length==n&&!memcmp(out,expected,n)&&!s.data);release(out);
  assert(mm_large_accept(&s,p,10,alloc,release,&out,&length)==-3);
  p[1]=0;w16(p+6,n);assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==-3);free(expected);
 }
 mm_large_message s={0};uint8_t p[1033]={127,0,77,0,0,0,0,0},*out;size_t length;
 assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==-1);w16(p+6,65535);fail=1;
 assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==-2);fail=0;
 assert(mm_large_accept(&s,p,8,alloc,release,&out,&length)==0);
 p[1]=1;w16(p+6,1);assert(mm_large_accept(&s,p,9,alloc,release,&out,&length)==-1);
 w16(p+6,0);assert(mm_large_accept(&s,p,sizeof p,alloc,release,&out,&length)==-1);
 p[2]=78;assert(mm_large_accept(&s,p,9,alloc,release,&out,&length)==-3);p[2]=77;
 p[1]=3;assert(mm_large_accept(&s,p,6,alloc,release,&out,&length)==0);mm_large_clear(&s,release);
 assert(!live);printf("PASS %u chunk/replay checks; maximum65535, zero/overflow, CRC, gaps, token, allocation, abort, cleanup\n",cases);
}
