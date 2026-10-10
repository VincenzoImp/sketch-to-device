#pragma once
#include "program_runtime.h"
#include "cJSON.h"
typedef struct {
    pr_program program;
    pr_asset assets[PR_ASSETS];
    char app_id[49], name[49];
    int32_t version;
    void *document;
} pr_package;
/* Caller-owned input need only survive this call; all outputs are owned. */
bool pr_package_parse(const void *bytes,size_t size,pr_package *out,const char **error);
void pr_package_free(pr_package *);
/* Shared strict JSON syntax gate for package/scenario readers. */
cJSON *pr_json_parse(const void *bytes,size_t size,size_t maximum);
void pr_sha256(const uint8_t *bytes,size_t size,char hex[65]);
