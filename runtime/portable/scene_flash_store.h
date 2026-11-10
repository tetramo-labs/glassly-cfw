#ifndef MM_SCENE_FLASH_STORE_H
#define MM_SCENE_FLASH_STORE_H
#include "scene_store.h"
#include "flash_store.h"
/* Bind an already initialized flash store. Scene owns only its logical epoch;
 * caller retains physical reservation, callback context and scratch lifetime. */
int mm_scene_flash_store_bind(mm_scene_store *,mm_flash_store *);
#endif
