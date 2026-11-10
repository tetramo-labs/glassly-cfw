/* Bounded RLE differential, original fixture and adversarial tests. MIT. */
#include "../rle.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int g2_rle_decode_reference(uint8_t *,uint32_t,uint32_t,uint32_t,const uint8_t *,uint32_t);
uint32_t g2_rle_fixture(uint8_t *,uint32_t,uint32_t,uint8_t);
int g2_rle_asset_valid(const uint8_t *,uint32_t);
static uint32_t seed=0x91fc1071;
static unsigned comparisons;
static uint32_t rnd(void) { seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed; }
static void u32(FILE *f,uint32_t n) { for(unsigned i=0;i<4;i++) fputc((n>>(8*i))&255,f); }
static void roundtrip(FILE *f,uint32_t rowbytes,uint32_t rows,uint32_t stride,unsigned pattern) {
    size_t bytes=(size_t)stride*rows;
    uint8_t *a=malloc(bytes+66),*b=malloc(bytes+66),*c=malloc(bytes+66);
    uint8_t *encoded=malloc((size_t)rowbytes*rows*2+2);
    assert(a && b && c && encoded);
    memset(a,0xa5,bytes+66);memset(b,0xa5,bytes+66);memset(c,0xa5,bytes+66);
    for(uint32_t y=0;y<rows;y++)for(uint32_t x=0;x<rowbytes;x++)
        a[33+y*stride+x]=pattern<16 ? pattern*17 : pattern==16 ? (uint8_t)rnd() : (uint8_t)(((x+y)%127 ? 15 : 2)*17);
    mm_rle_surface input={a+33,bytes,rowbytes,rows,stride},output={b+33,bytes,rowbytes,rows,stride};
    size_t needed=0,n=0;
    assert(mm_rle_encode(&input,0,0,&needed)==0 && needed>0);
    memset(encoded,0xa5,(size_t)rowbytes*rows*2+2);
    assert(mm_rle_encode(&input,encoded,needed-1,&n)==MM_RLE_CAPACITY && n==needed);
    for(size_t i=0;i<(size_t)rowbytes*rows*2+2;i++)assert(encoded[i]==0xa5);
    assert(mm_rle_encode(&input,encoded,needed,&n)==0 && n==needed && encoded[n]==0xa5);
    assert(mm_rle_validate(encoded,n,rowbytes*rows*2)==0);
    assert(mm_rle_decode(&output,encoded,n)==0);
    assert(g2_rle_decode_reference(c+33,stride,rowbytes,rows,encoded,(uint32_t)n));
    assert(!memcmp(a,b,bytes+66) && !memcmp(a,c,bytes+66));
    /* Corpus for comparison with actual upstream TypeScript encoder. */
    u32(f,rowbytes*rows);u32(f,(uint32_t)n);
    for(uint32_t y=0;y<rows;y++)assert(fwrite(a+33+y*stride,1,rowbytes,f)==rowbytes);
    assert(fwrite(encoded,1,n,f)==n);
    comparisons++;free(a);free(b);free(c);free(encoded);
}
static void unchanged(const uint8_t *src,size_t len) {
    uint8_t pixels[80],before[80];memset(pixels,0xa5,sizeof pixels);memcpy(before,pixels,sizeof pixels);
    mm_rle_surface s={pixels+1,78,3,6,13};
    assert(mm_rle_decode(&s,src,len)!=0 && !memcmp(before,pixels,sizeof pixels));
}
static void malformed(void) {
    const uint8_t valid[]={3,36},zero[]={3,0,0,0},over[]={3,37},under[]={3,35};
    unchanged(valid,0);unchanged(valid,1);unchanged(zero,4);unchanged(over,2);unchanged(under,2);unchanged(0,2);
    const uint8_t longform[]={3,0,36,0};
    for(size_t i=0;i<4;i++)unchanged(longform,i);
    const uint8_t trailing[]={3,36,0},extra[]={3,36,0x13};
    unchanged(trailing,3);unchanged(extra,3);
    uint8_t memory[80];memset(memory,0xa5,sizeof memory);memory[0]=3;memory[1]=36;
    mm_rle_surface s={memory,78,3,6,13};size_t n=0;
    assert(mm_rle_decode(&s,memory,2)==MM_RLE_ALIAS);
    assert(mm_rle_encode(&s,memory,sizeof memory,&n)==MM_RLE_ALIAS);
    assert(mm_rle_encode(&s,(uint8_t *)(void *)&s,sizeof s,&n)==MM_RLE_ALIAS);
    assert(mm_rle_encode(&s,0,0,(size_t *)(void *)&s)==MM_RLE_ALIAS);
    assert(mm_rle_encode(&s,memory+79,0,&n)==MM_RLE_CAPACITY);
    assert(mm_rle_encode(&s,0,1,&n)==MM_RLE_TARGET);
    assert(mm_rle_encode(&s,0,0,0)==MM_RLE_TARGET);
    assert(mm_rle_encode(&s,0,0,(size_t *)(void *)memory)==MM_RLE_ALIAS);
    assert(mm_rle_validate(valid,2,0)==MM_RLE_MESSAGE);
    assert(mm_rle_surface_validate(0)==MM_RLE_TARGET);
    mm_rle_surface alias={(uint8_t *)(void *)&s,sizeof s,1,1,1};
    s=alias; assert(mm_rle_surface_validate(&s)==MM_RLE_TARGET);
    s=(mm_rle_surface){memory,78,3,6,13};
    s.bytes=77;assert(mm_rle_surface_validate(&s)==MM_RLE_TARGET);
    s.bytes=SIZE_MAX;s.rows=UINT32_MAX;s.rowbytes=3;assert(mm_rle_surface_validate(&s)==MM_RLE_TARGET);
    s.rows=1;s.rowbytes=1;s.stride=0;assert(mm_rle_surface_validate(&s)==MM_RLE_TARGET);
    s.stride=1;s.pixels=0;assert(mm_rle_surface_validate(&s)==MM_RLE_TARGET);
}
static void tokens_and_original_fixture(void) {
    /* Every count and color, including legal noncanonical wider forms. */
    for(unsigned color=0;color<16;color++)for(uint32_t n=1;n<=65535;n++) {
        uint8_t b[4]={(uint8_t)color,0,(uint8_t)n,(uint8_t)(n>>8)};
        assert(mm_rle_validate(b,4,n)==0);
        assert(mm_rle_validate(b,4,n+1)==MM_RLE_MESSAGE);
        if(n<=255) {b[1]=(uint8_t)n;assert(mm_rle_validate(b,2,n)==0);}
        if(n<=15) {b[0]=(uint8_t)((n<<4)|color);assert(mm_rle_validate(b,1,n)==0);}
    }
    /* Exact upstream host/shapes test_assets fixture and mutation. The original
     * cache/refusal predicate remains unported; this checks its RLE boundary. */
    uint8_t img[64];uint32_t il=g2_rle_fixture(img,24,24,12);
    assert(g2_rle_asset_valid(img,il) && mm_rle_validate(img+2,il-2,24*24)==0);
    img[il-1]=0x11;
    assert(!g2_rle_asset_valid(img,il) && mm_rle_validate(img+2,il-2,24*24)==MM_RLE_MESSAGE);
    /* Odd cached image pixels deliberately differ from packed row padding. */
    il=g2_rle_fixture(img,3,3,4);
    assert(g2_rle_asset_valid(img,il) && mm_rle_validate(img+2,il-2,9)==0);
    assert(mm_rle_validate(img+2,il-2,12)==MM_RLE_MESSAGE);
    /* Small arbitrary token streams: exact upstream acceptance comparison. */
    for(unsigned trial=0;trial<20000;trial++) {
        uint8_t src[16],a[32],b[32];unsigned len=rnd()%17;
        for(unsigned i=0;i<len;i++)src[i]=(uint8_t)rnd();
        memset(a,0xa5,sizeof a);memset(b,0xa5,sizeof b);
        mm_rle_surface s={a,32,4,4,8};
        int old=g2_rle_decode_reference(b,8,4,4,src,len);
        assert((mm_rle_validate(src,len,32)==0)==old);
        assert((mm_rle_decode(&s,src,len)==0)==old);
        if(old)assert(!memcmp(a,b,sizeof a));
        else for(unsigned i=0;i<sizeof a;i++)assert(a[i]==0xa5);
    }
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *f=fopen(argv[1],"wb");assert(f);
    const uint32_t sizes[]={1,7,8,15,127,128,255,32767,32768,65535,65536};
    for(unsigned c=0;c<16;c++)for(unsigned i=0;i<sizeof sizes/sizeof sizes[0];i++)roundtrip(f,sizes[i],1,sizes[i]+1,c);
    roundtrip(f,300,350,320,16);roundtrip(f,300,175,320,17);
    for(unsigned i=0;i<200;i++)roundtrip(f,1+rnd()%99,1+rnd()%12,120,16+i%2);
    assert(fclose(f)==0);malformed();tokens_and_original_fixture();
    printf("PASS: %u RLE original-decoder comparisons/encoder corpus cases; 1048560 count/color combinations; 20000 malformed differential streams; original image fixture\n",comparisons);
}
