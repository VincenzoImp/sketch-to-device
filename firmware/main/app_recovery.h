#pragma once
#include "app_spec.h"

/* Existing metadata ABI: do not reorder/extend either structure. */
typedef struct {
    char deployment_id[129], app_id[AS_ID], sha256[65], path[160];
    int64_t sequence;
    int32_t version;
    uint32_t size;
} deployment;
typedef struct {
    uint32_t magic;
    int active, previous, pending, pending_slot;
    deployment slots[2];
    char blocked_id[129];
} install_metadata;

#define RECOVERY_MAGIC 0x534B5231u
#define RECOVERY_VERSION 1u
typedef enum { RECOVERY_INTENT = 1, RECOVERY_READY = 2 } recovery_stage;
typedef enum { RECOVERY_RUNTIME = 1, RECOVERY_ACTIVATION, RECOVERY_FAILED } recovery_error;
typedef struct {
    uint64_t sequence;
    char report_id[65];
    uint32_t stage, error;
    int failed_slot, recovered_slot;
    deployment failed, recovered;
} recovery_record;
/* Separate versioned NVS blob. Each commit is a single-key transaction;
 * INTENT replays independently of which metadata write reached flash. */
typedef struct {
    uint32_t magic, version, count, reserved;
    uint64_t next_sequence;
    int64_t quarantine_through;
    char failed_ids[2][129];
    int ack_slot;
    char ack_id[129];
    recovery_record records[2];
} recovery_journal;
