#include "storage_diag.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static mm_storage_snapshot sample;
static unsigned calls;
static int change=-1;
static uint8_t record[116];
static uint32_t actual=116;
static int kv_status;
static unsigned get_calls,crc_calls,valid_calls;
static uint32_t crc(const uint8_t *p){uint32_t n=0xffffffffu;for(unsigned i=0;i<112;i++){n^=p[i];for(unsigned b=0;b<8;b++)n=(n>>1)^((n&1)?0xedb88320u:0);}return ~n;}
static void word(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
int glassly_storage_badmap_read(uint8_t *out,uint32_t *length){for(unsigned i=0;i<116;i++)assert(!out[i]);assert(!*length);get_calls++;memcpy(out,record,116);*length=actual;return kv_status;}
uint32_t glassly_storage_badmap_crc(const uint8_t *p){crc_calls++;return crc(p);}
int glassly_storage_badmap_valid(const uint8_t *p){valid_calls++;return !p[0]&&!p[1];}
static void map_fixture(void){memset(record,0,116);word(record,0x474d4231);word(record+4,1);word(record+8,0x01500000);word(record+12,0x00300000);record[80]=1;record[111]=128;word(record+112,crc(record));actual=116;kv_status=0;}
static void map_render(char *out){uint8_t owned[118];memset(owned,0xa5,sizeof(owned));get_calls=crc_calls=valid_calls=0;assert(mm_storage_badmap_json(out,768,owned+1));assert(get_calls==1);assert(owned[0]==0xa5&&owned[117]==0xa5);}
void glassly_storage_snapshot(mm_storage_snapshot *out) {
    *out=sample;
    if(calls++==1 && change>=0)out->v[change]^=1;
}
static void reset(void){calls=0;change=-1;memset(&sample,0,sizeof(sample));}
static void render(char *out){calls=0;assert(mm_storage_topology_json(out,768));assert(calls==2);assert(strlen(out)<768);}
static void has(const char *out,const char *field,unsigned value){char expected[80];snprintf(expected,sizeof(expected),"\"%s\":%u",field,value);assert(strstr(out,expected));}
int main(void) {
    char out[768];reset();render(out);has(out,"consistent",1);has(out,"xip1Driver",0);has(out,"xip1LegacyId",0);puts(out);
    sample=(mm_storage_snapshot){{1,1,0x020107f0,0x02010898,1,1,1,0x851712ab,1,0x02010c6c,1,0x12345678,0x87654321,3,5,102,3,4,0,0xdeadbeef,255,0}};
    render(out);has(out,"xip0Driver",2);has(out,"xip1Driver",1);has(out,"xip1LegacyId",0x8517);has(out,"generalSpiPinsMatch",1);has(out,"cus8ContextPresent",1);has(out,"cus8ValidatedPackageState",255);puts(out);
    char baseline[768];strcpy(baseline,out);
    for(unsigned n=0;n<65536;n++){sample.v[7]=0x85170000u|n;render(out);assert(!strcmp(baseline,out));}
    for(unsigned n=0;n<22;n++){change=(int)n;render(out);has(out,"consistent",0);}change=-1;
    sample.v[6]=0;render(out);has(out,"xip1ProbeValid",0);has(out,"xip1LegacyId",0);
    sample.v[6]=1;sample.v[3]=0x020107f0;render(out);has(out,"xip1Driver",2);has(out,"xip1ProbeValid",0);has(out,"xip1LegacyId",0);
    sample.v[3]=0x12345678;render(out);has(out,"xip1Driver",3);has(out,"xip1LegacyId",0);assert(!strstr(out,"305419896"));
    for(unsigned n=14;n<=18;n++){sample.v[n]^=1;render(out);has(out,"generalSpiPinsMatch",0);sample.v[n]^=1;}
    sample.v[9]=0x02010c6d;render(out);has(out,"generalSpiBackendKnown",0);
    size_t need=strlen(out)+1;
    for(size_t n=1;n<=768;n++){
        unsigned char guarded[770];memset(guarded,0xa5,sizeof(guarded));calls=0;
        int ok=mm_storage_topology_json((char *)guarded+1,n);assert(calls==2);assert(ok==(n>=need));
        assert(guarded[0]==0xa5);for(size_t i=n+1;i<770;i++)assert(guarded[i]==0xa5);
        if(!ok)assert(guarded[1]==0);
    }
    calls=0;assert(!mm_storage_topology_json(0,768));assert(!mm_storage_topology_json(out,0));assert(!calls);
    map_fixture();map_render(out);assert(strstr(out,"\"recordState\":\"present\""));assert(crc_calls==1&&valid_calls==1);puts(out);
    for(unsigned i=0;i<116;i++){
        map_fixture();record[i]^=1;map_render(out);assert(strstr(out,"\"recordState\":\"invalid\""));assert(strstr(out,"\"mapHex\":\"\""));
    }
    for(unsigned bit=0;bit<16;bit++){
        map_fixture();record[16+bit/8]|=(uint8_t)(1u<<(bit%8));word(record+112,crc(record));map_render(out);assert(valid_calls==1);assert(strstr(out,"\"recordState\":\"invalid\""));
    }
    for(unsigned bit=16;bit<768;bit++){
        map_fixture();record[16+bit/8]|=(uint8_t)(1u<<(bit%8));word(record+112,crc(record));map_render(out);assert(strstr(out,"\"recordState\":\"present\""));
    }
    for(unsigned n=0;n<120;n++){if(n==116)continue;map_fixture();actual=n;map_render(out);assert(!crc_calls&&!valid_calls);assert(strstr(out,"\"recordState\":\"invalid\""));}
    map_fixture();actual=0;kv_status=7;map_render(out);assert(!crc_calls&&!valid_calls);assert(strstr(out,"\"recordState\":\"absent\""));assert(strstr(out,"\"recordHex\":\"\""));puts(out);
    for(int code=1;code<=13;code++){if(code==7)continue;kv_status=code;map_render(out);assert(!crc_calls&&!valid_calls);assert(strstr(out,"\"recordState\":\"unavailable\""));assert(strstr(out,"\"mapHex\":\"\""));}puts(out);
    map_fixture();record[0]^=1;map_render(out);puts(out);
    map_fixture();map_render(out);need=strlen(out)+1;
    for(size_t n=1;n<=768;n++){
        unsigned char guarded[770],owned[116];memset(guarded,0xa5,sizeof(guarded));
        int ok=mm_storage_badmap_json((char *)guarded+1,n,owned);assert(ok==(n>=need));
        assert(guarded[0]==0xa5);for(size_t i=n+1;i<770;i++)assert(guarded[i]==0xa5);if(!ok)assert(!guarded[1]);
    }
    get_calls=0;assert(!mm_storage_badmap_json(0,768,record));assert(!mm_storage_badmap_json(out,0,record));assert(!mm_storage_badmap_json(out,768,0));assert(!get_calls);
    puts("PASS topology:65536 UID exclusions,22 changed-snapshot fields,768 capacity boundaries,normalized pointers and invalid probes");
    puts("PASS badmap:116 record corruptions,768 sector bits,119 wrong lengths,absence/errors,768 capacity boundaries; one read per query");
}
