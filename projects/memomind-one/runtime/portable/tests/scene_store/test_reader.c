#include "scene_store.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint8_t bytes[600];unsigned calls;int fail;} backing;
static int aliases(void *u,const void *p,size_t n){uintptr_t a=(uintptr_t)u,b=(uintptr_t)p;return n&&(b<=a?a-b<n:b-a<sizeof(backing));}
static int read_bytes(void *u,uint32_t off,void *out,size_t n){backing *b=u;assert(off<=600&&n<=600-off);b->calls++;if(b->fail)return -7;memcpy(out,b->bytes+off,n);return 0;}
int main(void){
 backing b={0};for(unsigned i=0;i<600;i++)b.bytes[i]=(uint8_t)(i*17u);
 mm_scene_store store={.user=&b,.capacity=600,.read=read_bytes,.aliases=aliases};
 mm_scene_bytes ram={b.bytes,0,0,600},external={0,&store,0,600};uint8_t out[600];
 assert(!mm_scene_bytes_read(&ram,0,out,600)&&!memcmp(out,b.bytes,600));assert(!mm_scene_bytes_read(&external,0,out,600)&&b.calls==1);
 assert(mm_scene_bytes_read(&ram,0,b.bytes,1)==-1);assert(mm_scene_bytes_read(&ram,0,&ram,1)==-1);
 assert(mm_scene_bytes_read(&external,0,&store,1)==-1);assert(mm_scene_bytes_read(&external,0,&b,1)==-1);
 assert(!mm_scene_bytes_read(&ram,600,0,0));assert(mm_scene_bytes_read(&ram,600,out,1)==-1);assert(mm_scene_bytes_read(&ram,1,out,SIZE_MAX)==-1);
 mm_scene_bytes malformed=ram;malformed.ram=(void *)(UINTPTR_MAX-2);malformed.length=16;assert(mm_scene_bytes_read(&malformed,0,out,1)==-1);
 mm_scene_bytes result=ram,saved=result;assert(mm_scene_bytes_sub(&malformed,1,1,&result)==-1&&!memcmp(&result,&saved,sizeof result));
 malformed=external;malformed.offset=UINT32_MAX;malformed.length=2;assert(mm_scene_bytes_sub(&malformed,0,1,&result)==-1&&!memcmp(&result,&saved,sizeof result));
 assert(mm_scene_bytes_sub(&ram,601,0,&result)==-1&&!memcmp(&result,&saved,sizeof result));assert(mm_scene_bytes_sub(&ram,0,1,(void *)b.bytes)==-1);
 assert(!mm_scene_bytes_sub(&result,4,8,&result));assert(result.ram==b.bytes+4&&result.length==8&&result.offset==0);
 result=external;assert(!mm_scene_bytes_sub(&result,255,260,&result));assert(result.offset==255&&result.length==260);
 malformed=external;malformed.ram=b.bytes;assert(mm_scene_bytes_read(&malformed,0,out,1)==-1);
 malformed=ram;malformed.offset=1;assert(mm_scene_bytes_read(&malformed,0,out,1)==-1);
 mm_scene_store broken=store;malformed=external;malformed.store=&broken;broken.read=0;assert(mm_scene_bytes_read(&malformed,0,out,1)==-1);broken=store;broken.aliases=0;assert(mm_scene_bytes_read(&malformed,0,out,1)==-1);
 assert(mm_scene_bytes_read(&external,0,(void *)(UINTPTR_MAX-1),4)==-1);
 mm_scene_cursor cursor;memset(&cursor,0x55,sizeof cursor);mm_scene_cursor old=cursor;
 assert(mm_scene_cursor_init(&cursor,&malformed)==-1&&!memcmp(&cursor,&old,sizeof cursor));
 assert(!mm_scene_cursor_init(&cursor,&external));assert(!mm_scene_cursor_read(&cursor,254,out,300)&&!memcmp(out,b.bytes+254,300));
 old=cursor;assert(mm_scene_cursor_read(&cursor,0,cursor.data,1)==-1&&!memcmp(&cursor,&old,sizeof cursor));
 assert(mm_scene_cursor_read(&cursor,0,&cursor,1)==-1);assert(mm_scene_cursor_read(&cursor,0,(void *)(UINTPTR_MAX-1),4)==-1);assert(mm_scene_cursor_read(&cursor,0,b.bytes,1)==-1);
 assert(mm_scene_cursor_read(&cursor,600,out,1)==-1);assert(!mm_scene_cursor_read(&cursor,600,0,0));cursor.used=257;assert(mm_scene_cursor_read(&cursor,0,out,1)==-1);
 assert(!mm_scene_cursor_init(&cursor,&cursor.bytes));b.fail=1;assert(mm_scene_cursor_read(&cursor,0,out,4)==-2&&cursor.used==0);b.fail=0;assert(!mm_scene_cursor_read(&cursor,0,out,4)&&!memcmp(out,b.bytes,4));
 mm_scene_bytes inside={cursor.data,0,0,20};old=cursor;assert(mm_scene_cursor_init(&cursor,&inside)==-1&&!memcmp(&cursor,&old,sizeof cursor));
 puts("PASS reader malformed handles, overflow, alias, sub-on-self, failed outputs unchanged, cursor boundaries and recovery");return 0;
}
