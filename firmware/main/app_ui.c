/* One owner executes both legacy and JavaScript apps. LVGL callbacks copy values. */
#include "app_ui.h"
#ifdef APP_UI_HOST_TEST
#include "app_ui_port.h"
#else
#include "bsp/esp-bsp.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#endif
#include "lvgl.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    int widget;
    as_event_token token;
    pr_event pointer;
    bool is_pointer;
} ui_event;
typedef struct {
    lv_obj_t *root, *area, *status, *shell, *home_label;
    lv_obj_t *values[AS_MAX_WIDGETS], *indicators[AS_MAX_WIDGETS];
    ui_event bindings[AS_MAX_WIDGETS + 1];
    uint64_t activation, entry;
} ui_view;
typedef struct instance {
    app_package *package;
    app_ui_ticket ticket;
    as_runtime legacy;
    pr_runtime *script;
    ui_view *view;
    bool paused, failed, builtin, pointer_down;
} instance;
typedef struct { app_ui_operation operation; app_ui_ticket ticket; app_package *package; } ui_command;
static QueueHandle_t commands, events, edges, homes;
static SemaphoreHandle_t state_lock;
static TaskHandle_t owner_task;
static app_ui_state state;
static app_ui_ticket next_ticket;
static instance *live, *previous, *prepared, *retired;
static as_app *builtin_copy;
static bool committed, wall_synchronized, status_dirty;
static ui_event latest_move, urgent_cancel;
static bool move_pending, cancel_pending;
static char status_text[48] = "Ready | local fixture", requested_status[48] = "Ready | local fixture";
static uint64_t healthy_ticks;
static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }
static void guard(void) { xSemaphoreTake(state_lock, portMAX_DELAY); }
static void unguard(void) { xSemaphoreGive(state_lock); }
static pr_clock clock_now(void) {
    time_t epoch = time(NULL);
    guard(); bool synchronized = wall_synchronized; unguard();
    return (pr_clock){(uint64_t)now_ms(), epoch >= 1700000000 ? (int64_t)epoch * 1000 : 0,
        epoch < 1700000000 ? PR_WALL_UNAVAILABLE : synchronized ? PR_WALL_SYNCHRONIZED : PR_WALL_ESTIMATED};
}
static app_ui_ticket allocate_ticket(void) {
    guard(); app_ui_ticket ticket = ++next_ticket; unguard(); return ticket;
}
static void clicked(lv_event_t *event) {
    const ui_event *binding = lv_event_get_user_data(event);
    if (!binding) return;
    if (binding->widget == -1) xQueueOverwrite(homes, binding);
    else if (xQueueSend(events, binding, 0) != pdTRUE) {
        guard(); ++state.dropped_input; unguard();
    }
}
static void pointer_event(lv_event_t *event) {
    const ui_event *binding = lv_event_get_user_data(event);
    lv_indev_t *input = lv_event_get_indev(event);
    if (!binding || !input) return;
    lv_event_code_t code = lv_event_get_code(event);
    pr_event_type type = code == LV_EVENT_PRESSED ? PR_DOWN : code == LV_EVENT_PRESSING ? PR_MOVE :
        code == LV_EVENT_RELEASED ? PR_UP : PR_CANCEL;
    lv_point_t point; lv_indev_get_point(input, &point);
    lv_area_t area; lv_obj_get_coords(lv_event_get_target_obj(event), &area);
    int x = point.x - area.x1, y = point.y - area.y1;
    if (x < 0) x = 0;
    if (x >= PR_WIDTH) x = PR_WIDTH - 1;
    if (y < 0) y = 0;
    if (y >= PR_HEIGHT) y = PR_HEIGHT - 1;
    ui_event copied = *binding;
    copied.is_pointer = true;
    copied.pointer = (pr_event){binding->token.activation, (uint64_t)now_ms(), type, x, y};
    guard();
    if (type == PR_MOVE) { latest_move = copied; move_pending = true; }
    else if (xQueueSend(edges, &copied, 0) != pdTRUE) {
        /* A saturated edge queue collapses the gesture to an explicit cancel.
         * Moves can never consume edge capacity or strand a pressed state. */
        urgent_cancel = copied; urgent_cancel.pointer.type = PR_CANCEL;
        cancel_pending = true; ++state.dropped_input;
    }
    unguard();
}
static void wrap(char *out, size_t capacity, const char *text, int columns) {
    size_t at = 0;
    for (size_t i = 0; text[i] && at + 2 < capacity; ++i) {
        if (i && i % columns == 0) out[at++] = '\n';
        out[at++] = text[i];
    }
    out[at] = 0;
}
static lv_obj_t *label(lv_obj_t *parent, const char *text, int x, int y, int width, int height, uint32_t color) {
    char formatted[256];
    wrap(formatted,sizeof(formatted),text,width / 16);
    lv_point_t measured;
    int line_space = 24 - lv_font_montserrat_16.line_height;
    lv_text_get_size(&measured,formatted,&lv_font_montserrat_16,0,line_space,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
    if (measured.x > width || measured.y > height) return NULL;
    lv_obj_t *result = lv_label_create(parent);
    if (!result) return NULL;
    lv_obj_set_pos(result,x,y); lv_obj_set_size(result,width,height);
    lv_obj_set_style_text_font(result,&lv_font_montserrat_16,0);
    lv_obj_set_style_text_line_space(result,line_space,0);
    lv_obj_set_style_text_color(result,lv_color_hex(color),0);
    lv_label_set_long_mode(result,LV_LABEL_LONG_CLIP);
    lv_label_set_text(result,formatted);
    return result;
}
static void plain_box(lv_obj_t *o, int x, int y, int w, int h, uint32_t color) {
    lv_obj_remove_style_all(o);
    lv_obj_set_pos(o,x,y); lv_obj_set_size(o,w,h);
    lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(o,lv_color_hex(color),0);
    lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
}
static void value_text(char *out, size_t capacity, const as_runtime *r, const as_widget *w) {
    char prefix[256];
    wrap(prefix,sizeof(prefix),w->text,17);
    int32_t value = w->type == AS_COUNTER ? r->state[w->state] : (int32_t)((as_remaining(r,w->timer)+999)/1000);
    snprintf(out,capacity,"%s%s%" PRId32,prefix,*prefix ? "\n" : "",value);
}
static bool legacy_build(ui_view *next, const as_runtime *r) {
    memset(next,0,sizeof(*next));
    next->activation = r->activation; next->entry = r->entry;
    const as_app *app = r->app;
    uint32_t bg = app->dark ? 0x101820 : 0xFFFFFF;
    uint32_t fg = app->dark ? 0xFFFFFF : 0x102030;
    uint32_t accent = app->dark ? 0x80FF80 : 0x164EAD;
    uint32_t on_accent = app->dark ? 0x101820 : 0xFFFFFF;
    next->root = lv_obj_create(NULL);
    if (!next->root) return false;
    plain_box(next->root,0,0,320,480,bg);
    lv_obj_t *header = lv_obj_create(next->root);
    plain_box(header,0,0,320,48,0x243443);
    lv_obj_t *menu = lv_button_create(header);
    plain_box(menu,0,0,80,48,0x243443);
    if (!label(menu,r->in_shell ? "Back" : "Menu",8,12,64,24,0xFFFFFF)) return false;
    next->bindings[AS_MAX_WIDGETS] = (ui_event){.widget=-1,.token={r->activation,r->entry}};
    lv_obj_add_event_cb(menu,clicked,LV_EVENT_CLICKED,&next->bindings[AS_MAX_WIDGETS]);
    next->status = lv_label_create(header);
    lv_obj_set_pos(next->status,88,14); lv_obj_set_size(next->status,224,24);
    lv_obj_set_style_text_font(next->status,&lv_font_montserrat_12,0);
    lv_obj_set_style_text_color(next->status,lv_color_hex(0xFFFFFF),0);
    lv_label_set_long_mode(next->status,LV_LABEL_LONG_CLIP);
    lv_label_set_text(next->status,status_text);
    lv_obj_t *area = lv_obj_create(next->root);
    next->area = area;
    plain_box(area,0,48,320,432,bg);
    if (r->in_shell)
        return label(area,"Sketch to Device",16,16,288,24,fg) &&
            label(area,"App paused. Tap Back to resume.",16,64,288,72,fg);
    const as_screen *screen = &app->screens[r->screen];
    int y = 16, title_height = as_text_height(screen->title,288);
    if (!label(area,screen->title,16,y,288,title_height,fg)) return false;
    y += title_height;
    for (int i = screen->first; i < screen->first + screen->count; ++i) {
        const as_widget *w = &app->widgets[i];
        int height = as_widget_height(w); y += 8;
        if (w->type == AS_LABEL) {
            if (!label(area,w->text,16,y,288,height,fg)) return false;
        } else {
            bool button = w->type == AS_BUTTON || w->type == AS_TOGGLE;
            bool custom_color = w->type == AS_BUTTON && w->has_background_color;
            uint32_t control_bg = custom_color ? w->background_color : accent;
            uint32_t control_fg = custom_color ? as_color_foreground(control_bg) : on_accent;
            lv_obj_t *control = button ? lv_button_create(area) : lv_obj_create(area);
            plain_box(control,16,y,288,height,button ? control_bg : bg);
            lv_obj_set_style_radius(control,8,0);
            if (button) {
                next->bindings[i] = (ui_event){.widget=i,.token={r->activation,r->entry}};
                lv_obj_add_event_cb(control,clicked,LV_EVENT_CLICKED,&next->bindings[i]);
            }
            if (w->type == AS_COUNTER || w->type == AS_TIMER) {
                next->values[i] = label(control,"0",8,8,272,height-16,fg);
                if (!next->values[i]) return false;
                char number[300]; value_text(number,sizeof(number),r,w);
                lv_label_set_text(next->values[i],number);
            } else if (w->type == AS_TOGGLE) {
                next->indicators[i] = label(control,r->state[w->state] ? "+" : "-",8,8,32,24,on_accent);
                if (!next->indicators[i] || !label(control,w->text,40,8,240,height-16,on_accent)) return false;
            } else if (!label(control,w->text,8,8,272,height-16,control_fg)) return false;
        }
        y += height;
    }
    return y + 16 <= 432;
}

static bool display_lock(void) {
    /* The pinned adapter accepts signed -1 for an unbounded mutex wait. JS never
     * owns this lock. A dead BSP task is outside interpreter fault containment. */
    return bsp_display_lock(UINT32_MAX);
}
static void discard_input_locked(void) {
    /* LVGL event callbacks use this same BSP mutex. No old callback can enqueue
     * after the transition flush; lifecycle tickets deliberately remain stable. */
    guard();
    xQueueReset(events); xQueueReset(edges); xQueueReset(homes);
    move_pending=false; cancel_pending=false;
    unguard();
}
static void dispose(instance *app) {
    if (!app) return;
    if (app->view && display_lock()) {
        if (app->script) pr_detach(app->script);
        if (app->view->root) lv_obj_delete(app->view->root);
        bsp_display_unlock();
    }
    pr_destroy(app->script);
    free(app->view);
    app_package_free(app->package);
    free(app);
}
static bool program_build(instance *app) {
    ui_view *view = app->view;
    view->activation = app->ticket;
    view->root = lv_obj_create(NULL);
    if (!view->root) return false;
    plain_box(view->root, 0, 0, 320, 480, 0x101820);
    lv_obj_t *header = lv_obj_create(view->root);
    if (!header) return false;
    plain_box(header, 0, 0, 320, 48, 0x243443);
    lv_obj_t *home = lv_button_create(header);
    if (!home) return false;
    plain_box(home, 0, 0, 80, 48, 0x243443);
    view->home_label = label(home, "Menu", 8, 12, 64, 24, 0xFFFFFF);
    view->bindings[AS_MAX_WIDGETS] = (ui_event){.widget=-1, .token={app->ticket, 0}};
    lv_obj_add_event_cb(home, clicked, LV_EVENT_CLICKED, &view->bindings[AS_MAX_WIDGETS]);
    view->status = lv_label_create(header);
    if (view->status) {
        lv_obj_set_pos(view->status, 88, 14); lv_obj_set_size(view->status, 224, 24);
        lv_obj_set_style_text_font(view->status, &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_color(view->status, lv_color_hex(0xFFFFFF), 0);
        lv_label_set_long_mode(view->status, LV_LABEL_LONG_CLIP);
        lv_label_set_text(view->status, status_text);
    }
    view->area = lv_obj_create(view->root);
    if (!view->home_label || !view->status || !view->area) return false;
    plain_box(view->area, 0, 48, 320, 432, 0x101820);
    if (!pr_attach(app->script, view->area)) return false;
    lv_obj_remove_flag(pr_root(app->script), LV_OBJ_FLAG_HIDDEN);
    lv_obj_t *touch = lv_obj_create(pr_root(app->script));
    if (!touch) return false;
    lv_obj_remove_style_all(touch);
    lv_obj_set_size(touch, PR_WIDTH, PR_HEIGHT);
    lv_obj_remove_flag(touch, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(touch, LV_OBJ_FLAG_CLICKABLE);
    view->bindings[0] = (ui_event){.token={app->ticket, 0}, .is_pointer=true};
    lv_obj_add_event_cb(touch, pointer_event, LV_EVENT_PRESSED, &view->bindings[0]);
    lv_obj_add_event_cb(touch, pointer_event, LV_EVENT_PRESSING, &view->bindings[0]);
    lv_obj_add_event_cb(touch, pointer_event, LV_EVENT_RELEASED, &view->bindings[0]);
    lv_obj_add_event_cb(touch, pointer_event, LV_EVENT_PRESS_LOST, &view->bindings[0]);
    view->shell = lv_obj_create(view->area);
    if (!view->shell) return false;
    plain_box(view->shell, 0, 0, 320, 432, 0x101820);
    if (!label(view->shell,"Sketch to Device",16,16,288,24,0xFFFFFF) ||
        !label(view->shell,"App paused. Tap Back to resume.",16,64,288,72,0xFFFFFF)) return false;
    lv_obj_add_flag(view->shell, LV_OBJ_FLAG_HIDDEN);
    return true;
}
static bool admit_program(void) {
    /* Conservative admission, not an OOM guarantee: LVGL native constructors
     * and drawing scratch allocations are still outside QuickJS accounting. */
    return heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) >= 128 * 1024 &&
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) >= 32 * 1024 &&
        heap_caps_get_free_size(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) >= 1024 * 1024 &&
        heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) >= PR_WIDTH * PR_HEIGHT * 2;
}
static instance *create(app_package *package, app_ui_ticket ticket, const char **error) {
    instance *app = calloc(1, sizeof(*app));
    if (!app) { app_package_free(package); *error="allocation_failed"; return NULL; }
    app->package=package; app->ticket=ticket;
    app->view=calloc(1,sizeof(*app->view));
    if (!app->view) { *error="allocation_failed"; dispose(app); return NULL; }
    if (package->kind == APP_PACKAGE_PROGRAM) {
        if (!admit_program()) { *error="native_memory_admission"; dispose(app); return NULL; }
        app->script=pr_create(&package->data.program->program,clock_now(),esp_random(),error);
        if (!app->script) { dispose(app); return NULL; }
        pr_set_activation(app->script,ticket);
    } else as_install(&app->legacy,package->data.legacy,now_ms(),ticket);
    if (!display_lock()) { *error="display_lock"; dispose(app); return NULL; }
    bool ok=app->script ? program_build(app) : legacy_build(app->view,&app->legacy);
    bsp_display_unlock();
    if (!ok) { *error="view_activation"; dispose(app); return NULL; }
    *error=NULL;
    return app;
}
static void publish(void) {
    size_t internal=heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    size_t largest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    size_t external=heap_caps_get_free_size(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    guard();
    state.live=live ? live->ticket : 0;
    state.previous=previous ? previous->ticket : 0;
    state.prepared=prepared ? prepared->ticket : 0;
    state.paused=live && live->paused;
    state.owner_stack_free_bytes=uxTaskGetStackHighWaterMark(owner_task);
    state.internal_free_bytes=internal; state.internal_largest_bytes=largest; state.external_free_bytes=external;
    ++state.revision;
    unguard();
}
static void finish(const ui_command *command, bool ok, const char *error) {
    publish();
    guard();
    state.operation=command->operation; state.operation_ticket=command->ticket;
    state.pending=false; state.succeeded=ok;
    snprintf(state.error,sizeof(state.error),"%s",error ? error : "");
    ++state.revision;
    unguard();
}
static void fault(instance *app, const char *reason) {
    app->failed=true;
    if (app->script) pr_pause(app->script);
    if (app != live) return; /* A rejected offscreen candidate was never active. */
    guard();
    if (!state.fault_ticket) {
        state.fault_ticket=app->ticket;
        snprintf(state.fault,sizeof(state.fault),"%s",reason ? reason : "runtime_failure");
        state.recovered_ticket=0;
    }
    unguard();
}
static bool checkpoint(instance *app) {
    if (!app || app->failed || app->paused) return app && !app->failed;
    if (app->script) {
        pr_clock now=clock_now();
        if (!pr_dispatch(app->script,(pr_event){app->ticket,now.monotonic_ms,PR_TICK,0,0},now)) {
            fault(app,pr_get_metrics(app->script).fault); return false;
        }
    } else as_advance(&app->legacy,now_ms());
    if (!display_lock()) return false;
    bool ok=true;
    if (app->script) ok=pr_present(app->script);
    else if (app->view->entry != app->legacy.entry || app->view->activation != app->legacy.activation) {
        ui_view *view=calloc(1,sizeof(*view));
        ok=view && legacy_build(view,&app->legacy);
        if (ok) {
            if (app==live) lv_screen_load(view->root);
            lv_obj_delete(app->view->root); free(app->view); app->view=view;
        } else { if(view && view->root)lv_obj_delete(view->root); free(view); }
    } else if (!app->legacy.in_shell) {
        for (int i=0;i<app->legacy.app->widget_count;i++) {
            const as_widget *w=&app->legacy.app->widgets[i];
            if(app->view->values[i]){char number[300];value_text(number,sizeof(number),&app->legacy,w);lv_label_set_text(app->view->values[i],number);}
            if(app->view->indicators[i])lv_label_set_text(app->view->indicators[i],app->legacy.state[w->state]?"+":"-");
        }
    }
    bsp_display_unlock();
    if (!ok) { fault(app,"view_render"); return false; }
    guard(); ++healthy_ticks; state.checkpoint_ticket=app->ticket; ++state.checkpoints; unguard();
    return true;
}
static void pause_instance(instance *app, bool paused) {
    if (!app || app->failed) return;
    if (app->script) {
        if(paused && app->pointer_down) {
            pr_clock now=clock_now();
            app->pointer_down=false;
            if(!pr_dispatch(app->script,(pr_event){app->ticket,now.monotonic_ms,PR_CANCEL,0,0},now)) {
                fault(app,pr_get_metrics(app->script).fault);return;
            }
        }
        if (paused) pr_pause(app->script); else pr_resume(app->script,clock_now());
        if (display_lock()) {
            if(paused) {lv_obj_add_flag(pr_root(app->script),LV_OBJ_FLAG_HIDDEN);lv_obj_remove_flag(app->view->shell,LV_OBJ_FLAG_HIDDEN);}
            else {lv_obj_remove_flag(pr_root(app->script),LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(app->view->shell,LV_OBJ_FLAG_HIDDEN);}
            lv_label_set_text(app->view->home_label,paused?"Back":"Menu");
            discard_input_locked();
            bsp_display_unlock();
        }
    } else {
        as_shell(&app->legacy,paused,now_ms());
        app->paused=false;
        checkpoint(app);
        if(display_lock()){discard_input_locked();bsp_display_unlock();}
    }
    app->paused=paused;
}
static void command_execute(ui_command command) {
    bool ok=false; const char *error="invalid_ui_transition";
    guard(); bool recovery_pending=state.fault_ticket!=0; unguard();
    if(recovery_pending && (command.operation==APP_UI_PREPARE || command.operation==APP_UI_ACTIVATE || command.operation==APP_UI_COMMIT)) {
        app_package_free(command.package);
        finish(&command,false,"runtime_recovery_pending");return;
    }
    switch(command.operation) {
    case APP_UI_PREPARE:
    case APP_UI_PREPARE_RECOVERY:
        /* The trusted caller has persisted its recovery intent. A failed live
         * activation cannot COMMIT normally; retire only the obsolete older
         * fallback so a verified replacement can be constructed offscreen. */
        if(command.operation==APP_UI_PREPARE_RECOVERY && recovery_pending && live && live->failed && !prepared) {
            dispose(retired);retired=NULL;committed=true;
        }
        if (!prepared && !retired && (!live || committed) &&
            (command.operation!=APP_UI_PREPARE_RECOVERY || (recovery_pending && live && live->failed))) {
            prepared=create(command.package,command.ticket,&error);
            command.package=NULL;
            ok=prepared!=NULL;
        }
        app_package_free(command.package);
        break;
    case APP_UI_RETAIN_PREVIOUS:
        if(recovery_pending && live && live->failed && prepared && prepared->ticket==command.ticket && !retired && checkpoint(prepared)) {
            pause_instance(prepared,true);
            dispose(previous);previous=prepared;prepared=NULL;ok=true;
        } else error="recovery_candidate_invalid";
        break;
    case APP_UI_ACTIVATE:
        if(prepared && prepared->ticket==command.ticket && !retired) {
            /* First callback and presentation occur offscreen. A failure never
             * loads the candidate's screen or mutates the old active package. */
            if(checkpoint(prepared)) {
                if(live)pause_instance(live,true); /* May run pointer cancel: no BSP lock. */
                if((!live || !live->failed) && display_lock()) {
                    lv_screen_load(prepared->view->root);discard_input_locked();
                    bsp_display_unlock();
                    retired=previous; previous=live; live=prepared; prepared=NULL;
                    /* Pausing the former legacy app can publish its checkpoint.
                     * ACTIVATE completion must retain the candidate checkpoint
                     * already verified above, before any subsequent owner tick. */
                    guard();state.checkpoint_ticket=live->ticket;unguard();
                    committed=false; ok=true;
                } else error="previous_app_fault";
            } else error=prepared->script && pr_get_metrics(prepared->script).fault ?
                pr_get_metrics(prepared->script).fault : "activation_checkpoint";
        } else if(live && live->ticket==command.ticket)ok=true;
        break;
    case APP_UI_COMMIT:
        if(live && live->ticket==command.ticket && !live->failed) {
            dispose(retired); retired=NULL; committed=true; ok=true;
        }
        break;
    case APP_UI_ABORT:
        if(prepared && prepared->ticket==command.ticket) {
            dispose(prepared); prepared=NULL; ok=true;
            guard(); if(state.fault_ticket==command.ticket){state.fault_ticket=0;state.fault[0]=0;} unguard();
        } else if((!live || live->ticket!=command.ticket) && (!previous || previous->ticket!=command.ticket))ok=true;
        break;
    case APP_UI_ROLLBACK:
        if(live && live->ticket==command.ticket) {
            instance *fallback=previous;
            if(!fallback && builtin_copy) {
                app_package *package=app_package_copy_legacy(builtin_copy);
                if(package){fallback=create(package,allocate_ticket(),&error);if(fallback)fallback->builtin=true;}
            }
            if(fallback && !fallback->failed && display_lock()) {
                lv_screen_load(fallback->view->root);
                discard_input_locked();
                bsp_display_unlock();
                instance *failed=live; live=fallback; previous=retired; retired=NULL;
                pause_instance(live,false); dispose(failed); committed=true; ok=true;
                guard(); state.recovered_ticket=live->ticket; unguard();
            }
        } else {
            guard(); ok=state.recovered_ticket && state.fault_ticket==command.ticket; unguard();
        }
        break;
    default: break;
    }
    finish(&command,ok,ok?NULL:error);
}
static void input_execute(ui_event event) {
    app_ui_ticket ticket=event.is_pointer?event.pointer.activation:event.token.activation;
    if(!live || ticket!=live->ticket || live->paused || live->failed) {
        guard();++state.stale_input;unguard();return;
    }
    if(event.is_pointer && live->script) {
        if(event.pointer.type==PR_DOWN)live->pointer_down=true;
        else if(event.pointer.type==PR_UP || event.pointer.type==PR_CANCEL)live->pointer_down=false;
        if(!pr_dispatch(live->script,event.pointer,clock_now()))fault(live,pr_get_metrics(live->script).fault);
        else if(display_lock()){if(!pr_present(live->script))fault(live,"view_render");bsp_display_unlock();}
    } else if(!event.is_pointer && !live->script)as_press(&live->legacy,event.widget,now_ms(),event.token);
}
static void owner_step(void) {
    /* A prior recovery report may have occupied the sticky slot when its
     * fallback also failed. Re-publish that second fault after acknowledgment. */
    if(live && live->failed)fault(live,live->script?pr_get_metrics(live->script).fault:"runtime_failure");
    ui_event event;
    if(xQueueReceive(homes,&event,0)==pdTRUE) {
        if(live && event.token.activation==live->ticket) {
            /* Home is a separate overwrite mailbox, independent of app traffic. */
            if(live->failed) {
                if(display_lock()){
                    if(live->view->shell)lv_obj_remove_flag(live->view->shell,LV_OBJ_FLAG_HIDDEN);
                    bsp_display_unlock();
                }
            } else pause_instance(live,!live->paused);
        }
    }
    ui_command command;
    if(xQueueReceive(commands,&command,0)==pdTRUE)command_execute(command);
    bool have=false;
    guard();
    if(cancel_pending) {
        event=urgent_cancel; cancel_pending=false; move_pending=false;
        xQueueReset(edges); have=true;
    } else if(xQueueReceive(edges,&event,0)==pdTRUE) {
        have=true;
        if(event.pointer.type==PR_UP || event.pointer.type==PR_CANCEL)move_pending=false;
    } else if(move_pending) {event=latest_move;move_pending=false;have=true;}
    unguard();
    if(have)input_execute(event);
    else if(xQueueReceive(events,&event,0)==pdTRUE)input_execute(event);
    if(live && !live->paused && !live->failed)checkpoint(live);
    guard();
    bool update=status_dirty;
    if(update){memcpy(status_text,requested_status,sizeof(status_text));status_dirty=false;}
    unguard();
    if(update && live && display_lock()){lv_label_set_text(live->view->status,status_text);bsp_display_unlock();}
    publish();
}
static void owner(void *unused) {
    (void)unused;
    for(;;){owner_step();vTaskDelay(pdMS_TO_TICKS(20));}
}
bool app_ui_init(void) {
    if(owner_task)return true;
    state_lock=xSemaphoreCreateMutex();
    commands=xQueueCreate(1,sizeof(ui_command)); events=xQueueCreate(24,sizeof(ui_event));
    edges=xQueueCreate(8,sizeof(ui_event)); homes=xQueueCreate(1,sizeof(ui_event));
    if(state_lock && commands && events && edges && homes &&
       xTaskCreate(owner,"app_owner",64*1024,NULL,5,&owner_task)==pdPASS)return true;
    if(commands)vQueueDelete(commands);
    if(events)vQueueDelete(events);
    if(edges)vQueueDelete(edges);
    if(homes)vQueueDelete(homes);
    if(state_lock)vSemaphoreDelete(state_lock);
    commands=events=edges=homes=NULL;state_lock=NULL;owner_task=NULL;
    return false;
}
static bool prepare_request(app_package *package, app_ui_ticket *ticket, bool recovery) {
    if(!package || !ticket || !state_lock)return false;
    guard();
    if(state.pending || state.prepared || (recovery ? (!state.fault_ticket || state.fault_ticket!=state.live) : state.fault_ticket!=0)){unguard();return false;}
    app_ui_ticket value=++next_ticket;
    app_ui_operation operation=recovery?APP_UI_PREPARE_RECOVERY:APP_UI_PREPARE;
    ui_command command={operation,value,package};
    if(xQueueSend(commands,&command,0)!=pdTRUE){unguard();return false;}
    state.pending=true;state.operation=operation;state.operation_ticket=value;state.succeeded=false;
    state.error[0]=0;*ticket=value;unguard();return true;
}
bool app_ui_prepare(app_package *package,app_ui_ticket *ticket){return prepare_request(package,ticket,false);}
bool app_ui_prepare_recovery(app_package *package,app_ui_ticket *ticket){return prepare_request(package,ticket,true);}
bool app_ui_request(app_ui_operation operation,app_ui_ticket ticket) {
    if(!state_lock || !ticket || operation<APP_UI_ACTIVATE || operation>APP_UI_RETAIN_PREVIOUS || operation==APP_UI_PREPARE_RECOVERY)return false;
    guard();
    if(state.pending){unguard();return false;}
    bool recovery_blocks=state.fault_ticket && (operation==APP_UI_ACTIVATE || operation==APP_UI_COMMIT);
    if(!recovery_blocks && state.operation==operation && state.operation_ticket==ticket && state.succeeded){unguard();return true;}
    ui_command command={operation,ticket,NULL};
    if(xQueueSend(commands,&command,0)!=pdTRUE){unguard();return false;}
    state.pending=true;state.operation=operation;state.operation_ticket=ticket;state.succeeded=false;
    state.error[0]=0;unguard();return true;
}
void app_ui_snapshot(app_ui_state *out) {
    if(!out)return;
    if(!state_lock){memset(out,0,sizeof(*out));return;}
    guard();*out=state;unguard();
}
bool app_ui_ack_fault(app_ui_ticket ticket) {
    if(!state_lock)return false;
    guard();
    bool ok=state.fault_ticket==ticket && state.live!=ticket && state.recovered_ticket;
    if(ok){state.fault_ticket=0;state.fault[0]=0;}
    unguard();return ok;
}
void app_ui_wall_synchronized(bool synchronized) {
    if(!state_lock)return;
    guard();wall_synchronized=synchronized;unguard();
}
void app_ui_status(const char *message) {
    if(!state_lock || !message)return;
    guard();snprintf(requested_status,sizeof(requested_status),"%s",message);status_dirty=true;unguard();
}
static bool wait_operation(app_ui_operation operation,app_ui_ticket ticket) {
    /* Temporary legacy bridge owns no borrowed model/reply pointer. Ticket-based
     * production delivery does not use this blocking migration wrapper. */
    for(;;){app_ui_state copy;app_ui_snapshot(&copy);
        if(!copy.pending && copy.operation==operation && copy.operation_ticket==ticket)return copy.succeeded;
        vTaskDelay(pdMS_TO_TICKS(10));}
}
bool app_ui_activate(const as_app *app) {
    app_package *package=app_package_copy_legacy(app);
    if(!package)return false;
    if(!builtin_copy){builtin_copy=malloc(sizeof(*builtin_copy));if(builtin_copy)*builtin_copy=*app;}
    app_ui_ticket ticket;
    if(!app_ui_prepare(package,&ticket)){app_package_free(package);return false;}
    if(!wait_operation(APP_UI_PREPARE,ticket))return false;
    if(!app_ui_request(APP_UI_ACTIVATE,ticket) || !wait_operation(APP_UI_ACTIVATE,ticket)){
        app_ui_request(APP_UI_ABORT,ticket);return false;}
    return app_ui_request(APP_UI_COMMIT,ticket) && wait_operation(APP_UI_COMMIT,ticket);
}
void app_ui_tick(void) { /* Owner task supplies ticks. */ }
uint64_t app_ui_healthy_ticks(void) {
    if(!state_lock)return 0;
    guard();uint64_t result=healthy_ticks;unguard();return result;
}
