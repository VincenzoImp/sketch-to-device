#include "app_delivery.h"
#include "app_ui.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#define META_MAGIC 0x534B4431u
#define CONNECTED BIT0
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
static install_metadata metadata;
static nvs_handle_t storage;
static EventGroupHandle_t connectivity;
static const as_app *builtin_app;
static as_app *installed_app;

static const cJSON *item(const cJSON *o, const char *key) { return cJSON_GetObjectItemCaseSensitive(o,key); }
static const char *string(const cJSON *o, const char *key) { return cJSON_GetStringValue(item(o,key)); }
static bool number(const cJSON *n, double low, double high) {
    return cJSON_IsNumber(n) && isfinite(n->valuedouble) && n->valuedouble >= low && n->valuedouble <= high && floor(n->valuedouble) == n->valuedouble;
}
static bool token(const char *s, size_t maximum) {
    if (!s || !*s || strlen(s) > maximum) return false;
    for (; *s; ++s)
        if (!(*s >= 'a' && *s <= 'z') && !(*s >= 'A' && *s <= 'Z') &&
            !(*s >= '0' && *s <= '9') && *s != '_' && *s != '-' && *s != '.') return false;
    return true;
}
static bool app_id(const char *s) {
    if (!token(s,48) || *s < 'a' || *s > 'z') return false;
    for (; *s; ++s) if ((*s >= 'A' && *s <= 'Z') || *s == '.') return false;
    return true;
}
static bool hash_valid(const char *s) {
    if (!s || strlen(s) != 64) return false;
    for (; *s; ++s) if (!(*s >= '0' && *s <= '9') && !(*s >= 'a' && *s <= 'f')) return false;
    return true;
}
static bool runtime_supported(const char *version) {
    return version && (!strcmp(version,"0.1.0") || !strcmp(version,"0.2.0"));
}
static bool digest_matches(const char *bytes, size_t size, const char *expected) {
    unsigned char digest[32]; char hex[65];
    if (mbedtls_sha256((const unsigned char *)bytes,size,digest,0) != 0) return false;
    for (int i = 0; i < 32; ++i) snprintf(hex+2*i,3,"%02x",digest[i]);
    return !strcmp(hex,expected);
}
static bool same(const deployment *a, const deployment *b) {
    return a->sequence == b->sequence && a->version == b->version && a->size == b->size &&
        !strcmp(a->deployment_id,b->deployment_id) && !strcmp(a->app_id,b->app_id) && !strcmp(a->sha256,b->sha256);
}
static bool duplicate_keys(const cJSON *node) {
    for (const cJSON *a = node->child; a; a = a->next) {
        if (cJSON_IsObject(node)) for (const cJSON *b = a->next; b; b = b->next)
            if (!strcmp(a->string,b->string)) return true;
        if (duplicate_keys(a)) return true;
    }
    return false;
}
static cJSON *protocol_json(const char *bytes, size_t size) {
    int depth = 0; bool quoted = false, escaped = false;
    if (!size || size > 4096 || memchr(bytes,0,size)) return NULL;
    for (size_t i = 0; i < size; ++i) {
        char c = bytes[i];
        if (quoted) {
            if (escaped) { if (c == 'u' && i+4 < size && !memcmp(bytes+i+1,"0000",4)) return NULL; escaped = false; }
            else if (c == '\\') escaped = true;
            else if (c == '"') quoted = false;
        } else if (c == '"') quoted = true;
        else if (c == '{' || c == '[') { if (++depth > 12) return NULL; }
        else if (c == '}' || c == ']') --depth;
    }
    if (depth || quoted) return NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(bytes,size+1,NULL,true);
    if (root && duplicate_keys(root)) { cJSON_Delete(root); return NULL; }
    return root;
}
static bool request(const char *path, const char *body, char *out, size_t cap, size_t *used) {
    char url[512], authorization[192];
    if (strncmp(CONFIG_SKETCH_BACKEND_URL,"https://",8) || strlen(CONFIG_SKETCH_BACKEND_URL) > 256 ||
        !token(CONFIG_SKETCH_DEVICE_TOKEN,128) || path[0] != '/' || strchr(path,'?') || strchr(path,'#')) return false;
    snprintf(url,sizeof(url),"%s%s",CONFIG_SKETCH_BACKEND_URL,path);
    snprintf(authorization,sizeof(authorization),"Bearer %s",CONFIG_SKETCH_DEVICE_TOKEN);
    esp_http_client_config_t cfg = {.url=url,.timeout_ms=8000,.disable_auto_redirect=true,
        .crt_bundle_attach=esp_crt_bundle_attach,.buffer_size=2048};
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return false;
    bool ok = false; *used = 0;
    const char *stage = "open";
    int status = 0;
    esp_http_client_set_header(client,"Authorization",authorization);
    esp_http_client_set_header(client,"Accept","application/json");
    size_t body_size = body ? strlen(body) : 0;
    if (body) {
        esp_http_client_set_method(client,HTTP_METHOD_POST);
        esp_http_client_set_header(client,"Content-Type","application/json");
    }
    if (esp_http_client_open(client,(int)body_size) != ESP_OK) goto done;
    stage = "write";
    for (size_t sent = 0; sent < body_size;) {
        int written = esp_http_client_write(client,body+sent,(int)(body_size-sent));
        if (written <= 0) goto done;
        sent += written;
    }
    stage = "headers";
    int64_t declared = esp_http_client_fetch_headers(client);
    status = esp_http_client_get_status_code(client);
    if (declared < 0 || declared > (int64_t)cap || status != 200) goto done;
    stage = "body";
    for (;;) {
        char extra;
        int count = esp_http_client_read(client,*used < cap ? out+*used : &extra,
                                        *used < cap ? (int)(cap-*used) : 1);
        if (count < 0 || (count > 0 && *used == cap)) goto done;
        if (count == 0) break;
        *used += count;
    }
    stage = "complete";
    if (!esp_http_client_is_complete_data_received(client)) goto done;
    out[*used] = 0; ok = true;
done:
    if (!ok) ESP_LOGW("device","http_failed stage=%s status=%d",stage,status);
    esp_http_client_close(client); esp_http_client_cleanup(client);
    return ok;
}
/* Returns 1 for a deployment, 0 for no desired package, -1 for an invalid/unavailable response. */
static int desired(deployment *out) {
    char bytes[4097]; size_t size;
    if (!request("/api/device/desired",NULL,bytes,4096,&size)) return -1;
    cJSON *root = protocol_json(bytes,size);
    int result = -1;
    if (!root || !cJSON_IsObject(root) || cJSON_GetArraySize(root) != 1) goto done;
    const cJSON *d = item(root,"desired");
    if (cJSON_IsNull(d)) { result = 0; goto done; }
    const cJSON *m = item(d,"manifest");
    if (!cJSON_IsObject(d) || cJSON_GetArraySize(d) != 3 || !cJSON_IsObject(m) || cJSON_GetArraySize(m) != 7 ||
        !token(string(d,"deployment_id"),128) || !number(item(d,"sequence"),1,9007199254740991.0) ||
        !app_id(string(m,"app_id")) || !number(item(m,"version"),1,INT32_MAX) ||
        !number(item(m,"schema_version"),1,1) || !number(item(m,"size_bytes"),1,AS_MAX_BYTES) ||
        !hash_valid(string(m,"sha256")) || !runtime_supported(string(m,"min_runtime_version"))) goto done;
    memset(out,0,sizeof(*out));
    strcpy(out->deployment_id,string(d,"deployment_id")); strcpy(out->app_id,string(m,"app_id"));
    strcpy(out->sha256,string(m,"sha256")); out->sequence = (int64_t)item(d,"sequence")->valuedouble;
    out->version = (int32_t)item(m,"version")->valuedouble; out->size = (uint32_t)item(m,"size_bytes")->valuedouble;
    snprintf(out->path,sizeof(out->path),"/api/apps/%s/versions/%" PRId32,out->app_id,out->version);
    if (!string(m,"download_path") || strcmp(out->path,string(m,"download_path"))) goto done;
    result = 1;
done:
    cJSON_Delete(root); return result;
}
/* Active receipt: 1 accepted, 0 explicitly stale, -1 unknown and retryable. */
static int ack(const deployment *d, const char *status, const char *error) {
    char body[768], response[4097]; size_t used;
    if (!token(CONFIG_SKETCH_DEVICE_ID,128)) return -1;
    snprintf(body,sizeof(body),"{\"device_id\":\"%s\",\"deployment_id\":\"%s\",\"sequence\":%" PRId64
        ",\"app_id\":\"%s\",\"version\":%" PRId32 ",\"sha256\":\"%s\",\"status\":\"%s\"%s%s%s}",
        CONFIG_SKETCH_DEVICE_ID,d->deployment_id,d->sequence,d->app_id,d->version,d->sha256,status,
        error ? ",\"error_code\":\"" : "",error ? error : "",error ? "\"" : "");
    if (!request("/api/device/ack",body,response,4096,&used)) return -1;
    if (strcmp(status,"active")) return 1;
    cJSON *root = protocol_json(response,used);
    int result = -1;
    if (root && cJSON_IsObject(root) && cJSON_GetArraySize(root) == 3 &&
        cJSON_IsBool(item(root,"recorded")) && cJSON_IsBool(item(root,"current_success")) &&
        string(root,"deployment_id") && !strcmp(string(root,"deployment_id"),d->deployment_id))
        result = cJSON_IsTrue(item(root,"current_success")) ? 1 : 0;
    cJSON_Delete(root); return result;
}
static bool save_metadata(void) {
    return nvs_set_blob(storage,"metadata",&metadata,sizeof(metadata)) == ESP_OK && nvs_commit(storage) == ESP_OK;
}
static as_app *read_slot(int slot) {
    if (slot < 0 || slot > 1) return NULL;
    const deployment *d = &metadata.slots[slot];
    if (!d->size || d->size > AS_MAX_BYTES || !hash_valid(d->sha256)) return NULL;
    char *bytes = malloc(d->size); as_app *app = calloc(1,sizeof(*app));
    size_t size = d->size; const char *error;
    if (!bytes || !app || nvs_get_blob(storage,slot ? "slot_b" : "slot_a",bytes,&size) != ESP_OK || size != d->size ||
        !digest_matches(bytes,size,d->sha256) || !as_parse(bytes,size,app,&error) ||
        strcmp(app->app_id,d->app_id) || app->version != d->version) { free(app); app = NULL; }
    free(bytes); return app;
}
static bool healthy_activate(as_app *app, bool *activated) {
    *activated = app_ui_activate(app);
    if (!*activated) return false;
    uint64_t before = app_ui_healthy_ticks();
    for (int i = 0; i < 30; ++i) {
        vTaskDelay(pdMS_TO_TICKS(100));
        if (app_ui_healthy_ticks() > before) return true;
    }
    return false;
}
static bool restore(void) {
    if (nvs_flash_init_partition("apps") != ESP_OK || nvs_open_from_partition("apps","install",NVS_READWRITE,&storage) != ESP_OK) return false;
    size_t length = sizeof(metadata);
    esp_err_t result = nvs_get_blob(storage,"metadata",&metadata,&length);
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        memset(&metadata,0,sizeof(metadata)); metadata.magic = META_MAGIC;
        metadata.active = metadata.previous = metadata.pending_slot = -1;
        return save_metadata();
    }
    if (result != ESP_OK || length != sizeof(metadata) || metadata.magic != META_MAGIC ||
        metadata.active < -1 || metadata.active > 1 || metadata.previous < -1 || metadata.previous > 1 ||
        metadata.pending < 0 || metadata.pending > 2 || metadata.pending_slot < -1 || metadata.pending_slot > 1 ||
        (metadata.pending == 1 && metadata.pending_slot < 0) ||
        !memchr(metadata.blocked_id,0,sizeof(metadata.blocked_id))) return false;
    for (int i = 0; i < 2; ++i) {
        deployment *d = &metadata.slots[i];
        if (!memchr(d->deployment_id,0,sizeof(d->deployment_id)) || !memchr(d->app_id,0,sizeof(d->app_id)) ||
            !memchr(d->sha256,0,sizeof(d->sha256)) || !memchr(d->path,0,sizeof(d->path))) return false;
        if (d->size && (!token(d->deployment_id,128) || !app_id(d->app_id) || !hash_valid(d->sha256) ||
            d->size > AS_MAX_BYTES || d->sequence <= 0 || d->version <= 0)) return false;
    }
    if (metadata.pending == 1 && metadata.pending_slot >= 0)
        snprintf(metadata.blocked_id,sizeof(metadata.blocked_id),"%s",metadata.slots[metadata.pending_slot].deployment_id);
    if (metadata.pending == 2) {
        if (metadata.active >= 0) snprintf(metadata.blocked_id,sizeof(metadata.blocked_id),"%s",metadata.slots[metadata.active].deployment_id);
        metadata.active = metadata.previous; metadata.previous = -1;
    }
    metadata.pending = 0; metadata.pending_slot = -1;
    if (!save_metadata()) return false;
    if (metadata.active < 0) return true;
    as_app *app = read_slot(metadata.active);
    if (!app) { metadata.active = metadata.previous; metadata.previous = -1; app = read_slot(metadata.active); }
    if (!app) { metadata.active = -1; return save_metadata(); }
    /* A reset while constructing this boot view falls back to the previous slot. */
    metadata.pending = 2;
    if (!save_metadata()) { free(app); return false; }
    bool activated;
    if (!healthy_activate(app,&activated)) {
        if (!activated || app_ui_activate(builtin_app)) free(app);
        return false;
    }
    installed_app = app; metadata.pending = 0;
    if (!save_metadata()) return false;
    app_ui_status("Restored app"); return true;
}
static void reject(const deployment *d, const char *error) {
    snprintf(metadata.blocked_id,sizeof(metadata.blocked_id),"%s",d->deployment_id);
    metadata.pending = 0; metadata.pending_slot = -1;
    save_metadata(); ack(d,"failed",error); app_ui_status("Install rejected; app kept");
}
static bool rollback_candidate(as_app *candidate) {
    if (app_ui_activate(installed_app ? installed_app : builtin_app)) { free(candidate); return true; }
    /* Retain the live model and pending record if even recovery rendering fails. */
    app_ui_status("Recovery required");
    vTaskDelete(NULL);
    return false;
}
static void install(const deployment *d) {
    if (metadata.active >= 0 && same(d,&metadata.slots[metadata.active])) {
        int receipt = ack(d,"active",NULL);
        app_ui_status(receipt == 1 ? "App running | online" : "App running | awaiting receipt");
        return;
    }
    if (!strcmp(d->deployment_id,metadata.blocked_id)) { ack(d,"failed","previous_activation_failed"); return; }
    if (metadata.active >= 0 && d->sequence < metadata.slots[metadata.active].sequence) return;
    if (metadata.active >= 0) {
        deployment *active = &metadata.slots[metadata.active];
        if (d->version == active->version && d->size == active->size && !strcmp(d->app_id,active->app_id) && !strcmp(d->sha256,active->sha256)) {
            deployment current, previous = *active;
            if (desired(&current) != 1 || !same(d,&current)) return;
            *active = *d;
            if (save_metadata()) {
                int receipt = ack(d,"active",NULL);
                app_ui_status(receipt == 1 ? "App running | online" : "App running | awaiting receipt");
            } else *active = previous;
            return;
        }
    }
    char *bytes = malloc(d->size+1);
    if (!bytes) { app_ui_status("Waiting for memory"); return; }
    size_t size; app_ui_status("Downloading app"); ack(d,"downloading",NULL);
    if (!request(d->path,NULL,bytes,d->size,&size)) { free(bytes); app_ui_status("Download interrupted"); return; }
    if (size != d->size || !digest_matches(bytes,size,d->sha256)) { free(bytes); reject(d,"package_integrity"); return; }
    app_ui_status("Checking app"); ack(d,"validating",NULL);
    as_app *candidate = calloc(1,sizeof(*candidate)); const char *error;
    if (!candidate) { free(bytes); return; }
    if (!as_parse(bytes,size,candidate,&error) || strcmp(candidate->app_id,d->app_id) || candidate->version != d->version) {
        free(bytes); free(candidate); reject(d,"package_invalid"); return;
    }
    int slot = metadata.active == 0 ? 1 : 0;
    /* Reusing the inactive slot destroys its old backup, so stop naming it as one. */
    if (metadata.previous == slot) {
        metadata.previous = -1;
        if (!save_metadata()) { free(bytes); free(candidate); return; }
    }
    esp_err_t written = nvs_set_blob(storage,slot ? "slot_b" : "slot_a",bytes,size);
    free(bytes);
    if (written != ESP_OK || nvs_commit(storage) != ESP_OK) { free(candidate); app_ui_status("Storage unavailable"); return; }
    metadata.slots[slot] = *d;
    as_app *reread = read_slot(slot);
    if (!reread) { free(candidate); reject(d,"storage_integrity"); return; }
    free(reread);
    deployment current;
    if (desired(&current) != 1 || !same(d,&current)) { free(candidate); app_ui_status("Waiting for current request"); return; }
    metadata.pending = 1; metadata.pending_slot = slot;
    if (!save_metadata()) { free(candidate); return; }
    ack(d,"activating",NULL); app_ui_status("Starting app");
    bool activated;
    if (!healthy_activate(candidate,&activated)) {
        if (activated) { if (!rollback_candidate(candidate)) return; } else free(candidate);
        reject(d,"view_activation"); return;
    }
    if (desired(&current) != 1 || !same(d,&current)) {
        if (!rollback_candidate(candidate)) return;
        metadata.pending = 0; metadata.pending_slot = -1; save_metadata(); return;
    }
    int previous = metadata.active;
    /* Persist a coherent active package before reporting it to the backend. */
    metadata.active = slot; metadata.previous = previous; metadata.pending = 0; metadata.pending_slot = -1;
    if (!save_metadata()) {
        metadata.active = previous; metadata.previous = -1;
        rollback_candidate(candidate); return;
    }
    int receipt;
    while ((receipt = ack(d,"active",NULL)) < 0) {
        app_ui_status("Running | awaiting receipt");
        if (!(xEventGroupGetBits(connectivity) & CONNECTED)) {
            esp_wifi_connect();
            xEventGroupWaitBits(connectivity,CONNECTED,pdFALSE,pdTRUE,pdMS_TO_TICKS(5000));
        }
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    if (!receipt) {
        /* After an explicit stale receipt, a reset during rollback recovers the old slot. */
        metadata.pending = 2;
        save_metadata();
        snprintf(metadata.blocked_id,sizeof(metadata.blocked_id),"%s",d->deployment_id);
        metadata.active = previous; metadata.previous = -1; metadata.pending = 0;
        bool saved = save_metadata();
        if (!rollback_candidate(candidate)) return;
        app_ui_status(saved ? "New request pending" : "Recovery storage unavailable");
        if (!saved) vTaskDelete(NULL);
        return;
    }
    free(installed_app); installed_app = candidate;
    app_ui_status("App running");
}
static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)data;
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(connectivity,CONNECTED); ESP_LOGI("device","wifi_ip_ready");
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(connectivity,CONNECTED); ESP_LOGW("device","wifi_disconnected");
    }
}
static bool wifi_start(void) {
    if (!*CONFIG_SKETCH_WIFI_SSID || strlen(CONFIG_SKETCH_WIFI_SSID) > 32 || strlen(CONFIG_SKETCH_WIFI_PASSWORD) > 64) return false;
    connectivity = xEventGroupCreate();
    if (!connectivity || esp_netif_init() != ESP_OK || esp_event_loop_create_default() != ESP_OK || !esp_netif_create_default_wifi_sta()) return false;
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&cfg) != ESP_OK ||
        esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,NULL) != ESP_OK ||
        esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,NULL) != ESP_OK) return false;
    wifi_config_t wifi = {0};
    memcpy(wifi.sta.ssid,CONFIG_SKETCH_WIFI_SSID,strlen(CONFIG_SKETCH_WIFI_SSID));
    memcpy(wifi.sta.password,CONFIG_SKETCH_WIFI_PASSWORD,strlen(CONFIG_SKETCH_WIFI_PASSWORD));
    wifi.sta.threshold.authmode = *CONFIG_SKETCH_WIFI_PASSWORD ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    return esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK && esp_wifi_set_config(WIFI_IF_STA,&wifi) == ESP_OK && esp_wifi_start() == ESP_OK;
}
static bool seed_clock(void) {
    if (time(NULL) >= (time_t)SKETCH_BUILD_EPOCH) {
        ESP_LOGI("device","clock_source=rtc");
        return true;
    }
    /* A trusted local build supplies a lower bound; SNTP remains enabled. */
    struct timeval anchor = {.tv_sec=(time_t)SKETCH_BUILD_EPOCH,.tv_usec=0};
    if (settimeofday(&anchor,NULL) != 0) {
        ESP_LOGW("device","clock_anchor_failed");
        return false;
    }
    ESP_LOGI("device","clock_source=build_anchor");
    return true;
}
static void delivery(void *arg) {
    (void)arg;
    if (!restore()) { app_ui_status("Recovery storage unavailable"); vTaskDelete(NULL); return; }
    if (!*CONFIG_SKETCH_BACKEND_URL || !*CONFIG_SKETCH_DEVICE_TOKEN || !*CONFIG_SKETCH_DEVICE_ID) {
        app_ui_status("Ready | setup needed"); vTaskDelete(NULL); return;
    }
    if (!wifi_start()) { app_ui_status("Wi-Fi unavailable"); vTaskDelete(NULL); return; }
    seed_clock();
    bool sntp = false;
    unsigned clock_reports = 0;
    for (;;) {
        if (!(xEventGroupGetBits(connectivity) & CONNECTED)) {
            app_ui_status("Connecting Wi-Fi"); esp_wifi_connect();
            xEventGroupWaitBits(connectivity,CONNECTED,pdFALSE,pdTRUE,pdMS_TO_TICKS(5000));
        } else {
            if (!sntp) {
                esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
                esp_err_t result = esp_netif_sntp_init(&config);
                sntp = result == ESP_OK;
                ESP_LOGI("device","sntp_init_result=%d",result);
            }
            bool clock_valid = time(NULL) >= 1700000000;
            if (!(clock_reports++ % 5)) {
                unsigned reachability = 0;
                esp_err_t reach_result = esp_netif_sntp_reachability(0,&reachability);
                ESP_LOGI("device","clock_valid=%d sntp_started=%d reach=%u reach_result=%d",
                         clock_valid,sntp,reachability,reach_result);
            }
            if (!clock_valid) app_ui_status("Waiting for secure clock");
            else {
                deployment d; int result = desired(&d);
                if (result == 1) install(&d);
                else if (result == 0) app_ui_status(metadata.active >= 0 ? "App running | online" : "Ready | connected");
                else app_ui_status("Backend unavailable");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
bool app_delivery_start(const as_app *builtin) {
    builtin_app = builtin;
    return xTaskCreate(delivery,"app_delivery",12288,NULL,4,NULL) == pdPASS;
}
