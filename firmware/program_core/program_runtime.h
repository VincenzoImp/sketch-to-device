#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "lvgl.h"

#define PR_WIDTH 320
#define PR_HEIGHT 432
#define PR_PACKAGE_BYTES 65536
#define PR_SCENARIO_BYTES 524288
#define PR_ASSETS 32
#define PR_ASSET_BYTES 49152
#define PR_COMMANDS 128
#define PR_TEXT_BYTES 256
#define PR_CHECKPOINT_TEXT 4096
#define PR_PIXEL_WORK (4u * PR_WIDTH * PR_HEIGHT)

typedef struct { const char *id; unsigned width, height; const uint8_t *rgba; size_t size; } pr_asset;
typedef struct { const char *source; size_t source_size; const pr_asset *assets; size_t asset_count; } pr_program;
typedef enum { PR_WALL_UNAVAILABLE, PR_WALL_ESTIMATED, PR_WALL_SYNCHRONIZED } pr_wall_source;
typedef struct { uint64_t monotonic_ms; int64_t epoch_ms; pr_wall_source wall_source; } pr_clock;
typedef enum { PR_TICK, PR_DOWN, PR_MOVE, PR_UP, PR_CANCEL } pr_event_type;
typedef struct { uint64_t activation, timestamp_ms; pr_event_type type; int x, y; } pr_event;
typedef struct pr_runtime pr_runtime;
typedef struct {
    unsigned callbacks, frames, stale_events;
    size_t engine_payload, peak_engine_payload, owned_native_bytes;
    const char *fault;
} pr_metrics;

/* All calls belong to one owner thread/task. The caller serializes dispatch,
 * pause, activation, presentation and disposal. No API executes JavaScript
 * while calling LVGL. Programs contain no filesystem/network/native modules.
 * create copies assets and evaluates source; source need not outlive the call.
 * Engine interrupts are soft; LVGL native OOM is not contained by this API. */
pr_runtime *pr_create(const pr_program *, pr_clock, uint32_t seed, const char **error);
/* attach/present/detach require the caller's LVGL/BSP lock. Attach is hidden.
 * Detach deletes objects before backing pixels can be freed by destroy. */
bool pr_attach(pr_runtime *, lv_obj_t *parent);
bool pr_present(pr_runtime *);
lv_obj_t *pr_root(pr_runtime *);
void pr_detach(pr_runtime *);
void pr_destroy(pr_runtime *);
/* Dispatch executes JS and microtasks outside the LVGL/BSP lock. A fault
 * latches; no further program execution is allowed. Integration owns rollback
 * and durable recovery identity. A false result never commits a new frame. */
bool pr_dispatch(pr_runtime *, pr_event, pr_clock);
void pr_set_activation(pr_runtime *, uint64_t activation);
void pr_pause(pr_runtime *);
void pr_resume(pr_runtime *, pr_clock);
pr_metrics pr_get_metrics(const pr_runtime *);
/* RGB565 host-order backing frame, valid while runtime lives; read under lock. */
const uint16_t *pr_pixels(const pr_runtime *);
