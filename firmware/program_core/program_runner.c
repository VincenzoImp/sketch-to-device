/* Fixed host executable: input packages/scenarios are data, never commands. */
#include "program_package.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static uint16_t draw_buffer[PR_WIDTH*PR_HEIGHT], framebuffer[PR_WIDTH*PR_HEIGHT];
static void flush(lv_display_t *d,const lv_area_t *a,uint8_t *pixels) {
    int w=a->x2-a->x1+1;
    for(int y=a->y1;y<=a->y2;y++){memcpy(framebuffer+y*PR_WIDTH+a->x1,pixels,(size_t)w*2);pixels+=w*2;}
    lv_display_flush_ready(d);
}
static void *read_file(const char *name,size_t maximum,size_t *size) {
    FILE *f=fopen(name,"rb");if(!f)return NULL;
    unsigned char *p=malloc(maximum+1);if(!p){fclose(f);return NULL;}
    *size=fread(p,1,maximum+1,f);bool ok=!ferror(f)&&*size&&*size<=maximum;fclose(f);
    if(!ok){free(p);return NULL;}return p;
}
static const cJSON *get(const cJSON *v,const char *s){return cJSON_GetObjectItemCaseSensitive(v,s);}
static const char *text(const cJSON *v,const char *s){const cJSON *x=get(v,s);return cJSON_IsString(x)?x->valuestring:NULL;}
static bool num(const cJSON *v,const char *s,double lo,double hi,uint64_t *out){const cJSON *x=get(v,s);if(!cJSON_IsNumber(x)||x->valuedouble<lo||x->valuedouble>hi)return false;*out=(uint64_t)x->valuedouble;return true;}
static bool shape(const cJSON *v,const char *const *names,size_t n){if(!cJSON_IsObject(v)||cJSON_GetArraySize(v)!=(int)n)return false;for(size_t i=0;i<n;i++)if(!get(v,names[i]))return false;return true;}
static bool identifier(const char *s){if(!s||!*s||strlen(s)>48||*s<'a'||*s>'z')return false;for(;*s;s++)if(!(*s>='a'&&*s<='z')&&!(*s>='0'&&*s<='9')&&*s!='_'&&*s!='-')return false;return true;}
static bool save_frame(const char *directory,unsigned index,lv_display_t *display,cJSON *frames,const char *name) {
    lv_obj_update_layout(lv_screen_active());lv_obj_invalidate(lv_screen_active());lv_refr_now(display);
    uint8_t *raw=malloc(sizeof(framebuffer));if(!raw)return false;
    for(size_t i=0;i<PR_WIDTH*PR_HEIGHT;i++){raw[i*2]=framebuffer[i]&255;raw[i*2+1]=framebuffer[i]>>8;}
    char base[40],path[4096],hash[65];snprintf(base,sizeof(base),"frame-%04u.rgb565",index);pr_sha256(raw,sizeof(framebuffer),hash);
    bool ok=snprintf(path,sizeof(path),"%s/%s",directory,base)<(int)sizeof(path);FILE *f=ok?fopen(path,"wb"):NULL;
    if(!f){free(raw);return false;}ok=fwrite(raw,1,sizeof(framebuffer),f)==sizeof(framebuffer);ok=fclose(f)==0&&ok;free(raw);if(!ok)return false;
    chmod(path,0600);
    cJSON *entry=cJSON_CreateObject();cJSON_AddStringToObject(entry,"name",name);cJSON_AddStringToObject(entry,"rgb565",base);cJSON_AddStringToObject(entry,"sha256",hash);
    snprintf(base,sizeof(base),"frame-%04u.ppm",index);snprintf(path,sizeof(path),"%s/%s",directory,base);f=fopen(path,"wb");if(!f){cJSON_Delete(entry);return false;}
    ok=fprintf(f,"P6\n%d %d\n255\n",PR_WIDTH,PR_HEIGHT)>0;
    for(unsigned i=0;i<PR_WIDTH*PR_HEIGHT&&ok;i++){unsigned v=framebuffer[i];unsigned char rgb[]={(unsigned char)((v>>11)*255/31),(unsigned char)(((v>>5)&63)*255/63),(unsigned char)((v&31)*255/31)};ok=fwrite(rgb,1,3,f)==3;}
    ok=fclose(f)==0&&ok;chmod(path,0600);if(!ok){cJSON_Delete(entry);return false;}
    cJSON_AddStringToObject(entry,"ppm",base);cJSON_AddNumberToObject(entry,"width",PR_WIDTH);cJSON_AddNumberToObject(entry,"height",PR_HEIGHT);cJSON_AddItemToArray(frames,entry);return true;
}
int main(int argc,char **argv) {
    if(argc!=7||strcmp(argv[1],"--package")||strcmp(argv[3],"--scenario")||strcmp(argv[5],"--output")){puts("{\"status\":\"invalid_arguments\"}");return 2;}
    const char *fault="invalid_package";size_t size=0;void *raw=read_file(argv[2],PR_PACKAGE_BYTES,&size);pr_package package={0};
    cJSON *scenario=NULL,*frames=cJSON_CreateArray(),*report=cJSON_CreateObject();pr_runtime *r=NULL;lv_display_t *display=NULL;unsigned steps=0,frame_count=0;char package_hash[65]={0};bool lv_started=false,ok=false;pr_diagnostic diagnostic={0};
    if(!raw||!pr_package_parse(raw,size,&package,&fault))goto end;pr_sha256(raw,size,package_hash);free(raw);raw=NULL;
    fault="invalid_scenario";raw=read_file(argv[4],PR_SCENARIO_BYTES,&size);if(!raw)goto end;scenario=pr_json_parse(raw,size,PR_SCENARIO_BYTES);free(raw);raw=NULL;
    static const char *const skeys[]={"version","seed","initial_time_ms","wall_time","events"};uint64_t version,seed,start;
    if(!scenario||!shape(scenario,skeys,5)||!num(scenario,"version",1,1,&version)||!num(scenario,"seed",0,4294967295.,&seed)||!num(scenario,"initial_time_ms",0,9007199254620991.,&start))goto end;
    pr_clock clock={.monotonic_ms=start};const cJSON *wall=get(scenario,"wall_time");int64_t epoch=0;
    if(!cJSON_IsNull(wall)) {
        static const char *const wkeys[]={"epoch_ms","source"};uint64_t e;
        if(!shape(wall,wkeys,2)||!num(wall,"epoch_ms",0,9007199254620991.,&e)||!text(wall,"source"))goto end;
        const char *s=text(wall,"source");clock.wall_source=!strcmp(s,"estimated")?PR_WALL_ESTIMATED:!strcmp(s,"synchronized")?PR_WALL_SYNCHRONIZED:PR_WALL_UNAVAILABLE;if(!clock.wall_source)goto end;epoch=(int64_t)e;clock.epoch_ms=epoch;
    }
    const cJSON *events=get(scenario,"events");if(!cJSON_IsArray(events)||cJSON_GetArraySize(events)>4096)goto end;
    /* Validate the complete scenario before executing any source. */
    uint64_t last=start;unsigned nf=0;const char *names[16];
    for(const cJSON *e=events->child;e;e=e->next) {
        const char *t=text(e,"type");if(!t)goto end;
        if(!strcmp(t,"frame")) {
            static const char *const keys[]={"type","name"};const char *name=text(e,"name");if(!shape(e,keys,2)||!identifier(name)||nf>=16)goto end;
            for(unsigned i=0;i<nf;i++)if(!strcmp(names[i],name))goto end;names[nf++]=name;continue;
        }
        uint64_t time;if(!num(e,"time_ms",(double)last,(double)(start+120000),&time))goto end;last=time;
        if(!strcmp(t,"pointer")) {
            static const char *const keys[]={"type","phase","x","y","time_ms"};const char *p=text(e,"phase");uint64_t x,y;
            if(!shape(e,keys,5)||!p||(strcmp(p,"down")&&strcmp(p,"move")&&strcmp(p,"up")&&strcmp(p,"cancel"))||!num(e,"x",0,PR_WIDTH-1,&x)||!num(e,"y",0,PR_HEIGHT-1,&y))goto end;
        } else {static const char *const keys[]={"type","time_ms"};if(!shape(e,keys,2)||(strcmp(t,"tick")&&strcmp(t,"pause")&&strcmp(t,"resume")))goto end;}
    }
    lv_init();lv_started=true;display=lv_display_create(PR_WIDTH,PR_HEIGHT);if(!display){fault="native_allocation";goto end;}
    lv_display_set_color_format(display,LV_COLOR_FORMAT_RGB565);lv_display_set_buffers(display,draw_buffer,NULL,sizeof(draw_buffer),LV_DISPLAY_RENDER_MODE_FULL);lv_display_set_flush_cb(display,flush);
    r=pr_create_diagnostic(&package.program,clock,(uint32_t)seed,&fault,&diagnostic);if(!r)goto end;
    pr_set_activation(r,1);if(!pr_attach(r,lv_screen_active())){fault="native_attach";goto end;}lv_obj_remove_flag(pr_root(r),LV_OBJ_FLAG_HIDDEN);
    for(const cJSON *e=events->child;e;e=e->next) {
        const char *t=text(e,"type");steps++;
        if(!strcmp(t,"frame")){if(!pr_present(r)||!save_frame(argv[6],frame_count++,display,frames,text(e,"name"))){fault="frame_output";goto end;}continue;}
        uint64_t time=0;num(e,"time_ms",0,9007199254740991.,&time);clock.monotonic_ms=time;clock.epoch_ms=epoch+(int64_t)(time-start);
        if(!strcmp(t,"pause")){pr_pause(r);continue;}if(!strcmp(t,"resume")){pr_resume(r,clock);continue;}
        pr_event event={.activation=1,.timestamp_ms=time,.type=PR_TICK};
        if(!strcmp(t,"pointer")){const char *p=text(e,"phase");event.type=!strcmp(p,"down")?PR_DOWN:!strcmp(p,"move")?PR_MOVE:!strcmp(p,"up")?PR_UP:PR_CANCEL;uint64_t x=0,y=0;num(e,"x",0,319,&x);num(e,"y",0,431,&y);event.x=(int)x;event.y=(int)y;}
        if(!pr_dispatch(r,event,clock)){fault=pr_get_metrics(r).fault;goto end;}if(!pr_present(r)){fault="native_present";goto end;}
    }
    ok=true;fault=NULL;
end:
    free(raw);cJSON_AddStringToObject(report,"status",ok?"completed":"rejected");if(fault)cJSON_AddStringToObject(report,"error",fault);cJSON_AddStringToObject(report,"engine","quickjs-ng-0.14.0");cJSON_AddStringToObject(report,"sdk","device-js-1");cJSON_AddStringToObject(report,"profile","p4-canvas-1");cJSON_AddStringToObject(report,"package_sha256",package_hash);cJSON_AddNumberToObject(report,"steps",steps);cJSON_AddItemToObject(report,"frames",frames);
    if(r)pr_get_diagnostic(r,&diagnostic);
    if(!ok&&diagnostic.exception_name[0]) {
        cJSON *detail=cJSON_CreateObject();cJSON_AddStringToObject(detail,"phase",diagnostic.phase);
        cJSON_AddStringToObject(detail,"exception_name",diagnostic.exception_name);cJSON_AddStringToObject(detail,"message",diagnostic.message);
        if(diagnostic.line)cJSON_AddNumberToObject(detail,"line",diagnostic.line);else cJSON_AddNullToObject(detail,"line");
        if(diagnostic.column)cJSON_AddNumberToObject(detail,"column",diagnostic.column);else cJSON_AddNullToObject(detail,"column");
        cJSON_AddBoolToObject(detail,"truncated",diagnostic.truncated);cJSON_AddItemToObject(report,"diagnostic",detail);
    }
    if(r){pr_metrics m=pr_get_metrics(r);cJSON_AddNumberToObject(report,"callbacks",m.callbacks);cJSON_AddNumberToObject(report,"committed_frames",m.frames);cJSON_AddNumberToObject(report,"peak_engine_payload",(double)m.peak_engine_payload);cJSON_AddNumberToObject(report,"owned_native_bytes",(double)m.owned_native_bytes);pr_detach(r);pr_destroy(r);}
    cJSON_AddBoolToObject(report,"physical_execution",false);char *output=cJSON_PrintUnformatted(report);if(output){puts(output);free(output);}cJSON_Delete(report);cJSON_Delete(scenario);pr_package_free(&package);if(display)lv_display_delete(display);if(lv_started)lv_deinit();return ok?0:1;
}
