/* MIT. H001Y 1.0.3.127 pre-stock ANCS event adapter. */
#include "ancs_ingress.h"
static uint32_t u16(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8);}
static uint32_t u32(const uint8_t *p){return u16(p)|(u16(p+2)<<16);}
static int same(const uint8_t *a,const uint8_t *b){for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;return 1;}
static int reject(mm_ancs_ingress *s){if(s->rejected!=UINT32_MAX)s->rejected++;return 0;}
void mm_ancs_ingress_reset(mm_ancs_ingress *s){
    s->connected=0;s->next=0;s->generation++;s->session++;
    s->relay->ancs_tail=s->relay->ancs_head;
    for(unsigned i=0;i<MM_ANCS_UIDS;i++)s->uids[i].valid=0;
}
void mm_ancs_ingress_init(mm_ancs_ingress *s,mm_notifications *relay){
    for(size_t i=0;i<sizeof(*s);i++)((uint8_t *)s)[i]=0;
    s->relay=relay;
}
static void peer(mm_ancs_ingress *s,const uint8_t *p){
    if(s->connected && same(s->peer,p))return;
    mm_ancs_ingress_reset(s);
    for(unsigned i=0;i<6;i++)s->peer[i]=p[i];
    s->connected=1;
}
static mm_ancs_uid *find(mm_ancs_ingress *s,uint32_t uid){
    for(unsigned i=0;i<MM_ANCS_UIDS;i++)if(s->uids[i].valid && s->uids[i].uid==uid)return &s->uids[i];
    return 0;
}
static int attributes_valid(const uint8_t *b,size_t n){
    if(!b || n<7 || n>MM_ANCS_BODY_MAX)return 0;
    size_t at=4;unsigned count=0,seen=0;
    while(at<n){
        if(n-at<3 || b[at]>7)return 0;
        if(seen&(1u<<b[at]))return 0;
        seen|=1u<<b[at];
        size_t len=u16(b+at+1);at+=3;
        if(len>MM_NOTIFICATIONS_ATTRIBUTE_MAX || len>n-at || ++count>8)return 0;
        at+=len;
    }
    return at==n;
}
static int app_valid(const uint8_t *b,size_t n){
    if(!b || n<4 || n>=MM_NOTIFICATIONS_ATTRIBUTE_MAX)return 0;
    size_t at=0;while(at<n && b[at])at++;
    return at>0 && at<=64 && n-at>=4 && b[at+1]==0 && u16(b+at+2)==n-at-4;
}
int mm_ancs_ingress_event(mm_ancs_ingress *s,uint16_t event,const uint8_t *p,size_t n,const uint8_t *b,size_t bn){
    if(!s || !s->relay || !p)return 0;
    if(event==0x258){
        if(n<12)return reject(s);
        uint32_t state=u32(p+8);
        if(state==3)peer(s,p);
        else if(state<2 && s->connected && same(s->peer,p))mm_ancs_ingress_reset(s);
        return 1;
    }
    if(event==0x25a){
        if(n!=14 || p[6]>2)return reject(s);
        peer(s,p);s->generation++;uint32_t uid=u32(p+10);mm_ancs_uid *item=find(s,uid);
        if(p[6]==2){if(item)item->valid=0;}
        else {
            if(!item){item=&s->uids[s->next];s->next=(uint8_t)((s->next+1)%MM_ANCS_UIDS);}
            *item=(mm_ancs_uid){uid,p[7],1};
        }
        mm_notifications_source(s->relay,p+6,8);return 1;
    }
    if(event!=0x25b)return 0;
    if(n!=16 || u16(p+12)!=bn || !s->connected || !same(s->peer,p))return reject(s);
    if(p[6]==0){
        if(!attributes_valid(b,bn) || !find(s,u32(b)))return reject(s);
        uint32_t uid=u32(b);size_t at=4;
        while(at<bn){uint8_t id=b[at];size_t len=u16(b+at+1);at+=3;
            mm_notifications_attribute(s->relay,uid,id,b+at,len);at+=len;}
        return 1;
    }
    if(p[6]==1){
        if(!app_valid(b,bn))return reject(s);
        /* Build chunks directly; no 1024-byte native stack buffer. */
        uint8_t *copy=s->relay->platform.allocate(s->relay->platform.user,bn+1);
        if(!copy)return reject(s);
        copy[0]=1;for(size_t i=0;i<bn;i++)copy[i+1]=b[i];
        mm_notifications_app_response(s->relay,copy,bn+1);
        s->relay->platform.deallocate(s->relay->platform.user,copy);return 1;
    }
    return reject(s);
}
int mm_ancs_ingress_action(const mm_ancs_ingress *s,uint32_t uid,uint8_t action,uint8_t out[6],uint32_t *generation){
    if(!s || !out || !generation || !s->connected || action>1)return 0;
    for(unsigned i=0;i<MM_ANCS_UIDS;i++)if(s->uids[i].valid && s->uids[i].uid==uid &&
            (s->uids[i].flags&(8u<<action))){
        for(unsigned j=0;j<6;j++)out[j]=s->peer[j];
        *generation=s->generation;return 1;
    }
    return 0;
}
