/* Actual delivery state machine; synthetic NVS, transport and UI command port.
 * Real package decoders/hash are linked. This is not a physical-device test. */
#include "../main/app_delivery.c"
#include <assert.h>

static struct blob { unsigned char *data;size_t size; } disk[4],pending_blob;
static int pending_key=-1,persistence_calls,fail_at,fail_mode;
static bool slow_trickle;static unsigned reads;
static bool offline;static int active_result=1,recovery_reply_mode;
static int active_receipts,recovery_receipts,capability_receipts;
static uint64_t host_ms;static esp_reset_reason_t reset_reason;
static char envelope[2048],last_recovery[2048],last_capability[1024];
static const char *wire_package;static size_t wire_size;
static app_ui_state ui;static app_ui_ticket serial_ticket=1;
static app_package *ui_packages[1024];static app_ui_operation queued_op;static app_ui_ticket queued_ticket;
static bool fail_prepare,fail_activate,fail_retain;
static char status_text[64];static time_t host_time;
static bool fail_clock;static unsigned clock_sets;
static int key_index(const char *key){if(!strcmp(key,"metadata"))return 0;if(!strcmp(key,"recovery_v1"))return 1;if(!strcmp(key,"slot_a"))return 2;assert(!strcmp(key,"slot_b"));return 3;}
static void blob_copy(struct blob *b,const void *p,size_t n){free(b->data);b->data=malloc(n);assert(b->data);memcpy(b->data,p,n);b->size=n;}
int nvs_set_blob(nvs_handle_t h,const char *k,const void *p,size_t n){(void)h;++persistence_calls;if(persistence_calls==fail_at && fail_mode==0)return 2;pending_key=key_index(k);blob_copy(&pending_blob,p,n);return persistence_calls==fail_at?2:0;}
int nvs_commit(nvs_handle_t h){(void)h;++persistence_calls;if(persistence_calls==fail_at && fail_mode==0)return 2;if(pending_key>=0){blob_copy(&disk[pending_key],pending_blob.data,pending_blob.size);pending_key=-1;}return persistence_calls==fail_at?2:0;}
int nvs_get_blob(nvs_handle_t h,const char *k,void *p,size_t *n){(void)h;struct blob *b=&disk[key_index(k)];if(!b->data)return ESP_ERR_NVS_NOT_FOUND;if(*n<b->size)return 2;*n=b->size;memcpy(p,b->data,b->size);return 0;}
int nvs_flash_init_partition(const char *p){assert(!strcmp(p,"apps"));return 0;}
int nvs_open_from_partition(const char *p,const char *n,int mode,nvs_handle_t *h){assert(!strcmp(p,"apps")&&!strcmp(n,"install")&&mode==NVS_READWRITE);*h=1;return 0;}
static void clear_ui(void){for(int i=0;i<1024;i++){app_package_free(ui_packages[i]);ui_packages[i]=NULL;}ui=(app_ui_state){.live=1};serial_ticket=1;queued_op=APP_UI_NONE;queued_ticket=0;}
void app_ui_snapshot(app_ui_state *out){*out=ui;}
void app_ui_status(const char *s){assert(strlen(s)<sizeof(status_text));strcpy(status_text,s);}
void app_ui_wall_synchronized(bool value){(void)value;}
static bool prepare(app_package *p,app_ui_ticket *ticket,bool recovery){if(ui.pending||ui.prepared||(!recovery&&ui.fault_ticket)||(recovery&&ui.fault_ticket!=ui.live))return false;*ticket=++serial_ticket;assert(*ticket<1024);ui_packages[*ticket]=p;ui.pending=true;queued_op=recovery?APP_UI_PREPARE_RECOVERY:APP_UI_PREPARE;queued_ticket=*ticket;return true;}
bool app_ui_prepare(app_package *p,app_ui_ticket *t){return prepare(p,t,false);}
bool app_ui_prepare_recovery(app_package *p,app_ui_ticket *t){return prepare(p,t,true);}
bool app_ui_request(app_ui_operation op,app_ui_ticket t){if(ui.pending)return false;ui.pending=true;queued_op=op;queued_ticket=t;return true;}
bool app_ui_ack_fault(app_ui_ticket t){if(ui.fault_ticket!=t||ui.live==t||!ui.recovered_ticket)return false;ui.fault_ticket=0;return true;}
static void ui_step(void){if(!ui.pending)return;app_ui_operation op=queued_op;app_ui_ticket t=queued_ticket;bool ok=false;
 switch(op){case APP_UI_PREPARE:case APP_UI_PREPARE_RECOVERY:if(!fail_prepare){ui.prepared=t;ok=true;}else{fail_prepare=false;app_package_free(ui_packages[t]);ui_packages[t]=NULL;}break;
 case APP_UI_ACTIVATE:if(!ui.fault_ticket&&!fail_activate&&ui.prepared==t){ui.previous=ui.live;ui.live=t;ui.prepared=0;ui.checkpoint_ticket=t;ok=true;}fail_activate=false;break;
 case APP_UI_COMMIT:ok=ui.live==t&&!ui.fault_ticket;break;
 case APP_UI_ABORT:if(ui.prepared==t)ui.prepared=0;app_package_free(ui_packages[t]);ui_packages[t]=NULL;ok=true;break;
 case APP_UI_RETAIN_PREVIOUS:if(ui.fault_ticket==ui.live&&!fail_retain&&ui.prepared==t){ui.previous=t;ui.prepared=0;ok=true;}fail_retain=false;break;
 case APP_UI_ROLLBACK:if(ui.live==t&&ui.previous){ui.live=ui.previous;ui.previous=0;ui.recovered_ticket=ui.live;ok=true;}break;
 default:break;}
 ui.operation=op;ui.operation_ticket=t;ui.succeeded=ok;ui.pending=false;queued_op=APP_UI_NONE;
}
struct http {char url[512],body[2048],response[4097];const char *bytes;size_t size,cursor;};
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *c){assert(c->disable_auto_redirect&&c->crt_bundle_attach&&c->timeout_ms==8000);struct http *h=calloc(1,sizeof(*h));assert(h);strcpy(h->url,c->url);return h;}
int esp_http_client_set_header(esp_http_client_handle_t h,const char *k,const char *v){(void)h;if(!strcmp(k,"Authorization"))assert(!strcmp(v,"Bearer test_token"));return 0;}
int esp_http_client_set_timeout_ms(esp_http_client_handle_t h,int timeout){(void)h;assert(timeout>0&&timeout<=8000);return 0;}
int esp_http_client_set_method(esp_http_client_handle_t h,int m){(void)h;assert(m==HTTP_METHOD_POST);return 0;}
int esp_http_client_open(esp_http_client_handle_t h,int n){(void)h;assert(n<2048);return offline?2:0;}
int esp_http_client_write(esp_http_client_handle_t h,const char *p,int n){memcpy(h->body,p,n);h->body[n]=0;return n;}
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t h){
 if(strstr(h->url,"/desired")){h->bytes=envelope;h->size=strlen(envelope);}
 else if(strstr(h->url,"/runtime")){strcpy(last_capability,h->body);++capability_receipts;strcpy(h->response,"{\"recorded\":true}");}
 else if(strstr(h->url,"/recovery")){
  strcpy(last_recovery,h->body);++recovery_receipts;cJSON *j=cJSON_Parse(h->body);assert(j&&cJSON_GetArraySize(j)==6);
  snprintf(h->response,sizeof(h->response),"{\"report_id\":\"%s\",\"recovery_seq\":%.0f,\"recorded\":%s,\"applied\":false}",recovery_reply_mode==2?"wrong":string(j,"report_id"),item(j,"recovery_seq")->valuedouble,recovery_reply_mode==1?"false":"true");cJSON_Delete(j);if(recovery_reply_mode==3)return -1;
 }else if(strstr(h->url,"/ack")){
  cJSON *j=cJSON_Parse(h->body);assert(j);if(!strcmp(string(j,"status"),"active")){
   ++active_receipts;assert(disk[0].size==sizeof(metadata));install_metadata m;memcpy(&m,disk[0].data,sizeof(m));assert(m.pending==0&&m.active>=0&&!strcmp(m.slots[m.active].deployment_id,string(j,"deployment_id")));
   if(active_result<0){cJSON_Delete(j);return -1;}
  }
  snprintf(h->response,sizeof(h->response),"{\"recorded\":true,\"current_success\":%s,\"deployment_id\":\"%s\"}",active_result?"true":"false",string(j,"deployment_id"));cJSON_Delete(j);
 }else{h->bytes=wire_package;h->size=wire_size;}
 if(!h->bytes){h->bytes=h->response;h->size=strlen(h->response);}return h->size;
}
int esp_http_client_get_status_code(esp_http_client_handle_t h){(void)h;return 200;}
int esp_http_client_read(esp_http_client_handle_t h,char *p,int cap){size_t n=h->size-h->cursor;++reads;if(slow_trickle){host_ms+=1000;if(n>1)n=1;}if(n>(size_t)cap)n=cap;memcpy(p,h->bytes+h->cursor,n);h->cursor+=n;return (int)n;}
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t h){return h->cursor==h->size;}
int esp_http_client_close(esp_http_client_handle_t h){(void)h;return 0;}
int esp_http_client_cleanup(esp_http_client_handle_t h){free(h);return 0;}
time_t test_time(time_t *out){if(out)*out=host_time;return host_time;}
int test_settimeofday(const struct timeval *v,const struct timezone *z){assert(!z);++clock_sets;if(fail_clock)return -1;host_time=v->tv_sec;return 0;}
int64_t esp_timer_get_time(void){return (int64_t)host_ms*1000;}
esp_reset_reason_t esp_reset_reason(void){return reset_reason;}
const esp_app_desc_t *esp_app_get_description(void){static esp_app_desc_t d={{1,2,3}};return &d;}
void esp_fill_random(void *p,size_t n){memset(p,7,n);}
void vTaskDelay(int ms){host_ms+=(unsigned)ms;}
int xTaskCreate(void (*f)(void *),const char *n,int stack,void *p,int priority,void *h){(void)f;(void)n;(void)p;(void)priority;(void)h;assert(stack==24576);return pdPASS;}
EventGroupHandle_t xEventGroupCreate(void){return NULL;}
int xEventGroupSetBits(EventGroupHandle_t h,int b){(void)h;return b;}int xEventGroupClearBits(EventGroupHandle_t h,int b){(void)h;return b;}int xEventGroupGetBits(EventGroupHandle_t h){(void)h;return 0;}
int esp_netif_init(void){return 2;}int esp_event_loop_create_default(void){return 2;}void *esp_netif_create_default_wifi_sta(void){return NULL;}
int esp_wifi_init(const wifi_init_config_t *c){(void)c;return 2;}int esp_event_handler_register(esp_event_base_t b,int id,void (*f)(void *,esp_event_base_t,int32_t,void *),void *p){(void)b;(void)id;(void)f;(void)p;return 2;}
int esp_wifi_set_mode(int m){(void)m;return 2;}int esp_wifi_set_config(int i,const wifi_config_t *c){(void)i;(void)c;return 2;}int esp_wifi_start(void){return 2;}int esp_wifi_connect(void){return 2;}int esp_netif_sntp_init(const esp_sntp_config_t *c){(void)c;return 2;}
static void reboot(void){clear_ui();memset(&metadata,0,sizeof(metadata));memset(&journal,0,sizeof(journal));memset(slot_tickets,0,sizeof(slot_tickets));flow=(install_flow){0};storage_halted=boot_complete=false;pending_key=-1;next_network_ms=next_capability_ms=0;strcpy(boot_id,"test_boot");assert(restore());}
static void clean(void){clear_ui();for(int i=0;i<4;i++){free(disk[i].data);disk[i]=(struct blob){0};}fail_at=fail_mode=persistence_calls=0;offline=false;active_result=1;recovery_reply_mode=0;reset_reason=ESP_RST_POWERON;reboot();}
static void steps(unsigned n,bool network){for(unsigned i=0;i<n;i++){ui_step();local_step();host_ms+=2001;if(network)network_step();}}
static deployment describe(const char *id,int sequence,int schema){const char *error;app_package *p=app_package_parse(wire_package,wire_size,&error);assert(p);deployment d={0};strcpy(d.deployment_id,id);d.sequence=sequence;d.version=p->version;d.size=(uint32_t)wire_size;strcpy(d.app_id,p->app_id);app_package_free(p);unsigned char hash[32];mbedtls_sha256((const unsigned char *)wire_package,wire_size,hash,0);for(int i=0;i<32;i++)snprintf(d.sha256+2*i,3,"%02x",hash[i]);snprintf(d.path,sizeof(d.path),"/api/apps/%s/versions/%d",d.app_id,d.version);
 snprintf(envelope,sizeof(envelope),"{\"desired\":{\"deployment_id\":\"%s\",\"sequence\":%d,\"manifest\":{\"schema_version\":%d,\"app_id\":\"%s\",\"version\":%d,\"size_bytes\":%u,\"sha256\":\"%s\",\"min_runtime_version\":\"%s\",\"download_path\":\"%s\"}}}",id,sequence,schema,d.app_id,d.version,d.size,d.sha256,schema==2?"0.3.0":"0.1.0",d.path);desired_schema=schema;return d;}
static void install_and_ack(deployment d){install(&d);steps(30,true);if(storage_halted||flow.stage!=FLOW_NONE||journal.ack_slot!=-1||metadata.active<0)fprintf(stderr,"install %s halted%d flow%d ack%d active%d count%u fault%llu status%s\n",d.deployment_id,storage_halted,flow.stage,journal.ack_slot,metadata.active,journal.count,(unsigned long long)ui.fault_ticket,status_text);assert(!storage_halted&&flow.stage==FLOW_NONE&&journal.ack_slot==-1&&metadata.active>=0&&same(&metadata.slots[metadata.active],&d));}
static void fail_live(void){ui.fault_ticket=ui.live;strcpy(ui.fault,"runtime_error");}
static void assert_coherent(void){assert(metadata.active>=-1&&metadata.active<2);if(metadata.active>=0){app_package *p=read_slot(metadata.active);assert(p);app_package_free(p);assert(ui.live==slot_tickets[metadata.active]);}assert(!intent()&&!ui.fault_ticket);}
static char *load(const char *path,size_t *n){FILE *f=fopen(path,"rb");assert(f);fseek(f,0,SEEK_END);*n=(size_t)ftell(f);rewind(f);char *p=malloc(*n+1);assert(fread(p,1,*n,f)==*n);p[*n]=0;fclose(f);return p;}
int main(void){
 size_t legacy_size;char *legacy=load(APP_UI_FIXTURE,&legacy_size);as_app builtin;const char *error;assert(as_parse(legacy,legacy_size,&builtin,&error));builtin_app=&builtin;
 const char *program="{\"schema_version\":2,\"app_id\":\"ordinary\",\"name\":\"Ordinary program\",\"version\":1,\"runtime\":\"quickjs-ng-0.14.0\",\"sdk\":\"device-js-1\",\"profile\":\"p4-canvas-1\",\"requires\":[\"canvas\"],\"source\":\"gfx.begin('#112233');gfx.end();\",\"assets\":[]}";
 host_time=0;assert(seed_clock()&&host_time==SKETCH_BUILD_EPOCH&&clock_sets==1);assert(seed_clock()&&clock_sets==1);host_time+=500;assert(seed_clock()&&clock_sets==1);host_time=0;fail_clock=true;assert(!seed_clock());fail_clock=false;
 wire_package=legacy;wire_size=legacy_size;clean();deployment first=describe("first",1,1);
 char slow_body[4097];size_t slow_used;reads=0;slow_trickle=true;uint64_t started=host_ms;
 assert(!request("/api/device/desired",NULL,slow_body,4096,&slow_used)&&reads==8&&host_ms-started==8000);
 slow_trickle=false;install_and_ack(first);assert_coherent();
 reboot();steps(20,true);assert_coherent();assert(!strcmp(metadata.slots[metadata.active].deployment_id,"first"));
 /* Lost active ACK never prevents the local fault guard and rollback. */
 wire_package=program;wire_size=strlen(program);deployment second=describe("second",2,2);active_result=-1;install(&second);steps(30,true);assert(journal.ack_slot==metadata.active&&same(&metadata.slots[metadata.active],&second));
 offline=true;fail_live();steps(30,false);assert(journal.count==1&&journal.records[0].stage==RECOVERY_READY&&metadata.active==0&&journal.ack_slot==-1);assert_coherent();
 int before=active_receipts;steps(5,true);assert(active_receipts==before);offline=false;recovery_reply_mode=2;assert(!send_recovery()&&journal.count==1);recovery_reply_mode=1;assert(send_recovery()&&journal.count==0);cJSON *receipt=cJSON_Parse(last_recovery);assert(!strcmp(string(receipt,"error_code"),"runtime_error"));cJSON_Delete(receipt);
 /* A second offline fault occupies the second immutable FIFO entry. */
 active_result=1;second=describe("third",3,2);install_and_ack(second);offline=true;fail_live();steps(30,false);assert(journal.count==1&&metadata.active==0);recovery_record first_report=journal.records[0];fail_live();steps(30,false);assert(journal.count==2&&metadata.active==-1&&journal.records[1].recovered_slot==-1);assert(!memcmp(&first_report,&journal.records[0],sizeof(first_report)));assert_coherent();
 reboot();steps(20,false);assert(journal.count==2&&metadata.active==-1);offline=false;recovery_reply_mode=1;assert(send_recovery()&&journal.count==1);assert(send_recovery()&&!journal.count);
 assert(report_capabilities());cJSON *cap=cJSON_Parse(last_capability);assert(cap&&cJSON_GetArraySize(cap)==11&&!strcmp(string(cap,"runtime_version"),"0.3.0")&&cJSON_GetArraySize(item(cap,"schema_versions"))==2&&strlen(string(cap,"firmware_elf_sha256"))==64);cJSON_Delete(cap);
 /* Every recovery persistence call can fail before or after durable commit.
  * Reboot discards only volatile state and resumes from the actual disk bytes. */
 unsigned injected=0;
 for(int mode=0;mode<2;mode++)for(int boundary=1;boundary<=6;boundary++){
  wire_package=legacy;wire_size=legacy_size;clean();first=describe("base",1,1);install_and_ack(first);wire_package=program;wire_size=strlen(program);second=describe("candidate",2,2);install_and_ack(second);
  offline=true;fail_at=persistence_calls+boundary;fail_mode=mode;fail_live();steps(35,false);assert(storage_halted);fail_at=0;reset_reason=ESP_RST_PANIC;reboot();steps(40,false);if(storage_halted||journal.count!=1||journal.records[0].stage!=RECOVERY_READY)fprintf(stderr,"fault mode%d boundary%d halt%d count%u stage%u flow%d ui%llu op%d ok%d status%s\n",mode,boundary,storage_halted,journal.count,journal.records[0].stage,flow.stage,(unsigned long long)ui.live,ui.operation,ui.succeeded,status_text);assert(!storage_halted&&journal.count==1&&journal.records[0].stage==RECOVERY_READY);assert_coherent();++injected;
 }
 /* Installation persistence is also replayed from real durable blob snapshots. */
 for(int mode=0;mode<2;mode++)for(int boundary=1;boundary<=10;boundary++){
  wire_package=legacy;wire_size=legacy_size;clean();first=describe("old",1,1);install_and_ack(first);
  wire_package=program;wire_size=strlen(program);second=describe("new",2,2);
  fail_at=persistence_calls+boundary;fail_mode=mode;install(&second);steps(35,true);
  assert(storage_halted);fail_at=0;offline=true;reboot();steps(40,false);assert(!storage_halted);assert_coherent();++injected;
 }
 /* Explicitly stale active ACK rolls back, while unavailable ACK does not. */
 wire_package=legacy;wire_size=legacy_size;clean();first=describe("old_ack",1,1);install_and_ack(first);
 wire_package=program;wire_size=strlen(program);second=describe("stale",2,2);active_result=0;install(&second);steps(35,true);
 assert(metadata.active==0&&!strcmp(metadata.slots[0].deployment_id,"old_ack"));assert_coherent();
 /* Reboot reconstructs the prior package; it can pass activation and then
  * fail before COMMIT. Preserve A->B, then persist B->built-in separately. */
 wire_package=legacy;wire_size=legacy_size;clean();first=describe("fallback",1,1);install_and_ack(first);
 wire_package=program;wire_size=strlen(program);second=describe("failed",2,2);install_and_ack(second);
 assert(begin_recovery(metadata.active,metadata.previous,RECOVERY_RUNTIME));offline=true;reboot();
 for(int n=0;n<20&&flow.stage!=FLOW_ACTIVATE;n++)steps(1,false);
 assert(flow.stage==FLOW_ACTIVATE);ui_step();assert(ui.succeeded);fail_live();local_step();steps(40,false);
 assert(!storage_halted&&journal.count==2&&journal.records[0].recovered_slot==0&&journal.records[1].recovered_slot==-1&&metadata.active==-1);assert_coherent();
 /* A lost recovery response and each FIFO-removal write boundary are
  * harmless: the exact immutable receipt remains retryable after reboot. */
 for(int mode=0;mode<2;mode++)for(int boundary=1;boundary<=2;boundary++){
  wire_package=legacy;wire_size=legacy_size;clean();first=describe("receipt_base",1,1);install_and_ack(first);
  wire_package=program;wire_size=strlen(program);second=describe("receipt_bad",2,2);install_and_ack(second);
  offline=true;fail_live();steps(25,false);assert(journal.count==1);offline=false;
  recovery_reply_mode=3;assert(!send_recovery()&&journal.count==1);recovery_reply_mode=1;
  fail_at=persistence_calls+boundary;fail_mode=mode;assert(!send_recovery()&&storage_halted);fail_at=0;reboot();steps(25,false);
  assert(!storage_halted);if(journal.count)assert(send_recovery());assert(!journal.count&&journal.next_sequence==2);assert_coherent();++injected;
 }
 /* Both schemas restore through the same strict stored package decoder. */
 wire_package=program;wire_size=strlen(program);clean();second=describe("program_boot",1,2);install_and_ack(second);reboot();steps(20,false);assert_coherent();reset_reason=ESP_RST_PANIC;reboot();steps(30,false);assert(metadata.active==-1&&journal.count==1);reset_reason=ESP_RST_POWERON;
 /* Fresh activation failure reports actual old package, never success. */
 wire_package=legacy;wire_size=legacy_size;clean();first=describe("good",1,1);install_and_ack(first);wire_package=program;wire_size=strlen(program);second=describe("bad_init",2,2);fail_prepare=true;install(&second);steps(30,false);assert(metadata.active==0&&journal.count==1&&!intent());assert_coherent();
 clear_ui();for(int i=0;i<4;i++)free(disk[i].data);free(pending_blob.data);free(legacy);
 printf("{\"status\":\"delivery_recovery_passed\",\"persistence_fault_cases\":%u,\"physical_execution\":false}\n",injected);return 0;
}
