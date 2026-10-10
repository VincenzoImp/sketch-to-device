cmake_minimum_required(VERSION 3.16)
# Separate engine probe: no BSP, Wi-Fi, credentials, app storage or flash action.
get_filename_component(PROJECT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(EXTRA_COMPONENT_DIRS "${PROJECT_ROOT}/.tools/quickjs-probe/quickjs-ng")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(quickjs_feasibility)
