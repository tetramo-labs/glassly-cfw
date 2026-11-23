/* Host-only unchanged pinned G2 decoder and cached-image fixture. MIT. */
#define main unused_original_shape_suite_main
#include G2_REFERENCE_SOURCE
#undef main
#include G2_RLE_REFERENCE_SOURCE
int g2_rle_decode_reference(uint8_t *dst, uint32_t stride, uint32_t rowbytes,
                           uint32_t rows, const uint8_t *src, uint32_t len) {
    rle_state s; rle_init(&s,dst,stride,rowbytes,rows); rle_feed(&s,src,len);
    return !s.err && s.left==0 && s.st==0;
}
uint32_t g2_rle_fixture(uint8_t *dst,uint32_t w,uint32_t h,uint8_t color) {
    return mk_image(dst,w,h,color);
}
int g2_rle_asset_valid(const uint8_t *src,uint32_t len) {
    cfw_cached_image image;
    return cfw_texture_image_in(src,len,0,&image) && image.rle_len+2==len;
}
