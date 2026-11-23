/* Layout witness compiled for host and actual RV32 ABI. MIT. */
#include "../../scene.c"
const uint32_t mm_scene_layout[]={sizeof(mm_scene_context),sizeof(mm_scene_platform),sizeof(cfw_cache),sizeof(cfw_txn),sizeof(cfw_object),sizeof(cfw_asset),sizeof(cfw_undo),sizeof(((cfw_undo *)0)->granules[0]),sizeof(cfw_vector_work)};
#ifdef MM_SCENE_HOST_LAYOUT
#include <stdio.h>
int main(void){for(unsigned i=0;i<sizeof(mm_scene_layout)/sizeof(mm_scene_layout[0]);i++)printf("%u\n",mm_scene_layout[i]);}
#endif
