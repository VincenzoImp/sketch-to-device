cmake_minimum_required(VERSION 3.20)
project(app_owner_tests C CXX ASM)
add_compile_definitions(LV_FONT_MONTSERRAT_12=1)
add_subdirectory("../../program_core" shared)
add_executable(app_ui_test ../app_ui_test.c ../../main/app_package.c ../../main/app_spec.c)
target_include_directories(app_ui_test PRIVATE . ../../main)
target_compile_definitions(app_ui_test PRIVATE APP_UI_HOST_TEST
    APP_UI_FIXTURE="${CMAKE_CURRENT_LIST_DIR}/../../../contracts/fixtures/tap-sprint.json")
target_compile_options(app_ui_test PRIVATE -Wall -Wextra -Werror -Wno-misleading-indentation -UNDEBUG -fsanitize=address,undefined -fno-omit-frame-pointer)
target_link_options(app_ui_test PRIVATE -fsanitize=address,undefined)
target_link_libraries(app_ui_test PRIVATE program_core)

add_executable(app_delivery_test ../app_delivery_test.c ../../main/app_package.c ../../main/app_spec.c)
target_include_directories(app_delivery_test PRIVATE .. ../../main)
target_compile_definitions(app_delivery_test PRIVATE APP_DELIVERY_HOST_TEST
    APP_UI_FIXTURE="${CMAKE_CURRENT_LIST_DIR}/../../../contracts/fixtures/tap-sprint.json")
target_compile_options(app_delivery_test PRIVATE -Wall -Wextra -Werror -Wno-misleading-indentation -UNDEBUG -fsanitize=address,undefined -fno-omit-frame-pointer)
target_link_options(app_delivery_test PRIVATE -fsanitize=address,undefined)
target_link_libraries(app_delivery_test PRIVATE program_core)
