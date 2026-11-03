/* Compiler-emitted aggregate copies in the size-optimized RV32 build. */
#include <stddef.h>
void *memcpy(void *to,const void *from,size_t n){
    unsigned char *d=to;const unsigned char *s=from;
    for(size_t i=0;i<n;i++)d[i]=s[i];
    return to;
}
void *memset(void *to,int value,size_t n){
    volatile unsigned char *d=to;
    for(size_t i=0;i<n;i++)d[i]=(unsigned char)value;
    return to;
}
