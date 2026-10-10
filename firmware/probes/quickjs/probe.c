/* Isolated engine feasibility tests. No display, networking or device secrets. */
#include "quickjs.h"
#include <assert.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

#define ALLOCATION_LIMIT (512u * 1024u)
#define ENGINE_LIMIT (256u * 1024u)
#define JOB_LIMIT 64
#define DEADLINE_US 50000

typedef union {
    max_align_t alignment;
    struct { size_t size; } info;
} allocation_header;

typedef struct {
    size_t allocated, peak;
    unsigned calls, jobs, events;
    int64_t deadline;
    int interrupted;
    uint32_t color, score;
} probe_state;

static int64_t now_us(void)
{
#ifdef ESP_PLATFORM
    return esp_timer_get_time();
#else
    struct timespec value;
    assert(clock_gettime(CLOCK_MONOTONIC, &value) == 0);
    return (int64_t)value.tv_sec * 1000000 + value.tv_nsec / 1000;
#endif
}

static void *tracked_malloc(void *opaque, size_t size)
{
    probe_state *state = opaque;
    if (!size || size > ALLOCATION_LIMIT - state->allocated
        || size > SIZE_MAX - sizeof(allocation_header)) return NULL;
    allocation_header *header = malloc(sizeof(*header) + size);
    if (!header) return NULL;
    header->info.size = size;
    state->allocated += size;
    if (state->allocated > state->peak) state->peak = state->allocated;
    return header + 1;
}

static void tracked_free(void *opaque, void *pointer)
{
    if (!pointer) return;
    probe_state *state = opaque;
    allocation_header *header = (allocation_header *)pointer - 1;
    assert(state->allocated >= header->info.size);
    state->allocated -= header->info.size;
    free(header);
}

static void *tracked_calloc(void *opaque, size_t count, size_t size)
{
    if (count && size > SIZE_MAX / count) return NULL;
    size *= count;
    void *result = tracked_malloc(opaque, size);
    if (result) memset(result, 0, size);
    return result;
}

static void *tracked_realloc(void *opaque, void *pointer, size_t size)
{
    if (!pointer) return tracked_malloc(opaque, size);
    if (!size) { tracked_free(opaque, pointer); return NULL; }
    probe_state *state = opaque;
    allocation_header *old = (allocation_header *)pointer - 1;
    size_t old_size = old->info.size;
    if (size > ALLOCATION_LIMIT - (state->allocated - old_size)
        || size > SIZE_MAX - sizeof(*old)) return NULL;
    allocation_header *next = realloc(old, sizeof(*old) + size);
    if (!next) return NULL;
    next->info.size = size;
    state->allocated = state->allocated - old_size + size;
    if (state->allocated > state->peak) state->peak = state->allocated;
    return next + 1;
}

static size_t tracked_size(const void *pointer)
{
    return pointer ? ((const allocation_header *)pointer - 1)->info.size : 0;
}

static int interrupt(JSRuntime *runtime, void *opaque)
{
    (void)runtime;
    probe_state *state = opaque;
    if (++state->calls > 1000 || now_us() >= state->deadline) {
        state->interrupted = 1;
        return 1;
    }
    return 0;
}

static JSValue sink(JSContext *context, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    probe_state *state = JS_GetContextOpaque(context);
    int32_t color, score;
    if (argc != 2 || !JS_IsNumber(argv[0]) || !JS_IsNumber(argv[1])
        || JS_ToInt32(context, &color, argv[0]) || JS_ToInt32(context, &score, argv[1])
        || color < 0 || color > 0xffffff || score < 0 || score > 1000)
        return JS_ThrowTypeError(context, "invalid probe sink arguments");
    state->color = (uint32_t)color;
    state->score = (uint32_t)score;
    state->events++;
    return JS_UNDEFINED;
}

static void budget(probe_state *state)
{
    state->calls = state->jobs = 0;
    state->interrupted = 0;
    state->deadline = now_us() + DEADLINE_US;
}

static JSContext *create(probe_state *state)
{
    static const JSMallocFunctions functions = {
        .js_calloc = tracked_calloc, .js_malloc = tracked_malloc,
        .js_free = tracked_free, .js_realloc = tracked_realloc,
        .js_malloc_usable_size = tracked_size,
    };
    JSRuntime *runtime = JS_NewRuntime2(&functions, state);
    assert(runtime);
    JS_SetMemoryLimit(runtime, ENGINE_LIMIT);
    JS_SetMaxStackSize(runtime, 32768);
    JS_SetInterruptHandler(runtime, interrupt, state);
    JSContext *context = JS_NewContext(runtime);
    assert(context);
    JS_SetContextOpaque(context, state);
    JSValue global = JS_GetGlobalObject(context);
    assert(JS_SetPropertyStr(context, global, "sink", JS_NewCFunction(context, sink, "sink", 2)) == 1);
    JS_FreeValue(context, global);
    budget(state);
    return context;
}

static int evaluate(JSContext *context, const char *source)
{
    JSValue value = JS_Eval(context, source, strlen(source), "probe.js",
                            JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_STRICT);
    int ok = !JS_IsException(value);
    JS_FreeValue(context, value);
    if (!ok) JS_FreeValue(context, JS_GetException(context));
    return ok;
}

static int jobs(JSContext *context, probe_state *state)
{
    JSRuntime *runtime = JS_GetRuntime(context);
    while (JS_IsJobPending(runtime)) {
        if (state->jobs++ >= JOB_LIMIT || now_us() >= state->deadline) return 0;
        JSContext *owner = NULL;
        if (JS_ExecutePendingJob(runtime, &owner) < 0) {
            if (owner) JS_FreeValue(owner, JS_GetException(owner));
            return 0;
        }
    }
    return 1;
}

static void destroy(JSContext *context, probe_state *state)
{
    JSRuntime *runtime = JS_GetRuntime(context);
    JS_FreeContext(context);
    JS_FreeRuntime(runtime);
    assert(state->allocated == 0);
}

static const char application[] =
    "globalThis.onTap = (() => { const colors = [0xff69b4,0x164ead,0x80ff80];"
    "let score = 0; return () => { score += 1; sink(colors[(score-1)%colors.length], score); }; })();";

static void callback_test(JSContext *context, probe_state *state)
{
    budget(state);
    assert(evaluate(context, application));
    JSValue global = JS_GetGlobalObject(context);
    JSValue callback = JS_GetPropertyStr(context, global, "onTap");
    assert(JS_IsFunction(context, callback));
    static const uint32_t expected[] = {0xff69b4, 0x164ead, 0x80ff80};
    unsigned previous = state->events;
    for (int i = 0; i < 12; i++) {
        budget(state);
        JSValue result = JS_Call(context, callback, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(result));
        JS_FreeValue(context, result);
        assert(state->color == expected[i % 3] && state->score == (uint32_t)i + 1);
    }
    assert(state->events == previous + 12);
    JS_FreeValue(context, callback);
    JS_FreeValue(context, global);
}

static void recovery_test(probe_state *state)
{
    JSContext *context = create(state);
    callback_test(context, state);
    destroy(context, state);
}

static int run_tests(void)
{
    probe_state state = {0};
    int64_t start = now_us();
    JSContext *context = create(&state);
    callback_test(context, &state);
    assert(evaluate(context, "if (typeof std !== 'undefined' || typeof os !== 'undefined' || typeof fetch !== 'undefined') throw 1;"));
    budget(&state);
    assert(!evaluate(context, "let broken = ;"));
    budget(&state);
    assert(!evaluate(context, "throw new Error('expected');"));
    callback_test(context, &state);
    budget(&state);
    assert(!evaluate(context, "try { while (true) {} } catch (e) {}"));
    assert(state.interrupted);
    destroy(context, &state);
    recovery_test(&state);

    context = create(&state);
    budget(&state);
    assert(!evaluate(context, "(function recurse() { recurse(); })();"));
    assert(!state.interrupted);
    destroy(context, &state);
    recovery_test(&state);

    context = create(&state);
    budget(&state);
    assert(!evaluate(context, "globalThis.blocks=[]; while(true) blocks.push(new ArrayBuffer(32768));"));
    assert(!state.interrupted && state.peak <= ALLOCATION_LIMIT);
    destroy(context, &state);
    recovery_test(&state);

    context = create(&state);
    budget(&state);
    assert(evaluate(context, "function spin(){ Promise.resolve().then(spin); } spin();"));
    assert(!jobs(context, &state));
    assert(state.jobs > 0);
    destroy(context, &state);
    recovery_test(&state);

    for (int i = 0; i < 100; i++) {
        context = create(&state);
        callback_test(context, &state);
        destroy(context, &state);
    }
    printf("{\"status\":\"engine_checks_passed\",\"callback_checks\":%u,"
           "\"recreated_apps\":100,\"allocation_peak\":%zu,\"residual_bytes\":%zu,"
           "\"elapsed_us\":%" PRId64 "}\n", state.events, state.peak, state.allocated, now_us() - start);
    return 0;
}

#ifdef ESP_PLATFORM
static void probe_task(void *unused)
{
    (void)unused;
    size_t before = heap_caps_get_free_size(MALLOC_CAP_8BIT);
    run_tests();
    printf("{\"target\":\"esp32p4\",\"heap_before\":%zu,\"heap_after\":%zu}\n",
           before, heap_caps_get_free_size(MALLOC_CAP_8BIT));
    vTaskDelete(NULL);
}
void app_main(void)
{
    assert(xTaskCreate(probe_task, "quickjs_probe", 65536, NULL, 5, NULL) == pdPASS);
}
#else
int main(void) { return run_tests(); }
#endif
