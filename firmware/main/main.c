#include "app_spec.h"
#include "app_ui.h"
#include "app_delivery.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include <stdlib.h>

extern const char fixture_start[] asm("_binary_tap_sprint_json_start");
extern const char fixture_end[] asm("_binary_tap_sprint_json_end");
static as_app *builtin;

void app_main(void) {
    esp_err_t nvs_result = nvs_flash_init();
    bsp_display_cfg_t cfg = {.lv_adapter_cfg = ESP_LV_ADAPTER_DEFAULT_CONFIG()};
    if (!bsp_display_start_with_config(&cfg)) { ESP_LOGE("device","display_init_failed"); return; }
    ESP_ERROR_CHECK(bsp_display_backlight_on());
    builtin = calloc(1,sizeof(*builtin));
    const char *error = NULL;
    size_t size = (size_t)(fixture_end-fixture_start);
    if (size && fixture_start[size-1] == 0) --size;
    if (!builtin || !as_parse(fixture_start,size,builtin,&error) || !app_ui_init() || !app_ui_activate(builtin)) {
        ESP_LOGE("device","initial_runtime_failed"); return;
    }
    ESP_LOGI("device","local_runtime_ready");
    if (nvs_result != ESP_OK) app_ui_status("Network storage unavailable");
    else if (!app_delivery_start(builtin)) app_ui_status("Delivery unavailable");
    for (;;) { app_ui_tick(); vTaskDelay(pdMS_TO_TICKS(20)); }
}
