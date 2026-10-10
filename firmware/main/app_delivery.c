#include "app_delivery.h"
#include "app_ui.h"
#include "app_recovery.h"
#ifdef APP_DELIVERY_HOST_TEST
#include "delivery_port.h"
#else
#include "esp_app_desc.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
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
#endif
#include "cJSON.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#define META_MAGIC 0x534B4431u
#define CONNECTED BIT0
static install_metadata metadata;
static nvs_handle_t storage;
static EventGroupHandle_t connectivity;
static const as_app *builtin_app;
static recovery_journal journal;
static app_ui_ticket slot_tickets[2], builtin_ticket;
static char boot_id[33];
static bool storage_halted, boot_complete;
static uint64_t next_network_ms, next_capability_ms;
_Static_assert(sizeof(deployment)==424 && sizeof(install_metadata)==1008,
               "Legacy NVS metadata ABI changed");

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
    return version && (!strcmp(version,"0.1.0") || !strcmp(version,"0.2.0") || !strcmp(version,"0.3.0"));
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
/* Bound successful trickle loops as well as socket stalls. The ESP client's
 * synchronous resolver/open call still owns its internal preemption behavior. */
static bool request_budget(esp_http_client_handle_t client,int64_t deadline) {
    int64_t remaining=deadline-esp_timer_get_time();
    return remaining>0 && esp_http_client_set_timeout_ms(client,(int)((remaining+999)/1000))==ESP_OK;
}
static bool request(const char *path, const char *body, char *out, size_t cap, size_t *used) {
    int64_t deadline=esp_timer_get_time()+8000000;
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
    if (!request_budget(client,deadline) || esp_http_client_open(client,(int)body_size) != ESP_OK ||
        esp_timer_get_time()>=deadline) goto done;
    stage = "write";
    for (size_t sent = 0; sent < body_size;) {
        if(!request_budget(client,deadline))goto done;
        int written = esp_http_client_write(client,body+sent,(int)(body_size-sent));
        if (written <= 0 || esp_timer_get_time()>=deadline) goto done;
        sent += written;
    }
    stage = "headers";
    if(!request_budget(client,deadline))goto done;
    int64_t declared = esp_http_client_fetch_headers(client);
    status = esp_http_client_get_status_code(client);
    if (declared < 0 || declared > (int64_t)cap || status != 200 || esp_timer_get_time()>=deadline) goto done;
    stage = "body";
    for (;;) {
        char extra;
        if(!request_budget(client,deadline))goto done;
        int count = esp_http_client_read(client,*used < cap ? out+*used : &extra,
                                        *used < cap ? (int)(cap-*used) : 1);
        if (count < 0 || (count > 0 && *used == cap) || esp_timer_get_time()>=deadline) goto done;
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
static int desired_schema;
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
        !number(item(m,"schema_version"),1,2) || !number(item(m,"size_bytes"),1,AS_MAX_BYTES) ||
        !hash_valid(string(m,"sha256")) || !runtime_supported(string(m,"min_runtime_version"))) goto done;
    int schema = item(m,"schema_version")->valueint;
    if (schema == 2 && strcmp(string(m,"min_runtime_version"),"0.3.0")) goto done;
    desired_schema = schema;
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
/* Active receipt: 1 latest intent or exact healthy active identity confirmed,
 * 0 explicitly stale, -1 unknown and retryable. Legacy three-field replies
 * remain supported; an additive confirmation never overrides identity checks. */
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
    const cJSON *confirmed=item(root,"active_confirmed");
    int fields=root?cJSON_GetArraySize(root):0;
    if (root && cJSON_IsObject(root) &&
        ((fields==3 && !confirmed) || (fields==4 && cJSON_IsBool(confirmed))) &&
        cJSON_IsBool(item(root,"recorded")) && cJSON_IsBool(item(root,"current_success")) &&
        string(root,"deployment_id") && !strcmp(string(root,"deployment_id"),d->deployment_id))
        result = cJSON_IsTrue(item(root,"current_success")) || cJSON_IsTrue(confirmed) ? 1 : 0;
    cJSON_Delete(root); return result;
}
static bool persist_blob(const char *key,const void *bytes,size_t size) {
    if(storage_halted)return false;
    if(nvs_set_blob(storage,key,bytes,size)!=ESP_OK || nvs_commit(storage)!=ESP_OK) {
        storage_halted=true;app_ui_status("Recovery storage unavailable");return false;
    }
    return true;
}
static bool save_metadata(void){return persist_blob("metadata",&metadata,sizeof(metadata));}
static bool save_journal(void){return persist_blob("recovery_v1",&journal,sizeof(journal));}
static bool terminated(const char *s,size_t size){return memchr(s,0,size)!=NULL;}
static bool valid_deployment(const deployment *d) {
    return terminated(d->deployment_id,sizeof(d->deployment_id)) && terminated(d->app_id,sizeof(d->app_id)) &&
        terminated(d->sha256,sizeof(d->sha256)) && terminated(d->path,sizeof(d->path)) &&
        token(d->deployment_id,128) && app_id(d->app_id) && hash_valid(d->sha256) &&
        d->size && d->size<=AS_MAX_BYTES && d->sequence>0 && d->sequence<=9007199254740991LL && d->version>0;
}
static bool quarantined(int slot) {
    return slot<0 || slot>1 || !valid_deployment(&metadata.slots[slot]) ||
        !strcmp(journal.failed_ids[slot],metadata.slots[slot].deployment_id);
}
static app_package *read_slot(int slot) {
    if(slot<0 || slot>1 || !valid_deployment(&metadata.slots[slot]))return NULL;
    const deployment *d=&metadata.slots[slot];char *bytes=malloc(d->size);if(!bytes)return NULL;
    size_t size=d->size;app_package *package=NULL;const char *error;
    if(nvs_get_blob(storage,slot?"slot_b":"slot_a",bytes,&size)==ESP_OK && size==d->size && digest_matches(bytes,size,d->sha256))
        package=app_package_parse(bytes,size,&error);
    free(bytes);
    if(package && (strcmp(package->app_id,d->app_id) || package->version!=d->version)){app_package_free(package);package=NULL;}
    return package;
}
static bool load_journal(void) {
    size_t size=sizeof(journal);esp_err_t result=nvs_get_blob(storage,"recovery_v1",&journal,&size);
    if(result==ESP_ERR_NVS_NOT_FOUND) {
        memset(&journal,0,sizeof(journal));journal.magic=RECOVERY_MAGIC;journal.version=RECOVERY_VERSION;
        journal.next_sequence=1;journal.ack_slot=-1;
        for(int i=0;i<2;i++)if(metadata.slots[i].size && !strcmp(metadata.blocked_id,metadata.slots[i].deployment_id)) {
            strcpy(journal.failed_ids[i],metadata.blocked_id);journal.quarantine_through=metadata.slots[i].sequence;
        }
        return save_journal();
    }
    if(result!=ESP_OK || size!=sizeof(journal) || journal.magic!=RECOVERY_MAGIC || journal.version!=RECOVERY_VERSION ||
       journal.count>2 || !journal.next_sequence || journal.next_sequence>9007199254740991ULL || journal.quarantine_through<0 ||
       journal.ack_slot< -1 || journal.ack_slot>1 || !terminated(journal.ack_id,sizeof(journal.ack_id)))return false;
    for(int i=0;i<2;i++)if(!terminated(journal.failed_ids[i],sizeof(journal.failed_ids[i])))return false;
    if(journal.ack_slot>=0 && !token(journal.ack_id,128))return false;
    for(unsigned i=0;i<journal.count;i++) {
        recovery_record *r=&journal.records[i];
        if((r->stage!=RECOVERY_INTENT && r->stage!=RECOVERY_READY) ||
           (r->stage==RECOVERY_INTENT && i+1!=journal.count) || r->error<RECOVERY_RUNTIME || r->error>RECOVERY_FAILED ||
           r->failed_slot<0 || r->failed_slot>1 || r->recovered_slot< -1 || r->recovered_slot>1 ||
           !r->sequence || r->sequence>=journal.next_sequence ||
           (i && r->sequence!=journal.records[i-1].sequence+1) ||
           !terminated(r->report_id,sizeof(r->report_id)) || !token(r->report_id,64) || !valid_deployment(&r->failed) ||
           (r->recovered_slot>=0 && !valid_deployment(&r->recovered)))return false;
    }
    return true;
}
static recovery_record *intent(void) {
    if(journal.count && journal.records[journal.count-1].stage==RECOVERY_INTENT)return &journal.records[journal.count-1];
    return NULL;
}
static const char *diagnostic_error(const char *value) {
    static const char *const names[]={"allocation_failed","native_memory_admission","view_activation",
        "display_lock","runtime_recovery_pending","invalid_ui_transition","previous_app_fault",
        "activation_checkpoint","recovery_candidate_invalid","execution_budget","microtask_budget",
        "unhandled_rejection","drawing_budget","script_exception","invalid_event","view_render",
        "allocation_or_program_error","invalid_program","runtime_failure"};
    if(!value || !*value)return "none";
    for(size_t i=0;i<sizeof(names)/sizeof(names[0]);i++)if(!strcmp(value,names[i]))return names[i];
    return "unclassified";
}
static bool begin_recovery(int failed_slot,int fallback,recovery_error error) {
    if(intent())return true;
    if(journal.count==2 || journal.next_sequence>=9007199254740991ULL || failed_slot<0 || failed_slot>1 || !valid_deployment(&metadata.slots[failed_slot]))return false;
    app_ui_state observed;app_ui_snapshot(&observed);
    ESP_LOGW("device","recovery_start reason=%u pending=%d op=%d succeeded=%d error=%s fault=%s stack=%" PRIu32 " internal=%zu largest=%zu external=%zu",
        (unsigned)error,metadata.pending,(int)observed.operation,(int)observed.succeeded,
        diagnostic_error(observed.error),diagnostic_error(observed.fault),observed.owner_stack_free_bytes,
        observed.internal_free_bytes,observed.internal_largest_bytes,observed.external_free_bytes);
    if(quarantined(fallback) || fallback==failed_slot)fallback=-1;
    recovery_record *r=&journal.records[journal.count++];memset(r,0,sizeof(*r));
    r->sequence=journal.next_sequence++;r->stage=RECOVERY_INTENT;r->error=error;
    snprintf(r->report_id,sizeof(r->report_id),"r_%s_%" PRIu64,boot_id,r->sequence);
    r->failed_slot=failed_slot;r->failed=metadata.slots[failed_slot];r->recovered_slot=fallback;
    if(fallback>=0)r->recovered=metadata.slots[fallback];
    strcpy(journal.failed_ids[failed_slot],r->failed.deployment_id);
    if(r->failed.sequence>journal.quarantine_through)journal.quarantine_through=r->failed.sequence;
    journal.ack_slot=-1;journal.ack_id[0]=0;
    /* One durable key records intent, quarantine and ACK cancellation before
     * any UI or active-pointer change. Never infer a multi-key atomic commit. */
    return save_journal();
}
static const char *recovery_error_name(unsigned error) {
    return error==RECOVERY_RUNTIME?"runtime_error":error==RECOVERY_ACTIVATION?"activation_failed":"recovery_failed";
}
static cJSON *identity_json(const deployment *d) {
    cJSON *o=cJSON_CreateObject();if(!o)return NULL;
    cJSON_AddStringToObject(o,"deployment_id",d->deployment_id);cJSON_AddNumberToObject(o,"sequence",(double)d->sequence);
    cJSON_AddStringToObject(o,"app_id",d->app_id);cJSON_AddNumberToObject(o,"version",d->version);
    cJSON_AddStringToObject(o,"sha256",d->sha256);return o;
}
static bool send_recovery(void) {
    if(!journal.count || journal.records[0].stage!=RECOVERY_READY)return false;
    recovery_record *r=&journal.records[0];cJSON *body=cJSON_CreateObject();if(!body)return false;
    cJSON_AddNumberToObject(body,"protocol_version",1);cJSON_AddStringToObject(body,"report_id",r->report_id);
    cJSON_AddNumberToObject(body,"recovery_seq",(double)r->sequence);cJSON_AddItemToObject(body,"failed",identity_json(&r->failed));
    cJSON_AddItemToObject(body,"recovered",r->recovered_slot>=0?identity_json(&r->recovered):cJSON_CreateNull());
    cJSON_AddStringToObject(body,"error_code",recovery_error_name(r->error));
    char *encoded=cJSON_PrintUnformatted(body);cJSON_Delete(body);if(!encoded)return false;
    char response[4097];size_t size;bool sent=request("/api/device/recovery",encoded,response,4096,&size);free(encoded);
    if(!sent)return false;
    cJSON *reply=protocol_json(response,size);
    bool matched=reply && cJSON_IsObject(reply) && cJSON_GetArraySize(reply)==4 &&
        string(reply,"report_id") && !strcmp(string(reply,"report_id"),r->report_id) &&
        number(item(reply,"recovery_seq"),1,9007199254740991.0) && (uint64_t)item(reply,"recovery_seq")->valuedouble==r->sequence &&
        cJSON_IsBool(item(reply,"recorded")) && cJSON_IsBool(item(reply,"applied"));
    cJSON_Delete(reply);if(!matched)return false;
    /* recorded=false is the successful duplicate after a lost first response. */
    if(journal.count==2)journal.records[0]=journal.records[1];
    memset(&journal.records[--journal.count],0,sizeof(journal.records[0]));
    return save_journal();
}
static bool report_capabilities(void) {
    const esp_app_desc_t *description=esp_app_get_description();char hash[65];
    for(int i=0;i<32;i++)snprintf(hash+2*i,3,"%02x",description->app_elf_sha256[i]);
    char body[768],response[4097];size_t size;
    if(!token(CONFIG_SKETCH_DEVICE_ID,128))return false;
    snprintf(body,sizeof(body),"{\"protocol_version\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"runtime_version\":\"0.3.0\",\"schema_versions\":[1,2],\"engine\":\"quickjs-ng-0.14.0\","
        "\"sdk\":\"device-js-1\",\"profile\":\"p4-canvas-1\",\"modules\":[\"canvas\",\"input\",\"time\"],"
        "\"viewport\":{\"width\":320,\"height\":432},\"firmware_elf_sha256\":\"%s\"}",CONFIG_SKETCH_DEVICE_ID,boot_id,hash);
    if(!request("/api/device/runtime",body,response,4096,&size))return false;
    cJSON *reply=protocol_json(response,size);bool ok=reply && cJSON_IsObject(reply) && cJSON_GetArraySize(reply)==1 && cJSON_IsTrue(item(reply,"recorded"));
    cJSON_Delete(reply);return ok;
}

typedef enum { FLOW_NONE,FLOW_PREPARE,FLOW_READY,FLOW_ACTIVATE,FLOW_ACTIVE,FLOW_COMMIT,FLOW_ABORT,FLOW_RETAIN,FLOW_ROLLBACK } flow_stage;
typedef enum { FLOW_INSTALL,FLOW_BOOT,FLOW_RECOVERY } flow_kind;
typedef struct {
    flow_stage stage;flow_kind kind;int slot,old_active;app_ui_ticket ticket,failed_ticket;
    deployment deployment;bool reconstruct,retained;
} install_flow;
static install_flow flow;
static int ticket_slot(app_ui_ticket ticket) {
    for(int i=0;i<2;i++)if(ticket && slot_tickets[i]==ticket)return i;
    return -1;
}
static bool ui_finished(const app_ui_state *s,app_ui_operation op,app_ui_ticket ticket) {
    return !s->pending && s->operation==op && s->operation_ticket==ticket;
}
static bool begin_prepare(app_package *package,int slot,flow_kind kind,bool reconstruct) {
    app_ui_ticket ticket;
    bool accepted=reconstruct?app_ui_prepare_recovery(package,&ticket):app_ui_prepare(package,&ticket);
    if(!accepted){app_package_free(package);return false;}
    flow=(install_flow){.stage=FLOW_PREPARE,.kind=kind,.slot=slot,.old_active=metadata.active,.ticket=ticket,.reconstruct=reconstruct};
    if(slot>=0)flow.deployment=metadata.slots[slot];
    return true;
}
static bool recovery_to_builtin(recovery_record *r) {
    if(r->recovered_slot>=0) {
        int failed=r->recovered_slot;strcpy(journal.failed_ids[failed],r->recovered.deployment_id);
        if(r->recovered.sequence>journal.quarantine_through)journal.quarantine_through=r->recovered.sequence;
    }
    r->recovered_slot=-1;memset(&r->recovered,0,sizeof(r->recovered));r->error=RECOVERY_FAILED;
    return save_journal();
}
static bool finish_recovery(const app_ui_state *s,app_ui_ticket expected) {
    recovery_record *r=intent();if(!r || s->live!=expected)return false;
    metadata.active=r->recovered_slot;metadata.previous=-1;metadata.pending=0;metadata.pending_slot=-1;
    strcpy(metadata.blocked_id,r->failed.deployment_id);
    if(!save_metadata())return false;
    if(r->recovered_slot>=0)slot_tickets[r->recovered_slot]=expected;else builtin_ticket=expected;
    r->stage=RECOVERY_READY;
    if(!save_journal())return false;
    /* Only a durable actual fallback/report releases the owner's sticky fault. */
    if(s->fault_ticket && s->fault_ticket!=expected && !app_ui_ack_fault(s->fault_ticket))return false;
    flow=(install_flow){0};boot_complete=true;app_ui_status("Previous app recovered");return true;
}
static void recover_step(app_ui_state s) {
    recovery_record *r=intent();if(!r)return;
    if(s.pending)return;
    if(flow.kind!=FLOW_RECOVERY && flow.stage!=FLOW_NONE) {
        if(s.prepared){app_ui_request(APP_UI_ABORT,s.prepared);return;}
        flow=(install_flow){0};
    }
    if(flow.stage==FLOW_NONE) {
        int target=r->recovered_slot;
        app_ui_ticket wanted=target>=0?slot_tickets[target]:builtin_ticket;
        if(wanted && s.live==wanted && !s.fault_ticket) {finish_recovery(&s,wanted);return;}
        if(wanted && s.previous==wanted) {
            flow=(install_flow){.stage=FLOW_ROLLBACK,.kind=FLOW_RECOVERY,.slot=target,.ticket=wanted,.failed_ticket=s.live};
            if(!app_ui_request(APP_UI_ROLLBACK,s.live))flow.stage=FLOW_NONE;
            return;
        }
        app_package *package=target>=0?read_slot(target):app_package_copy_legacy(builtin_app);
        if(!package) {if(target>=0)recovery_to_builtin(r);else storage_halted=true;return;}
        bool reconstruct=s.fault_ticket==s.live && s.fault_ticket;
        if(begin_prepare(package,target,FLOW_RECOVERY,reconstruct))flow.failed_ticket=s.live;
        return;
    }
    if(flow.stage==FLOW_PREPARE && ui_finished(&s,flow.reconstruct?APP_UI_PREPARE_RECOVERY:APP_UI_PREPARE,flow.ticket)) {
        if(!s.succeeded) {flow=(install_flow){0};if(r->recovered_slot>=0)recovery_to_builtin(r);else storage_halted=true;return;}
        app_ui_operation op=flow.reconstruct?APP_UI_RETAIN_PREVIOUS:APP_UI_ACTIVATE;
        if(app_ui_request(op,flow.ticket))flow.stage=flow.reconstruct?FLOW_RETAIN:FLOW_ACTIVATE;
    } else if(flow.stage==FLOW_RETAIN && ui_finished(&s,APP_UI_RETAIN_PREVIOUS,flow.ticket)) {
        if(!s.succeeded) {if(app_ui_request(APP_UI_ABORT,flow.ticket))flow.stage=FLOW_ABORT;
            return;}
        if(app_ui_request(APP_UI_ROLLBACK,flow.failed_ticket))flow.stage=FLOW_ROLLBACK;
    } else if(flow.stage==FLOW_ABORT && ui_finished(&s,APP_UI_ABORT,flow.ticket)) {
        flow=(install_flow){0};if(r->recovered_slot>=0)recovery_to_builtin(r);else storage_halted=true;
    } else if(flow.stage==FLOW_ROLLBACK && ui_finished(&s,APP_UI_ROLLBACK,flow.failed_ticket)) {
        if(!s.succeeded || s.live!=flow.ticket) {storage_halted=true;app_ui_status("Recovery required");return;}
        finish_recovery(&s,flow.ticket);
    } else if(flow.stage==FLOW_ACTIVATE && ui_finished(&s,APP_UI_ACTIVATE,flow.ticket)) {
        if(!s.succeeded) {if(s.prepared)app_ui_request(APP_UI_ABORT,s.prepared);flow.stage=FLOW_ABORT;return;}
        /* Durable selection precedes COMMIT; no network success is required. */
        metadata.active=r->recovered_slot;metadata.previous=-1;metadata.pending=0;metadata.pending_slot=-1;
        strcpy(metadata.blocked_id,r->failed.deployment_id);
        if(save_metadata() && app_ui_request(APP_UI_COMMIT,flow.ticket))flow.stage=FLOW_COMMIT;
    } else if(flow.stage==FLOW_COMMIT && ui_finished(&s,APP_UI_COMMIT,flow.ticket)) {
        if(!s.succeeded && s.fault_ticket!=flow.ticket){storage_halted=true;return;}
        /* A fallback can pass activation, then fail before COMMIT. Record the
         * real A-to-B transition; the next local step journals B-to-built-in. */
        finish_recovery(&s,flow.ticket);
    }
}
static bool initialize_storage(void) {
    if(nvs_flash_init_partition("apps")!=ESP_OK || nvs_open_from_partition("apps","install",NVS_READWRITE,&storage)!=ESP_OK)return false;
    size_t size=sizeof(metadata);esp_err_t result=nvs_get_blob(storage,"metadata",&metadata,&size);
    if(result==ESP_ERR_NVS_NOT_FOUND) {
        memset(&metadata,0,sizeof(metadata));metadata.magic=META_MAGIC;
        metadata.active=metadata.previous=metadata.pending_slot=-1;
        if(!save_metadata())return false;
    } else {
        if(result!=ESP_OK || size!=sizeof(metadata) || metadata.magic!=META_MAGIC ||
           metadata.active< -1 || metadata.active>1 || metadata.previous< -1 || metadata.previous>1 ||
           metadata.pending<0 || metadata.pending>2 || metadata.pending_slot< -1 || metadata.pending_slot>1 ||
           (metadata.pending==1 && metadata.pending_slot<0) || !terminated(metadata.blocked_id,sizeof(metadata.blocked_id)))return false;
        for(int i=0;i<2;i++)if(metadata.slots[i].size && !valid_deployment(&metadata.slots[i]))return false;
    }
    return load_journal();
}
static bool start_boot_restore(void) {
    if(intent())return true;
    if(metadata.pending==1)return begin_recovery(metadata.pending_slot,metadata.active,RECOVERY_ACTIVATION);
    if(metadata.pending==2 && metadata.active>=0)return begin_recovery(metadata.active,metadata.previous,RECOVERY_ACTIVATION);
    if(metadata.active<0){boot_complete=true;return true;}
    int slot=metadata.active;app_package *package=read_slot(slot);
    if(!package)return begin_recovery(slot,metadata.previous,RECOVERY_FAILED);
    esp_reset_reason_t reason=esp_reset_reason();
    bool crash=reason==ESP_RST_PANIC || reason==ESP_RST_INT_WDT || reason==ESP_RST_TASK_WDT ||
        reason==ESP_RST_WDT || reason==ESP_RST_CPU_LOCKUP;
    if(quarantined(slot) || (crash && package->kind==APP_PACKAGE_PROGRAM)) {
        app_package_free(package);return begin_recovery(slot,metadata.previous,RECOVERY_RUNTIME);
    }
    metadata.pending=2;
    if(!save_metadata()){app_package_free(package);return false;}
    return begin_prepare(package,slot,FLOW_BOOT,false);
}
static bool restore(void) {
    app_ui_state s;app_ui_snapshot(&s);builtin_ticket=s.live;
    return initialize_storage() && start_boot_restore();
}
static bool finalize_activation(void) {
    if(flow.kind==FLOW_INSTALL || (flow.kind==FLOW_BOOT && !journal.count)) {
        journal.ack_slot=flow.slot;strcpy(journal.ack_id,flow.deployment.deployment_id);
        if(!save_journal())return false;
    }
    if(flow.kind==FLOW_INSTALL) {
        /* This key lands before clearing the old metadata activation guard.
         * Either crash order retains an explicit installation/recovery state. */
        metadata.active=flow.slot;metadata.previous=flow.old_active;
    }
    metadata.pending=0;metadata.pending_slot=-1;
    if(!save_metadata())return false;
    if(app_ui_request(APP_UI_COMMIT,flow.ticket)){flow.stage=FLOW_COMMIT;return true;}
    return false;
}
static void installation_local(app_ui_state s) {
    if(flow.kind==FLOW_RECOVERY || flow.stage==FLOW_NONE || s.pending)return;
    if(flow.stage==FLOW_PREPARE && ui_finished(&s,APP_UI_PREPARE,flow.ticket)) {
        if(!s.succeeded){begin_recovery(flow.slot,flow.old_active==flow.slot?metadata.previous:flow.old_active,RECOVERY_ACTIVATION);return;}
        if(flow.kind==FLOW_BOOT) {
            slot_tickets[flow.slot]=flow.ticket;
            if(app_ui_request(APP_UI_ACTIVATE,flow.ticket))flow.stage=FLOW_ACTIVATE;
        } else flow.stage=FLOW_READY;
    } else if(flow.stage==FLOW_ACTIVATE && ui_finished(&s,APP_UI_ACTIVATE,flow.ticket)) {
        if(!s.succeeded || s.live!=flow.ticket || s.checkpoint_ticket!=flow.ticket) {
            begin_recovery(flow.slot,flow.old_active==flow.slot?metadata.previous:flow.old_active,RECOVERY_ACTIVATION);return;
        }
        if(flow.kind==FLOW_BOOT)finalize_activation();else flow.stage=FLOW_ACTIVE;
    } else if(flow.stage==FLOW_COMMIT && ui_finished(&s,APP_UI_COMMIT,flow.ticket)) {
        if(!s.succeeded || s.live!=flow.ticket){begin_recovery(flow.slot,metadata.previous,RECOVERY_ACTIVATION);return;}
        ESP_LOGI("device","runtime_health stack=%" PRIu32 " internal=%zu largest=%zu external=%zu checkpoints=%" PRIu64,
            s.owner_stack_free_bytes,s.internal_free_bytes,s.internal_largest_bytes,s.external_free_bytes,s.checkpoints);
        slot_tickets[flow.slot]=flow.ticket;flow=(install_flow){0};boot_complete=true;app_ui_status("App running | awaiting receipt");
    } else if(flow.stage==FLOW_ABORT && ui_finished(&s,APP_UI_ABORT,flow.ticket)) {
        metadata.pending=0;metadata.pending_slot=-1;
        if(save_metadata())flow=(install_flow){0};
    }
}
static void local_step(void) {
    if(storage_halted)return;
    app_ui_state s;app_ui_snapshot(&s);
    if(!intent() && s.fault_ticket) {
        int failed=ticket_slot(s.fault_ticket);
        if(failed<0){app_ui_status("Recovery required");return;}
        int fallback=failed==metadata.active?metadata.previous:metadata.active;
        if(!begin_recovery(failed,fallback,RECOVERY_RUNTIME)) {
            app_ui_status("Recovery queued; app stopped");return;
        }
    }
    if(intent()){recover_step(s);return;}
    installation_local(s);
}
static void reject(const deployment *d,const char *error) {
    strcpy(metadata.blocked_id,d->deployment_id);metadata.pending=0;metadata.pending_slot=-1;
    if(save_metadata())ack(d,"failed",error);
    app_ui_status("Install rejected; app kept");
}
static void install(const deployment *d) {
    if(storage_halted || !boot_complete || flow.stage!=FLOW_NONE || journal.count || journal.ack_slot>=0)return;
    if(d->sequence<=journal.quarantine_through || !strcmp(d->deployment_id,metadata.blocked_id))return;
    if(metadata.active>=0 && same(d,&metadata.slots[metadata.active])) {
        return;
    }
    if(metadata.active>=0 && d->sequence<metadata.slots[metadata.active].sequence)return;
    char *bytes=malloc(d->size+1);if(!bytes)return;
    size_t size=0;app_ui_status("Downloading app");
    if(!request(d->path,NULL,bytes,d->size,&size)){free(bytes);return;}
    if(size!=d->size || !digest_matches(bytes,size,d->sha256)){free(bytes);reject(d,"package_integrity");return;}
    const char *error;app_package *package=app_package_parse(bytes,size,&error);
    if(!package || (int)package->kind!=desired_schema || strcmp(package->app_id,d->app_id) || package->version!=d->version) {
        free(bytes);app_package_free(package);reject(d,"package_invalid");return;
    }
    int slot=metadata.active==0?1:0;
    if(metadata.previous==slot) {
        metadata.previous=-1;
        if(!save_metadata()){free(bytes);app_package_free(package);return;}
    }
    slot_tickets[slot]=0;
    if(!persist_blob(slot?"slot_b":"slot_a",bytes,size)){free(bytes);app_package_free(package);return;}
    free(bytes);metadata.slots[slot]=*d;
    app_package *reread=read_slot(slot);
    if(!reread){app_package_free(package);reject(d,"storage_integrity");return;}
    app_package_free(reread);
    if(!save_metadata()){app_package_free(package);return;}
    app_ui_status("Checking app");
    begin_prepare(package,slot,FLOW_INSTALL,false);
}
static void network_step(void) {
    if(storage_halted)return;
    uint64_t now=(uint64_t)esp_timer_get_time()/1000;
    if(now<next_network_ms)return;
    next_network_ms=now+2000;
    if(now>=next_capability_ms) {
        next_capability_ms=now+10000;report_capabilities();return;
    }
    if(journal.count && journal.records[0].stage==RECOVERY_READY){send_recovery();return;}
    if(intent() || !boot_complete)return;
    app_ui_state s;app_ui_snapshot(&s);if(s.fault_ticket)return;
    if(flow.stage==FLOW_READY) {
        deployment current;
        if(desired(&current)!=1 || !same(&current,&flow.deployment)) {
            if(app_ui_request(APP_UI_ABORT,flow.ticket))flow.stage=FLOW_ABORT;
            return;
        }
        metadata.pending=1;metadata.pending_slot=flow.slot;
        if(!save_metadata())return;
        slot_tickets[flow.slot]=flow.ticket;
        ack(&flow.deployment,"activating",NULL);
        if(app_ui_request(APP_UI_ACTIVATE,flow.ticket))flow.stage=FLOW_ACTIVATE;
        return;
    }
    if(flow.stage==FLOW_ACTIVE) {
        deployment current;
        if(desired(&current)!=1 || !same(&current,&flow.deployment)) {
            begin_recovery(flow.slot,flow.old_active,RECOVERY_ACTIVATION);return;
        }
        finalize_activation();return;
    }
    if(flow.stage!=FLOW_NONE)return;
    if(journal.ack_slot>=0) {
        int slot=journal.ack_slot;
        if(slot!=metadata.active || strcmp(journal.ack_id,metadata.slots[slot].deployment_id) || s.live!=slot_tickets[slot]) {
            storage_halted=true;app_ui_status("Receipt identity mismatch");return;
        }
        int result=ack(&metadata.slots[slot],"active",NULL);
        if(result<0){app_ui_status("Running | awaiting receipt");return;}
        if(!result){begin_recovery(slot,metadata.previous,RECOVERY_ACTIVATION);return;}
        journal.ack_slot=-1;journal.ack_id[0]=0;
        if(save_journal())app_ui_status("App running | online");
        return;
    }
    if(journal.count)return;
    deployment wanted;int result=desired(&wanted);
    if(result==1)install(&wanted);
    else if(result==0)app_ui_status(metadata.active>=0?"App running | online":"Ready | connected");
    else app_ui_status("Backend unavailable");
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
static void synchronized_clock(struct timeval *value) {
    (void)value;app_ui_wall_synchronized(true);
    ESP_LOGI("device","clock_source=sntp");
}
static void delivery_task(void *unused) {
    (void)unused;
    uint8_t nonce[16];esp_fill_random(nonce,sizeof(nonce));
    for(size_t i=0;i<sizeof(nonce);i++)snprintf(boot_id+2*i,3,"%02x",nonce[i]);
    if(!restore()){storage_halted=true;app_ui_status("Recovery storage unavailable");}
    bool network=wifi_start();
    if(network) {
        seed_clock();
        esp_sntp_config_t config=ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
        config.sync_cb=synchronized_clock;
        esp_netif_sntp_init(&config);
    }
    uint64_t next_connect=0;
    for(;;) {
        local_step();
        uint64_t now=(uint64_t)esp_timer_get_time()/1000;
        if(network && !(xEventGroupGetBits(connectivity)&CONNECTED)) {
            if(now>=next_connect){esp_wifi_connect();next_connect=now+5000;}
        } else if(network && time(NULL)>=(time_t)SKETCH_BUILD_EPOCH)network_step();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
bool app_delivery_start(const as_app *builtin) {
    if(!builtin || builtin_app)return false;
    builtin_app=builtin;
    if(xTaskCreate(delivery_task,"app_delivery",24576,NULL,4,NULL)!=pdPASS){builtin_app=NULL;return false;}
    return true;
}
