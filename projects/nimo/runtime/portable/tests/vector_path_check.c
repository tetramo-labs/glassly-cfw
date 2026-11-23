/* Portable equivalent of pinned vector_path_check.c stdin compiler harness. MIT. */
#include "../vector.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    uint8_t data[MM_VECTOR_MAX_BYTES+1];
    size_t size=fread(data,1,sizeof(data),stdin);
    if(ferror(stdin))return 2;
    mm_vector_work *work=calloc(1,sizeof(*work));
    if(!work)return 2;
    int edges=mm_vector_compile(work,sizeof(*work),data,size,0,0,0);
    free(work);printf("%d\n",edges);return edges<0?1:0;
}
