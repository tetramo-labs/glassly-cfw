#include "scene_flash_store.h"
static int read_bytes(void *u,uint32_t off,void *p,size_t n){return mm_flash_store_read(u,off,p,n);}
static int begin(void *u){return mm_flash_store_begin(u);}
static int write_bytes(void *u,uint32_t off,const void *p,size_t n){return mm_flash_store_write(u,off,p,n);}
static int commit(void *u){return mm_flash_store_commit(u);}
static void abort_tx(void *u){(void)mm_flash_store_abort(u);}
static void reset(void *u){
    mm_flash_store *s=u;uint8_t bad[32];for(unsigned i=0;i<32;i++)bad[i]=s->unavailable[i];
    mm_flash_geometry g={s->base,MM_FLASH_PHYSICAL_BYTES,MM_FLASH_LOGICAL_BYTES,MM_FLASH_SECTOR_BYTES,MM_FLASH_PAGE_BYTES};
    /* Initial successful init establishes the exact geometry and usable count. */
    (void)mm_flash_store_init(s,&g,&s->io,bad,s->workspace,MM_FLASH_SECTOR_BYTES);
}
static int overlaps(const void *a,size_t n,const void *b,size_t m){uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return n&&m&&(x<=y?y-x<n:x-y<m);}
static int aliases(void *u,const void *p,size_t n){mm_flash_store *s=u;return overlaps(p,n,s,sizeof(*s))||overlaps(p,n,s->workspace,MM_FLASH_SECTOR_BYTES);}
int mm_scene_flash_store_bind(mm_scene_store *out,mm_flash_store *s){
    if(!out||!s||mm_flash_store_read(s,0,0,0)||s->transaction||!s->workspace||!s->io.read||!s->io.erase||!s->io.program||aliases(s,out,sizeof(*out)))return -1;
    *out=(mm_scene_store){s,MM_FLASH_LOGICAL_BYTES,read_bytes,begin,write_bytes,commit,abort_tx,reset,aliases};return 0;
}
