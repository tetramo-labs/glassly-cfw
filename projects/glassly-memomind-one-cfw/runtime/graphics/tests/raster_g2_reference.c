/* Exact pinned G2 decoder; kept separate from portable symbols. Host only. */
#include G2_RLE_REFERENCE_SOURCE
int g2_rle_decode_reference(uint8_t *dst,uint32_t stride,uint32_t rowbytes,
                           uint32_t rows,const uint8_t *src,uint32_t len) {
    rle_state s;rle_init(&s,dst,stride,rowbytes,rows);rle_feed(&s,src,len);
    return !s.err && !s.left && !s.st;
}
