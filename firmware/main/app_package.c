#include "app_package.h"
#include <stdlib.h>
#include <string.h>

void app_package_free(app_package *package) {
    if (!package) return;
    if (package->kind == APP_PACKAGE_PROGRAM && package->data.program) {
        pr_package_free(package->data.program);
        free(package->data.program);
    } else if (package->kind == APP_PACKAGE_LEGACY) free(package->data.legacy);
    free(package);
}

app_package *app_package_copy_legacy(const as_app *app) {
    if (!app) return NULL;
    app_package *package = calloc(1, sizeof(*package));
    if (!package) return NULL;
    package->kind = APP_PACKAGE_LEGACY;
    package->data.legacy = malloc(sizeof(*app));
    if (!package->data.legacy) { app_package_free(package); return NULL; }
    *package->data.legacy = *app;
    memcpy(package->app_id, app->app_id, sizeof(package->app_id));
    memcpy(package->name, app->name, sizeof(package->name));
    package->version = app->version;
    return package;
}

app_package *app_package_parse(const void *bytes, size_t size, const char **error) {
    if (error) *error = "package_invalid";
    /* This dispatch is not validation. Each selected trusted parser rechecks the
     * complete document, including duplicate/unknown keys and exact schema. */
    cJSON *document = pr_json_parse(bytes, size, PR_PACKAGE_BYTES);
    if (!document) return NULL;
    cJSON *schema = cJSON_GetObjectItemCaseSensitive(document, "schema_version");
    int kind = cJSON_IsNumber(schema) ? schema->valueint : 0;
    cJSON_Delete(document);
    if (kind != APP_PACKAGE_LEGACY && kind != APP_PACKAGE_PROGRAM) return NULL;
    app_package *package = calloc(1, sizeof(*package));
    if (!package) { if (error) *error = "allocation_failed"; return NULL; }
    package->kind = (app_package_kind)kind;
    bool ok = false;
    if (kind == APP_PACKAGE_LEGACY) {
        package->data.legacy = calloc(1, sizeof(as_app));
        if (package->data.legacy) ok = as_parse(bytes, size, package->data.legacy, error);
        if (ok) {
            memcpy(package->app_id, package->data.legacy->app_id, sizeof(package->app_id));
            memcpy(package->name, package->data.legacy->name, sizeof(package->name));
            package->version = package->data.legacy->version;
        }
    } else {
        package->data.program = calloc(1, sizeof(pr_package));
        if (package->data.program) ok = pr_package_parse(bytes, size, package->data.program, error);
        if (ok) {
            memcpy(package->app_id, package->data.program->app_id, sizeof(package->app_id));
            memcpy(package->name, package->data.program->name, sizeof(package->name));
            package->version = package->data.program->version;
        }
    }
    if (!ok) { app_package_free(package); return NULL; }
    if (error) *error = NULL;
    return package;
}
