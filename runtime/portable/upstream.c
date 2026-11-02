/* MIT. G2 commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce:
 * protobuf.c, settings_ext.c, zlib_glue.c, ring_battery.c, compass.c, ble_link.c.
 * Native layouts normalized at the caller boundary; see UPSTREAM_PORT.md. */
#include "upstream.h"
static void copy(uint8_t *d,const uint8_t *s,unsigned n){for(unsigned i=0;i<n;i++)d[i]=s[i];}
static void w16(uint8_t *p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static unsigned varsize(unsigned n){unsigned k=1;while(n>=128){n>>=7;k++;}return k;}
static unsigned writevar(uint8_t *p,unsigned n){unsigned k=0;do{uint8_t b=n&127;n>>=7;p[k++]=b|(n?128:0);}while(n);return k;}
static int overlap(const void *a,unsigned an,const void *b,unsigned bn){uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
unsigned mm_upstream_append(uint8_t *buf,unsigned len,unsigned capacity,unsigned field,const uint8_t *data,unsigned n){
    if(!buf || (!data && n) || !field || field>0x1fffffffu || len>capacity)return len;
    unsigned tag=(field<<3)|2u,t=varsize(tag),l=varsize(n),left=capacity-len;
    if(t>left)return len;
    left-=t;
    if(l>left)return len;
    left-=l;
    if(n>left)return len;
    if(n && overlap(buf+len,t+l+n,data,n))return len;
    uint8_t *p=buf+len;p+=writevar(p,tag);p+=writevar(p,n);if(n)copy(p,data,n);
    return len+t+l+n;
}
static int readvar(const uint8_t **cursor,const uint8_t *end,uint32_t *value){
    uint32_t out=0,shift=0;const uint8_t *p=*cursor;
    while(p<end && shift<32){uint8_t b=*p++;out|=(uint32_t)(b&127u)<<shift;
        if(!(b&128u)){*cursor=p;*value=out;return 1;}shift+=7;}
    return 0;
}
void mm_upstream_scan(const uint8_t *buf,unsigned len,mm_upstream_control dispatch,void *user){
    if(!buf || !dispatch || len>65535)return;
    const uint8_t *p=buf,*end=buf+len;
    while(p<end){uint32_t key,n;if(!readvar(&p,end,&key))return;
        unsigned field=key>>3,wire=key&7;
        if(wire==0){if(!readvar(&p,end,&n))return;}
        else if(wire==1){if((unsigned)(end-p)<8)return;p+=8;}
        else if(wire==2){if(!readvar(&p,end,&n) || n>(unsigned)(end-p))return;
            if(field==101 || field==103 || field==126 || field==127 || field==130 || field==132)dispatch(user,field,p,n);
            p+=n;
        }else if(wire==5){if((unsigned)(end-p)<4)return;p+=4;}else return;
    }
}
int mm_upstream_shadow(const uint8_t *p,unsigned n){if(!p || !n)return 0;uint8_t m=p[0]&127;
    return m==3 || m==6 || m==8 || m==9 || m==11 || m==15 || m==19 || m==20 || m==36 || (m>=37 && m<=41);}
unsigned mm_upstream_battery_append(uint8_t *buf,unsigned len,unsigned cap,mm_upstream_battery b){
    uint8_t body[5]={'R','B',1,0,255};if(b.connected){body[3]=1;if(b.level<=100){body[3]|=2;if(b.charging)body[3]|=4;body[4]=b.level;}}
    return mm_upstream_append(buf,len,cap,106,body,sizeof body);
}
int mm_upstream_battery_query(const uint8_t *p,unsigned n,unsigned side,mm_upstream_battery b,mm_upstream_send send,void *user){
    if(!p || n!=2 || p[0]!=17 || p[1]!=0)return -1;
    if(side!=1)return 0;
    if(!send)return -1;
    uint8_t buf[12]={8,3,16,0};unsigned len=mm_upstream_battery_append(buf,4,sizeof buf,b);return send(user,1,9,buf,len);
}
int mm_upstream_settings_send(int type,int channel,uint8_t *buf,unsigned len,unsigned cap,const mm_upstream_extension *ext,unsigned count,unsigned side,mm_upstream_battery b,mm_upstream_send send,void *user){
    if(!buf || len>cap || !send || (count && !ext) || count>32)return -1;
    /* Validate immutable descriptors before appending: avoid invalid extension
     * pointers or descriptor mutation through an overlapping response buffer. */
    if(count && overlap(buf,cap,ext,count*(unsigned)sizeof *ext))return -1;
    for(unsigned i=0;i<count;i++)if((ext[i].length && !ext[i].data) || !ext[i].field || ext[i].field>0x1fffffffu || (ext[i].length && overlap(buf,cap,ext[i].data,ext[i].length)))return -1;
    if(channel==9){for(unsigned i=0;i<count;i++)len=mm_upstream_append(buf,len,cap,ext[i].field,ext[i].data,ext[i].length);
        int result=send(user,type,channel,buf,len);
        if(!result){const uint8_t q[2]={17,0};(void)mm_upstream_battery_query(q,2,side,b,send,user);}return result;}
    return send(user,type,channel,buf,len);
}
void mm_upstream_capture_sample(mm_upstream_state *s,unsigned i,uint32_t stamp,const mm_upstream_capture *g){
    if(!s || !g || !s->compass_forward || i>=20)return;
    if(overlap(s,sizeof *s,g,sizeof *g))return;
    mm_upstream_sample *p=&s->compass_samples[i];p->timestamp=stamp;p->source=0;p->flags=128;
    if(g->grv){p->source=1;p->flags|=1;}if(g->gmrv && g->gmrv_heading){p->source=2;p->flags|=2;}if(g->rv && g->rv_heading){p->source=3;p->flags|=4;}
    if(g->mag_fresh){p->accuracy=g->accuracy;p->anomalies=g->anomalies;p->flags|=8;}
    else{p->accuracy=g->mag_seen?g->cached_accuracy:255;p->anomalies=g->mag_seen?g->cached_anomalies:255;}
}
unsigned mm_upstream_heading(const mm_upstream_state *s,unsigned event,int heading,unsigned side,const mm_upstream_record *records,unsigned count,uint8_t *buf,unsigned cap){
    if(!s || event!=9 || heading<0 || heading>=360 || !s->compass_forward || side!=1 || !buf || cap<24 || (count && !records))return 0;
    if(overlap(buf,cap,s,sizeof *s) || (count<=20 && count && overlap(buf,cap,records,count*(unsigned)sizeof *records)))return 0;
    uint8_t d[12]={'C','M',1,255,255,0,0,0,0,0,0,0};
    if(count<=20){while(count){unsigned i=--count;if(!records[i].heading_valid)continue;const mm_upstream_sample *p=&s->compass_samples[i];uint32_t t=records[i].timestamp;
        if((p->flags&128) && p->timestamp==t){d[3]=p->accuracy;d[4]=p->anomalies;d[5]=p->source;d[6]=p->flags;for(unsigned k=0;k<4;k++)d[8+k]=(uint8_t)(t>>(8*k));}break;}}
    buf[0]=8;buf[1]=15;buf[2]=16;buf[3]=0;buf[4]=0x52;buf[6]=8;unsigned n=writevar(buf+7,(unsigned)heading);buf[5]=(uint8_t)(n+1);
    return mm_upstream_append(buf,7+n,cap,100,d,sizeof d);
}
unsigned mm_upstream_filter(const mm_upstream_state *s,unsigned mode){return s && s->ble_fast?0xa3:mode;}
unsigned mm_upstream_classify(const mm_upstream_state *s,const mm_upstream_link *p,const void *conn,int connected,unsigned interval,unsigned latency){
    if(s && s->ble_fast)return connected && interval==6 && !latency?0xa3:0xa4;
    return p && p->classify?p->classify(p->user,conn):0xa4;
}
int mm_upstream_request(mm_upstream_state *s,const mm_upstream_link *p,unsigned mode,void *conn){
    if(!p || !p->request)return -1;
    if(s && s->ble_fast && (mode&255u)==0xa3){
        if(!p->stock_fast || !p->profile_set)return -1;
        const mm_upstream_profile *v=p->stock_fast(p->user);if(!v)return -1;
        s->profile.prefix=v->prefix;s->profile.min=6;s->profile.max=6;s->profile.latency=0;
        s->profile.timeout=v->timeout;s->profile.retries=v->retries;s->profile.suffix=v->suffix;p->profile_set(p->user,&s->profile);
    }return p->request(p->user,mode,conn);
}
static int valid_link(const mm_upstream_link *p){return p && p->profile_get && p->stock_fast && p->profile_set && p->wanted && p->clear_applied && p->set_wanted && p->generation && p->cancel && p->post;}
static void request_mode(const mm_upstream_link *p,unsigned mode){p->clear_applied(p->user);p->set_wanted(p->user,mode);p->cancel(p->user);p->post(p->user,mode|(p->generation(p->user)<<8),0);}
static void set_fast(mm_upstream_state *s,const mm_upstream_link *p,int fast){
    if(fast){s->ble_fast=1;request_mode(p,0xa3);return;}
    s->ble_fast=0;if(p->profile_get(p->user)==&s->profile)p->profile_set(p->user,p->stock_fast(p->user));
    unsigned wanted=p->wanted(p->user);request_mode(p,wanted==0xa3?0xa3:0xa4);
}
void mm_upstream_link_control(mm_upstream_state *s,const mm_upstream_link *p,const uint8_t *data,unsigned n){
    if(!s || !valid_link(p) || !data || n<4 || data[0]!='B' || data[1]!='L' || data[2]!=1)return;
    unsigned op=data[3];if(op>1 || ((op==1)==(s->ble_fast!=0)))return;set_fast(s,p,op==1);
}
void mm_upstream_link_cleanup(mm_upstream_state *s,const mm_upstream_link *p){if(s && s->ble_fast && valid_link(p))set_fast(s,p,0);}
void mm_upstream_link_status(const mm_upstream_state *s,const mm_upstream_link *p,unsigned side,int connected,unsigned interval,unsigned latency,uint8_t body[17]){
    if(!body)return;
    for(unsigned i=0;i<17;i++)body[i]=0;
    body[0]='B';body[1]='L';body[2]=1;body[3]=s && s->ble_fast;body[4]=(uint8_t)side;
    if(p){if(p->wanted)body[5]=(uint8_t)p->wanted(p->user);if(p->applied)body[6]=(uint8_t)p->applied(p->user);
        const mm_upstream_profile *v=p->profile_get?p->profile_get(p->user):0;if(v){w16(body+7,v->min);w16(body+9,v->max);w16(body+11,v->latency);}}
    if(connected){w16(body+13,interval);w16(body+15,latency);}
}
