/* Test-only host zlib adapter. test_allocate/release supplied by fixture.
 * No native MemoMind inflater address/ABI is implied. */
static voidpf zalloc_test(voidpf user,uInt n,uInt size) {
    if (size && (size_t)n>SIZE_MAX/size) return NULL;
    return test_allocate(user,(size_t)n*size);
}
static void zfree_test(voidpf user,voidpf p) { test_release(user,p); }
static void test_end(void *user,void **state) {
    if (*state) {inflateEnd(*state);test_release(user,*state);*state=NULL;}
}
static int test_decode(void *user,void **state,const uint8_t *input,uint16_t bytes,
                        uint8_t *output,uint32_t capacity,uint32_t *output_bytes) {
    z_stream *z=*state;
    if (!z) {
        z=test_allocate(user,sizeof *z); if (!z) return -1;
        memset(z,0,sizeof *z);z->zalloc=zalloc_test;z->zfree=zfree_test;z->opaque=user;
        if(inflateInit2(z,15)!=Z_OK) {test_release(user,z);return -1;}
        *state=z;
    }
    z->next_in=(Bytef *)input;z->avail_in=bytes;z->next_out=output;z->avail_out=capacity;
    int result=0;
    while(z->avail_in) {
        uInt before=z->avail_in,space=z->avail_out;
        if(inflate(z,Z_NO_FLUSH)!=Z_OK || !z->avail_out ||
           (before==z->avail_in && space==z->avail_out)) {result=-1;break;}
    }
    *output_bytes=capacity-z->avail_out;
    z->next_in=NULL;z->next_out=NULL;z->avail_in=z->avail_out=0;
    return result;
}
