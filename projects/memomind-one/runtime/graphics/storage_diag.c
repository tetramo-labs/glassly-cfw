#include "storage_diag.h"
typedef struct {char *out;size_t capacity,used;int failed;} writer;
static void put(writer *w,char c) {
    if(w->used+1>=w->capacity){w->failed=1;return;}
    w->out[w->used++]=c;
}
static void text(writer *w,const char *s){while(*s)put(w,*s++);}
static void number(writer *w,uint32_t n){char digits[10];unsigned i=0;do{digits[i++]=(char)('0'+n%10u);n/=10u;}while(n);while(i)put(w,digits[--i]);}
static void field(writer *w,const char *name,uint32_t value){text(w,",\"");text(w,name);text(w,"\":");number(w,value);}
static uint32_t driver(uint32_t p){return p==0?0:p==0x02010898u?1:p==0x020107f0u?2:3;}
static uint32_t le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void hex(writer *w,const uint8_t *p,size_t n){static const char digits[]="0123456789abcdef";for(size_t i=0;i<n;i++){put(w,digits[p[i]>>4]);put(w,digits[p[i]&15]);}}
int mm_storage_badmap_json(char *out,size_t capacity,uint8_t *record) {
    if(!out || !capacity || !record)return 0;
    out[0]=0;for(size_t i=0;i<116;i++)record[i]=0;
    uint32_t actual=0;int status=glassly_storage_badmap_read(record,&actual);
    int present=0,absent=status==7;const char *state="unavailable";
    if(absent){
        /* Native-defined absence is an effective zero map, not an acquired
         * persisted record. Never retain any partially written getter bytes. */
        for(size_t i=0;i<116;i++)record[i]=0;
        state="absent";
    }else if(status==0){
        present=actual==116 && le32(record)==0x474d4231u && le32(record+4)==1 &&
            le32(record+8)==0x01500000u && le32(record+12)==0x00300000u &&
            le32(record+112)==glassly_storage_badmap_crc(record) &&
            glassly_storage_badmap_valid(record+16)!=0;
        state=present?"present":"invalid";
    }
    writer w={out,capacity,0,0};
    text(&w,"{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"diagnostic\":\"badmap\"");
    field(&w,"kvStatus",(uint32_t)status);field(&w,"actualLength",actual);
    text(&w,",\"recordState\":\"");text(&w,state);text(&w,"\",\"mapHex\":\"");
    if(present || absent)hex(&w,record+16,96);
    text(&w,"\",\"recordHex\":\"");if(present)hex(&w,record,116);
    text(&w,"\"}");
    if(w.failed){out[0]=0;return 0;}out[w.used]=0;return 1;
}
int mm_storage_topology_json(char *out,size_t capacity) {
    if(!out || !capacity)return 0;
    out[0]=0;
    mm_storage_snapshot a,b;
    glassly_storage_snapshot(&a);glassly_storage_snapshot(&b);
    int same=1;for(size_t i=0;i<22;i++)if(a.v[i]!=b.v[i])same=0;
    writer w={out,capacity,0,0};
    text(&w,"{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"diagnostic\":\"topology\"");
    field(&w,"consistent",(uint32_t)same);
    field(&w,"xip0Initialized",!!a.v[0]);field(&w,"xip1Initialized",!!a.v[1]);
    field(&w,"xip0Driver",driver(a.v[2]));field(&w,"xip1Driver",driver(a.v[3]));
    field(&w,"xip0QuadConfigured",!!a.v[4]);field(&w,"xip1QuadConfigured",!!a.v[5]);
    uint32_t valid=!!a.v[6] && driver(a.v[3])==1;
    field(&w,"xip1ProbeValid",valid);field(&w,"xip1LegacyId",valid?a.v[7]>>16:0);
    field(&w,"sharedC8ProbeValid",!!a.v[8]);
    field(&w,"generalSpiBackendKnown",a.v[9]==0x02010c6cu);
    field(&w,"generalSpiReady",!!a.v[10]);
    field(&w,"generalSpiMutexPresent",!!a.v[11]);field(&w,"generalSpiSemaphorePresent",!!a.v[12]);
    field(&w,"generalSpi0Configured",a.v[13]&3u);
    field(&w,"generalSpiPinsMatch",a.v[14]==5 && a.v[15]==102 && a.v[16]==3 && a.v[17]==4 && a.v[18]==0);
    field(&w,"cus8ContextPresent",!!a.v[19]);field(&w,"cus8ValidatedPackageState",a.v[20]&255u);
    put(&w,'}');
    if(w.failed){out[0]=0;return 0;}
    out[w.used]=0;return 1;
}
