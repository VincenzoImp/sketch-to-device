#pragma once
#include "app_spec.h"

/* All public functions acquire the BSP LVGL lock internally. */
bool app_ui_init(void);
bool app_ui_activate(const as_app *app);
void app_ui_tick(void);
void app_ui_status(const char *message);
uint64_t app_ui_healthy_ticks(void);
