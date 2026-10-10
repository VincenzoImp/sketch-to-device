cmake_minimum_required(VERSION 3.16)
get_filename_component(WORKSPACE "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
# Reuse the independently verified official engine cache. No network fetch or
# unpinned component resolution is part of a firmware build.
set(EXTRA_COMPONENT_DIRS "${WORKSPACE}/.tools/quickjs-probe/quickjs-ng")
if(NOT EXISTS "${EXTRA_COMPONENT_DIRS}/quickjs-ng/quickjs.h")
    message(FATAL_ERROR "Verified QuickJS cache missing; run the reviewed runtime fetch helper first")
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(sketch_to_device)
