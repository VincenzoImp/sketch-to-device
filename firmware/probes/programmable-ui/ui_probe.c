/* Isolated real QuickJS/LVGL host proof. No production API or device I/O. */
#include "quickjs.h"
#include "lvgl.h"
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "allocator.h"

#define WIDTH 320
#define HEIGHT 480
#define OBJECT_LIMIT 32
#define TEXT_LIMIT 128
#define QUEUE_LIMIT 24
#define REJECTION_LIMIT 16

typedef struct { uint64_t activation; uint32_t handle; } event_message;
typedef struct {
    lv_obj_t *object, *label;
    uint32_t handle;
    int button;
    event_message binding;
    JSValue callback;
} widget;
typedef struct app {
    probe_state memory;
    JSRuntime *runtime;
    JSContext *context;
    lv_obj_t *root;
    uint64_t activation;
    widget widgets[OBJECT_LIMIT];
    unsigned count;
    JSValue rejections[REJECTION_LIMIT];
    unsigned rejection_count;
    int rejection_overflow;
} app;
static app *live, *previous;
static lv_obj_t *shell;
static lv_display_t *display;
static uint32_t draw_buffer[WIDTH * HEIGHT], framebuffer[WIDTH * HEIGHT];
static event_message queue[QUEUE_LIMIT];
static unsigned queue_head, queue_count, dropped, stale, callbacks, rejected, installs;
static uint32_t next_handle;
static uint64_t next_activation;
static size_t peak_payload;
static unsigned alive_apps;
static pthread_t owner;

static void owner_only(void) { assert(pthread_equal(pthread_self(), owner)); }
static void reset_budget(app *a) {
    a->memory.calls = a->memory.jobs = a->memory.interrupted = 0;
    a->memory.deadline = now_us() + DEADLINE_US;
}
static void discard_exception(JSContext *context) {
    JS_FreeValue(context, JS_GetException(context));
}
static void promise_rejection(JSContext *context, JSValueConst promise,
                              JSValueConst reason, bool handled, void *opaque) {
    (void)reason;
    owner_only();
    app *a = opaque;
    for (unsigned i = 0; i < a->rejection_count; ++i) {
        if (JS_IsSameValue(context, a->rejections[i], promise)) {
            if (handled) {
                JS_FreeValue(context, a->rejections[i]);
                a->rejections[i] = a->rejections[--a->rejection_count];
                a->rejections[a->rejection_count] = JS_UNDEFINED;
            }
            return;
        }
    }
    if (handled) return;
    if (a->rejection_count == REJECTION_LIMIT) { a->rejection_overflow = 1; return; }
    a->rejections[a->rejection_count++] = JS_DupValue(context, promise);
}
static int drain_jobs(app *a) {
    while (JS_IsJobPending(a->runtime)) {
        if (a->memory.jobs++ >= JOB_LIMIT || now_us() >= a->memory.deadline) return 0;
        JSContext *context = NULL;
        if (JS_ExecutePendingJob(a->runtime, &context) < 0) {
            if (context) discard_exception(context);
            return 0;
        }
    }
    return !a->rejection_count && !a->rejection_overflow;
}
static JSValue invalid(JSContext *context) {
    return JS_ThrowTypeError(context, "invalid UI arguments or exhausted UI resources");
}
static int integer(JSContext *context, JSValueConst value, int min, int max, int *out) {
    double number;
    if (!JS_IsNumber(value) || JS_ToFloat64(context, &number, value)
        || !isfinite(number) || number < min || number > max || floor(number) != number) return 0;
    *out = (int)number;
    return 1;
}
static int field_integer(JSContext *c, JSValueConst object, const char *name, int min, int max, int *out) {
    JSValue v = JS_GetPropertyStr(c, object, name);
    int ok = integer(c, v, min, max, out);
    JS_FreeValue(c, v);
    return ok;
}
static int text_value(JSContext *c, JSValueConst value, char out[TEXT_LIMIT + 1]) {
    if (!JS_IsString(value)) return 0;
    size_t size;
    const char *text = JS_ToCStringLen(c, &size, value);
    if (!text) return 0;
    int ok = size <= TEXT_LIMIT && memchr(text, 0, size) == NULL;
    if (ok) memcpy(out, text, size + 1);
    JS_FreeCString(c, text);
    return ok;
}
static int color_value(JSContext *c, JSValueConst value, uint32_t *out) {
    if (!JS_IsString(value)) return 0;
    size_t size;
    const char *text = JS_ToCStringLen(c, &size, value);
    if (!text) return 0;
    int ok = size == 7 && text[0] == '#';
    uint32_t color = 0;
    for (size_t i = 1; ok && i < 7; ++i) {
        char ch = text[i];
        int digit = ch >= '0' && ch <= '9' ? ch - '0' :
            ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 :
            ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
        if (digit < 0) ok = 0;
        else color = color * 16 + (unsigned)digit;
    }
    JS_FreeCString(c, text);
    if (ok) *out = color;
    return ok;
}
static int allowed_fields(JSContext *c, JSValueConst options, const char *const *allowed) {
    if (!JS_IsObject(options) || JS_IsArray(options)) return 0;
    JSPropertyEnum *props = NULL;
    uint32_t count = 0;
    if (JS_GetOwnPropertyNames(c, &props, &count, options, JS_GPN_STRING_MASK | JS_GPN_SYMBOL_MASK) < 0) return 0;
    int ok = count <= 8;
    for (uint32_t i = 0; ok && i < count; ++i) {
        const char *name = JS_AtomToCString(c, props[i].atom);
        int found = 0;
        for (unsigned j = 0; name && allowed[j]; ++j) if (!strcmp(name, allowed[j])) found = 1;
        if (!found) ok = 0;
        JS_FreeCString(c, name);
    }
    for (uint32_t i = 0; i < count; ++i) JS_FreeAtom(c, props[i].atom);
    js_free(c, props);
    return ok;
}
static void enqueue(lv_event_t *event) {
    owner_only();
    const event_message *binding = lv_event_get_user_data(event);
    if (queue_count == QUEUE_LIMIT) { ++dropped; return; }
    queue[(queue_head + queue_count++) % QUEUE_LIMIT] = *binding;
    /* This callback never executes JavaScript and copies no native pointer. */
}
static void plain(lv_obj_t *object, int x, int y, int width, int height) {
    lv_obj_remove_style_all(object);
    lv_obj_set_pos(object, x, y);
    lv_obj_set_size(object, width, height);
    lv_obj_remove_flag(object, LV_OBJ_FLAG_SCROLLABLE);
}
static JSValue create_widget(JSContext *c, JSValueConst self, int argc, JSValueConst *argv, int button) {
    (void)self;
    owner_only();
    app *a = JS_GetContextOpaque(c);
    static const char *const labels[] = {"x", "y", "width", "height", "text", "color", NULL};
    static const char *const buttons[] = {"x", "y", "width", "height", "text", "background", "onClick", NULL};
    if (argc != 1 || !allowed_fields(c, argv[0], button ? buttons : labels)) return invalid(c);
    int x, y, width, height;
    if (!field_integer(c, argv[0], "x", 0, WIDTH - 1, &x)
        || !field_integer(c, argv[0], "y", 0, HEIGHT - 1, &y)
        || !field_integer(c, argv[0], "width", 1, WIDTH, &width)
        || !field_integer(c, argv[0], "height", 1, HEIGHT, &height)
        || x + width > WIDTH || y + height > HEIGHT) return invalid(c);
    JSValue text = JS_GetPropertyStr(c, argv[0], "text");
    char buffer[TEXT_LIMIT + 1];
    int ok = text_value(c, text, buffer);
    JS_FreeValue(c, text);
    uint32_t color = button ? 0x164ead : 0xffffff;
    JSValue raw_color = JS_GetPropertyStr(c, argv[0], button ? "background" : "color");
    if (!JS_IsUndefined(raw_color)) ok = ok && color_value(c, raw_color, &color);
    JS_FreeValue(c, raw_color);
    JSValue callback = button ? JS_GetPropertyStr(c, argv[0], "onClick") : JS_UNDEFINED;
    if (button && !JS_IsFunction(c, callback)) ok = 0;
    /* Decode first: property getters may execute JavaScript recursively. */
    if (!ok || a->count >= OBJECT_LIMIT || next_handle == UINT32_MAX) {
        JS_FreeValue(c, callback);
        return invalid(c);
    }
    widget *w = &a->widgets[a->count];
    w->object = button ? lv_button_create(a->root) : lv_label_create(a->root);
    if (!w->object) { JS_FreeValue(c, callback); return JS_ThrowOutOfMemory(c); }
    plain(w->object, x, y, width, height);
    w->label = button ? lv_label_create(w->object) : w->object;
    if (!w->label) { lv_obj_delete(w->object); JS_FreeValue(c, callback); return JS_ThrowOutOfMemory(c); }
    if (button) {
        lv_obj_set_style_bg_opa(w->object, LV_OPA_COVER, 0);
        lv_obj_set_style_bg_color(w->object, lv_color_hex(color), 0);
        lv_obj_set_style_radius(w->object, 12, 0);
        lv_obj_set_style_text_color(w->label, lv_color_hex(0x101820), 0);
    } else lv_obj_set_style_text_color(w->label, lv_color_hex(color), 0);
    lv_obj_set_style_text_font(w->label, &lv_font_montserrat_16, 0);
    lv_label_set_text(w->label, buffer);
    if (button) lv_obj_center(w->label);
    w->handle = ++next_handle;
    w->button = button;
    w->callback = callback;
    w->binding = (event_message){a->activation, w->handle};
    if (button) lv_obj_add_event_cb(w->object, enqueue, LV_EVENT_CLICKED, &w->binding);
    ++a->count;
    return JS_NewInt64(c, w->handle);
}
static JSValue make_label(JSContext *c, JSValueConst self, int argc, JSValueConst *argv) {
    return create_widget(c, self, argc, argv, 0);
}
static JSValue make_button(JSContext *c, JSValueConst self, int argc, JSValueConst *argv) {
    return create_widget(c, self, argc, argv, 1);
}
static widget *lookup(app *a, uint32_t handle) {
    for (unsigned i = 0; i < a->count; ++i) if (a->widgets[i].handle == handle) return &a->widgets[i];
    return NULL;
}
static JSValue update(JSContext *c, JSValueConst self, int argc, JSValueConst *argv) {
    (void)self;
    owner_only();
    app *a = JS_GetContextOpaque(c);
    static const char *const fields[] = {"text", "background", "color", NULL};
    double number;
    if (argc != 2 || !JS_IsNumber(argv[0]) || JS_ToFloat64(c, &number, argv[0])
        || number < 1 || number > UINT32_MAX || floor(number) != number
        || !allowed_fields(c, argv[1], fields)) return invalid(c);
    widget *w = lookup(a, (uint32_t)number);
    if (!w) return invalid(c);
    JSValue text = JS_GetPropertyStr(c, argv[1], "text");
    JSValue background = JS_GetPropertyStr(c, argv[1], "background");
    JSValue foreground = JS_GetPropertyStr(c, argv[1], "color");
    char buffer[TEXT_LIMIT + 1];
    uint32_t bg = 0, fg = 0;
    int has_text = !JS_IsUndefined(text), has_bg = !JS_IsUndefined(background), has_fg = !JS_IsUndefined(foreground);
    int ok = (!has_text || text_value(c, text, buffer))
        && (!has_bg || (w->button && color_value(c, background, &bg)))
        && (!has_fg || color_value(c, foreground, &fg));
    JS_FreeValue(c, text); JS_FreeValue(c, background); JS_FreeValue(c, foreground);
    if (!ok) return invalid(c);
    if (has_text) { lv_label_set_text(w->label, buffer); if (w->button) lv_obj_center(w->label); }
    if (has_bg) lv_obj_set_style_bg_color(w->object, lv_color_hex(bg), 0);
    if (has_fg) lv_obj_set_style_text_color(w->label, lv_color_hex(fg), 0);
    return JS_UNDEFINED;
}
static void destroy(app *a) {
    if (!a) return;
    owner_only();
    assert(lv_screen_active() != a->root);
    lv_obj_delete(a->root);
    JS_SetHostPromiseRejectionTracker(a->runtime, NULL, NULL);
    for (unsigned i = 0; i < a->rejection_count; ++i) JS_FreeValue(a->context, a->rejections[i]);
    for (unsigned i = 0; i < a->count; ++i) JS_FreeValue(a->context, a->widgets[i].callback);
    JS_FreeContext(a->context);
    JS_FreeRuntime(a->runtime);
    assert(a->memory.allocated == 0);
    if (a->memory.peak > peak_payload) peak_payload = a->memory.peak;
    --alive_apps;
    free(a);
}
static app *create(void) {
    static const JSMallocFunctions allocator = {tracked_calloc, tracked_malloc, tracked_free, tracked_realloc, tracked_size};
    app *a = calloc(1, sizeof(*a));
    assert(a);
    a->activation = ++next_activation;
    a->runtime = JS_NewRuntime2(&allocator, &a->memory);
    assert(a->runtime);
    JS_SetMemoryLimit(a->runtime, ENGINE_LIMIT);
    JS_SetMaxStackSize(a->runtime, 32768);
    JS_SetInterruptHandler(a->runtime, interrupt, &a->memory);
    JS_SetHostPromiseRejectionTracker(a->runtime, promise_rejection, a);
    a->context = JS_NewContext(a->runtime);
    assert(a->context);
    JS_SetContextOpaque(a->context, a);
    a->root = lv_obj_create(NULL);
    assert(a->root);
    plain(a->root, 0, 0, WIDTH, HEIGHT);
    lv_obj_set_style_bg_opa(a->root, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(a->root, lv_color_hex(0x101820), 0);
    JSValue api = JS_NewObject(a->context);
    assert(JS_SetPropertyStr(a->context, api, "label", JS_NewCFunction(a->context, make_label, "label", 1)) > 0);
    assert(JS_SetPropertyStr(a->context, api, "button", JS_NewCFunction(a->context, make_button, "button", 1)) > 0);
    assert(JS_SetPropertyStr(a->context, api, "update", JS_NewCFunction(a->context, update, "update", 2)) > 0);
    JSValue global = JS_GetGlobalObject(a->context);
    assert(JS_SetPropertyStr(a->context, global, "ui", api) > 0);
    JS_FreeValue(a->context, global);
    ++alive_apps;
    return a;
}
static int evaluate(app *a, const char *source) {
    reset_budget(a);
    JSValue result = JS_Eval(a->context, source, strlen(source), "isolated-app.js", JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_STRICT);
    int ok = !JS_IsException(result);
    JS_FreeValue(a->context, result);
    if (!ok) discard_exception(a->context);
    return ok && drain_jobs(a);
}
static int install(const char *source) {
    owner_only();
    app *candidate = create();
    if (!evaluate(candidate, source)) { ++rejected; destroy(candidate); return 0; }
    lv_screen_load(candidate->root);
    destroy(previous);
    previous = live;
    live = candidate;
    ++installs;
    return 1;
}
static int pump(void) {
    owner_only();
    while (queue_count) {
        event_message event = queue[queue_head];
        queue_head = (queue_head + 1) % QUEUE_LIMIT;
        --queue_count;
        if (!live || event.activation != live->activation) { ++stale; continue; }
        widget *w = lookup(live, event.handle);
        if (!w || !w->button) { ++stale; continue; }
        reset_budget(live);
        JSValue result = JS_Call(live->context, w->callback, JS_UNDEFINED, 0, NULL);
        int ok = !JS_IsException(result);
        JS_FreeValue(live->context, result);
        if (!ok) discard_exception(live->context);
        ++callbacks;
        if (!ok || !drain_jobs(live)) {
            app *failed = live;
            live = previous; previous = NULL;
            if (live) {
                /* Restoring an old model is a new activation, never a replay. */
                live->activation = ++next_activation;
                for (unsigned i = 0; i < live->count; ++i)
                    live->widgets[i].binding.activation = live->activation;
            }
            lv_screen_load(live ? live->root : shell);
            destroy(failed);
            return 0;
        }
    }
    return 1;
}
static void flush(lv_display_t *disp, const lv_area_t *area, uint8_t *pixels) {
    int width = area->x2 - area->x1 + 1;
    for (int y = area->y1; y <= area->y2; ++y) {
        memcpy(&framebuffer[y * WIDTH + area->x1], pixels, (size_t)width * 4);
        pixels += width * 4;
    }
    lv_display_flush_ready(disp);
}
static void render(void) {
    lv_obj_update_layout(lv_screen_active());
    lv_obj_invalidate(lv_screen_active());
    lv_refr_now(display);
}
static uint32_t pixel(int x, int y) { return framebuffer[y * WIDTH + x] & 0xffffff; }
static void screenshot(const char *name) {
    render();
    FILE *out = fopen(name, "wb"); assert(out);
    fprintf(out, "P6\n%d %d\n255\n", WIDTH, HEIGHT);
    for (unsigned i = 0; i < WIDTH * HEIGHT; ++i) {
        unsigned char rgb[] = {framebuffer[i] >> 16, framebuffer[i] >> 8, framebuffer[i]};
        assert(fwrite(rgb, 1, 3, out) == 3);
    }
    assert(!fclose(out));
}
static void click(unsigned index) {
    assert(live && index < live->count && live->widgets[index].button);
    lv_obj_send_event(live->widgets[index].object, LV_EVENT_CLICKED, NULL);
}
static const char colors[] =
    "(() => { let n = 0; const colors = ['#ff69b4','#4287f5','#80ff80'];"
    "ui.label({x:24,y:36,width:272,height:40,text:'Hello World',color:'#ffffff'});"
    "const b = ui.button({x:24,y:132,width:272,height:72,text:'Change color',background:colors[0],"
    "onClick:() => { n += 1; ui.update(b,{background:colors[n % colors.length]}); }}); })();";
static const char calculation[] =
    "(() => { let count = 0; const prices = [3,5,7];"
    "const label = ui.label({x:24,y:36,width:272,height:40,text:'Total: 0',color:'#ffffff'});"
    "ui.button({x:24,y:132,width:272,height:72,text:'Add item',background:'#ffcc80',onClick:() => {"
    "count++; const total = prices.slice(0, count % 4).reduce((sum,price) => sum+price,0);"
    "ui.update(label,{text:'Total: '+total+(total>=8?' | discount':'')}); }}); })();";
int main(void) {
    owner = pthread_self();
    lv_init();
    assert(LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR == 4);
    display = lv_display_create(WIDTH, HEIGHT); assert(display);
    lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(display, draw_buffer, NULL, sizeof(draw_buffer), LV_DISPLAY_RENDER_MODE_FULL);
    lv_display_set_flush_cb(display, flush);
    shell = lv_screen_active();
    assert(install(colors));
    render(); assert(pixel(40, 150) == 0xff69b4); screenshot("color-0.ppm");
    static const uint32_t expected[] = {0x4287f5,0x80ff80,0xff69b4};
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t before = pixel(40, 150);
        click(1); render(); assert(pixel(40, 150) == before);
        assert(pump()); render(); assert(pixel(40, 150) == expected[i]);
        char name[32]; snprintf(name, sizeof(name), "color-%u.ppm", i + 1); screenshot(name);
    }
    app *working = live;
    uint64_t active = live->activation;
    click(1);
    assert(install(calculation));
    assert(pump()); assert(stale == 1 && callbacks == 3);
    click(1); assert(pump()); assert(!strcmp(lv_label_get_text(live->widgets[0].label), "Total: 3"));
    click(1); assert(pump()); assert(!strcmp(lv_label_get_text(live->widgets[0].label), "Total: 8 | discount"));
    screenshot("calculation.ppm");
    assert(previous == working && previous->activation == active);
    working = live;
    const char *bad[] = {
        "ui.label({x:1,y:1,width:20,height:20,text:'hidden'}); throw Error('init');",
        "ui.label({x:1,y:1,width:20,height:20,text:'hidden'}); while(true){}",
        "function spin(){Promise.resolve().then(spin)} spin();",
        "Promise.reject(Error('init rejection'));",
        "(async()=>{throw Error('async init')})();",
        "Promise.resolve().then(()=>{throw Error('microtask init')});",
        "const pending=[];for(let i=0;i<17;i++)pending.push(Promise.reject(i));pending.forEach(p=>p.catch(()=>{}));",
        "ui.label({x:319,y:1,width:20,height:20,text:'offscreen'});",
        "ui.label({x:NaN,y:1,width:20,height:20,text:'bad'});",
        "ui.label({x:1,y:1,width:20,height:20,text:'x'.repeat(129)});",
        "ui.label({x:1,y:1,width:20,height:20,text:'x\\u0000x'});",
        "ui.label({x:1,y:1,width:20,height:20,text:'x',color:'#fffffg'});",
        "ui.update(1,{text:'foreign handle'});",
        "for(let i=0;i<33;i++)ui.label({x:1,y:1,width:20,height:20,text:'x'});",
        "ui.label({x:1,y:1,width:20,height:20,text:'x',nativePointer:1});",
        "ui.button({x:1,y:1,width:20,height:20,text:'x',onClick:4});",
        "ui.label({get x(){throw Error('getter')},y:1,width:20,height:20,text:'x'});",
        "ui.label({x:{valueOf(){while(true){}}},y:1,width:20,height:20,text:'x'});",
        "ui.update({valueOf(){while(true){}}},{text:'x'});",
        "ui.label({x:1,y:1,width:20,height:20,text:{toString(){while(true){}}}});",
        "ui.label({get x(){ui.label({x:1,y:1,width:20,height:20,text:'nested'});throw Error('getter')},y:1,width:20,height:20,text:'x'});",
        "const h=ui.label({x:1,y:1,width:20,height:20,text:'x'});ui.update(h,{background:'#ffffff'});"
    };
    for (unsigned i = 0; i < sizeof(bad)/sizeof(*bad); ++i) {
        assert(!install(bad[i])); assert(live == working && lv_screen_active() == working->root);
        assert(alive_apps == 2);
    }
    const char *failures[] = {"throw Error('click');", "while(true){}",
        "function spin(){Promise.resolve().then(spin)}spin();",
        "return Promise.reject(Error('rejected click'));",
        "return (async()=>{throw Error('async click')})();",
        "return Promise.resolve().then(()=>{throw Error('microtask click')});"};
    for (unsigned i = 0; i < sizeof(failures)/sizeof(*failures); ++i) {
        char source[512]; snprintf(source, sizeof(source),
            "ui.button({x:24,y:132,width:272,height:72,text:'Fail safely',onClick:()=>{%s}});", failures[i]);
        event_message old_binding = working->widgets[1].binding;
        assert(install(source)); click(0); click(0); assert(!pump());
        assert(working->activation != old_binding.activation);
        queue[(queue_head + queue_count++) % QUEUE_LIMIT] = old_binding;
        assert(live == working && lv_screen_active() == working->root);
        assert(pump());
        click(1); assert(pump());
    }
    assert(install("const p=Promise.reject(Error('handled init'));Promise.resolve().then(()=>p.catch(()=>{}));"
        "ui.button({x:24,y:132,width:272,height:72,text:'Handled',onClick:async()=>{"
        "const rejected=Promise.reject(Error('handled click'));"
        "await Promise.resolve().then(()=>rejected.catch(()=>{}));}});"));
    app *handled = live;
    click(0); assert(pump()); assert(live == handled && !live->rejection_count);
    assert(install(colors));
    for (unsigned i = 0; i < QUEUE_LIMIT + 5; ++i) click(1);
    assert(queue_count == QUEUE_LIMIT && dropped == 5); assert(pump());
    for (unsigned i = 0; i < 100; ++i) {
        click(1); /* Remains a value-only stale message after replacement. */
        assert(install(colors)); assert(pump());
        click(1); assert(pump()); render(); assert(pixel(40,150) == 0x4287f5);
        assert(alive_apps == 2);
    }
    lv_screen_load(shell);
    destroy(live); destroy(previous); live = previous = NULL;
    assert(alive_apps == 0 && queue_count == 0);
    lv_display_delete(display);
    lv_deinit();
    printf("{\"status\":\"real_ui_probe_passed\",\"engine\":\"QuickJS-NG0.14.0\",\"lvgl\":\"9.4\",\"installs\":%u,\"callbacks\":%u,\"rejected_initializations\":%u,\"stale_events\":%u,\"dropped_events\":%u,\"peak_engine_allocation_payload\":%zu,\"remaining_apps\":%u,\"physical_execution\":false}\n",
        installs, callbacks, rejected, stale, dropped, peak_payload, alive_apps);
    return 0;
}
