/* Same owner/lifecycle/renderer with real QuickJS and LVGL. Scheduling is stepped
 * deterministically; this does not measure FreeRTOS timing or physical heap. */
#include "app_ui_port.h"
#include "program_runtime.h"
/* Assert the real binding is never entered with the display mutex held. */
static pr_runtime *checked_create(const pr_program *p,pr_clock c,uint32_t seed,const char **error,pr_diagnostic *diagnostic,pr_startup *startup){assert(!host_display_locked);return pr_create_observed(p,c,seed,error,diagnostic,startup);}
static bool checked_dispatch(pr_runtime *r,pr_event e,pr_clock c){assert(!host_display_locked);return pr_dispatch(r,e,c);}
static void checked_destroy(pr_runtime *r){assert(!host_display_locked);pr_destroy(r);}
static bool checked_attach(pr_runtime *r,lv_obj_t *p){assert(host_display_locked);return pr_attach(r,p);}
static bool checked_present(pr_runtime *r){assert(host_display_locked);return pr_present(r);}
static void checked_detach(pr_runtime *r){assert(host_display_locked);pr_detach(r);}
#define pr_create_observed checked_create
#define pr_dispatch checked_dispatch
#define pr_destroy checked_destroy
#define pr_attach checked_attach
#define pr_present checked_present
#define pr_detach checked_detach
#include "../main/app_ui.c"
#include <assert.h>
#include <stdio.h>
static uint16_t display_pixels[320*480];
static void flush(lv_display_t *display,const lv_area_t *area,uint8_t *pixels){
    (void)area;(void)pixels;lv_display_flush_ready(display);
}
static app_package *program(const char *source){
    cJSON *v=cJSON_CreateObject();
    cJSON_AddNumberToObject(v,"schema_version",2);cJSON_AddStringToObject(v,"app_id","test_program");
    cJSON_AddStringToObject(v,"name","Runtime test");cJSON_AddNumberToObject(v,"version",1);
    cJSON_AddStringToObject(v,"runtime","quickjs-ng-0.14.0");cJSON_AddStringToObject(v,"sdk","device-js-1");
    cJSON_AddStringToObject(v,"profile","p4-canvas-1");cJSON_AddArrayToObject(v,"requires");
    cJSON_AddStringToObject(v,"source",source);cJSON_AddArrayToObject(v,"assets");
    char *bytes=cJSON_PrintUnformatted(v);const char *error=NULL;
    app_package *p=app_package_parse(bytes,strlen(bytes),&error);
    assert(p && !error);free(bytes);cJSON_Delete(v);return p;
}
static void step(void){host_us+=20000;owner_step();assert(!host_display_locked);lv_timer_handler();}
static app_ui_state snapshot(void){app_ui_state s;app_ui_snapshot(&s);return s;}
static app_ui_ticket prepare_source(const char *source,bool succeeds){
    app_ui_ticket t=0;assert(app_ui_prepare(program(source),&t));assert(t && snapshot().pending);
    step();app_ui_state s=snapshot();assert(!s.pending && s.operation_ticket==t);
    assert(s.succeeded==succeeds);return t;
}
static void request(app_ui_operation op,app_ui_ticket t,bool succeeds){
    assert(app_ui_request(op,t));step();app_ui_state s=snapshot();assert(!s.pending);
    assert(s.operation==op && s.operation_ticket==t && s.succeeded==succeeds);
}
static const char *base="let n=0; const colors=['#ff00ff','#0000ff','#00ff00']; function draw(){gfx.begin(colors[n%3]);gfx.end();} draw(); app.onPointer(e=>{if(e.type==='down'){n++;draw();}});";
static app_ui_ticket install(const char *source){app_ui_ticket t=prepare_source(source,true);request(APP_UI_ACTIVATE,t,true);request(APP_UI_COMMIT,t,true);return t;}
static app_package *legacy_fixture(void){
    FILE *file=fopen(APP_UI_FIXTURE,"rb");assert(file);char bytes[16384];
    size_t n=fread(bytes,1,sizeof(bytes),file);assert(n && !ferror(file) && feof(file));fclose(file);
    const char *error=NULL;app_package *package=app_package_parse(bytes,n,&error);
    assert(package && package->kind==APP_PACKAGE_LEGACY && !error);return package;
}
static void pointer(app_ui_ticket t,pr_event_type type){
    ui_event e={.is_pointer=true,.pointer={t,(uint64_t)(host_us/1000),type,10,10}};
    assert(xQueueSend(edges,&e,0));step();
}
int main(void){
    lv_init();lv_display_t *display=lv_display_create(320,480);assert(display);
    lv_display_set_color_format(display,LV_COLOR_FORMAT_RGB565);
    lv_display_set_buffers(display,display_pixels,NULL,sizeof(display_pixels),LV_DISPLAY_RENDER_MODE_FULL);
    lv_display_set_flush_cb(display,flush);
    assert(app_ui_init() && host_stack_size==65536);
    app_package *legacy=legacy_fixture();
    builtin_copy=malloc(sizeof(*builtin_copy));assert(builtin_copy);*builtin_copy=*legacy->data.legacy;
    app_ui_ticket legacy_ticket;
    assert(app_ui_prepare(legacy,&legacy_ticket));step();
    request(APP_UI_ACTIVATE,legacy_ticket,true);request(APP_UI_COMMIT,legacy_ticket,true);
    int start=as_find_widget(live->legacy.app,"start");assert(start>=0);
    ui_event start_event={.widget=start,.token={legacy_ticket,live->legacy.entry}};
    assert(xQueueSend(events,&start_event,0));step();assert(live->legacy.screen!=0);
    /* Delivery may run immediately after command completion, before the next
     * owner tick obtains the BSP mutex. Pausing a legacy prior app performs its
     * own checkpoint; it must not replace the candidate activation evidence. */
    app_ui_ticket first=prepare_source(base,true);
    assert(app_ui_request(APP_UI_ACTIVATE,first));
    ui_command activation_command;assert(xQueueReceive(commands,&activation_command,0));
    command_execute(activation_command);
    assert(snapshot().live==first && snapshot().succeeded && snapshot().checkpoint_ticket==first);
    request(APP_UI_COMMIT,first,true);
    assert(snapshot().previous==legacy_ticket);
    uint16_t initial=pr_pixels(live->script)[0];pointer(first,PR_DOWN);
    assert(pr_pixels(live->script)[0]!=initial);
    uint16_t changed=pr_pixels(live->script)[0];
    prepare_source("Promise.reject(Error('initialization failure'))",false);
    assert(snapshot().live==first && pr_pixels(live->script)[0]==changed);
    prepare_source("for(;;){}",false);assert(snapshot().live==first);
    host_internal_free=65536;prepare_source(base,false);host_internal_free=8*1024*1024;
    assert(snapshot().live==first && strcmp(snapshot().error,"native_memory_admission")==0);
    app_ui_ticket rejected=prepare_source("gfx.begin('#000000');gfx.end();app.onTick(()=>{throw Error('first tick')});",true);
    request(APP_UI_ACTIVATE,rejected,false);assert(snapshot().live==first);
    request(APP_UI_ABORT,rejected,true);assert(!snapshot().fault_ticket);
    app_ui_ticket second=install("gfx.begin('#ffffff');gfx.end();app.onPointer(async()=>{throw Error('late fault')});");
    pointer(second,PR_DOWN);assert(snapshot().fault_ticket==second && live->failed);
    assert(!app_ui_ack_fault(second));request(APP_UI_ROLLBACK,second,true);
    assert(snapshot().live==first && snapshot().recovered_ticket==first);
    assert(pr_pixels(live->script)[0]==changed);assert(app_ui_ack_fault(second));
    pointer(second,PR_DOWN);assert(snapshot().live==first && snapshot().stale_input);
    app_ui_ticket staged=prepare_source(base,true);request(APP_UI_ABORT,staged,true);
    assert(snapshot().live==first && snapshot().prepared==0);
    app_ui_ticket busy_ticket;
    assert(app_ui_prepare(program(base),&busy_ticket));
    app_package *not_transferred=program(base);app_ui_ticket unused=0;
    assert(!app_ui_prepare(not_transferred,&unused));app_package_free(not_transferred);
    step();request(APP_UI_ABORT,busy_ticket,true);
    /* Real LVGL callback fills protected edge queue, overflow emits a cancel. */
    lv_indev_t *input=lv_indev_create();assert(input);lv_indev_set_type(input,LV_INDEV_TYPE_POINTER);
    lv_obj_t *touch=lv_obj_get_child(pr_root(live->script),-1);
    for(int i=0;i<8;i++)lv_obj_send_event(touch,LV_EVENT_PRESSED,input);
    lv_obj_send_event(touch,LV_EVENT_RELEASED,input);
    assert(cancel_pending && snapshot().dropped_input);step();assert(!cancel_pending && !edges->count);
    lv_indev_delete(input);
    /* Home survives an overfull ordinary event queue, then resumes unchanged. */
    ui_event home={.widget=-1,.token={first,0}};
    for(int i=0;i<24;i++)assert(xQueueSend(events,&home,0));
    assert(xQueueOverwrite(homes,&home));step();assert(snapshot().paused);
    assert(xQueueOverwrite(homes,&home));step();assert(!snapshot().paused);
    xQueueReset(events);
    app_ui_ticket before=install(base);
    app_ui_ticket candidate=prepare_source(base,true);
    uint16_t before_queued=pr_pixels(live->script)[0];
    ui_event queued_old={.is_pointer=true,.pointer={before,(uint64_t)(host_us/1000),PR_DOWN,12,12}};
    assert(xQueueSend(edges,&queued_old,0));assert(xQueueSend(edges,&queued_old,0));
    request(APP_UI_ACTIVATE,candidate,true);request(APP_UI_ROLLBACK,candidate,true);
    assert(snapshot().live==before); /* Stale-before-commit restores actual prior. */
    assert(pr_pixels(live->script)[0]==before_queued && !edges->count);
    pointer(before,PR_DOWN);assert(pr_pixels(live->script)[0]!=before_queued);
    uint16_t before_home=pr_pixels(live->script)[0];
    assert(xQueueSend(edges,&queued_old,0));assert(xQueueSend(edges,&queued_old,0));
    home.token.activation=before;xQueueOverwrite(homes,&home);step();
    xQueueOverwrite(homes,&home);step();
    assert(pr_pixels(live->script)[0]==before_home && !edges->count);
    app_ui_ticket faulted=install("gfx.begin('#000000');gfx.end();app.onPointer(()=>{throw Error('fault')});");
    app_ui_ticket ready_during_fault=prepare_source(base,true);
    pointer(faulted,PR_DOWN);assert(snapshot().fault_ticket==faulted);
    request(APP_UI_ACTIVATE,ready_during_fault,false);
    assert(snapshot().live==faulted && snapshot().prepared==ready_during_fault);
    request(APP_UI_COMMIT,faulted,false);
    request(APP_UI_ABORT,ready_during_fault,true);
    request(APP_UI_ROLLBACK,faulted,true);assert(app_ui_ack_fault(faulted));
    /* Two independently failing programs recover through the retained app and
     * then the trusted built-in, while each sticky fault requires acknowledgment. */
    const char *bad="gfx.begin('#000000');gfx.end();app.onPointer(()=>{throw Error('fault')});";
    app_ui_ticket old_bad=install(bad),new_bad=install(bad);
    pointer(new_bad,PR_DOWN);request(APP_UI_ROLLBACK,new_bad,true);assert(snapshot().live==old_bad);
    pointer(old_bad,PR_DOWN);assert(snapshot().fault_ticket==new_bad);
    assert(app_ui_ack_fault(new_bad));step();assert(snapshot().fault_ticket==old_bad);
    request(APP_UI_ROLLBACK,old_bad,true);assert(live->builtin && !live->script);
    assert(app_ui_ack_fault(old_bad));
    for(unsigned i=0;i<100;i++)install(base);
    /* Reboot recovery can reconstruct the stored prior app offscreen, without
     * resuming failed JS or showing the fallback before the rollback command. */
    app_ui_ticket recover_fault=install(bad);pointer(recover_fault,PR_DOWN);
    app_ui_ticket stored_prior;
    assert(app_ui_prepare_recovery(program(base),&stored_prior));step();
    assert(snapshot().live==recover_fault && snapshot().prepared==stored_prior);
    request(APP_UI_RETAIN_PREVIOUS,stored_prior,true);
    assert(snapshot().live==recover_fault && snapshot().previous==stored_prior && previous->paused);
    request(APP_UI_ROLLBACK,recover_fault,true);assert(snapshot().live==stored_prior);
    assert(app_ui_ack_fault(recover_fault));pointer(stored_prior,PR_DOWN);
    /* A failure between ACTIVATE and COMMIT cannot strand recovery behind the
     * older retired instance. The guarded seam keeps the immediate previous. */
    app_ui_ticket uncommitted_bad=prepare_source(bad,true);
    request(APP_UI_ACTIVATE,uncommitted_bad,true);
    pointer(uncommitted_bad,PR_DOWN);assert(snapshot().fault_ticket==uncommitted_bad && !committed);
    app_ui_ticket emergency;
    assert(app_ui_prepare_recovery(program(base),&emergency));step();
    assert(snapshot().prepared==emergency && !retired && committed);
    request(APP_UI_RETAIN_PREVIOUS,emergency,true);
    request(APP_UI_ROLLBACK,uncommitted_bad,true);assert(app_ui_ack_fault(uncommitted_bad));
    /* Release all actual backing buffers only after detaching LVGL objects. */
    lv_obj_t *empty=lv_obj_create(NULL);lv_screen_load(empty);
    dispose(prepared);dispose(retired);dispose(previous);dispose(live);
    prepared=retired=previous=live=NULL;
    free(builtin_copy);builtin_copy=NULL;
    lv_timer_handler();lv_display_delete(display);lv_deinit();
    free(commands);free(events);free(edges);free(homes);
    puts("{\"status\":\"app_ui_lifecycle_passed\",\"replacement_cycles\":100,\"physical_execution\":false}");
    return 0;
}
