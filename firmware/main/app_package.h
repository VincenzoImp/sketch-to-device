#pragma once
#include "app_spec.h"
#include "program_package.h"

typedef enum { APP_PACKAGE_LEGACY = 1, APP_PACKAGE_PROGRAM = 2 } app_package_kind;
typedef struct app_package {
    app_package_kind kind;
    char app_id[AS_ID], name[AS_ID];
    int32_t version;
    union { as_app *legacy; pr_package *program; } data;
} app_package;

/* Exact bytes are copied/decoded. Input may be released after this returns.
 * A failed parse returns NULL and a fixed diagnostic code, never source text. */
app_package *app_package_parse(const void *bytes, size_t size, const char **error);
app_package *app_package_copy_legacy(const as_app *app);
void app_package_free(app_package *package);
