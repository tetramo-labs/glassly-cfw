/* Display-task ownership model: DELETE callback precedes recursive child DELETE. */
#include "graphics.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef struct image {void *parent,*user;mm_callback deleted;struct image *next;const mm_native_image *source;int hidden;} image;
static image *images;static unsigned owned,allocs,presents;static int fail_alloc,fail_event;static void *screen=(void *)0x1234;
static void *allocate(size_t n){allocs++;if(fail_alloc)return 0;owned++;return calloc(1,n);}
static void deallocate(void *p){assert(owned);owned--;free(p);}
static void *create_image(void *p){image *i=calloc(1,sizeof(*i));assert(i);i->parent=p;i->next=images;images=i;return i;}
static int on_delete(void *p,mm_callback cb,void *u){if(fail_event)return 0;image *i=p;i->deleted=cb;i->user=u;return 1;}
static void *userdata(void *e){return ((image *)e)->user;}
static void delete_image(void *p){image *i=p;if(i->deleted)i->deleted(i);for(;;){image *child=images;while(child&&child->parent!=i)child=child->next;if(!child)break;delete_image(child);}image **at=&images;while(*at!=i){assert(*at);at=&(*at)->next;}*at=i->next;free(i);}
static void *find_owner(void *p,mm_callback cb){for(image *i=images;i;i=i->next)if(i->parent==p&&i->deleted==cb)return i->user;return 0;}
static uint32_t free_bytes(void){return 1024*1024;}
static void cache(const mm_native_image *p){assert(p);}
static void *json(const char *p){size_t n=strlen(p)+1;char *out=malloc(n);assert(out);memcpy(out,p,n);return out;}
const mm_graphics_platform mm_graphics_native={.alloc=allocate,.free=deallocate,.json=json,.free_bytes=free_bytes,.image_create=create_image,.image_delete=delete_image,.on_delete=on_delete,.event_userdata=userdata,.find_owner=find_owner,.cache_invalidate=cache};
void glassly_diagnostics_hidden(void *p,int hidden){((image *)p)->hidden=hidden;}
void glassly_diagnostics_source(void *p,const mm_native_image *s){assert(((s->header>>10)&2047)==80 && (s->header>>21)==18 && s->data_size==784);((image *)p)->source=s;presents++;}
#include "../diagnostics.c"
void g2_reference_frame(int,uint16_t);void g2_reference_control(unsigned);void g2_reference_snapshot(uint32_t *);
static void control(unsigned n){char *p=mm_diagnostics_control(screen,n);assert(p&&strstr(p,"\"presentation\":\"unchanged\"")&&strstr(p,"\"stateHex\":\""));puts(p);free(p);}
static void compare(void){uint32_t r[28];g2_reference_snapshot(r);diagnostic_owner *d=diagnostic_find(screen);assert(d);assert(d->flags==(r[0]|(r[1]<<1)|(r[2]<<2)));assert(d->hidden==r[3]&&d->seen==r[4]&&d->resync==r[5]&&d->last==r[6]&&d->high==r[7]&&d->pos==r[8]);for(unsigned i=0;i<16;i++)assert(d->recent[i]==r[9+i]);}
static void tracking(void){
    control(0);g2_reference_control(0);compare();diagnostic_owner *d=diagnostic_find(screen);
    uint16_t edges[]={65535,0,1,3,2,3,32770,65534,65535,0,32768};
    for(unsigned i=0;i<sizeof(edges)/sizeof(*edges);i++){diagnostic_frame(d,1,edges[i]);g2_reference_frame(1,edges[i]);compare();}
    diagnostic_frame(d,0,0);g2_reference_frame(0,0);compare();diagnostic_frame(d,1,0);g2_reference_frame(1,0);compare();
    uint32_t seed=17;for(unsigned i=0;i<100000;i++){seed=seed*1664525u+1013904223u;if(i%101==0){diagnostic_frame(d,0,0);g2_reference_frame(0,0);}else{diagnostic_frame(d,1,(uint16_t)(seed>>8));g2_reference_frame(1,(uint16_t)(seed>>8));}compare();}
    for(unsigned i=0;i<256;i++){control(i);g2_reference_control(i);compare();}
    d->epoch=23;mm_diagnostics_failure(screen,15,1);assert(d->worker==1&&d->allocation==1&&d->failed_mode==15);control(0);assert(!d->worker&&!d->allocation&&!d->failed_mode&&d->epoch==23);
}
static void lifecycle(void){
    image *graphics=create_image(screen);diagnostic_owner *d=diagnostic_find(screen);control(2);unsigned n=presents;assert(!d->overlay);
    mm_diagnostics_present(screen,graphics);assert(presents==n+1&&d->overlay&&((image *)d->overlay)->parent==graphics&&!((image *)d->overlay)->hidden);
    control(1);assert(!((image *)d->overlay)->hidden&&presents==n+1);mm_diagnostics_present(screen,graphics);assert(((image *)d->overlay)->hidden&&presents==n+1);
    control(2);mm_diagnostics_present(screen,graphics);mm_diagnostics_cleanup(screen,24);assert(d->hidden&&d->epoch==24&&((image *)d->overlay)->hidden);
    /* Graphics first: its recursive child deletion clears the weak pointer. */
    delete_image(graphics);assert(!d->overlay&&owned==1);delete_image(d->image);assert(!images&&!owned);
    /* Metadata first: deletes its overlay while userdata is still live. */
    control(2);d=diagnostic_find(screen);graphics=create_image(screen);mm_diagnostics_present(screen,graphics);delete_image(d->image);assert(owned==0&&images==graphics);delete_image(graphics);assert(!images);
    control(2);d=diagnostic_find(screen);graphics=create_image(screen);fail_event=1;mm_diagnostics_present(screen,graphics);fail_event=0;assert(!d->overlay);delete_image(graphics);delete_image(d->image);assert(!images&&!owned);
    fail_alloc=1;char *p=mm_diagnostics_control(screen,0);assert(strstr(p,"allocation-failed"));free(p);fail_alloc=0;assert(!images&&!owned);
    fail_event=1;p=mm_diagnostics_control(screen,0);assert(strstr(p,"allocation-failed"));free(p);fail_event=0;assert(!images&&!owned);
}
int main(void){tracking();lifecycle();puts("diagnostics: 100000 original FID transitions, edgecases/control modes, deferredoverlay and both destruction orders passed");return 0;}
