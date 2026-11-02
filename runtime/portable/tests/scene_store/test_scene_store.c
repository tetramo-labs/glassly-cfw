#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "scene_flash_store.h"
#define bzero mm_test_zero
#include "../../scene.c"
#define PIXELS (320u*480u)
typedef struct owner {
 mm_scene_context ctx;mm_flash_store flash;uint8_t scratch[4096],bad[32];
 uint8_t *physical,*pixels;size_t allocated,ops,reads,erases,programs,fail_at;
 uint32_t now;unsigned presents,settles;uint16_t tag;int fail_alloc,lease;
} owner;
static int bad_access(owner *o,uint32_t off,size_t n){assert(off<1048576&&n<=1048576-off);assert(!(o->bad[(off/4096)/8]&(1u<<((off/4096)%8))));return 0;}
static int io_read(void *u,uint32_t off,void *p,size_t n){owner *o=u;bad_access(o,off,n);o->reads++;if(++o->ops==o->fail_at)return -1;memcpy(p,o->physical+off,n);return 0;}
static void unowned(owner *o,uint32_t off){for(unsigned i=0;i<64;i++){assert(o->flash.active[i]!=off/4096);assert(o->flash.staged[i]!=off/4096);}}
static int io_erase(void *u,uint32_t off,size_t n){owner *o=u;bad_access(o,off,n);assert(!(off%4096)&&n==4096);unowned(o,off);o->erases++;if(++o->ops==o->fail_at){memset(o->physical+off,255,n/2);return -1;}memset(o->physical+off,255,n);return 0;}
static int io_program(void *u,uint32_t off,const void *p,size_t n){owner *o=u;bad_access(o,off,n);assert(!(off%256)&&n==256);unowned(o,off);o->programs++;const uint8_t *s=p;for(unsigned i=0;i<n;i++)assert(o->physical[off+i]==255);if(++o->ops==o->fail_at){memcpy(o->physical+off,p,n/2);return -1;}memcpy(o->physical+off,s,n);return 0;}
static void *allocate(void *u,unsigned kind,size_t n){owner *o=u;(void)kind;if(o->fail_alloc)return 0;void *p=malloc(n);assert(p);o->allocated++;return p;}
static void deallocate(void *u,unsigned kind,void *p){owner *o=u;(void)kind;assert(o->allocated);o->allocated--;free(p);}
static uint32_t now(void *u){return ((owner *)u)->now;}
static int lease(void *u){return ((owner *)u)->lease;}
static int shadow(void *u,mm_raster *r){owner *o=u;*r=(mm_raster){o->pixels,PIXELS,640,480,320};return 1;}
static uintptr_t timer_new(void *u,void (*fn)(void *),void *p){(void)u;(void)fn;(void)p;return 1;}
static void timer_start(void *u,uintptr_t t,uint32_t ms){(void)u;assert(t==1&&ms);}
static void timer_stop(void *u,uintptr_t t){(void)u;(void)t;}
static void present(void *u,mm_scene_context *ctx,const mm_raster *r,mm_scene_dirty *d){owner *o=u;(void)r;mm_scene_render_if_due(ctx,o->pixels);assert(!ctx->shadow_invalid);o->presents++;if(d)d->direct_submitted=1;}
static void settled(void *u,uint16_t tag){owner *o=u;o->settles++;o->tag=tag;}
static int builtin(void *u,const mm_raster *r,const uint8_t *p,size_t n,mm_scene_dirty *d,uint32_t *tokens,size_t cap){(void)u;(void)d;(void)tokens;assert(n==6u+p[5]&&p[5]<=cap);int32_t x=(int16_t)rd16(p),y=(int16_t)rd16(p+2);for(int32_t yy=y;yy<y+20;yy++)for(int32_t xx=x;xx<x+10*p[5];xx++)if(xx>=0&&yy>=0&&(uint32_t)xx<r->width&&(uint32_t)yy<r->height){uint8_t *v=r->pixels+yy*r->stride+xx/2;if(xx&1)*v=(*v&240)|(p[4]&15);else *v=(*v&15)|((p[4]&15)<<4);}return 0;}
static owner *create(int external){owner *o=calloc(1,sizeof(*o));assert(o);o->lease=1;o->pixels=calloc(1,PIXELS);assert(o->pixels);mm_scene_platform p={o,allocate,deallocate,now,lease,shadow,timer_new,timer_start,timer_stop,0,0,present,settled,0,builtin};
 if(external){o->physical=malloc(1048576);assert(o->physical);memset(o->physical,0x5a,1048576);o->bad[0]=1;o->bad[31]=128;o->bad[8]=8;mm_flash_geometry g={0,1048576,262144,4096,256};mm_flash_callbacks cb={o,io_read,io_erase,io_program};assert(!mm_flash_store_init(&o->flash,&g,&cb,o->bad,o->scratch,4096));mm_scene_store ops;assert(!mm_scene_flash_store_bind(&ops,&o->flash));assert(!mm_scene_init_with_store(&o->ctx,&p,&ops));}
 else assert(!mm_scene_init(&o->ctx,&p,262144));o->ctx.cache_reply_cap=245;return o;}
static void destroy(owner *o){size_t writes=o->erases+o->programs;mm_scene_release(&o->ctx);assert(writes==o->erases+o->programs);assert(!o->allocated);free(o->physical);free(o->pixels);free(o);}
static void w16(uint8_t *p,unsigned v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void w32(uint8_t *p,uint32_t v){w16(p,v);w16(p+2,v>>16);}
static int send(owner *o,const uint8_t *p,size_t n){assert(n&&n<=65535);o->ctx.cache_reply_len=0;o->ctx.direct_pending=0;mm_scene_dirty dirty={0};if(p[0]>=37&&p[0]<=41){mm_scene_prepare(&o->ctx,p[0],p+1,n-1);return mm_scene_dispatch(&o->ctx,p[0],p+1,n-1,1,&dirty);}return mm_scene_immediate(&o->ctx,&(mm_raster){o->pixels,PIXELS,640,480,320},p,n,&dirty);}
static void reset(owner *o){uint8_t p[6]={41,1,0,1,0,0};assert(!send(o,p,6));assert(o->ctx.cache_reply[3]==0);assert(rd16(o->ctx.cache_reply+11)==256);}
static void compare(owner *a,owner *b){assert(a->ctx.cache_reply_len==b->ctx.cache_reply_len);assert(!memcmp(a->ctx.cache_reply,b->ctx.cache_reply,a->ctx.cache_reply_len));assert(!memcmp(a->pixels,b->pixels,PIXELS));assert(a->settles==b->settles&&a->tag==b->tag&&a->presents==b->presents);cfw_cache *x=a->ctx.scene,*y=b->ctx.scene;assert(!!x==!!y);if(x){assert(x->revision==y->revision&&x->use_clock==y->use_clock&&x->active_count==y->active_count);assert(!memcmp(x->objects,y->objects,sizeof x->objects));assert(!memcmp(x->assets,y->assets,sizeof x->assets));assert(!memcmp(x->bitmap,y->bitmap,sizeof x->bitmap));assert(!memcmp(x->journal,y->journal,sizeof x->journal));assert(!memcmp(x->active,y->active,sizeof x->active));}}
static void pair(owner *a,owner *b,const uint8_t *p,size_t n){size_t writes=b->erases+b->programs;int x=send(a,p,n),y=send(b,p,n);if(p[0]==19||p[0]==20||p[0]==36||p[0]>=39||(p[0]==38&&p[7]==0))assert(writes==b->erases+b->programs);if(x!=y){fprintf(stderr,"mode%u results%d/%d io%u\n",p[0],x,y,b->ctx.storage_io);abort();}compare(a,b);}
static void replay(const char *name){FILE *f=fopen(name,"rb");assert(f);fseek(f,0,SEEK_END);long length=ftell(f);rewind(f);uint8_t *data=malloc((size_t)length);assert(data&&fread(data,1,(size_t)length,f)==(size_t)length);fclose(f);owner *a=create(0),*b=create(1);reset(a);reset(b);uint32_t pos=0,messages=0,probes=0;uint16_t request=0;while(pos<(uint32_t)length){uint8_t kind=data[pos++];if(kind==1){unsigned n=rd16(data+pos);pos+=2;assert(n&&n<=length-pos);uint8_t *msg=data+pos;if(msg[0]>=37&&msg[0]<=41&&!rd16(msg+1)){w16(msg+1,a->ctx.cache_epoch);if(msg[0]!=40&&!rd16(msg+3))w16(msg+3,++request);}pair(a,b,msg,n);pos+=n;messages++;}else if(kind==2){uint32_t ms=rd32(data+pos);pos+=4;while(ms){uint32_t step=ms<33?ms:33;a->now+=step;b->now+=step;a->ctx.direct_pending=b->ctx.direct_pending=0;mm_scene_tick(&a->ctx);mm_scene_tick(&b->ctx);compare(a,b);ms-=step;}}else if(kind==3){unsigned n=data[pos++];pos+=n;}else if(kind==4){unsigned x=rd16(data+pos),y=rd16(data+pos+2),color=data[pos+4];pos+=5;assert(x<640&&y<480);uint8_t v=b->pixels[y*320+x/2];assert((unsigned)(x&1?v&15:v>>4)==color);probes++;}else assert(kind==5);}
 printf("differential %s messages=%u probes=%u reads=%zu erases=%zu programs=%zu\n",name,messages,probes,b->reads,b->erases,b->programs);destroy(a);destroy(b);free(data);}

static size_t asset_message(uint8_t *p,uint16_t request,uint32_t id,uint32_t version,uint8_t kind,uint32_t total,uint32_t off,const uint8_t *data,unsigned n){p[0]=37;w16(p+1,1);w16(p+3,request);p[5]=0;w32(p+6,id);w32(p+10,version);p[14]=kind;w32(p+15,total);w32(p+19,off);w16(p+23,n);memcpy(p+25,data,n);return 25u+n;}
static void metadata_equal(const cfw_cache *a,const cfw_cache *b){
 assert(a->revision==b->revision&&a->use_clock==b->use_clock&&a->active_count==b->active_count&&a->store_bytes==b->store_bytes&&a->journal_lost_rev==b->journal_lost_rev&&a->journal_head==b->journal_head&&a->journal_count==b->journal_count);
 assert(!memcmp(a->objects,b->objects,sizeof a->objects));assert(!memcmp(a->assets,b->assets,sizeof a->assets));assert(!memcmp(a->bitmap,b->bitmap,sizeof a->bitmap));assert(!memcmp(a->journal,b->journal,sizeof a->journal));assert(!memcmp(a->active,b->active,sizeof a->active));assert(!memcmp(a->next,b->next,sizeof a->next));
}
static void full_capacity_and_faults(void){
 owner *a=create(0),*b=create(1);reset(a);reset(b);
 uint8_t *font=calloc(1,262144),*msg=malloc(65535),*logical=malloc(262144);assert(font&&msg&&logical);
 /* A complete96-entry font may have absent glyphs and arbitrary trailing data. */
 for(unsigned i=384;i<262144;i++)font[i]=(uint8_t)(i*17u);
 unsigned request=2;
 for(unsigned off=0;off<262144;){unsigned n=262144-off;if(n>65510)n=65510;size_t size=asset_message(msg,(uint16_t)request++,5,1,1,262144,off,font+off,n);pair(a,b,msg,size);assert(b->ctx.cache_reply[3]==0);off+=n;}
 assert(!mm_flash_store_read(&b->flash,0,logical,262144));assert(!memcmp(logical,font,262144));assert(b->ctx.scene->assets[0].length==262144);
 /* First replacement chunk evicts the unreferenced full asset and overwrites
  * its logical sector range. Every callback is failed after prior mutations. */
 size_t n=asset_message(msg,20,6,1,1,262144,0,font,65510);
 mm_scene_prepare(&b->ctx,37,msg+1,n-1);cfw_cache *cache=b->ctx.scene;cfw_cache *saved=malloc(sizeof(*saved));assert(saved);*saved=*cache;
 mm_flash_store before=b->flash;uint8_t *physical=malloc(1048576);assert(physical);memcpy(physical,b->physical,1048576);
 b->ops=0;assert(!send(b,msg,n));size_t boundaries=b->ops;assert(boundaries>500);
 for(size_t fail=1;fail<=boundaries;fail++){
  memcpy(b->physical,physical,1048576);b->flash=before;*cache=*saved;b->ops=0;b->fail_at=fail;
  assert(send(b,msg,n)==MM_SCENE_STORAGE_IO);assert(b->ops==fail);assert(!b->ctx.cache_reply_len);assert(!b->flash.transaction&&!b->flash.poisoned);
  metadata_equal(saved,cache);b->fail_at=0;assert(!mm_flash_store_read(&b->flash,0,logical,262144));assert(!memcmp(logical,font,262144));
 }
 memcpy(b->physical,physical,1048576);b->flash=before;*cache=*saved;b->fail_at=0;
 /* No metadata snapshot: refuse before writes, never use RAM's degraded path. */
 cfw_undo *undo=cache->undo;cache->undo=0;b->fail_alloc=1;size_t calls=b->ops;
 assert(!send(b,msg,n));assert(b->ctx.cache_reply[3]==CFW_CACHE_REPLY_CAPACITY&&b->ops==calls);cache->undo=undo;b->fail_alloc=0;metadata_equal(saved,cache);
 /* Complete the multi-message replacement without reducing its capacity. */
 pair(a,b,msg,n);assert(b->ctx.cache_reply[3]==0);
 unsigned off=65510;
 while(off<262144){unsigned chunk=262144-off;if(chunk>65510)chunk=65510;n=asset_message(msg,(uint16_t)++request,6,1,1,262144,off,font+off,chunk);pair(a,b,msg,n);off+=chunk;}
 assert(!mm_flash_store_read(&b->flash,0,logical,262144));assert(!memcmp(logical,font,262144));
 size_t writes=b->erases+b->programs;mm_scene_lose(&b->ctx);mm_scene_reap(&b->ctx);assert(!b->allocated&&writes==b->erases+b->programs);assert(!mm_flash_store_read(&b->flash,0,logical,262144));for(unsigned i=0;i<262144;i++)assert(!logical[i]);
 printf("fullcapacity=262144 fullmessage=65535 callback_faults=%zu mandatory_snapshot=yes\n",boundaries);
 free(font);free(msg);free(logical);free(saved);free(physical);destroy(a);destroy(b);
}
static int refused_transaction(void *u){(void)u;return -1;}
static void cached_assets_and_io(void){
 owner *a=create(0),*b=create(1);reset(a);reset(b);uint8_t msg[65535];unsigned request=2;
 /* Place a valid glyph across a sector; image contains all RLE token forms. */
 uint8_t font[8200]={0};w32(font+('A'-32)*4,4094);font[4094]=20;font[4095]=20;font[4096]=0x1f;font[4097]=0x0f;font[4098]=99;font[4099]=0x0f;font[4100]=0;font[4101]=44;font[4102]=1;
 size_t n=asset_message(msg,request++,10,1,1,sizeof font,0,font,sizeof font);pair(a,b,msg,n);assert(b->ctx.cache_reply[3]==0);
 uint8_t string[]={1,'A',31,'A'};n=asset_message(msg,request++,11,1,2,sizeof string,0,string,sizeof string);pair(a,b,msg,n);assert(b->ctx.cache_reply[3]==0);
 uint8_t image[]={20,20,0x1f,0x0f,99,0x0f,0,44,1};n=asset_message(msg,request++,12,1,0,sizeof image,0,image,sizeof image);pair(a,b,msg,n);
 /* Retained cached-font object + image + native text and inline text. */
 uint8_t records[4][32]={{16,1,15,0},{14,1,0x2f,0},{15,1,15,0},{17,1,15,0}};
 w16(records[0]+4,10);w16(records[0]+6,10);w32(records[0]+8,11);w32(records[0]+12,10);
 w16(records[1]+4,70);w16(records[1]+6,10);w32(records[1]+8,12);
 w16(records[2]+4,100);w16(records[2]+6,10);w32(records[2]+8,11);
 w16(records[3]+4,150);w16(records[3]+6,10);records[3][12]=3;memcpy(records[3]+13,"ABC",3);
 unsigned lengths[]={16,12,12,16};
 for(unsigned i=0;i<4;i++){msg[0]=37;w16(msg+1,1);w16(msg+3,request++);msg[5]=1;w32(msg+6,i+1);w32(msg+10,1);memcpy(msg+14,records[i],lengths[i]);pair(a,b,msg,14+lengths[i]);assert(b->ctx.cache_reply[3]==0);}
 uint8_t show[42]={38,1,0,100,0,1,0,0,4,0};for(unsigned i=0;i<4;i++){w32(show+10+8*i,i+1);w32(show+14+8*i,1);}pair(a,b,show,sizeof show);assert(b->ctx.cache_reply[3]==0);
 /* Immediate image, cached text and mode36 asset records share readers. */
 uint8_t im[20]={19};w32(im+1,12);w16(im+5,200);w16(im+7,100);im[9]=31;pair(a,b,im,10);
 im[0]=20;w32(im+1,10);w16(im+5,240);w16(im+7,100);im[9]=47;im[10]=4;memcpy(im+11,string,4);pair(a,b,im,15);
 uint8_t shapes[18]={36,1};memcpy(shapes+2,records[0],16);pair(a,b,shapes,18);
 /* Callback begin/commit failures retain previous logical bytes/metadata. */
 n=asset_message(msg,request++,13,1,0,sizeof image,0,image,sizeof image);mm_scene_prepare(&b->ctx,37,msg+1,n-1);
 cfw_cache begin_before=*b->ctx.scene;int (*begin_cb)(void *)=b->ctx.external_store.begin;
 b->ctx.external_store.begin=refused_transaction;size_t io=b->ops;
 assert(send(b,msg,n)==MM_SCENE_STORAGE_IO&&b->ops==io);metadata_equal(&begin_before,b->ctx.scene);assert(!b->flash.transaction);b->ctx.external_store.begin=begin_cb;
 int (*commit_cb)(void *)=b->ctx.external_store.commit;b->ctx.external_store.commit=refused_transaction;
 assert(send(b,msg,n)==MM_SCENE_STORAGE_IO);metadata_equal(&begin_before,b->ctx.scene);assert(!b->flash.transaction);b->ctx.external_store.commit=commit_cb;
 /* Completed-content read failure must restore asset bytes/descriptors. */
 cfw_cache before=*b->ctx.scene;mm_flash_store flash=b->flash;uint8_t *physical=malloc(1048576),*logical=malloc(262144),*saved=malloc(262144);assert(physical&&logical&&saved);memcpy(physical,b->physical,1048576);assert(!mm_flash_store_read(&b->flash,0,saved,262144));b->ops=0;assert(!send(b,msg,n));size_t boundaries=b->ops;
 for(size_t at=1;at<=boundaries;at++){*b->ctx.scene=before;b->flash=flash;memcpy(b->physical,physical,1048576);b->ops=0;b->fail_at=at;assert(send(b,msg,n)==MM_SCENE_STORAGE_IO);metadata_equal(&before,b->ctx.scene);b->fail_at=0;assert(!mm_flash_store_read(&b->flash,0,logical,262144));assert(!memcmp(logical,saved,262144));}
 *b->ctx.scene=before;b->flash=flash;memcpy(b->physical,physical,1048576);
 /* Malformed final content refuses without changing prior metadata/bytes. */
 uint8_t invalid[]={2,2,0};n=asset_message(msg,request++,13,1,0,sizeof invalid,0,invalid,sizeof invalid);
 pair(a,b,msg,n);assert(b->ctx.cache_reply[3]==CFW_CACHE_REPLY_REFUSED);metadata_equal(&before,b->ctx.scene);
 assert(!mm_flash_store_read(&b->flash,0,logical,262144));assert(!memcmp(logical,saved,262144));
 /* Every render read fails in turn, including the second drawing pass. */
 show[3]=101;b->ops=0;assert(!send(b,show,sizeof show));size_t render_reads=b->ops;unsigned presents=b->presents;
 for(size_t at=1;at<=render_reads;at++){
  *b->ctx.scene=before;b->flash=flash;b->ctx.shadow_invalid=0;b->ops=0;b->fail_at=at;
  assert(send(b,show,sizeof show)==MM_SCENE_STORAGE_IO);assert(b->ops==at);assert(b->ctx.shadow_invalid&&b->presents==presents&&!b->ctx.scene->anim_active);b->fail_at=0;
 }
 assert(!send(b,show,sizeof show));assert(!b->ctx.shadow_invalid); /* same request heals, no reapply */
 printf("cached-font-cross-sector=yes mixed-rle=yes immediate-retained=yes asset_faults=%zu render_faults=%zu render_failure=explicit\n",boundaries,render_reads);
 free(physical);free(logical);free(saved);destroy(a);destroy(b);
}

static void maximum_paths_and_header_fault(void){
 owner *a=create(0),*b=create(1);reset(a);reset(b);uint8_t commands[8192],msg[16384];unsigned len=0;
 for(unsigned i=0;i<128;i++){unsigned x=20+(i%16)*10,y=20+(i/16)*10;int points[4][2]={{(int)x,(int)y},{(int)x+8,(int)y},{(int)x+8,(int)y+8},{(int)x,(int)y+8}};for(unsigned j=0;j<4;j++){commands[len++]=j?1:0;w16(commands+len,(unsigned)points[j][0]*16);w16(commands+len+2,(unsigned)points[j][1]*16);len+=4;}commands[len++]=4;}
 for(unsigned id=1;id<=9;id++){msg[0]=37;w16(msg+1,1);w16(msg+3,id+2);msg[5]=1;w32(msg+6,id);w32(msg+10,1);uint8_t *p=msg+14;memset(p,0,12);p[0]=18;p[1]=1;p[2]=15;w16(p+8,256);w16(p+10,len);memcpy(p+12,commands,len);pair(a,b,msg,26+len);assert(b->ctx.cache_reply[3]==0);cfw_asset *asset=&b->ctx.scene->assets[b->ctx.scene->objects[id-1].asset-1];assert(asset->length==8196);}
 uint8_t show[82]={38,1,0,100,0,1,0,0,8,0};for(unsigned i=0;i<9;i++){w32(show+10+i*8,i+1);w32(show+14+i*8,1);}pair(a,b,show,74);assert(b->ctx.cache_reply[3]==0);
 cfw_cache saved=*b->ctx.scene;size_t presents=b->presents;
 show[3]=101;b->ops=0;b->fail_at=1;assert(send(b,show,74)==MM_SCENE_STORAGE_IO);b->fail_at=0;metadata_equal(&saved,b->ctx.scene);assert(b->presents==presents&&!b->ctx.shadow_invalid);
 show[8]=9;pair(a,b,show,82);assert(b->ctx.cache_reply[3]==CFW_CACHE_REPLY_REFUSED);metadata_equal(&saved,b->ctx.scene);
 printf("paths=512edges/8196bytes scene_edges=4096 overbudget_rejected=yes show_header_failure_rollback=yes\n");destroy(a);destroy(b);
}
typedef struct {const void *owned;size_t bytes,reads;} alias_backend;
static int alias_read(void *u,uint32_t off,void *dst,size_t n){alias_backend *b=u;(void)off;b->reads++;memset(dst,0,n);return 0;}
static int alias_owned(void *u,const void *p,size_t n){alias_backend *b=u;return mm_scene_overlap(p,n,b->owned,b->bytes);}
static void reader_owner_aliases(void){
 mm_vector_work *work=malloc(sizeof(*work));uint8_t *pixels=malloc(PIXELS),*saved_work=malloc(sizeof(*work)),*saved_pixels=malloc(PIXELS);
 assert(work&&pixels&&saved_work&&saved_pixels);uint8_t path_data[20]={1};
 mm_raster target={pixels,PIXELS,640,480,320};mm_vector_transform transform={.scale=256};
 alias_backend backend={0,0,0};mm_scene_store ops={.user=&backend,.capacity=20,.read=alias_read,.aliases=alias_owned};
 for(unsigned test=0;test<8;test++){
  memset(work,0xa5,sizeof(*work));memset(pixels,0x5a,PIXELS);backend=(alias_backend){0,0,0};
  mm_scene_bytes handle={path_data,0,0,sizeof(path_data)};const mm_scene_bytes *input=&handle;
  if(test<2){mm_scene_bytes *embedded=test==0?(mm_scene_bytes *)(void *)work:(mm_scene_bytes *)(void *)pixels;*embedded=handle;input=embedded;}
  else if(test<4){mm_scene_store *embedded=test==2?(mm_scene_store *)(void *)work:(mm_scene_store *)(void *)pixels;*embedded=ops;handle=(mm_scene_bytes){0,embedded,0,20};}
  else if(test<6){backend.owned=test==4?(void *)work:(void *)pixels;backend.bytes=test==4?sizeof(*work):PIXELS;handle=(mm_scene_bytes){0,&ops,0,20};}
  else {handle.ram=test==6?(const uint8_t *)work:pixels;}
  memcpy(saved_work,work,sizeof(*work));memcpy(saved_pixels,pixels,PIXELS);
  assert(mm_vector_draw_path_reader(&target,work,sizeof(*work),input,&transform,15)==MM_VECTOR_ALIAS);
  assert(!backend.reads&&!memcmp(saved_work,work,sizeof(*work))&&!memcmp(saved_pixels,pixels,PIXELS));
 }
 owner *o=create(1);owner *saved=malloc(sizeof(*saved));assert(saved);memcpy(saved,o,sizeof(*saved));
 mm_scene_store store=o->ctx.external_store;mm_scene_platform platform=o->ctx.platform;
 assert(mm_scene_init_with_store((mm_scene_context *)(void *)&o->flash,&platform,&store)==-1);assert(!memcmp(o,saved,sizeof(*o)));
 assert(mm_scene_init_with_store((mm_scene_context *)(void *)o->scratch,&platform,&store)==-1);assert(!memcmp(o,saved,sizeof(*o)));
 free(saved);destroy(o);free(work);free(pixels);free(saved_work);free(saved_pixels);
 puts("reader-owner-aliases=8 initializer-backend-aliases=2 unchanged-on-rejection=yes");
}
int main(int argc,char **argv){reader_owner_aliases();for(int i=1;i<argc;i++)replay(argv[i]);full_capacity_and_faults();cached_assets_and_io();maximum_paths_and_header_fault();puts("PASS scene-store differential and transaction failures");return 0;}
