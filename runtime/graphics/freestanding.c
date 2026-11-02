/* Compiler-emitted aggregate copies in the size-optimized RV32 build. */
#include <stddef.h>
void *memcpy(void *to,const void *from,size_t n){
    unsigned char *d=to;const unsigned char *s=from;
    for(size_t i=0;i<n;i++)d[i]=s[i];
    return to;
}
