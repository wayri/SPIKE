# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
cmake_minimum_required(VERSION 3.20)
project(SPIKEOpticsReference LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_library(spike_optics_reference STATIC planar_reference.cpp)
set_target_properties(spike_optics_reference PROPERTIES
    CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN YES)
target_include_directories(spike_optics_reference PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
add_executable(test_native_optics_reference
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/test_native_optics_reference.cpp")
target_link_libraries(test_native_optics_reference PRIVATE spike_optics_reference)
foreach(target spike_optics_reference test_native_optics_reference)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /WX /fp:strict)
    else()
        target_compile_options(${target} PRIVATE
            -Wall -Wextra -Werror -Wpedantic -fno-fast-math -ffp-contract=off)
    endif()
endforeach()
enable_testing()
add_test(NAME native_optics_reference COMMAND test_native_optics_reference)
