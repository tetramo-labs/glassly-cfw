/* MIT. Public normalized-event, instance and lifetime boundary tests. */
#include "keyboard.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint32_t now;unsigned timers,sends,posts,requests,closes,auths,confirms;int request_ok,send_fail;uint8_t last[130];uint32_t len;} fake;
static uint32_t now(void *u){return ((fake *)u)->now;}
static int timer(void *u,uintptr_t t,uint32_t n){assert(t==7 && n==20);((fake *)u)->timers++;return 0;}
static int post(void *u){((fake *)u)->posts++;return 1;}
static int send(void *u,const uint8_t *p,uint32_t n){fake *f=u;assert(n<=130);f->sends++;memcpy(f->last,p,n);f->len=n;return f->send_fail;}
static int available(void *u){(void)u;return 1;}
static void scan(void *u){(void)u;}
static int can(void *u,uint8_t t,const uint8_t *p){(void)u;(void)t;(void)p;return KB_OK;}
static uint8_t open_link(void *u,uint8_t t,const uint8_t *p){(void)u;(void)t;(void)p;return 2;}
static void close_link(void *u,uint8_t c){assert(c==2);((fake *)u)->closes++;}
static int pair(void *u,uint8_t c){(void)u;assert(c==2);return 0;}
static void auth(void *u,uint8_t c,const uint8_t *p){assert(c==2 && p);((fake *)u)->auths++;}
static void compare(void *u,uint8_t c,uint8_t a){(void)u;assert(c==2 && a<=1);}
static int request(void *u,uint8_t c,uint8_t op,uint16_t h,uint16_t arg,const uint8_t *p,uint16_t n){fake *f=u;assert(c==2 && h);(void)op;(void)arg;(void)p;(void)n;f->requests++;return f->request_ok;}
static void confirm(void *u,uint8_t c){assert(c==2);((fake *)u)->confirms++;}
static void dm(void *u,const mm_keyboard_event *e){(void)u;assert(e->param==2);}
static int security(void *u,const mm_keyboard_event *e){dm(u,e);return 1;}
static mm_keyboard_platform platform(fake *f){mm_keyboard_platform p={f,now,timer,post,send,available,scan,can,open_link,close_link,pair,auth,compare,request,confirm,dm,security};return p;}
static void ctl(mm_keyboard *s,uint8_t op,const uint8_t *b,unsigned n){uint8_t p[80]={'K','B',1,op,1,0,(uint8_t)s->epoch,(uint8_t)(s->epoch>>8)};if(n)memcpy(p+8,b,n);mm_keyboard_control(s,p,8+n);}
static void event(mm_keyboard *s,uint8_t e){mm_keyboard_event p={.param=2,.event=e};assert(mm_keyboard_handle_event(s,&p));}
static void drain(mm_keyboard *s){unsigned guard=0;while(s->head!=s->tail){mm_keyboard_tick(s);assert(++guard<20);}}
int main(void){
    fake a={.now=100},b={.now=100};mm_keyboard x,y;mm_keyboard_platform p=platform(&a),q=platform(&b);
    assert(mm_keyboard_init(&x,&p,7));assert(mm_keyboard_init(&y,&q,7));
    assert(!mm_keyboard_init(0,&p,7));q.post_poll=0;assert(!mm_keyboard_init(&y,&q,7));
    assert(!mm_keyboard_validate_control(0,0));assert(!mm_keyboard_validate_control((uint8_t *)&x,81));
    mm_keyboard_control(&x,(uint8_t *)&x,8);assert(!x.head && !a.timers);
    ctl(&x,KB_ENABLE,0,0);uint8_t peer[7]={1,2,3,4,5,6,7};ctl(&x,KB_CONNECT,peer,7);
    event(&x,0x27);event(&x,0x2c);assert(x.conn==2 && x.connected && x.encrypted);assert(!y.conn && !y.head);
    drain(&x);mm_keyboard_poll(&x);
    /* Malformed normalized prompt lengths/values leave state untouched. */
    uint8_t prompt[4]={0,1,0,0};mm_keyboard_event e={.param=2,.event=0x2e,.data=prompt,.len=1};
    uint32_t head=x.head;assert(!mm_keyboard_handle_event(&x,&e) && x.head==head && !x.auth);
    e.len=2;assert(mm_keyboard_handle_event(&x,&e) && x.auth);drain(&x);
    e.event=0x35;e.len=3;assert(!mm_keyboard_handle_event(&x,&e));
    e.len=4;memset(prompt,255,4);assert(!mm_keyboard_handle_event(&x,&e) && !x.compare);
    prompt[0]=0x3f;prompt[1]=0x42;prompt[2]=0x0f;prompt[3]=0;
    assert(mm_keyboard_handle_event(&x,&e) && x.compare);drain(&x);
    /* G2 bond-key event forwards metadata but never exports its provided bytes. */
    e.event=0x2f;assert(mm_keyboard_handle_event(&x,&e));
    mm_keyboard_record *r=&x.queue[x.tail%KB_SLOTS];assert(r->data[3]==KB_DM && r->len==KB_HEADER);drain(&x);
    uint8_t watch[3]={1,15,0};ctl(&x,KB_WATCH,watch,3);drain(&x);
    e.event=13;e.handle=15;e.data=0;e.len=1;unsigned drops=x.drops;
    assert(mm_keyboard_handle_event(&x,&e) && x.drops==drops+1);assert(x.head==x.tail);
    e.data=(uint8_t *)&x;e.len=8;head=x.head;assert(!mm_keyboard_handle_event(&x,&e) && x.head==head);
    assert(!mm_keyboard_handle_event(&x,(mm_keyboard_event *)&x));
    e.data=prompt;e.len=4;assert(mm_keyboard_handle_event(&x,&e));a.send_fail=1;
    drain(&x);head=x.tail;mm_keyboard_tick(&x);assert(x.tail==head);a.send_fail=0;
    /* Allocation failures are explicit request callback failures, no core heap. */
    uint8_t read[4]={12,0,0,0};ctl(&x,KB_READ,read,4);assert(a.requests==1 && !x.pending_event && !x.deadline);drain(&x);
    a.request_ok=1;ctl(&x,KB_READ,read,4);assert(x.pending_event==5);a.now+=30001;mm_keyboard_poll(&x);
    assert(x.conn==2 && x.closing && a.closes==1);event(&x,0x28);assert(!x.conn);drain(&x);
    unsigned seq=x.sequence;mm_keyboard_lost(&x);assert(x.sequence==seq+1 && x.drops==drops+2);
    assert(!b.sends && !b.posts && !b.timers);ctl(&y,KB_QUERY,0,0);drain(&y);assert(b.sends==1);
    /* A validated advertisement is bounded and independent of Cordio layout. */
    ctl(&y,KB_ENABLE,0,0);ctl(&y,KB_SCAN,0,0);drain(&y);
    e.param=0;e.event=0x26;e.data=prompt;e.len=4;e.addr_type=1;e.rssi=-42;
    assert(mm_keyboard_handle_event(&y,&e));r=&y.queue[y.tail%KB_SLOTS];assert(r->data[3]==KB_ADVERT && r->data[31]==(uint8_t)-42);drain(&y);
    e.len=32;head=y.head;assert(mm_keyboard_handle_event(&y,&e) && y.head==head);
    mm_keyboard_tick(0);mm_keyboard_poll(0);mm_keyboard_lost(0);
    puts("keyboard public API: two contexts, normalized prompts/advertisements, bounds/alias, failures and no replay passed");return 0;
}
