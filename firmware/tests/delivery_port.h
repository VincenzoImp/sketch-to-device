#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/time.h>
#include <time.h>
#define SKETCH_BUILD_EPOCH 1800000000
time_t test_time(time_t *out);
int test_settimeofday(const struct timeval *tv,const struct timezone *zone);
#define time test_time
#define settimeofday test_settimeofday
static inline void test_log(const char *tag,const char *format,...) { (void)tag; (void)format; }
#define ESP_LOGI(...) test_log(__VA_ARGS__)
#define ESP_LOGW(...) test_log(__VA_ARGS__)
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 1
#define NVS_READWRITE 1
#define BIT0 1
#define pdMS_TO_TICKS(x) (x)
#define pdFALSE 0
#define pdTRUE 1
#define pdPASS 1
#define HTTP_METHOD_POST 1
#define IP_EVENT ((void *)1)
#define WIFI_EVENT ((void *)2)
#define IP_EVENT_STA_GOT_IP 1
#define WIFI_EVENT_STA_DISCONNECTED 2
#define ESP_EVENT_ANY_ID -1
#define WIFI_AUTH_WPA2_PSK 1
#define WIFI_AUTH_OPEN 0
#define WIFI_MODE_STA 1
#define WIFI_IF_STA 1
#define CONFIG_SKETCH_BACKEND_URL "https://test.invalid"
#define CONFIG_SKETCH_DEVICE_TOKEN "test_token"
#define CONFIG_SKETCH_DEVICE_ID "test_device"
#define CONFIG_SKETCH_WIFI_SSID ""
#define CONFIG_SKETCH_WIFI_PASSWORD ""
typedef int nvs_handle_t;
typedef void *EventGroupHandle_t;
typedef void *esp_event_base_t;
typedef struct { const char *url; int timeout_ms; bool disable_auto_redirect; void *crt_bundle_attach; int buffer_size; } esp_http_client_config_t;
typedef struct http *esp_http_client_handle_t;
typedef struct { int unused; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() ((wifi_init_config_t){0})
typedef struct { struct { unsigned char ssid[32],password[64]; struct { int authmode; } threshold; } sta; } wifi_config_t;
typedef struct { void (*sync_cb)(struct timeval *); } esp_sntp_config_t;
#define ESP_NETIF_SNTP_DEFAULT_CONFIG(s) ((esp_sntp_config_t){0})
#define esp_crt_bundle_attach ((void *)1)
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *c);
int esp_http_client_set_header(esp_http_client_handle_t,const char *,const char *);
int esp_http_client_set_timeout_ms(esp_http_client_handle_t,int);
int esp_http_client_set_method(esp_http_client_handle_t,int);
int esp_http_client_open(esp_http_client_handle_t,int);
int esp_http_client_write(esp_http_client_handle_t,const char *,int);
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t);
int esp_http_client_get_status_code(esp_http_client_handle_t);
int esp_http_client_read(esp_http_client_handle_t,char *,int);
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t);
int esp_http_client_close(esp_http_client_handle_t);
int esp_http_client_cleanup(esp_http_client_handle_t);
int mbedtls_sha256(const unsigned char *,size_t,unsigned char *,int);
int nvs_set_blob(nvs_handle_t,const char *,const void *,size_t);
int nvs_get_blob(nvs_handle_t,const char *,void *,size_t *);
int nvs_commit(nvs_handle_t);
int nvs_flash_init_partition(const char *);
int nvs_open_from_partition(const char *,const char *,int,nvs_handle_t *);
void vTaskDelay(int);
void vTaskDelete(void *);
int xTaskCreate(void (*)(void *),const char *,int,void *,int,void *);
EventGroupHandle_t xEventGroupCreate(void);
int xEventGroupSetBits(EventGroupHandle_t,int);
int xEventGroupClearBits(EventGroupHandle_t,int);
int xEventGroupGetBits(EventGroupHandle_t);
int xEventGroupWaitBits(EventGroupHandle_t,int,int,int,int);
int esp_netif_init(void);
int esp_event_loop_create_default(void);
void *esp_netif_create_default_wifi_sta(void);
int esp_wifi_init(const wifi_init_config_t *);
int esp_event_handler_register(esp_event_base_t,int,void (*)(void *,esp_event_base_t,int32_t,void *),void *);
int esp_wifi_set_mode(int);
int esp_wifi_set_config(int,const wifi_config_t *);
int esp_wifi_start(void);
int esp_wifi_connect(void);
int esp_netif_sntp_init(const esp_sntp_config_t *);
int esp_netif_sntp_reachability(unsigned int,unsigned int *);

typedef struct { uint8_t app_elf_sha256[32]; } esp_app_desc_t;
const esp_app_desc_t *esp_app_get_description(void);
void esp_fill_random(void *,size_t);
int64_t esp_timer_get_time(void);
typedef enum { ESP_RST_POWERON,ESP_RST_PANIC,ESP_RST_INT_WDT,ESP_RST_TASK_WDT,ESP_RST_WDT,ESP_RST_CPU_LOCKUP } esp_reset_reason_t;
esp_reset_reason_t esp_reset_reason(void);
