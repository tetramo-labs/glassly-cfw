/* Offset-based cached assets. Included only by MM_SCENE_EXTERNAL_STORE builds. */
typedef struct {uint32_t offset,length,width,height;} mm_external_image;
static mm_scene_bytes mm_asset_bytes(mm_scene_context *ctx,uint32_t off,uint32_t n) {
    mm_scene_bytes b={0,&ctx->external_store,off,n};return b;
}
static int mm_external_read(mm_scene_context *ctx,const mm_scene_bytes *b,uint32_t off,void *out,size_t n) {
    int rc=mm_scene_bytes_read(b,off,out,n);if(rc==-2)ctx->storage_io=1;return rc;
}
static int mm_external_cursor(mm_scene_context *ctx,mm_scene_cursor *c,uint32_t off,void *out,size_t n) {
    int rc=mm_scene_cursor_read(c,off,out,n);if(rc==-2)ctx->storage_io=1;return rc;
}
static int mm_external_token(mm_scene_context *ctx,mm_scene_cursor *c,uint32_t off,uint32_t *used,uint32_t *count,uint8_t *color) {
    uint8_t p[4];if(mm_external_cursor(ctx,c,off,p,1))return 0;
    unsigned n=p[0]>>4;*color=p[0]&15;
    if(n){*used=1;*count=n;return 1;}
    if(mm_external_cursor(ctx,c,off,p,2))return 0;
    if(p[1]){*used=2;*count=p[1];return 1;}
    if(mm_external_cursor(ctx,c,off,p,4))return 0;
    n=rd16(p+2);if(!n)return 0;*used=4;*count=n;return 1;
}
static int mm_external_image_in(mm_scene_context *ctx,const mm_scene_bytes *b,uint32_t off,mm_external_image *img) {
    uint8_t h[2];if(mm_external_read(ctx,b,off,h,2)||!h[0]||!h[1])return 0;
    mm_scene_cursor c;if(mm_scene_cursor_init(&c,b))return 0;uint32_t pos=off+2,left=(uint32_t)h[0]*h[1];
    while(left){uint32_t used,count;uint8_t color;if(!mm_external_token(ctx,&c,pos,&used,&count,&color)||count>left)return 0;left-=count;pos+=used;}
    *img=(mm_external_image){off+2,pos-off-2,h[0],h[1]};return 1;
}
/* Header only: every resident image and font was validated token by token at
 * commit (mm_external_content), so a draw needs just the size; the render stops
 * at the last pixel and a token past the asset fails in the cursor. */
static int mm_external_image_head(mm_scene_context *ctx,const mm_scene_bytes *b,uint32_t off,mm_external_image *img) {
    uint8_t h[2];if(off>b->length||b->length-off<2||mm_external_read(ctx,b,off,h,2)||!h[0]||!h[1])return 0;
    *img=(mm_external_image){off+2,b->length-off-2,h[0],h[1]};return 1;
}
static int mm_external_content(mm_scene_context *ctx,const mm_scene_bytes *b,uint8_t kind) {
    if(kind==CFW_ASSET_IMAGE){mm_external_image img;return mm_external_image_in(ctx,b,0,&img)&&img.length+2==b->length;}
    if(kind==CFW_ASSET_FONT){
        if(b->length<384)return 0;
        for(unsigned i=0;i<96;i++){uint8_t raw[4];if(mm_external_read(ctx,b,i*4,raw,4))return 0;uint32_t off=rd32(raw);mm_external_image img;if(off&&(off<384||!mm_external_image_in(ctx,b,off,&img)))return 0;}
        return 1;
    }
    if(kind==CFW_ASSET_STRING){uint8_t s[128];return b->length<=128&&!mm_external_read(ctx,b,0,s,b->length)&&cfw_texture_string_valid(s,b->length);}
    return 0;
}
/* Content was validated at commit, so rows below the view are not read. */
static int mm_external_render(mm_scene_context *ctx,const cfw_raster *r,const mm_scene_bytes *b,const mm_external_image *img,
                              int32_t x0,int32_t y0,const uint8_t *lut,int transparent) {
    mm_scene_cursor c;if(mm_scene_cursor_init(&c,b))return -1;uint32_t pos=0,pixel=0,total=img->width*img->height,col=0;int32_t y=y0;
    while(pixel<total&&y<r->h){
        uint32_t used,count;uint8_t color;
        if(pos>=img->length||!mm_external_token(ctx,&c,img->offset+pos,&used,&count,&color)||used>img->length-pos||count>total-pixel)return -1;
        pos+=used;pixel+=count;int skip=transparent&&!color;uint8_t mapped=lut[color];
        while(count){
            uint32_t run=img->width-col;if(run>count)run=count;
            if(!skip&&y>=0){
                int32_t x=x0+(int32_t)col,end=x+(int32_t)run;if(x<0)x=0;if(end>r->w)end=r->w;
                for(;x<end;x++){uint8_t *p=r->buf+(uint32_t)y*r->stride+((uint32_t)x>>1);if(x&1)*p=(uint8_t)((*p&240)|mapped);else *p=(uint8_t)((*p&15)|(mapped<<4));}
            }
            count-=run;col+=run;
            if(col==img->width){col=0;if(++y>=r->h)return 0;}
        }
    }
    return 0;
}
static int mm_external_image_draw(mm_scene_context *ctx,const cfw_raster *r,const mm_scene_bytes *b,int32_t x,int32_t y,uint8_t options,cfw_rectlist *rl) {
    mm_external_image img;if(!mm_external_image_head(ctx,b,0,&img))return -1;
    uint8_t lut[16];cfw_texture_make_lut(options,lut);
    if(mm_external_render(ctx,r,b,&img,x,y,lut,options&CFW_TEXTURE_OPT_TRANSPARENT))return -1;
    cfw_texture_add_rect(rl,x,y,img.width,img.height,(uint32_t)r->w,(uint32_t)r->h);return 0;
}
static int mm_external_string_draw(mm_scene_context *ctx,const cfw_raster *r,const mm_scene_bytes *font,const mm_scene_bytes *string,int32_t x,int32_t y,uint8_t options,cfw_rectlist *rl) {
    /* Immediate mode20 permits255 bytes; retained strings remain<=128. */
    uint8_t s[255];if(string->length>255||font->length<384||mm_external_read(ctx,string,0,s,string->length))return -1;
    for(unsigned i=0;i<string->length;i++){
        if(s[i]>=1&&s[i]<=31)continue;
        if(s[i]<32||s[i]>127)return -1;
        uint8_t raw[4];if(mm_external_read(ctx,font,(s[i]-32)*4,raw,4))return -1;
        uint32_t off=rd32(raw);if(off<384||off>font->length-2)return -1;
    }
    uint8_t lut[16];cfw_texture_make_lut(options,lut);
    for(unsigned i=0;i<string->length;i++){
        if(s[i]<=31){x+=(int32_t)s[i]-11;continue;}
        uint8_t raw[4];if(mm_external_read(ctx,font,(s[i]-32)*4,raw,4))return -1;
        mm_external_image img;if(!mm_external_image_head(ctx,font,rd32(raw),&img)||mm_external_render(ctx,r,font,&img,x,y,lut,options&CFW_TEXTURE_OPT_TRANSPARENT))return -1;
        cfw_texture_add_rect(rl,x,y,img.width,img.height,(uint32_t)r->w,(uint32_t)r->h);x+=(int32_t)img.width;
    }
    return 0;
}
