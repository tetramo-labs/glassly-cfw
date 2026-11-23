#include "flash_store.h"
#define STORE_MAGIC UINT32_C(0x4d465331)
#define NO_OPEN_SECTOR 0xffu
_Static_assert(sizeof(mm_flash_store)<=512,"Small caller-owned context");
_Static_assert(MM_FLASH_PHYSICAL_SECTORS<=256u && MM_FLASH_LOGICAL_SECTORS<NO_OPEN_SECTOR,"Sector indices fit one byte");
static int initialized(const mm_flash_store *s){return s&&s->magic==STORE_MAGIC;}
static int fail(mm_flash_store *s,int code){if(initialized(s)&&s->transaction)s->poisoned=1;return code;}
static int usable(mm_flash_store *s){return !initialized(s)?MM_FLASH_STATE:s->poisoned?MM_FLASH_POISONED:MM_FLASH_OK;}
static int span(const void *p,size_t n){return p&&n<=UINTPTR_MAX-(uintptr_t)p;}
static int overlap(const void *a,size_t an,const void *b,size_t bn){
    uintptr_t ap=(uintptr_t)a,bp=(uintptr_t)b;
    return ap<=bp ? bp-ap<an : ap-bp<bn;
}
static int buffer(mm_flash_store *s,const void *p,size_t n){
    if(!n)return MM_FLASH_OK;
    if(!span(p,n))return MM_FLASH_ARGUMENT;
    if(overlap(p,n,s,sizeof(*s))||overlap(p,n,s->workspace,MM_FLASH_SECTOR_BYTES))return MM_FLASH_ALIAS;
    return MM_FLASH_OK;
}
static int range(uint32_t offset,size_t n){return offset<=MM_FLASH_LOGICAL_BYTES&&n<=MM_FLASH_LOGICAL_BYTES-offset;}
static void copy(uint8_t *out,const uint8_t *in,size_t n){while(n--)*out++=*in++;}
static void zero(uint8_t *out,size_t n){while(n--)*out++=0;}
static void map_copy(uint16_t *out,const uint16_t *in){for(unsigned i=0;i<MM_FLASH_LOGICAL_SECTORS;i++)out[i]=in[i];}
int mm_flash_store_init(mm_flash_store *s,const mm_flash_geometry *g,const mm_flash_callbacks *io,const uint8_t unavailable[MM_FLASH_UNAVAILABLE_BYTES],void *workspace,size_t n){
    if(!s||!g||!io||!io->read||!io->erase||!io->program||!span(unavailable,MM_FLASH_UNAVAILABLE_BYTES)||n!=MM_FLASH_SECTOR_BYTES||!span(s,sizeof(*s))||!span(workspace,n))return MM_FLASH_ARGUMENT;
    if(g->physical_bytes!=MM_FLASH_PHYSICAL_BYTES||g->logical_bytes!=MM_FLASH_LOGICAL_BYTES||g->sector_bytes!=MM_FLASH_SECTOR_BYTES||g->page_bytes!=MM_FLASH_PAGE_BYTES||
       (g->physical_base&(MM_FLASH_SECTOR_BYTES-1u))||g->physical_base>UINT32_MAX-MM_FLASH_PHYSICAL_BYTES)return MM_FLASH_GEOMETRY;
    if(overlap(s,sizeof(*s),workspace,n)||overlap(s,sizeof(*s),unavailable,MM_FLASH_UNAVAILABLE_BYTES))return MM_FLASH_ALIAS;
    unsigned usable_sectors=0;
    for(unsigned i=0;i<MM_FLASH_PHYSICAL_SECTORS;i++)if(!(unavailable[i>>3]&(1u<<(i&7u))))usable_sectors++;
    if(usable_sectors<MM_FLASH_MIN_USABLE_SECTORS)return MM_FLASH_NO_SPACE;
    /* Copy potentially overlapping configuration before initializing context. */
    mm_flash_callbacks callbacks=*io;uint32_t base=g->physical_base;
    for(unsigned i=0;i<MM_FLASH_UNAVAILABLE_BYTES;i++)s->unavailable[i]=unavailable[i];
    s->io=callbacks;s->workspace=workspace;s->base=base;s->magic=STORE_MAGIC;
    s->next_sector=0;s->open_sector=NO_OPEN_SECTOR;s->transaction=0;s->poisoned=0;
    for(unsigned i=0;i<MM_FLASH_LOGICAL_SECTORS;i++)s->active[i]=s->staged[i]=MM_FLASH_UNMAPPED;
    return MM_FLASH_OK;
}
int mm_flash_store_begin(mm_flash_store *s){
    int rc=usable(s);if(rc)return rc;
    if(s->transaction)return fail(s,MM_FLASH_STATE);
    map_copy(s->staged,s->active);s->open_sector=NO_OPEN_SECTOR;s->transaction=1;return MM_FLASH_OK;
}
static int read_map(mm_flash_store *s,const uint16_t *map,uint32_t offset,uint8_t *out,size_t n){
    while(n){
        unsigned logical=offset/MM_FLASH_SECTOR_BYTES,within=offset&(MM_FLASH_SECTOR_BYTES-1u);
        size_t take=MM_FLASH_PAGE_BYTES-(within&(MM_FLASH_PAGE_BYTES-1u));if(take>n)take=n;
        uint16_t physical=map[logical];
        if(map==s->staged&&logical==s->open_sector)copy(out,s->workspace+within,take);
        else if(physical==MM_FLASH_UNMAPPED)zero(out,take);
        else{
            if(physical>=MM_FLASH_PHYSICAL_SECTORS||(s->unavailable[physical>>3]&(1u<<(physical&7u))))return fail(s,MM_FLASH_STATE);
            uint32_t address=s->base+(uint32_t)physical*MM_FLASH_SECTOR_BYTES+within;
            if(s->io.read(s->io.user,address,out,take))return fail(s,MM_FLASH_IO);
        }
        offset+=(uint32_t)take;out+=take;n-=take;
    }
    return MM_FLASH_OK;
}
int mm_flash_store_read(mm_flash_store *s,uint32_t offset,void *out,size_t n){
    int rc=usable(s);if(rc)return rc;
    if(!range(offset,n))return fail(s,MM_FLASH_RANGE);
    rc=buffer(s,out,n);if(rc)return fail(s,rc);
    return read_map(s,s->transaction?s->staged:s->active,offset,out,n);
}
static int sector_used(const mm_flash_store *s,unsigned sector){
    if(s->unavailable[sector>>3]&(1u<<(sector&7u)))return 1;
    for(unsigned i=0;i<MM_FLASH_LOGICAL_SECTORS;i++)if(s->active[i]==sector||s->staged[i]==sector)return 1;
    return 0;
}
static int allocate_sector(mm_flash_store *s){
    for(unsigned n=0;n<MM_FLASH_PHYSICAL_SECTORS;n++){
        unsigned candidate=(s->next_sector+n)%MM_FLASH_PHYSICAL_SECTORS;
        if(!sector_used(s,candidate)){s->next_sector=(uint8_t)((candidate+1u)%MM_FLASH_PHYSICAL_SECTORS);return (int)candidate;}
    }
    return -1;
}
static int flush(mm_flash_store *s){
    if(s->open_sector==NO_OPEN_SECTOR)return MM_FLASH_OK;
    int physical=allocate_sector(s);if(physical<0)return fail(s,MM_FLASH_NO_SPACE);
    uint32_t address=s->base+(uint32_t)physical*MM_FLASH_SECTOR_BYTES;
    if(s->io.erase(s->io.user,address,MM_FLASH_SECTOR_BYTES))return fail(s,MM_FLASH_IO);
    for(unsigned page=0;page<MM_FLASH_SECTOR_BYTES;page+=MM_FLASH_PAGE_BYTES)
        if(s->io.program(s->io.user,address+page,s->workspace+page,MM_FLASH_PAGE_BYTES))return fail(s,MM_FLASH_IO);
    /* Publish only a completely programmed sector. Active map never changes
     * before commit. Previous staged-only sectors become reusable here. */
    s->staged[s->open_sector]=(uint16_t)physical;s->open_sector=NO_OPEN_SECTOR;
    return MM_FLASH_OK;
}
int mm_flash_store_write(mm_flash_store *s,uint32_t offset,const void *data,size_t n){
    int rc=usable(s);if(rc)return rc;
    if(!s->transaction)return MM_FLASH_STATE;
    if(!range(offset,n))return fail(s,MM_FLASH_RANGE);
    rc=buffer(s,data,n);if(rc)return fail(s,rc);
    const uint8_t *in=data;
    while(n){
        unsigned logical=offset/MM_FLASH_SECTOR_BYTES,within=offset&(MM_FLASH_SECTOR_BYTES-1u);
        size_t take=MM_FLASH_SECTOR_BYTES-within;if(take>n)take=n;
        if(logical!=s->open_sector){
            rc=flush(s);if(rc)return rc;
            rc=read_map(s,s->staged,logical*MM_FLASH_SECTOR_BYTES,s->workspace,MM_FLASH_SECTOR_BYTES);
            if(rc)return rc;
            s->open_sector=(uint8_t)logical;
        }
        copy(s->workspace+within,in,take);
        offset+=(uint32_t)take;in+=take;n-=take;
    }
    return MM_FLASH_OK;
}
int mm_flash_store_commit(mm_flash_store *s){
    int rc=usable(s);if(rc)return rc;
    if(!s->transaction)return MM_FLASH_STATE;
    rc=flush(s);if(rc)return rc;
    map_copy(s->active,s->staged);s->transaction=0;return MM_FLASH_OK;
}
int mm_flash_store_abort(mm_flash_store *s){
    if(!initialized(s)||!s->transaction)return MM_FLASH_STATE;
    map_copy(s->staged,s->active);s->open_sector=NO_OPEN_SECTOR;s->transaction=0;s->poisoned=0;return MM_FLASH_OK;
}
int mm_flash_store_view(mm_flash_store *s,uint32_t offset,size_t max_length,const uint8_t **view,size_t *length){
    int rc=usable(s);if(rc)return rc;
    if(!view||!length)return fail(s,MM_FLASH_ARGUMENT);
    rc=buffer(s,view,sizeof(*view));if(rc)return fail(s,rc);
    rc=buffer(s,length,sizeof(*length));if(rc)return fail(s,rc);
    if(overlap(view,sizeof(*view),length,sizeof(*length)))return fail(s,MM_FLASH_ALIAS);
    *view=0;*length=0;
    if(!max_length||offset>=MM_FLASH_LOGICAL_BYTES||!range(offset,max_length))return fail(s,MM_FLASH_RANGE);
    unsigned logical=offset/MM_FLASH_SECTOR_BYTES,within=offset&(MM_FLASH_SECTOR_BYTES-1u);
    size_t n=MM_FLASH_SECTOR_BYTES-within;if(n>max_length)n=max_length;
    if(s->transaction&&logical==s->open_sector){*view=s->workspace+within;*length=n;return MM_FLASH_OK;}
    if(s->transaction){rc=flush(s);if(rc)return rc;}
    rc=read_map(s,s->transaction?s->staged:s->active,offset,s->workspace,n);if(rc)return rc;
    *view=s->workspace;*length=n;return MM_FLASH_OK;
}
