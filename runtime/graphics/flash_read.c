/* Fixed physical read allowlists for H001Y1.0.3.127. No mutation APIs exist here.
 * Native read holds native serialization and may busy-wait without a timeout.
 */
#include "flash_read.h"
#ifdef MM_STORAGE_DIAG_OPS
#include "storage_diag.h"
#endif
#define FP mm_graphics_native
static const char invalid[]="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"invalid\"}";
static const char nomem[]="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"allocation-failed\"}";
static const char failed[]="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"read-failed\"}";
#if defined(MM_FLASH_CANARY)
#define READ_PROFILE "H001Y-1.0.3.127-flash-canary-v1"
#elif defined(MM_FULL_STORE_READ)
#define READ_PROFILE "H001Y-1.0.3.127-full-store-read-v1"
#elif defined(MM_STORAGE_DIAG_OPS)
#define READ_PROFILE "H001Y-1.0.3.127-storage-diag-v1"
#elif defined(MM_EXTERNAL_TAIL_READ)
#define READ_PROFILE "H001Y-1.0.3.127-external-v1"
#else
#define READ_PROFILE "H001Y-1.0.3.127"
#endif
static const char query[]="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"profile\":\"" READ_PROFILE "\",\"maxRead\":256,\"alignment\":256,\"ranges\":["
    "{\"device\":0,\"start\":0,\"end\":65536},"
    "{\"device\":0,\"start\":2011136,\"end\":2011392},"
    "{\"device\":0,\"start\":8372224,\"end\":8380416},"
#ifdef MM_FULL_STORE_READ
    "{\"device\":1,\"start\":5242880,\"end\":8388608}"
#else
    "{\"device\":1,\"start\":5242880,\"end\":5308416}"
#ifdef MM_EXTERNAL_TAIL_READ
    ",{\"device\":1,\"start\":7340032,\"end\":8388608}"
#endif
#endif
    "]}";
typedef struct {uint8_t bytes[256];char json[768];} flash_workspace;
_Static_assert(sizeof(flash_workspace)==MM_FLASH_READ_WORKSPACE,"Fixed workspace bound");
static uint32_t le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static int inside(uint32_t offset,uint32_t length,uint32_t begin,uint32_t end){
    return offset>=begin && offset<end && length<=end-offset;
}
static int allowed(uint32_t device,uint32_t offset,uint32_t length){
    if(!length || length>256u || (offset&255u))return 0;
    if(device==0)return inside(offset,length,0,0x10000u) ||
        inside(offset,length,0x1eb000u,0x1eb100u) || inside(offset,length,0x7fc000u,0x7fe000u);
#ifdef MM_FULL_STORE_READ
    return device==1 && inside(offset,length,0x500000u,0x800000u);
#else
    return device==1 && (inside(offset,length,0x500000u,0x510000u)
#ifdef MM_EXTERNAL_TAIL_READ
        || inside(offset,length,0x700000u,0x800000u)
#endif
        );
#endif
}
static void *reply(const char *text){void *p=FP.json(text);return p?p:FP.status(4,0);}
static char *text(char *p,const char *s){while(*s)*p++=*s++;return p;}
static char *number(char *p,uint32_t value){char digits[10];unsigned n=0;do{digits[n++]=(char)('0'+value%10u);value/=10u;}while(value);while(n)*p++=digits[--n];return p;}
void glassly_flash_read_command(uint32_t command,void *request,const uint8_t *event,void **response){
    (void)command;const uint8_t *data=0;size_t length=0;
    uint32_t device=0,offset=0,count=0;int valid=0,is_query=0;
#ifdef MM_STORAGE_DIAG_OPS
    int diagnostic=0;
#endif
    *response=0;
    if(event && FP.request_bytes(request,&data,&length) && data){
        if(length==1 && data[0]==0){valid=1;is_query=1;}
#ifdef MM_STORAGE_DIAG_OPS
        else if(length==1 && (data[0]==2 || data[0]==3)){valid=1;diagnostic=data[0];}
#endif
        else if(length==8 && data[0]==1){
            device=data[1];offset=le32(data+2);count=(uint32_t)data[6]|((uint32_t)data[7]<<8);
            valid=allowed(device,offset,count);
        }
    }
    /* No borrowed request/event pointer is accessed below this release. */
    if(request)FP.release(&request);
    if(!valid){*response=reply(invalid);return;}
    if(FP.free_bytes()<MM_FLASH_READ_HEADROOM+(is_query?MM_FLASH_READ_WORKSPACE:2u*MM_FLASH_READ_WORKSPACE)){
        *response=reply(nomem);return;
    }
    if(is_query){*response=reply(query);return;}
    flash_workspace *w=FP.alloc(sizeof(*w));
    if(!w){*response=reply(nomem);return;}
#ifdef MM_STORAGE_DIAG_OPS
    if(diagnostic){
        int ok=diagnostic==2?mm_storage_topology_json(w->json,sizeof(w->json)):
            mm_storage_badmap_json(w->json,sizeof(w->json),w->bytes);
        *response=reply(ok?w->json:failed);FP.free(w);return;
    }
#endif
    for(size_t i=0;i<sizeof(w->bytes);i++)w->bytes[i]=0;
    int result=glassly_flash_read_native(device,offset,w->bytes,count);
    if(result!=0){FP.free(w);*response=reply(failed);return;}
    char *p=text(w->json,"{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":");
    p=number(p,device);p=text(p,",\"offset\":");p=number(p,offset);
    p=text(p,",\"length\":");p=number(p,count);p=text(p,",\"hex\":\"");
    static const char hex[]="0123456789abcdef";
    for(uint32_t i=0;i<count;i++){*p++=hex[w->bytes[i]>>4];*p++=hex[w->bytes[i]&15u];}
    *p++='"';*p++='}';*p=0;
    /* Max3 ten-digit integers +512hex + fixed text is below768 bytes. */
    *response=reply(w->json); /* json synchronously copies before free. */
    FP.free(w);
}
