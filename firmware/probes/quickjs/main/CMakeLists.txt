idf_component_register(SRCS "../probe.c" REQUIRES quickjs-ng esp_timer freertos)
target_compile_options(${COMPONENT_LIB} PRIVATE -UNDEBUG)
