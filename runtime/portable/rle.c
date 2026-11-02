/* G2 commit 1a6db4fd75de202a96599cc8f9f12fa721e7c3ce, modified 2026-10-31.
 * rle.c state machine + texture_cache.c token parser; explicit bounded API and
 * prevalidation, byte stores replace word stores. Encoder follows video-bench.ts.
 * MIT; see PROVENANCE.md and LICENSE. */
#include "rle.h"
typedef struct {
    uint8_t *base;
    uint32_t stride;      /* bytes between rows in the destination */
    uint32_t rowbytes;    /* bytes per row actually written */
    uint32_t rows;
    uint32_t r;           /* current row */
    uint32_t bpos;        /* byte offset within the current row */
    uint32_t hi;          /* 1 = next nibble is the high (left) one */
    uint32_t left;        /* nibbles still expected */
    uint32_t st;          /* token parser: 0 = opcode, 1 = cnt8, 2 = cntLo, 3 = cntHi */
    uint32_t cnt;
    uint8_t  color;
    uint8_t  err;
} rle_state;



static void rle_init(rle_state *s, uint8_t *base, uint32_t stride,
                     uint32_t rowbytes, uint32_t rows) {
    s->base = base; s->stride = stride; s->rowbytes = rowbytes; s->rows = rows;
    s->r = 0; s->bpos = 0; s->hi = 1;
    s->left = rowbytes * rows * 2;
    s->st = 0; s->cnt = 0; s->color = 0; s->err = 0;
}

/* Write `n` pixels of color `v`. Aligned whole-byte spans are filled a byte at a time
 * (both nibbles at once, v*0x11); only a leading/trailing odd nibble is read-modify-
 * written. */
static void rle_emit(rle_state *s, uint8_t v, uint32_t n) {
    if (n > s->left) { s->err = 1; return; }        /* overruns the frame -> malformed */
    s->left -= n;
    uint8_t pair = (uint8_t)(v * 0x11u);
    while (n) {
        if (s->r >= s->rows) { s->err = 1; return; }
        uint8_t *row = s->base + s->r * s->stride;
        if (!s->hi) {                                /* finish the byte we're inside */
            row[s->bpos] = (uint8_t)((row[s->bpos] & 0xf0u) | v);
            s->bpos++; s->hi = 1; n--;
        } else {
            uint32_t avail = s->rowbytes - s->bpos;  /* whole bytes left in this row */
            uint32_t bytes = n >> 1;
            if (bytes > avail) bytes = avail;
            /* Byte stores preserve arbitrary alignment and C effective types. */
            for (uint32_t i = 0; i < bytes; i++) row[s->bpos + i] = pair;
            s->bpos += bytes; n -= bytes * 2;
            if (n && s->bpos < s->rowbytes) {        /* odd tail: open the next byte */
                row[s->bpos] = (uint8_t)((row[s->bpos] & 0x0fu) | (uint8_t)(v << 4));
                s->hi = 0; n--;
            }
        }
        if (s->hi && s->bpos >= s->rowbytes) { s->bpos = 0; s->r++; }   /* next row */
    }
}

/* Feed `n` bytes of RLE stream. Stops early (leaving err set) on a malformed stream. */
static void rle_feed(rle_state *s, const uint8_t *p, uint32_t n) {
    for (uint32_t i = 0; i < n && !s->err; i++) {
        uint8_t b = p[i];
        if (s->st == 0) {
            s->color = (uint8_t)(b & 0x0fu);
            uint32_t c = b >> 4;
            if (c) rle_emit(s, s->color, c);         /* short form: count in the high nibble */
            else s->st = 1;                          /* escape: count follows */
        } else if (s->st == 1) {
            if (b) { rle_emit(s, s->color, b); s->st = 0; }
            else s->st = 2;                          /* second escape: 16-bit count follows */
        } else if (s->st == 2) {
            s->cnt = b; s->st = 3;
        } else {
            s->cnt |= (uint32_t)b << 8;
            if (s->cnt == 0) s->err = 1;             /* a 0-length run can't be encoded */
            else rle_emit(s, s->color, s->cnt);
            s->st = 0;
        }
    }
}

static int rle_token(const uint8_t *p, size_t len,
                                 uint32_t *used, uint32_t *count,
                                 uint8_t *color) {
    if (len < 1) return 0;
    uint8_t op = p[0];
    *color = (uint8_t)(op & 0x0fu);
    uint32_t n = op >> 4;
    if (n) {
        *used = 1;
        *count = n;
        return 1;
    }
    if (len < 2) return 0;
    n = p[1];
    if (n) {
        *used = 2;
        *count = n;
        return 1;
    }
    if (len < 4) return 0;
    n = (uint32_t)p[2] | ((uint32_t)p[3] << 8);
    if (n == 0) return 0;
    *used = 4;
    *count = n;
    return 1;
}

static int overlaps(const void *a, size_t an, const void *b, size_t bn) {
    if (!an || !bn) return 0;
    uintptr_t x=(uintptr_t)a, y=(uintptr_t)b;
    return x<=y ? y-x<an : x-y<bn;
}
int mm_rle_validate(const uint8_t *src, size_t length, uint32_t expected_pixels) {
    if (!src || !expected_pixels) return MM_RLE_MESSAGE;
    size_t pos=0; uint32_t left=expected_pixels;
    while (pos<length) {
        uint32_t used, count; uint8_t color;
        if (!rle_token(src+pos,length-pos,&used,&count,&color) || count>left)
            return MM_RLE_MESSAGE;
        pos+=used; left-=count;
    }
    return left ? MM_RLE_MESSAGE : MM_RLE_OK;
}
int mm_rle_surface_validate(const mm_rle_surface *s) {
    if (!s || !s->pixels || !s->rowbytes || !s->rows || s->stride<s->rowbytes ||
        s->rowbytes>UINT32_MAX/2u/s->rows || s->stride>UINT32_MAX/s->rows ||
        (size_t)s->stride>s->bytes/s->rows) return MM_RLE_TARGET;
    if (overlaps(s,sizeof(*s),s->pixels,s->bytes)) return MM_RLE_TARGET;
    return MM_RLE_OK;
}
int mm_rle_decode(const mm_rle_surface *s, const uint8_t *src, size_t length) {
    if (mm_rle_surface_validate(s)) return MM_RLE_TARGET;
    if (length>UINT32_MAX) return MM_RLE_MESSAGE;
    int valid=mm_rle_validate(src,length,s->rowbytes*s->rows*2u);
    if (valid) return valid;
    if (overlaps(s->pixels,s->bytes,src,length)) return MM_RLE_ALIAS;
    rle_state state; rle_init(&state,s->pixels,s->stride,s->rowbytes,s->rows);
    rle_feed(&state,src,(uint32_t)length);
    return state.err || state.left || state.st ? MM_RLE_MESSAGE : MM_RLE_OK;
}
int mm_rle_decode_window(const mm_rle_surface *s,uint32_t x,uint32_t y,
                         uint32_t width,uint32_t height,const uint8_t *src,size_t length) {
    if(!s || sizeof(*s)>UINTPTR_MAX-(uintptr_t)s || mm_rle_surface_validate(s) ||
       s->bytes>UINTPTR_MAX-(uintptr_t)s->pixels || !width || !height ||
       x>s->rowbytes || width>s->rowbytes-x || y>s->rows || height>s->rows-y)
        return MM_RLE_TARGET;
    if(!src || length>UINT32_MAX || length>UINTPTR_MAX-(uintptr_t)src)
        return MM_RLE_MESSAGE;
    if(overlaps(s,sizeof(*s),src,length) || overlaps(s->pixels,s->bytes,src,length))
        return MM_RLE_ALIAS;
    int valid=mm_rle_validate(src,length,width*height*2u);
    if(valid)return valid;
    rle_state state;rle_init(&state,s->pixels+(size_t)y*s->stride+x,s->stride,width,height);
    rle_feed(&state,src,(uint32_t)length);
    return state.err || state.left || state.st ? MM_RLE_MESSAGE:MM_RLE_OK;
}
static uint8_t nibble(const mm_rle_surface *s, uint32_t i) {
    uint32_t b=i>>1;
    uint8_t v=s->pixels[(b/s->rowbytes)*s->stride+b%s->rowbytes];
    return (i&1u) ? v&15u : v>>4;
}
static size_t encode_pass(const mm_rle_surface *s, uint8_t *dst) {
    uint32_t n=s->rowbytes*s->rows*2u, i=0;
    size_t o=0;
    while (i<n) {
        uint8_t v=nibble(s,i); uint32_t j=i+1;
        while (j<n && nibble(s,j)==v) j++;
        uint32_t run=j-i;
        while (run) {
            uint32_t c=run>65535u ? 65535u : run;
            if (c<=15u) { if (dst) dst[o]=(uint8_t)((c<<4)|v); o++; }
            else if (c<=255u) {
                if (dst) { dst[o]=v; dst[o+1]=(uint8_t)c; } o+=2;
            } else {
                if (dst) { dst[o]=v; dst[o+1]=0; dst[o+2]=(uint8_t)c; dst[o+3]=(uint8_t)(c>>8); } o+=4;
            }
            run-=c;
        }
        i=j;
    }
    return o;
}
int mm_rle_encode(const mm_rle_surface *s, uint8_t *dst, size_t capacity, size_t *written) {
    if (!written) return MM_RLE_TARGET;
    /* Check metadata and aliases before writing the result pointer. */
    if (s && overlaps(written,sizeof(*written),s,sizeof(*s))) return MM_RLE_ALIAS;
    if (s && s->pixels && overlaps(written,sizeof(*written),s->pixels,s->bytes)) return MM_RLE_ALIAS;
    if (dst && overlaps(written,sizeof(*written),dst,capacity)) return MM_RLE_ALIAS;
    *written=0;
    if (mm_rle_surface_validate(s)) return MM_RLE_TARGET;
    if (!dst && capacity) return MM_RLE_TARGET;
    if (dst && (overlaps(s->pixels,s->bytes,dst,capacity) ||
                overlaps(s,sizeof(*s),dst,capacity))) return MM_RLE_ALIAS;
    size_t needed=encode_pass(s,0); *written=needed;
    if (!dst) return MM_RLE_OK;
    if (capacity<needed) return MM_RLE_CAPACITY;
    encode_pass(s,dst);
    return MM_RLE_OK;
}
