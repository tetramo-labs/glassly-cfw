#include "flash_store_native.h"
#include <stddef.h>
const uint32_t mm_flash_native_layout[]={sizeof(mm_flash_native),offsetof(mm_flash_native,last_native_status),offsetof(mm_flash_native,verification),offsetof(mm_flash_native,busy),offsetof(mm_flash_native,phase)};
