/* Pinned H001Y1.0.3.127 RAM slots; see flash-topology/diagnostics.md.
 * The snapshot invokes no native function, MMIO or SPI transaction and never
 * dereferences a singleton pointer. Two samples are not an atomic snapshot.
 * Separate badmap veneers call only the reviewed getter and pure validators. */
#include "storage_diag.h"
_Static_assert(sizeof(void *)==4,"Actual RV32 native addresses required");
#define U8(a) (*(volatile const uint8_t *)(uintptr_t)(a))
#define U32(a) (*(volatile const uint32_t *)(uintptr_t)(a))
#define FN(a,t) ((t)(uintptr_t)(a))
int glassly_storage_badmap_read(uint8_t *record,uint32_t *actual) {
    typedef int (*get_fn)(uint32_t,void *,uint32_t,uint32_t *);
    return FN(0x04235032u,get_fn)(0x6009u,record,116u,actual);
}
uint32_t glassly_storage_badmap_crc(const uint8_t *record) {
    typedef uint32_t (*crc_fn)(const void *);
    return FN(0x042a9c84u,crc_fn)(record);
}
int glassly_storage_badmap_valid(const uint8_t *bitmap) {
    typedef int (*valid_fn)(const void *);
    return FN(0x042a9ccau,valid_fn)(bitmap);
}
void glassly_storage_snapshot(mm_storage_snapshot *s) {
    s->v[0]=U8(0x0201234c); s->v[1]=U8(0x0201234d);
    s->v[2]=U32(0x02012330); s->v[3]=U32(0x02012334);
    s->v[4]=U8(0x02012338); s->v[5]=U8(0x02012339);
    s->v[6]=U8(0x0205c8e0); s->v[7]=U32(0x0205c8e4);
    s->v[8]=U8(0x02012350); s->v[9]=U32(0x020124d0);
    s->v[10]=U8(0x020124d4); s->v[11]=U32(0x020124d8);
    s->v[12]=U32(0x020124dc); s->v[13]=U8(0x0205c2ac);
    s->v[14]=U32(0x0205c26c); s->v[15]=U32(0x0205c270);
    s->v[16]=U32(0x0205c274); s->v[17]=U32(0x0205c278);
    s->v[18]=U8(0x0205c27c); s->v[19]=U32(0x02011e48);
    s->v[20]=U8(0x02011e50);
    s->v[21]=0; /* Reserved internal scalar, initialized in every sample. */
}
