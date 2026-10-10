#include "program_package.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint16_t draw[PR_WIDTH*PR_HEIGHT];
static void flush(lv_display_t *d,const lv_area_t *a,uint8_t *p){(void)a;(void)p;lv_display_flush_ready(d);}
static pr_clock clock_at(uint64_t t){return(pr_clock){t,1000000+(int64_t)t,PR_WALL_SYNCHRONIZED};}
static pr_runtime *make(const char *s){pr_program p={s,strlen(s),NULL,0};const char *error=NULL;pr_runtime *r=pr_create(&p,clock_at(0),123,&error);if(error)fprintf(stderr,"create: %s\n",error);return r;}
static void show(pr_runtime *r){assert(pr_attach(r,lv_screen_active()));lv_obj_remove_flag(pr_root(r),LV_OBJ_FLAG_HIDDEN);pr_set_activation(r,1);}
static void drop(pr_runtime *r){pr_detach(r);pr_destroy(r);lv_refr_now(lv_display_get_default());}
static bool tick(pr_runtime *r,uint64_t t){return pr_dispatch(r,(pr_event){1,t,PR_TICK,0,0},clock_at(t));}
static uint16_t rgb(unsigned n){return(uint16_t)(((n>>19)<<11)|(((n>>10)&63)<<5)|((n>>3)&31));}
static unsigned pixel(pr_runtime *r,int x,int y){return pr_pixels(r)[y*PR_WIDTH+x];}
int main(void){
    lv_init();lv_display_t *d=lv_display_create(PR_WIDTH,PR_HEIGHT);assert(d);lv_display_set_color_format(d,LV_COLOR_FORMAT_RGB565);lv_display_set_buffers(d,draw,NULL,sizeof(draw),LV_DISPLAY_RENDER_MODE_FULL);lv_display_set_flush_cb(d,flush);
    const char *logic="let n=0;function paint(c){gfx.begin('#000000');gfx.rect(3,4,12,13,c);gfx.end()}paint('#ff69b4');app.onPointer(e=>{if(e.type==='down'){n++;paint(['#ff69b4','#4287f5','#80ff80'][n%3]);}});";
    pr_runtime *r=make(logic);assert(r);show(r);assert(pixel(r,4,5)==rgb(0xff69b4));
    const unsigned colors[]={0x4287f5,0x80ff80,0xff69b4};
    for(unsigned i=0;i<3;i++){assert(pr_dispatch(r,(pr_event){1,i+1,PR_DOWN,4,5},clock_at(i+1)));assert(pr_present(r));assert(pixel(r,4,5)==rgb(colors[i]));}
    assert(pr_dispatch(r,(pr_event){999,4,PR_DOWN,4,5},clock_at(4)));assert(pr_get_metrics(r).stale_events==1);drop(r);
    const char *bad[]={"throw Error('init')","while(true){}","Promise.reject(Error('init'))","Promise.resolve().then(()=>{throw Error('async')})","function spin(){Promise.resolve().then(spin)}spin()","const a=[];while(true)a.push('x'.repeat(1000))","function f(){f()}f()","gfx.begin('#000000');gfx.begin('#ffffff')","gfx.begin('#000000');try{for(let i=0;i<1000;i++)gfx.rect(0,0,1,1,'#ffffff')}catch(e){}gfx.end()","gfx.begin('#000000');gfx.rect({valueOf(){while(true){}}},0,1,1,'#ffffff')"};
    for(size_t i=0;i<sizeof(bad)/sizeof(*bad);i++){pr_program p={bad[i],strlen(bad[i]),NULL,0};const char *e=NULL;assert(!pr_create(&p,clock_at(0),1,&e));assert(e);}
    r=make("const p=Promise.reject(1);Promise.resolve().then(()=>p.catch(()=>{}));gfx.begin('#123456');gfx.end();");assert(r);show(r);assert(pixel(r,0,0)==rgb(0x123456));drop(r);
    const char *end_failures[]={"throw Error('sync')","return Promise.reject(Error('async'))","return Promise.resolve().then(()=>{throw Error('job')})","while(true){}"};
    for(size_t i=0;i<sizeof(end_failures)/sizeof(*end_failures);i++){char s[512];snprintf(s,sizeof(s),"gfx.begin('#123456');gfx.end();app.onTick(()=>{gfx.begin('#ffffff');gfx.end();%s});",end_failures[i]);r=make(s);assert(r);show(r);assert(!tick(r,1));assert(!pr_present(r));assert(pixel(r,0,0)==rgb(0x123456));drop(r);}
    r=make("gfx.begin('#123456');gfx.end();app.onTick(()=>{gfx.begin('#ffffff');gfx.rect(0,0,10,10,'#ff0000')});");assert(r);show(r);assert(tick(r,5000));assert(pr_present(r));assert(pixel(r,0,0)==rgb(0x123456));drop(r);
    r=make("let n=0;app.onTick(e=>{if(e.delta!==5000||e.now!==5000||app.now()!==5000)throw Error('clock');app.onTick(e=>{if(e.delta!==0)throw Error('resume');gfx.begin('#00ff00');gfx.end()});gfx.begin('#ff0000');gfx.end()});");assert(r);show(r);assert(tick(r,5000));assert(pr_present(r));assert(pixel(r,0,0)==rgb(0xff0000));pr_pause(r);assert(tick(r,6000));pr_resume(r,clock_at(9000));assert(tick(r,9000));assert(pr_present(r));assert(pixel(r,0,0)==rgb(0x00ff00));drop(r);
    r=make("if(typeof Date!=='undefined'||typeof performance!=='undefined')throw Error('host clock');if(app.wallTime().source!=='synchronized'||!app.wallTime().valid)throw Error('wall');gfx.begin('#000000');gfx.text(0,0,'Computed '+[2,3,4].reduce((a,b)=>a*b,1),'#ffffff');gfx.line(0,30,319,30,'#ff0000',2);gfx.end();");assert(r);show(r);assert(pixel(r,160,30)==rgb(0xff0000));drop(r);
    const uint8_t rgba[]={255,0,0,255,0,255,0,0,0,0,255,255,255,255,255,128};
    pr_asset asset={"sprite",2,2,rgba,sizeof(rgba)};const char *s="gfx.begin('#000000');gfx.image('sprite',1,1);gfx.end()";pr_program p={s,strlen(s),&asset,1};const char *error=NULL;r=pr_create(&p,clock_at(0),1,&error);assert(r);show(r);assert(pixel(r,1,1)==rgb(0xff0000));assert(pixel(r,2,1)==0);assert(pixel(r,1,2)==rgb(0x0000ff));assert(pixel(r,2,2)>0&&pixel(r,2,2)<65535);assert(rgba[0]==255&&rgba[2]==0);drop(r);
    for(unsigned i=0;i<100;i++){r=make(logic);assert(r);show(r);assert(tick(r,100));drop(r);}
    const char *invalid_json[]={"{\"x\":1,\"x\":2}","{\"x\":1.0}","{\"x\":1e0}","{\"x\":\"\\u0000\"}","{\"x\":\"\\ud800\"}","{\"x\":\"\\udc00\"}","{\"x\":\"\xc0\x80\"}","[[[[[[[[[[[[[0]]]]]]]]]]]]]"};
    for(size_t i=0;i<sizeof(invalid_json)/sizeof(*invalid_json);i++)assert(!pr_json_parse(invalid_json[i],strlen(invalid_json[i]),65536));
    cJSON *valid=pr_json_parse("{\"x\":\"\\ud83d\\ude00\"}",20,65536);assert(valid);cJSON_Delete(valid);
    lv_display_delete(d);lv_deinit();puts("{\"status\":\"program_core_tests_passed\",\"install_cycles\":100,\"physical_execution\":false}");return 0;
}
