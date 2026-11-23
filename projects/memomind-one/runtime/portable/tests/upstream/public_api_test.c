/* MIT. Portable boundaries independent of the G2 native test shim. */
#include "upstream.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {mm_upstream_profile stock;const mm_upstream_profile *selected;unsigned wanted,applied,gen,cancels,posts,arg,requests,classifies,sends,controls;int fail;uint8_t last[256];unsigned len;} fake;
static const mm_upstream_profile *profile(void *u){return ((fake *)u)->selected;}
static const mm_upstream_profile *stock(void *u){return &((fake *)u)->stock;}
static void select_profile(void *u,const mm_upstream_profile *v){((fake *)u)->selected=v;}
static unsigned wanted(void *u){return ((fake *)u)->wanted;}
static unsigned applied(void *u){return ((fake *)u)->applied;}
static void clear(void *u){((fake *)u)->applied=0;}
static void want(void *u,unsigned m){fake *f=u;f->wanted=m;f->gen++;}
static unsigned gen(void *u){return ((fake *)u)->gen;}
static void cancel(void *u){((fake *)u)->cancels++;}
static void post(void *u,unsigned a,unsigned ms){fake *f=u;assert(!ms);f->posts++;f->arg=a;}
static int request(void *u,unsigned m,void *c){fake *f=u;(void)m;(void)c;f->requests++;return 11;}
static unsigned classify(void *u,const void *c){fake *f=u;(void)c;f->classifies++;return 0xa3;}
static mm_upstream_link link(fake *f){mm_upstream_link p={f,profile,stock,select_profile,wanted,applied,clear,want,gen,cancel,post,request,classify};return p;}
static int send(void *u,int type,int channel,const uint8_t *b,unsigned n){fake *f=u;assert(type==1 && (channel==8 || channel==9) && n<=sizeof f->last);f->sends++;memcpy(f->last,b,n);f->len=n;return f->fail;}
static void control(void *u,unsigned field,const uint8_t *p,unsigned n){fake *f=u;assert(field==101 || field==103 || field==126 || field==127 || field==130 || field==132);assert(p || !n);f->controls++;}
int main(void){
    fake a={.stock={0x12345678,12,24,0,600,5,0x4567},.wanted=0xa4,.applied=0xa4,.gen=122};a.selected=&a.stock;
    mm_upstream_state x={0},y={0};mm_upstream_link platform=link(&a);
    const uint8_t fast[]={'B','L',1,1},normal[]={'B','L',1,0};
    mm_upstream_link_control(&x,&platform,fast,4);assert(x.ble_fast && !y.ble_fast && a.arg==(0xa3u|(123u<<8)));
    assert(mm_upstream_request(&x,&platform,0xa3,0)==11 && a.selected==&x.profile);
    assert(x.profile.min==6 && x.profile.max==6 && !x.profile.latency && x.profile.prefix==0x12345678 && x.profile.suffix==0x4567 && x.profile.timeout==600 && x.profile.retries==5);
    assert(mm_upstream_classify(&x,&platform,0,0,6,0)==0xa4 && !a.classifies);
    assert(mm_upstream_classify(&y,&platform,0,0,6,0)==0xa3 && a.classifies==1);
    mm_upstream_link_control(&x,&platform,normal,4);assert(!x.ble_fast && a.selected==&a.stock && a.posts==2);
    mm_upstream_link_cleanup(&x,&platform);assert(a.posts==2);
    mm_upstream_link incomplete=platform;incomplete.post=0;mm_upstream_link_control(&x,&incomplete,fast,4);assert(!x.ble_fast);
    uint8_t guarded[258];memset(guarded,0xa5,sizeof guarded);uint8_t *buf=guarded+1;
    uint8_t payload[]={1,2,3};assert(mm_upstream_append(buf,0,4,130,payload,3)==0 && buf[0]==0xa5);
    assert(mm_upstream_append(buf,0,256,0,payload,3)==0);assert(mm_upstream_append(buf,0,256,130,0,3)==0);
    assert(mm_upstream_append(buf,0,256,130,buf,3)==0 && buf[0]==0xa5);
    unsigned n=mm_upstream_append(buf,0,256,130,payload,3);assert(n==6);mm_upstream_scan(buf,n,control,&a);assert(a.controls==1);
    for(unsigned i=0;i<n;i++){unsigned before=a.controls;mm_upstream_scan(buf,i,control,&a);assert(a.controls==before);}
    mm_upstream_scan(0,100,control,&a);mm_upstream_scan(buf,n,0,&a);
    uint32_t seed=1;for(unsigned trial=0;trial<20000;trial++){uint8_t random[81];for(unsigned i=0;i<81;i++){seed=seed*1664525u+1013904223u;random[i]=(uint8_t)(seed>>24);}mm_upstream_scan(random,trial%82,control,&a);}
    assert(guarded[0]==0xa5 && guarded[257]==0xa5);
    mm_upstream_battery battery={1,2,100};uint8_t q[]={17,0};a.sends=0;
    assert(mm_upstream_battery_query(q,2,1,battery,send,&a)==0 && a.last[10]==7 && a.last[11]==100);
    mm_upstream_extension ext={100,payload,sizeof payload};memset(buf,0,256);a.sends=0;a.fail=1;
    assert(mm_upstream_settings_send(1,9,buf,4,256,&ext,1,1,battery,send,&a)==1 && a.sends==1);
    a.fail=0;a.sends=0;assert(mm_upstream_settings_send(1,9,buf,4,256,&ext,1,1,battery,send,&a)==0 && a.sends==2);
    a.sends=0;ext.data=buf;assert(mm_upstream_settings_send(1,9,buf,4,256,&ext,1,1,battery,send,&a)==-1 && !a.sends);
    for(unsigned m=0;m<256;m++){uint8_t mode=(uint8_t)m;unsigned v=m&127;int expected=v==3||v==6||v==8||v==9||v==11||v==15||v==19||v==20||v==36||(v>=37&&v<=41);assert(mm_upstream_shadow(&mode,1)==expected);}
    /* Source precedence, fallback metadata, stale capture and bounded packet. */
    x.compass_forward=1;mm_upstream_capture capture={.grv=1,.gmrv=1,.gmrv_heading=1,.mag_seen=1,.cached_accuracy=2,.cached_anomalies=1};
    mm_upstream_capture_sample(&x,19,0x12345678,&capture);assert(x.compass_samples[19].source==2 && x.compass_samples[19].flags==0x83 && x.compass_samples[19].accuracy==2);
    assert(!y.compass_samples[19].flags);mm_upstream_record records[20]={0};records[19].timestamp=0x12345678;records[19].heading_valid=1;
    assert(mm_upstream_heading(&x,9,359,1,records,20,buf,23)==0);
    n=mm_upstream_heading(&x,9,359,1,records,20,buf,256);assert(n==24 && buf[15]==2 && buf[17]==2 && buf[18]==0x83);
    records[19].timestamp++;n=mm_upstream_heading(&x,9,0,1,records,20,buf,256);assert(n==23 && buf[14]==255 && !buf[16] && !buf[17]);
    assert(!mm_upstream_heading(&x,9,0,1,records,20,(uint8_t *)&x,24));
    assert(!mm_upstream_heading(&x,9,0,1,records,20,(uint8_t *)records,24));
    assert(!mm_upstream_heading(&x,9,0,1,0,1,buf,256));
    mm_upstream_capture_sample(&x,20,1,&capture);mm_upstream_capture_sample(&x,0,1,(mm_upstream_capture *)&x);assert(!x.compass_samples[0].flags);
    puts("upstream public API: normalized profiles/generation, two states, 20000 malformed packets, bounds/alias, composition and heading matching passed");return 0;
}
