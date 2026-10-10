idf_component_register(SRCS "main.c" "app_spec.c" "app_ui.c" "app_delivery.c" "tls_diagnostics.c"
    INCLUDE_DIRS "." REQUIRES json esp_timer nvs_flash esp_http_client esp_netif esp_event esp_wifi mbedtls)
target_add_binary_data(${COMPONENT_LIB} "../../contracts/fixtures/tap-sprint.json" TEXT)
execute_process(COMMAND "${PYTHON}" -c "import time; print(int(time.time()))"
    OUTPUT_VARIABLE SKETCH_BUILD_EPOCH OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
target_compile_definitions(${COMPONENT_LIB} PRIVATE SKETCH_BUILD_EPOCH=${SKETCH_BUILD_EPOCH})
target_link_options(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=mbedtls_x509_crt_parse_der" "-Wl,-u,__wrap_mbedtls_x509_crt_parse_der")
