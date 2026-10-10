#pragma once
#include "app_package.h"

typedef uint64_t app_ui_ticket;
typedef enum {
    APP_UI_NONE, APP_UI_PREPARE, APP_UI_ACTIVATE, APP_UI_COMMIT,
    APP_UI_ABORT, APP_UI_ROLLBACK, APP_UI_PREPARE_RECOVERY, APP_UI_RETAIN_PREVIOUS
} app_ui_operation;
typedef struct {
    uint64_t revision;
    app_ui_ticket live, previous, prepared;
    app_ui_ticket operation_ticket;
    app_ui_operation operation;
    bool pending, succeeded, paused;
    char error[48];
    app_ui_ticket checkpoint_ticket;
    uint64_t checkpoints;
    /* Sticky until recovery is durable and app_ui_ack_fault succeeds. */
    app_ui_ticket fault_ticket, recovered_ticket;
    char fault[48];
    uint32_t dropped_input, stale_input, owner_stack_free_bytes;
    size_t internal_free_bytes, internal_largest_bytes, external_free_bytes;
} app_ui_state;

/* Starts the sole JS/UI owner task with a 64 KiB stack. No JS runs in an
 * LVGL callback or delivery task. Public calls only copy/enqueue bounded data;
 * the owner evaluates JS outside the BSP lock and draws under that lock. */
bool app_ui_init(void);

/* PREPARE is asynchronous. Success transfers package ownership and assigns a
 * nonzero boot-local ticket; failure (busy/queue full/allocation) leaves ownership
 * with the caller. Caller waits using snapshot; no stack reply pointer survives.
 * READY is pending=false, operation=PREPARE, succeeded=true, prepared=ticket.
 * Preparation never changes live UI. Only one delivery command may be pending.
 * Tickets are not deployment identities and do not survive a reboot. */
bool app_ui_prepare(app_package *package, app_ui_ticket *ticket);
/* Trusted delivery only, after a recovery intent is durable. A sticky live
 * fault is required. RETAIN_PREVIOUS checkpoints and pauses this candidate,
 * replacing the hidden fallback without presenting it; ROLLBACK then uses it.
 * This guard also closes an uncommitted failed activation, disposing only its
 * obsolete older fallback; the current prior app stays until retention succeeds.
 * Ownership and asynchronous completion match PREPARE. */
bool app_ui_prepare_recovery(app_package *package, app_ui_ticket *ticket);

/* ACTIVATE switches a READY candidate and reports an activation-specific first
 * healthy checkpoint. COMMIT follows coherent durable device metadata, without
 * waiting for network ACK; it retains the former live instance for recovery and
 * frees only the older previous instance. ABORT discards an unactivated candidate.
 * ROLLBACK restores the actual prior instance (or built-in shell fallback), then
 * disposes the failed/stale candidate. It must follow the durable recovery guard.
 * Successful repeats are idempotent. Busy/malformed/queue-full returns false with
 * no ownership change. Invalid lifecycle transitions complete with succeeded=false.
 * Snapshot operation+ticket identify asynchronous completion.
 * ABORT cannot substitute for ROLLBACK after activation. */
bool app_ui_request(app_ui_operation operation, app_ui_ticket ticket);
void app_ui_snapshot(app_ui_state *out);
/* Clear only a recovered ticket's sticky fault, after persisting recovery/outbox.
 * A live fault cannot be acknowledged away to resume failed JavaScript. */
bool app_ui_ack_fault(app_ui_ticket ticket);
/* Fixed-quality clock input: false is estimated/unavailable, never synchronized.
 * Called by trusted time service after an actual SNTP synchronization callback. */
void app_ui_wall_synchronized(bool synchronized);
void app_ui_status(const char *message);

/* Migration-only schema1 shims; delivery will switch to ticket operations.
 * activate copies the legacy app and waits for the owner, never lends its pointer.
 * tick is inert: the owner task supplies monotonic ticks. Generic healthy_ticks
 * is retained only for old delivery and is not programmable activation evidence. */
bool app_ui_activate(const as_app *app);
void app_ui_tick(void);
uint64_t app_ui_healthy_ticks(void);
