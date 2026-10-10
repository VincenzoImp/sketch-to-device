#include "app_ui.h"
#include "bsp/esp-bsp.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "lvgl.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int widget; as_event_token token; } ui_event;
typedef struct {
    lv_obj_t *root, *status, *values[AS_MAX_WIDGETS], *indicators[AS_MAX_WIDGETS];
    ui_event bindings[AS_MAX_WIDGETS + 1];
    uint64_t activation, entry;
} ui_view;
static QueueHandle_t events;
static as_runtime runtime;
static char status_text[48] = "Ready | local fixture";
static uint64_t healthy_ticks;
static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

static void clicked(lv_event_t *event) {
    const ui_event *binding = lv_event_get_user_data(event);
    /* Queue a value copy: navigation may delete the originating widget. */
    if (binding) xQueueSend(events, binding, 0);
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
static bool build(ui_view *next, const as_runtime *r) {
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
            lv_obj_t *control = button ? lv_button_create(area) : lv_obj_create(area);
            plain_box(control,16,y,288,height,button ? accent : bg);
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
            } else if (!label(control,w->text,8,8,272,height-16,on_accent)) return false;
        }
        y += height;
    }
    return y + 16 <= 432;
}
/* Allocate views on the heap so callback user-data addresses never move. */
static ui_view *live;
static bool render(const as_runtime *r) {
    ui_view *next = calloc(1,sizeof(*next));
    if (!next) return false;
    if (!build(next,r)) { if (next->root) lv_obj_delete(next->root); free(next); return false; }
    lv_screen_load(next->root);
    if (live) { lv_obj_delete(live->root); free(live); }
    live = next;
    return true;
}
bool app_ui_init(void) {
    events = xQueueCreate(24,sizeof(ui_event));
    return events != NULL;
}
bool app_ui_activate(const as_app *app) {
    if (!bsp_display_lock(1000)) return false;
    as_runtime candidate;
    as_install(&candidate,app,now_ms(),runtime.activation + 1);
    bool ok = render(&candidate);
    if (ok) runtime = candidate;
    bsp_display_unlock();
    return ok;
}
void app_ui_tick(void) {
    if (!bsp_display_lock(100)) return;
    if (runtime.app) {
        ui_event event;
        while (xQueueReceive(events,&event,0) == pdTRUE) {
            int64_t now = now_ms();
            if (event.widget == -1) {
                if (event.token.activation == runtime.activation && event.token.entry == runtime.entry)
                    as_shell(&runtime,!runtime.in_shell,now);
            } else as_press(&runtime,event.widget,now,event.token);
        }
        as_advance(&runtime,now_ms());
        if (!live || live->entry != runtime.entry || live->activation != runtime.activation) {
            if (!render(&runtime)) { as_shell(&runtime,true,now_ms()); render(&runtime); }
        } else if (!runtime.in_shell) {
            for (int i = 0; i < runtime.app->widget_count; ++i) {
                const as_widget *w = &runtime.app->widgets[i];
                if (live->values[i]) { char number[300]; value_text(number,sizeof(number),&runtime,w); lv_label_set_text(live->values[i],number); }
                if (live->indicators[i]) lv_label_set_text(live->indicators[i],runtime.state[w->state] ? "+" : "-");
            }
        }
        ++healthy_ticks;
    }
    bsp_display_unlock();
}
void app_ui_status(const char *message) {
    if (!bsp_display_lock(1000)) return;
    snprintf(status_text,sizeof(status_text),"%s",message);
    if (live) lv_label_set_text(live->status,status_text);
    bsp_display_unlock();
}
uint64_t app_ui_healthy_ticks(void) {
    if (!bsp_display_lock(1000)) return 0;
    uint64_t ticks = healthy_ticks;
    bsp_display_unlock();
    return ticks;
}
