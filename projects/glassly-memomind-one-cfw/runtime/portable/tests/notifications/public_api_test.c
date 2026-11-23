/* MIT. Additional portable ownership/bounds/lifecycle tests. */
#include "notifications.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef struct {
    unsigned locked,allocations,frees,sends,actions,starts;
    int oom,new_fail,start_fail,delete_fail,send_fail;
    uint32_t now;
    void (*tick)(void *);void *arg;
    uint8_t sent[160];uint32_t len;
} fake;
static void enter(void *p){fake *f=p;assert(!f->locked);f->locked=1;}
static void leave(void *p){fake *f=p;assert(f->locked);f->locked=0;}
static void *allocate(void *p,size_t n){fake *f=p;assert(f->locked);if(f->oom)return 0;f->allocations++;return malloc(n);}
static void deallocate(void *p,void *v){fake *f=p;assert(f->locked);f->frees++;free(v);}
static uint32_t now(void *p){return ((fake *)p)->now;}
static uint32_t side(void *p){(void)p;return 1;}
static uintptr_t timer_new(void *p,void (*cb)(void *),void *arg){fake *f=p;if(f->new_fail)return 0;f->tick=cb;f->arg=arg;return 7;}
static int start(void *p,uintptr_t t,uint32_t ms){fake *f=p;assert(t==7 && (ms==20 || ms==100));f->starts++;return f->start_fail;}
static int stop(void *p,uintptr_t t){(void)p;assert(t==7);return 0;}
static int del(void *p,uintptr_t t){fake *f=p;assert(t==7);return f->delete_fail;}
static int send(void *p,const uint8_t *b,uint32_t n){fake *f=p;assert(f->locked && n<=sizeof f->sent);f->sends++;memcpy(f->sent,b,n);f->len=n;return f->send_fail;}
static void action(void *p,uint32_t uid,uint32_t op){fake *f=p;assert(f->locked && uid==0x1234 && op<=1);f->actions++;}
static mm_notifications_platform platform(fake *f){mm_notifications_platform p={f,allocate,deallocate,now,side,timer_new,start,stop,del,send,action,enter,leave};return p;}
static void control(mm_notifications *c,uint8_t op){uint8_t p[]={'A','N',1,op};mm_notifications_control(c,p,sizeof p);}
static void drain(mm_notifications *c){unsigned guard=0;while(c->ancs_head!=c->ancs_tail){mm_notifications_tick(c);assert(++guard<4096);}}
int main(void){
    fake a={.now=1000},b={.now=1000};mm_notifications x,y;mm_notifications_platform p=platform(&a),q=platform(&b);
    assert(mm_notifications_init(&x,&p));assert(mm_notifications_init(&y,&q));
    assert(!mm_notifications_init(0,&p));q.send=0;assert(!mm_notifications_init(&y,&q));q.send=send;
    /* Truncated, bad version, malformed app records and oversized inputs. */
    uint8_t bytes[1100]={0},src[8]={0};
    for(size_t n=0;n<4;n++)mm_notifications_control(&x,bytes,n);
    uint8_t bad[]={'A','N',2,1};mm_notifications_control(&x,bad,4);
    mm_notifications_source(&x,src,7);mm_notifications_source(&x,0,8);
    assert(!a.sends && !a.allocations);
    a.oom=1;control(&x,1);assert(!x.ancs_ring && !x.ancs_lease_deadline);a.oom=0;
    a.new_fail=1;control(&x,1);assert(x.ancs_ring && !x.ancs_timer && !x.ancs_lease_deadline);a.new_fail=0;
    a.start_fail=1;control(&x,1);assert(x.ancs_idle);a.start_fail=0;
    mm_notifications_source(&x,src,8);assert(!x.ancs_idle);drain(&x);
    unsigned saved=a.sends;
    mm_notifications_attribute(&x,1,3,bytes,1025);mm_notifications_app_response(&x,bytes,1025);
    mm_notifications_source(&x,(uint8_t *)&x,8);mm_notifications_source(&x,x.ancs_ring,8);
    mm_notifications_control(&x,0,4);mm_notifications_attribute(&x,1,3,0,1);
    for(size_t n=0;n<100;n++)mm_notifications_app_response(&x,bytes,n);
    assert(a.sends==saved && x.ancs_head==x.ancs_tail);
    /* Zero attr, max attribute, app-name chunking, >64-byte app ids rejected. */
    mm_notifications_attribute(&x,1,2,0,0);drain(&x);assert(a.len==20);
    saved=x.ancs_seq;mm_notifications_attribute(&x,1,3,bytes,1024);drain(&x);assert(x.ancs_seq==saved+8);
    memset(bytes,'a',sizeof bytes);bytes[0]=1;bytes[65]=0;bytes[66]=0;bytes[67]=0x2c;bytes[68]=1;
    saved=x.ancs_seq;mm_notifications_app_response(&x,bytes,369);drain(&x);assert(x.ancs_seq==saved+4);
    bytes[65]='a';bytes[66]=0;mm_notifications_app_response(&x,bytes,369);assert(x.ancs_head==x.ancs_tail);
    /* Independent contexts plus ring's 16-bit counter wrap. */
    control(&y,1);saved=b.sends;
    for(unsigned i=0;i<6000;i++){mm_notifications_source(&x,src,8);mm_notifications_tick(&x);}
    assert(b.sends==saved && y.ancs_seq==0 && x.ancs_head==x.ancs_tail);
    /* Send errors saturate; failed record is consumed, never replayed. */
    a.send_fail=1;x.ancs_send_errs=254;
    for(unsigned i=0;i<3;i++){mm_notifications_source(&x,src,8);mm_notifications_tick(&x);}
    assert(x.ancs_send_errs==255 && x.ancs_head==x.ancs_tail);a.send_fail=0;
    /* Millisecond wrap uses original signed deadline subtraction. */
    a.now=0xfffffff0u;control(&x,1);a.now=0x10;mm_notifications_source(&x,src,8);drain(&x);
    assert(x.ancs_lease_deadline!=0);a.now+=90000;mm_notifications_tick(&x);assert(!x.ancs_lease_deadline);
    uint8_t act[]={'A','N',1,4,0x34,0x12,0,0,1};mm_notifications_control(&x,act,9);assert(a.actions==1);
    act[8]=2;mm_notifications_control(&x,act,9);assert(a.actions==1);
    /* Failed timer delete retains allocation/context for a safe later retry. */
    a.delete_fail=1;assert(!mm_notifications_destroy(&x));assert(x.ancs_ring && x.ancs_timer && !a.frees);
    a.delete_fail=0;assert(mm_notifications_destroy(&x));assert(a.frees==a.allocations);
    assert(mm_notifications_destroy(&y));assert(b.frees==b.allocations);
    mm_notifications_tick(&x);mm_notifications_cleanup(&x);assert(!mm_notifications_destroy(&x));
    puts("notification public API: bounds, two contexts, 6000 wrap records, failures and lifecycle passed");return 0;
}
