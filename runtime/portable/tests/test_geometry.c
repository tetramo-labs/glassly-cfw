/* Host-only differential and boundary tests. MIT; see LICENSE. */
#include "../geometry.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int g2_geometry_reference(const mm_raster *, const uint8_t *, size_t);
static unsigned comparisons;
static uint32_t random_state = 0x13579bdf;
static uint32_t random32(void) {
    uint32_t v = random_state;
    v ^= v << 13; v ^= v >> 17; v ^= v << 5;
    return random_state = v;
}
static void record(uint8_t *r, uint8_t type, uint8_t color, uint8_t width, const int *p) {
    r[0] = type; r[1] = 0xff; r[2] = color; r[3] = width;
    for (unsigned i = 0; i < 8; i++) {
        unsigned v = (unsigned)(uint16_t)p[i];
        r[4 + 2*i] = (uint8_t)v; r[5 + 2*i] = (uint8_t)(v >> 8);
    }
}
static void sentinels(const uint8_t *base, const mm_raster *t) {
    for (unsigned i = 0; i < 33; i++) assert(base[i] == 0xa5);
    for (unsigned i = 0; i < 33; i++) assert(t->pixels[t->bytes + i] == 0xa5);
    for (unsigned y = 0; y < t->height; y++) {
        unsigned rowbytes = (t->width + 1) / 2;
        if (t->width & 1) assert((t->pixels[y*t->stride + rowbytes - 1] & 15) == 5);
        for (unsigned x = rowbytes; x < t->stride; x++) assert(t->pixels[y*t->stride + x] == 0xa5);
    }
}
static void compare(unsigned w, unsigned h, unsigned stride, const uint8_t *packet, size_t length) {
    size_t bytes = (size_t)stride * h;
    uint8_t *a = malloc(bytes + 66), *b = malloc(bytes + 66);
    assert(a && b); memset(a, 0xa5, bytes + 66); memset(b, 0xa5, bytes + 66);
    mm_raster ours = {a + 33, bytes, w, h, stride}, original = {b + 33, bytes, w, h, stride};
    assert(mm_geometry_validate_message(packet,length)==0);
    assert(mm_geometry_mode36(&ours, packet, length) == 0);
    assert(g2_geometry_reference(&original, packet, length) == 0);
    if (memcmp(a, b, bytes + 66)) {
        fprintf(stderr, "Pixel mismatch comparison %u, type %u, %ux%u stride %u\n",
                comparisons, length > 2 ? packet[2] : 0, w, h, stride);
        abort();
    }
    sentinels(a, &ours); sentinels(b, &original);
    comparisons++; free(a); free(b);
}
static void differential(void) {
    const int examples[13][8] = {
        {-20,5,620,345,0,0,0,0}, {30,40,200,80,14,0,0,0}, {201,200,170,90,17,0,0,0},
        {300,175,90,0,0,0,0,0}, {1,1,2,0,0,0,0,0}, {10,10,200,50,90,320,0,0},
        {-9,-9,150,90,5,352,0,0}, {50,10,300,20,590,300,45,90},
        {12,12,580,20,590,340,5,90}, {3,3,620,30,290,340,0,0},
        {1,349,20,0,580,350,599,0}, {300,175,120,-45,290,0,0,0},
        {300,175,110,90,-180,0,0,0}
    };
    const unsigned dimensions[5][3] = {{600,350,300},{600,350,320},{600,175,320},{601,351,311},{31,23,21}};
    uint8_t packet[MM_GEOMETRY_MAX_MESSAGE] = {36,1};
    for (unsigned dim = 0; dim < 5; dim++) {
        for (unsigned type = 1; type <= 13; type++) {
            const unsigned widths[] = {0,1,2,17,255};
            for (unsigned k = 0; k < 5; k++) {
                record(packet + 2, type, 0xcf, widths[k], examples[type - 1]);
                compare(dimensions[dim][0], dimensions[dim][1], dimensions[dim][2], packet, 22);
            }
        }
    }
    for (unsigned trial = 0; trial < 500; trial++) {
        int p[8];
        for (unsigned i = 0; i < 8; i++) p[i] = trial & 1 ? (int)(random32() % 1600) - 500 : (int)(random32() & 65535) - 32768;
        record(packet + 2, 1 + random32() % 13, random32(), random32(), p);
        compare(600,350,303,packet,22);
    }
    packet[1] = 255;
    for (unsigned i = 0; i < 255; i++) record(packet + 2 + 20*i, 1 + i%13, i, i%8, examples[i%13]);
    compare(600,350,300,packet,sizeof(packet));
    compare(640,480,320,packet,sizeof(packet));
    packet[1] = 0; compare(601,351,311,packet,2);
}
static void reject_unchanged(mm_raster *t, const uint8_t *message, size_t length, int expected) {
    uint8_t before[256]; assert(t->bytes <= sizeof(before));
    memcpy(before,t->pixels,t->bytes);
    if(expected != MM_GEOMETRY_ALIAS) assert(mm_geometry_validate_message(message,length) == expected);
    assert(mm_geometry_mode36(t,message,length) == expected);
    assert(!memcmp(before,t->pixels,t->bytes));
}
static void malformed(void) {
    uint8_t buffer[256], packet[43] = {36,2}; memset(buffer,0xa5,sizeof(buffer));
    mm_raster t = {buffer, sizeof(buffer),31,8,32};
    int p[8] = {0,0,10,6,0,0,0,0};
    record(packet+2,3,15,0,p); record(packet+22,5,3,0,p);
    for (size_t length = 0; length < 42; length++) reject_unchanged(&t,packet,length,MM_GEOMETRY_MESSAGE);
    reject_unchanged(&t,packet,43,MM_GEOMETRY_MESSAGE);
    reject_unchanged(&t,0,42,MM_GEOMETRY_MESSAGE);
    packet[22]=14; reject_unchanged(&t,packet,42,MM_GEOMETRY_UNSUPPORTED);
    packet[22]=0; reject_unchanged(&t,packet,42,MM_GEOMETRY_UNSUPPORTED);
    packet[22]=255; reject_unchanged(&t,packet,42,MM_GEOMETRY_UNSUPPORTED);
    packet[22]=1; packet[0]=0xa4; reject_unchanged(&t,packet,42,MM_GEOMETRY_UNSUPPORTED);
    packet[0]=35; reject_unchanged(&t,packet,42,MM_GEOMETRY_UNSUPPORTED);
    buffer[0]=36; buffer[1]=0; reject_unchanged(&t,buffer,2,MM_GEOMETRY_ALIAS);
    t.stride=15; assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
    t.stride=32;t.bytes=255;assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
    t.bytes=256;t.height=0;assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
    t.height=8;t.width=4097;assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
    t.width=31;t.pixels=0;assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
    assert(mm_raster_validate(0)==MM_GEOMETRY_TARGET);
    t.pixels=buffer;t.stride=UINT32_MAX;t.height=2;t.bytes=SIZE_MAX;
    assert(mm_raster_validate(&t)==MM_GEOMETRY_TARGET);
}
static void pixels(void) {
    uint8_t buffer[66];memset(buffer,0xa5,sizeof(buffer));
    mm_raster t={buffer+1,64,9,8,8};
    assert(mm_raster_pixel(&t,0,0,0x13)==0 && buffer[1]==0x35);
    assert(mm_raster_pixel(&t,1,0,0x2e)==0 && buffer[1]==0x3e);
    assert(mm_raster_pixel(&t,-1,0,0)==0 && buffer[1]==0x3e);
    assert(mm_raster_pixel(&t,INT32_MAX,INT32_MIN,0)==0);
    assert(mm_raster_span(&t,INT32_MIN,INT32_MAX,1,2)==0);
    assert(buffer[9]==0x22 && buffer[13]==0x25 && buffer[14]==0xa5);
    assert(mm_raster_clear(&t,7)==0);
    for(unsigned y=0;y<8;y++){
        for(unsigned x=0;x<4;x++)assert(buffer[1+y*8+x]==0x77);
        assert(buffer[1+y*8+4]==0x75);
        for(unsigned x=5;x<8;x++)assert(buffer[1+y*8+x]==0xa5);
    }
    assert(buffer[0]==0xa5 && buffer[65]==0xa5);
}
int main(void) {
    differential(); malformed(); pixels();
    printf("PASS: %u original-G2 pixel comparisons; GRAY4 nibble/padding guards; malformed input unchanged\n",comparisons);
    return 0;
}
