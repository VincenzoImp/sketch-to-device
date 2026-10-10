#include "delivery_port.h"
#include "../main/app_delivery.c"
#include <CommonCrypto/CommonDigest.h>
#include <assert.h>

struct http { const char *response; size_t size, cursor; char url[512]; char body[1024]; };
static char envelope[2048];
static const char *package;
static size_t package_size;
static int desired_calls, supersede_after, activations, fail_activation, active_acks, failed_acks;
static uint64_t ticks;
static const as_app *shown;
static char shown_status[64];
static bool fail_storage, fail_health;
static int ack_result=1, unknown_acks;
static char receipt_json[256];
static bool disconnect_on_active_ack,network_down;
static int reconnects;
static const as_app *retained_during_reconnect;
static time_t simulated_clock;
static int clock_sets;
static bool clock_set_failure;
time_t test_time(time_t *out){if(out)*out=simulated_clock;return simulated_clock;}
int test_settimeofday(const struct timeval *tv,const struct timezone *zone){assert(!zone);++clock_sets;if(clock_set_failure)return -1;simulated_clock=tv->tv_sec;return 0;}
static struct blob { char key[16]; unsigned char *data; size_t size; } blobs[3];
static void reset_transport(void) { desired_calls=0; supersede_after=0; fail_activation=0; fail_health=false; active_acks=failed_acks=0; ack_result=1;unknown_acks=0;disconnect_on_active_ack=network_down=false;reconnects=0;retained_during_reconnect=NULL; }
static int blob_index(const char *key) { return !strcmp(key,"metadata") ? 0 : !strcmp(key,"slot_a") ? 1 : 2; }
int nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t size) {
    (void)h;if(fail_storage)return 2;struct blob *b=&blobs[blob_index(key)];free(b->data);b->data=malloc(size);assert(b->data);memcpy(b->data,data,size);b->size=size;return 0;
}
int nvs_get_blob(nvs_handle_t h,const char *key,void *data,size_t *size) {
    (void)h;struct blob *b=&blobs[blob_index(key)];if(!b->data)return ESP_ERR_NVS_NOT_FOUND;
    if(*size<b->size)return 2;*size=b->size;memcpy(data,b->data,b->size);return 0;
}
int nvs_commit(nvs_handle_t h){(void)h;return fail_storage?2:0;}
int nvs_flash_init_partition(const char *p){assert(!strcmp(p,"apps"));return 0;}
int nvs_open_from_partition(const char *p,const char *n,int mode,nvs_handle_t *h){(void)p;(void)n;(void)mode;*h=1;return 0;}
int mbedtls_sha256(const unsigned char *p,size_t n,unsigned char *out,int mode){assert(!mode);CC_SHA256(p,(CC_LONG)n,out);return 0;}
bool app_ui_activate(const as_app *app){if(fail_activation){--fail_activation;return false;}shown=app;++activations;return true;}
void app_ui_status(const char *message){assert(message && strlen(message)<sizeof(shown_status));strcpy(shown_status,message);}
uint64_t app_ui_healthy_ticks(void){return ticks;}
void vTaskDelay(int ms){(void)ms;if(!fail_health)++ticks;}
void vTaskDelete(void *p){(void)p;assert(!"unexpected task termination");}
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *c){
    assert(c->disable_auto_redirect && c->crt_bundle_attach && c->timeout_ms==8000);
    struct http *h=calloc(1,sizeof(*h));strcpy(h->url,c->url);return h;
}
int esp_http_client_set_header(esp_http_client_handle_t h,const char *k,const char *v){(void)h;if(!strcmp(k,"Authorization"))assert(!strcmp(v,"Bearer test_token"));return 0;}
int esp_http_client_set_method(esp_http_client_handle_t h,int method){(void)h;assert(method==HTTP_METHOD_POST);return 0;}
int esp_http_client_open(esp_http_client_handle_t h,int size){(void)h;assert(size<1024);return network_down?2:0;}
int esp_http_client_write(esp_http_client_handle_t h,const char *p,int size){memcpy(h->body,p,size);h->body[size]=0;return size;}
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t h){
    if(strstr(h->url,"/desired")){++desired_calls;h->response=(supersede_after && desired_calls>=supersede_after)?"{\"desired\":null}":envelope;h->size=strlen(h->response);}
    else if(strstr(h->url,"/ack")){
        cJSON *j=cJSON_Parse(h->body);assert(j);assert(!strcmp(string(j,"device_id"),"test_device"));
        if(!strcmp(string(j,"status"),"active")){
            if(disconnect_on_active_ack){disconnect_on_active_ack=false;network_down=true;cJSON_Delete(j);return -1;}
            ++active_acks;
            if(unknown_acks>0){--unknown_acks;strcpy(receipt_json,unknown_acks ? "{}" : "{\"recorded\":true,\"current_success\":false,\"deployment_id\":\"wrong\"}");}
            else snprintf(receipt_json,sizeof(receipt_json),"{\"recorded\":true,\"current_success\":%s,\"deployment_id\":\"%s\"}",ack_result?"true":"false",string(j,"deployment_id"));
        }else{if(!strcmp(string(j,"status"),"failed"))++failed_acks;strcpy(receipt_json,"{}");}
        cJSON_Delete(j);h->response=receipt_json;h->size=strlen(receipt_json);
    }
    else{h->response=package;h->size=package_size;}return h->size;
}
int esp_http_client_get_status_code(esp_http_client_handle_t h){(void)h;return 200;}
int esp_http_client_read(esp_http_client_handle_t h,char *out,int cap){size_t n=h->size-h->cursor;if(n>(size_t)cap)n=cap;memcpy(out,h->response+h->cursor,n);h->cursor+=n;return (int)n;}
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t h){return h->cursor==h->size;}
int esp_http_client_close(esp_http_client_handle_t h){(void)h;return 0;}
int esp_http_client_cleanup(esp_http_client_handle_t h){free(h);return 0;}
/* Unused production startup functions are linked, but tests never simulate Wi-Fi success. */
int xTaskCreate(void (*f)(void *),const char *n,int s,void *p,int priority,void *handle){(void)f;(void)n;(void)s;(void)p;(void)priority;(void)handle;return 0;}
EventGroupHandle_t xEventGroupCreate(void){return NULL;}
int xEventGroupSetBits(EventGroupHandle_t h,int b){(void)h;return b;}
int xEventGroupClearBits(EventGroupHandle_t h,int b){(void)h;return b;}
int xEventGroupGetBits(EventGroupHandle_t h){(void)h;return network_down?0:CONNECTED;}
int xEventGroupWaitBits(EventGroupHandle_t h,int a,int b,int c,int d){(void)h;(void)a;(void)b;(void)c;(void)d;return 0;}
int esp_netif_init(void){return 2;}int esp_event_loop_create_default(void){return 2;}
void *esp_netif_create_default_wifi_sta(void){return NULL;}
int esp_wifi_init(const wifi_init_config_t *c){(void)c;return 2;}
int esp_event_handler_register(esp_event_base_t b,int id,void (*f)(void *,esp_event_base_t,int32_t,void *),void *p){(void)b;(void)id;(void)f;(void)p;return 2;}
int esp_wifi_set_mode(int m){(void)m;return 2;}int esp_wifi_set_config(int i,const wifi_config_t *c){(void)i;(void)c;return 2;}
int esp_wifi_start(void){return 2;}
int esp_wifi_connect(void){++reconnects;if(retained_during_reconnect)assert(installed_app==retained_during_reconnect);network_down=false;return 0;}
int esp_netif_sntp_init(const esp_sntp_config_t *c){(void)c;return 2;}
int esp_netif_sntp_reachability(unsigned int server,unsigned int *reach){(void)server;*reach=0;return 2;}

static deployment describe(const char *id,int sequence) {
    deployment d={0};strcpy(d.deployment_id,id);d.sequence=sequence;d.version=1;d.size=(uint32_t)package_size;
    as_app *app=calloc(1,sizeof(*app));const char *error;assert(as_parse(package,package_size,app,&error));strcpy(d.app_id,app->app_id);free(app);
    unsigned char hash[32];mbedtls_sha256((const unsigned char *)package,package_size,hash,0);
    for(int i=0;i<32;i++)snprintf(d.sha256+2*i,3,"%02x",hash[i]);
    snprintf(d.path,sizeof(d.path),"/api/apps/%s/versions/1",d.app_id);
    snprintf(envelope,sizeof(envelope),"{\"desired\":{\"deployment_id\":\"%s\",\"sequence\":%d,\"manifest\":{\"schema_version\":1,\"app_id\":\"%s\",\"version\":1,\"size_bytes\":%zu,\"sha256\":\"%s\",\"min_runtime_version\":\"0.1.0\",\"download_path\":\"%s\"}}}",id,sequence,d.app_id,package_size,d.sha256,d.path);
    return d;
}
static char *load(const char *path,size_t *size){FILE *f=fopen(path,"rb");assert(f);fseek(f,0,SEEK_END);*size=(size_t)ftell(f);rewind(f);char *b=malloc(*size+1);assert(fread(b,1,*size,f)==*size);b[*size]=0;fclose(f);return b;}
int main(int argc,char **argv) {
    simulated_clock=0;assert(seed_clock() && simulated_clock==SKETCH_BUILD_EPOCH && clock_sets==1);
    simulated_clock=SKETCH_BUILD_EPOCH-1;assert(seed_clock() && simulated_clock==SKETCH_BUILD_EPOCH && clock_sets==2);
    assert(seed_clock() && clock_sets==2);
    simulated_clock=SKETCH_BUILD_EPOCH+3600;assert(seed_clock() && simulated_clock==SKETCH_BUILD_EPOCH+3600 && clock_sets==2);
    simulated_clock=0;clock_set_failure=true;assert(!seed_clock() && simulated_clock==0);clock_set_failure=false;
    assert(argc==3);size_t a_size,b_size;char *a=load(argv[1],&a_size),*b=load(argv[2],&b_size);
    as_app local={0};const char *error;assert(as_parse(a,a_size,&local,&error));builtin_app=&local;shown=&local;assert(restore());
    package=a;package_size=a_size;deployment first=describe("first",1),parsed;
    assert(desired(&parsed)==1 && same(&first,&parsed));
    char tiny[9];size_t used;assert(!request("/api/device/desired",NULL,tiny,8,&used));
    assert(!protocol_json("{\"x\":1,\"x\":2}",13));
    assert(!protocol_json("{\"x\":\"\\u0000\"}",14));
    assert(!protocol_json("{} trailing",11));
    char valid_envelope[2048];strcpy(valid_envelope,envelope);
    char *schema=strstr(envelope,"\"schema_version\":1");assert(schema);schema[strlen("\"schema_version\":")]='2';assert(desired(&parsed)==-1);strcpy(envelope,valid_envelope);
    install(&first);
    assert(active_acks==1 && metadata.active==0 && shown==installed_app);
    const as_app *old=shown;int count=activations;app_ui_status("Waiting for secure clock");
    install(&first);assert(active_acks==2 && activations==count && !strcmp(shown_status,"App running | online"));
    reset_transport();deployment equivalent=describe("equivalent",2);install(&equivalent);assert(active_acks==1 && shown==old && activations==count);
    package=b;package_size=b_size;deployment next=describe("next",3);
    reset_transport();deployment corrupt=next;corrupt.sha256[0]=corrupt.sha256[0]=='0'?'1':'0';install(&corrupt);assert(failed_acks==1 && shown==old && metadata.active==0);
    reset_transport();next=describe("next2",4);supersede_after=1;install(&next);assert(!active_acks && shown==old && metadata.active==0);
    reset_transport();next=describe("next3",5);supersede_after=2;install(&next);assert(!active_acks && shown==old && metadata.active==0 && !metadata.pending);
    reset_transport();next=describe("next4",6);fail_activation=1;install(&next);assert(failed_acks==1 && shown==old && metadata.active==0);
    reset_transport();next=describe("next5",7);fail_storage=true;install(&next);fail_storage=false;assert(!active_acks && shown==old && metadata.active==0);
    reset_transport();next=describe("next6",8);fail_health=true;install(&next);assert(failed_acks==1 && shown==old && metadata.active==0);
    reset_transport();next=describe("stale_ack",9);ack_result=0;install(&next);assert(active_acks==1 && metadata.active==0 && shown==old && !metadata.pending);
    reset_transport();next=describe("next7",10);unknown_acks=2;disconnect_on_active_ack=true;retained_during_reconnect=old;
    int before_activation=activations;install(&next);assert(active_acks==3 && reconnects==1 && activations==before_activation+1 && metadata.active==1 && metadata.previous==0 && shown!=old && !metadata.pending);
    free(installed_app);installed_app=NULL;shown=&local;memset(&metadata,0,sizeof(metadata));assert(restore());assert(metadata.active==1 && !strcmp(shown->app_id,next.app_id));
    metadata.pending=1;metadata.pending_slot=0;assert(save_metadata());free(installed_app);installed_app=NULL;shown=&local;assert(restore());assert(metadata.active==1 && !metadata.pending);
    metadata.pending=2;assert(save_metadata());free(installed_app);installed_app=NULL;shown=&local;assert(restore());assert(metadata.active==0 && metadata.previous==-1 && !strcmp(shown->app_id,first.app_id));
    blobs[1].data[0]^=1;free(installed_app);installed_app=NULL;shown=&local;assert(restore());assert(metadata.active==-1 && shown==&local);
    for(int i=0;i<3;i++)free(blobs[i].data);free(installed_app);free(a);free(b);
    puts("PASS: delivery identity, duplicate no-reset, tamper, stale-before/after-view, render/health/storage failure, reboot and pending recovery");return 0;
}
