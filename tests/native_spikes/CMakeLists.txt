# SPDX-License-Identifier: Apache-2.0
# Standalone circuit-engine regression build, without the PCB/desktop dependencies.
cmake_minimum_required(VERSION 3.24)
project(SPIKESNativeRegression LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(OpenMP)
get_filename_component(SPIKES_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(SPIKES_SRC "${SPIKES_ROOT}/src/spikes")
set(SPIKES_TRANSIENT_SOURCE "${SPIKES_SRC}/transient_solver.cpp" CACHE FILEPATH
    "Transient implementation to compile (allows controlled numerical experiments)")
add_library(spikes_core STATIC
    ${SPIKES_SRC}/dc_solver.cpp ${SPIKES_SRC}/osdi_device.cpp
    ${SPIKES_TRANSIENT_SOURCE} ${SPIKES_SRC}/transient_session.cpp)
set_target_properties(spikes_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(spikes_core PUBLIC "${SPIKES_ROOT}/src")
target_link_libraries(spikes_core PUBLIC Eigen3::Eigen ${CMAKE_DL_LIBS})
if(OpenMP_CXX_FOUND)
    target_link_libraries(spikes_core PUBLIC OpenMP::OpenMP_CXX)
endif()
add_library(spikes_c_api SHARED ${SPIKES_SRC}/c_api.cpp)
target_link_libraries(spikes_c_api PRIVATE spikes_core)
target_compile_definitions(spikes_c_api PRIVATE SPIKES_SHARED SPIKES_BUILDING_LIBRARY)
if(MSVC)
    target_compile_options(spikes_core PRIVATE /fp:strict)
else()
    target_compile_options(spikes_core PRIVATE -fno-fast-math -ffp-contract=off)
endif()
enable_testing()
foreach(test IN ITEMS dc c_api transient transient_c_api transient_session
                     transient_session_c_api electrothermal_reference pwm_electrothermal)
    add_executable(test_spikes_${test} "${SPIKES_ROOT}/tests/test_spikes_${test}.cpp")
    if(test MATCHES "c_api")
        target_link_libraries(test_spikes_${test} PRIVATE spikes_c_api)
        target_include_directories(test_spikes_${test} PRIVATE "${SPIKES_ROOT}/src")
        target_compile_definitions(test_spikes_${test} PRIVATE SPIKES_SHARED)
    else()
        target_link_libraries(test_spikes_${test} PRIVATE spikes_core)
    endif()
    # These regression fixtures use assert; never disable checks in Release.
    if(MSVC)
        target_compile_options(test_spikes_${test} PRIVATE /UNDEBUG)
    else()
        target_compile_options(test_spikes_${test} PRIVATE -UNDEBUG)
    endif()
    add_test(NAME test_spikes_${test} COMMAND test_spikes_${test})
endforeach()
# Include the existing native callback fixtures when installed; availability is
# explicit at configure time rather than silently omitting their checks.
foreach(binding IN ITEMS
    "SPIKES_TEST_OSDI_ARTIFACT|artifacts/hdl-qualification-wave4-current/spikes_linear_resistor.osdi"
    "SPIKES_TEST_OSDI04_CAPACITOR|artifacts/hdl-qualification-wave5-capacitor.osdi"
    "SPIKES_TEST_OSDI04_NOISE|artifacts/hdl-qualification-wave5-noise.osdi"
    "SPIKES_TEST_BSIM_BULK_OSDI|artifacts/models/bsimbulk-107.2.1-windows-x64.osdi"
    "SPIKES_TEST_BSIM_CMG_OSDI|artifacts/models/bsimcmg-112.1.0-windows-x64.osdi")
    string(REPLACE "|" ";" fields "${binding}")
    list(GET fields 0 macro)
    list(GET fields 1 relative_path)
    if(EXISTS "${SPIKES_ROOT}/${relative_path}")
        target_compile_definitions(test_spikes_dc PRIVATE
            ${macro}="${SPIKES_ROOT}/${relative_path}")
        if(macro STREQUAL "SPIKES_TEST_OSDI04_CAPACITOR")
            target_compile_definitions(test_spikes_transient PRIVATE
                ${macro}="${SPIKES_ROOT}/${relative_path}")
        endif()
        message(STATUS "Native callback fixture enabled: ${relative_path}")
    else()
        message(STATUS "Native callback fixture unavailable: ${relative_path}")
    endif()
endforeach()
