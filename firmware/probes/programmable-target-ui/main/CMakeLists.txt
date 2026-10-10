idf_component_register(SRCS "../ui_probe.c" INCLUDE_DIRS ".."
 REQUIRES quickjs-ng esp_timer freertos esp_psram waveshare__esp32_p4_wifi6_touch_lcd_3_5
 lvgl__lvgl espressif__esp_lvgl_adapter espressif__esp_codec_dev espressif__esp_lcd_touch
 espressif__esp_lcd_touch_ft5x06 espressif__esp_lcd_st7796 espressif__cmake_utilities)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -UNDEBUG)
