cmake_minimum_required(VERSION 3.20)
project(SPIKE VERSION 0.3.0 LANGUAGES CXX)

set(SPIKES_ENGINE_PRERELEASE "beta.1" CACHE STRING
    "SPIKES engine prerelease identifier")
set(SPIKES_ENGINE_VERSION
    "${PROJECT_VERSION}-${SPIKES_ENGINE_PRERELEASE}")

# ============================================================================
# SPIKE: Signal, Power, and Integrity Knowledge Engine
# Build Configuration - Professional EDA-Grade Standards
# ============================================================================

# C++20 Standard (for concepts, ranges, coroutines)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type default
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Legacy field-kernel optimization policy.  Keep these flags target-scoped:
# circuit convergence/failure detection must not inherit fast-math or a
# build-machine ISA requirement.
function(spike_enable_legacy_hpc TARGET_NAME)
if(MSVC)
    target_compile_options(${TARGET_NAME} PRIVATE
        /arch:AVX2
        /openmp
        $<$<CONFIG:Release>:/O2>
        $<$<CONFIG:Release>:/Oi>
        $<$<CONFIG:Release>:/Ot>
        $<$<CONFIG:Release>:/GL>
    )
    target_link_options(${TARGET_NAME} PRIVATE $<$<CONFIG:Release>:/LTCG>)
else()
    target_compile_options(${TARGET_NAME} PRIVATE
        $<$<CONFIG:Release>:-O3>
        -march=native
        -fopenmp
        -ffast-math
    )
    target_link_options(${TARGET_NAME} PRIVATE -fopenmp)
endif()
endfunction()

# ============================================================================
# Dependencies
# ============================================================================

# Eigen3 for sparse linear algebra
find_package(Eigen3 3.4 REQUIRED NO_MODULE)

# OpenMP for multi-core parallelism
find_package(OpenMP REQUIRED)

# Python for nanobind (will be configured in v0.1.7.0)
# find_package(Python 3.11 COMPONENTS Interpreter Development REQUIRED)

# ============================================================================
# C++ Kernel Libraries
# ============================================================================

# PEEC Solver Library
add_library(spike_peec STATIC
    src/peec/peec_solver.cpp
)
target_include_directories(spike_peec PUBLIC 
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(spike_peec PUBLIC 
    Eigen3::Eigen
    OpenMP::OpenMP_CXX
)
if(MSVC)
    target_compile_options(spike_peec PRIVATE /fp:strict)
else()
    target_compile_options(spike_peec PRIVATE -fno-fast-math -ffp-contract=off)
endif()

# Finite-volume inductance verification kernel. Deliberately isolated from the
# legacy PEEC model until barrel geometry and overlap-aware bases are qualified.
add_library(spike_peec_volume STATIC src/peec/volume_inductance.cpp)
target_include_directories(spike_peec_volume PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
if(MSVC)
    target_compile_options(spike_peec_volume PRIVATE /W4 /WX /fp:strict)
else()
    target_compile_options(spike_peec_volume PRIVATE -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off)
endif()
add_library(spike_peec_volume_matrix STATIC
    src/peec/volume_matrix.cpp
    src/peec/annular_inductance.cpp)
target_include_directories(spike_peec_volume_matrix PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(spike_peec_volume_matrix PUBLIC spike_peec_volume Eigen3::Eigen)
set_target_properties(spike_peec_volume spike_peec_volume_matrix PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
    target_compile_options(spike_peec_volume_matrix PRIVATE /W4 /WX /fp:strict)
else()
    target_compile_options(spike_peec_volume_matrix PRIVATE -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off)
endif()

# Isolated affine-prism verification kernel. It is not wired into the board
# extractor until touching bases, contacts, and mixed annular terms are solved.
add_library(spike_peec_affine_triangle STATIC
    src/peec/affine_triangle_basis.cpp)
target_include_directories(spike_peec_affine_triangle PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src)
if(MSVC)
    target_compile_options(spike_peec_affine_triangle PRIVATE /W4 /WX /fp:strict)
else()
    target_compile_options(spike_peec_affine_triangle PRIVATE
        -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off)
endif()

# Strict typed geometry admission only. Keep this target independent of Eigen,
# OpenMP, PEEC solver APIs, and legacy fast-math/ISA flags.
add_library(spike_transition_handoff STATIC
    src/peec/via_transition_mesh_input.cpp
    src/peec/reference_plane_antipad_mesh_input.cpp
    src/peec/generalized_reference_plane_mesh_input.cpp
)
target_include_directories(spike_transition_handoff PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
set_target_properties(spike_transition_handoff PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# Solver-independent planar topology predicates and canonical source geometry.
add_library(spike_geometry STATIC
    src/geometry/planar_topology.cpp
    src/geometry/constrained_triangulation.cpp)
target_include_directories(spike_geometry PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
set_target_properties(spike_geometry PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Thermal FEM Library
add_library(spike_thermal STATIC
    src/thermal/thermal_solver.cpp
)
target_include_directories(spike_thermal PUBLIC 
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(spike_thermal PUBLIC 
    Eigen3::Eigen
    OpenMP::OpenMP_CXX
)
spike_enable_legacy_hpc(spike_thermal)

# Math Utilities Library (header-only for now)
add_library(spike_math INTERFACE)
target_include_directories(spike_math INTERFACE 
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(spike_math INTERFACE 
    Eigen3::Eigen
    OpenMP::OpenMP_CXX
)

# SPIKES Circuit Solver Core
#
# Keep this target independent of PEEC, thermal, Python, and UI contracts.  The
# dense Phase-1 backend is a correctness oracle; sparse/nonlinear backends can
# replace it without changing the public circuit API.
add_library(spikes_core STATIC
    src/spikes/dc_solver.cpp
    src/spikes/osdi_device.cpp
    src/spikes/transient_solver.cpp
    src/spikes/transient_session.cpp
)
target_link_libraries(spikes_core PRIVATE Eigen3::Eigen OpenMP::OpenMP_CXX)
target_include_directories(spikes_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
set_target_properties(spikes_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Stable language-neutral embedding boundary.  Keep this wrapper separate from
# the numerical archive so Python, C dashboards, and HIL hosts can load one
# versioned shared library without exposing C++ ABI types.
add_library(spikes_c_api SHARED
    src/spikes/c_api.cpp
)
target_include_directories(spikes_c_api PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(spikes_c_api PRIVATE spikes_core)
target_compile_definitions(spikes_c_api PUBLIC SPIKES_SHARED PRIVATE SPIKES_BUILDING_LIBRARY)

# Reusable compiled probe/telemetry/dashboard layer and its native console.
# This remains UI-toolkit independent so the later GUI can reuse the same
# session, rolling-buffer, limit, and control semantics.
add_library(spikes_dashboard STATIC
    src/spikes/console_dashboard.cpp
)
target_include_directories(spikes_dashboard PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_link_libraries(spikes_dashboard PUBLIC spikes_core)
set_target_properties(spikes_dashboard PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_executable(spikes_console
    src/spikes/console_main.cpp
)
target_link_libraries(spikes_console PRIVATE spikes_dashboard)
target_compile_definitions(spikes_console PRIVATE
    SPIKES_ENGINE_VERSION="${SPIKES_ENGINE_VERSION}")

add_executable(spikes_osdi_worker src/spikes/osdi_worker_main.cpp)
target_link_libraries(spikes_osdi_worker PRIVATE spikes_core)

add_executable(spikes_appcontainer_launcher
    src/spikes/appcontainer_launcher.cpp)
if(WIN32)
    target_link_libraries(spikes_appcontainer_launcher PRIVATE userenv advapi32)
endif()

# Circuit convergence and failure detection require strict IEEE semantics.
# These target-local options intentionally override the repository's legacy
# global fast-math setting for the SPIKES numerical kernel.
if(MSVC)
    target_compile_options(spikes_core PRIVATE /EHsc /fp:strict)
    target_compile_options(spikes_c_api PRIVATE /EHsc)
    target_compile_options(spikes_dashboard PRIVATE /EHsc /fp:strict)
    target_compile_options(spikes_console PRIVATE /EHsc /fp:strict)
    target_compile_options(spikes_osdi_worker PRIVATE /EHsc /fp:strict)
    target_compile_options(spikes_appcontainer_launcher PRIVATE /EHsc)
else()
    target_compile_options(spikes_core PRIVATE -fno-fast-math -ffp-contract=off)
    target_compile_options(spikes_dashboard PRIVATE -fno-fast-math -ffp-contract=off)
    target_compile_options(spikes_console PRIVATE -fno-fast-math -ffp-contract=off)
endif()

# ============================================================================
# Python Bindings (nanobind) - To be configured in v0.1.7.0
# ============================================================================

# find_package(nanobind CONFIG REQUIRED)
# nanobind_add_module(spike_core ...)

# ============================================================================
# Installation
# ============================================================================

install(TARGETS spike_peec spike_peec_volume spike_peec_volume_matrix spike_transition_handoff spike_geometry spike_thermal spike_math spikes_core spikes_c_api spikes_dashboard spikes_console spikes_osdi_worker spikes_appcontainer_launcher
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    RUNTIME DESTINATION bin
)
install(FILES
    src/peec/volume_inductance.hpp
    src/peec/annular_inductance.hpp
    src/peec/volume_matrix.hpp
    src/peec/via_transition_mesh_input.hpp
    src/peec/reference_plane_antipad_mesh_input.hpp
    src/geometry/planar_topology.hpp
    src/spikes/dc_solver.hpp
    src/spikes/osdi_device.hpp
    src/spikes/transient_solver.hpp
    src/spikes/transient_session.hpp
    src/spikes/console_dashboard.hpp
    src/spikes/c_api.h
    DESTINATION include/spikes
)

# ============================================================================
# Testing (Optional - will be expanded)
# ============================================================================

option(BUILD_TESTING "Build tests" ON)
if(BUILD_TESTING)
    enable_testing()

    add_executable(spikes_sandbox_probe tests/spikes_sandbox_probe.cpp)
    if(WIN32)
        target_link_libraries(spikes_sandbox_probe PRIVATE ws2_32)
    endif()
    
    # PEEC Solver Tests
    add_executable(test_peec tests/test_peec.cpp)
    target_link_libraries(test_peec PRIVATE spike_peec)
    
    add_test(NAME test_peec COMMAND test_peec)

    add_executable(test_peec_admission tests/test_peec_admission.cpp)
    target_link_libraries(test_peec_admission PRIVATE spike_peec)
    add_test(NAME test_peec_admission COMMAND test_peec_admission)

    add_executable(test_volume_inductance tests/test_volume_inductance.cpp)
    target_link_libraries(test_volume_inductance PRIVATE spike_peec_volume Eigen3::Eigen)
    add_test(NAME test_volume_inductance COMMAND test_volume_inductance)

    add_executable(test_volume_matrix tests/test_volume_matrix.cpp)
    target_link_libraries(test_volume_matrix PRIVATE spike_peec_volume_matrix Eigen3::Eigen)
    add_test(NAME test_volume_matrix COMMAND test_volume_matrix)

    add_executable(test_annular_inductance tests/test_annular_inductance.cpp)
    target_link_libraries(test_annular_inductance PRIVATE spike_peec_volume_matrix)
    add_test(NAME test_annular_inductance COMMAND test_annular_inductance)

    add_executable(test_affine_triangle_basis tests/test_affine_triangle_basis.cpp)
    target_link_libraries(test_affine_triangle_basis PRIVATE spike_peec_affine_triangle)
    add_test(NAME test_affine_triangle_basis COMMAND test_affine_triangle_basis)

    add_executable(test_via_transition_mesh_input
        tests/test_via_transition_mesh_input.cpp)
    target_link_libraries(test_via_transition_mesh_input PRIVATE
        spike_transition_handoff)
    add_test(NAME test_via_transition_mesh_input
        COMMAND test_via_transition_mesh_input)

    add_executable(test_reference_plane_antipad_mesh_input
        tests/test_reference_plane_antipad_mesh_input.cpp)
    target_link_libraries(test_reference_plane_antipad_mesh_input PRIVATE
        spike_transition_handoff)
    add_test(NAME test_reference_plane_antipad_mesh_input
        COMMAND test_reference_plane_antipad_mesh_input)

    add_executable(test_generalized_reference_plane_mesh_input
        tests/test_generalized_reference_plane_mesh_input.cpp)
    target_link_libraries(test_generalized_reference_plane_mesh_input PRIVATE
        spike_transition_handoff)
    add_test(NAME test_generalized_reference_plane_mesh_input
        COMMAND test_generalized_reference_plane_mesh_input)

    add_executable(test_planar_topology tests/test_planar_topology.cpp)
    target_link_libraries(test_planar_topology PRIVATE spike_geometry)
    add_test(NAME test_planar_topology COMMAND test_planar_topology)

    # SPIKES Phase-1 deterministic DC operating-point tests
    add_executable(test_spikes_core tests/test_spikes_dc.cpp)
    target_link_libraries(test_spikes_core PRIVATE spikes_core)
    target_compile_definitions(test_spikes_core PRIVATE
        SPIKES_TEST_OSDI_ARTIFACT="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/hdl-qualification-wave4-current/spikes_linear_resistor.osdi"
        SPIKES_TEST_OSDI04_CAPACITOR="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/hdl-qualification-wave5-capacitor.osdi"
        SPIKES_TEST_OSDI04_NOISE="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/hdl-qualification-wave5-noise.osdi"
        SPIKES_TEST_BSIM_BULK_OSDI="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/models/bsimbulk-107.2.1-windows-x64.osdi"
        SPIKES_TEST_BSIM_CMG_OSDI="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/models/bsimcmg-112.1.0-windows-x64.osdi")
    add_test(NAME test_spikes_core COMMAND test_spikes_core)

    add_executable(test_spikes_c_api tests/test_spikes_c_api.cpp)
    target_link_libraries(test_spikes_c_api PRIVATE spikes_c_api)
    add_test(NAME test_spikes_c_api COMMAND test_spikes_c_api)

    add_executable(test_spikes_transient tests/test_spikes_transient.cpp)
    target_link_libraries(test_spikes_transient PRIVATE spikes_core)
    target_compile_definitions(test_spikes_transient PRIVATE
        SPIKES_TEST_OSDI04_CAPACITOR="${CMAKE_CURRENT_SOURCE_DIR}/artifacts/hdl-qualification-wave5-capacitor.osdi")
    add_test(NAME test_spikes_transient COMMAND test_spikes_transient)

    add_executable(test_spikes_transient_c_api
        tests/test_spikes_transient_c_api.cpp)
    target_link_libraries(test_spikes_transient_c_api PRIVATE spikes_c_api)
    add_test(NAME test_spikes_transient_c_api
        COMMAND test_spikes_transient_c_api)

    add_executable(test_spikes_transient_session
        tests/test_spikes_transient_session.cpp)
    target_link_libraries(test_spikes_transient_session PRIVATE spikes_core)
    add_test(NAME test_spikes_transient_session
        COMMAND test_spikes_transient_session)

    add_executable(test_spikes_transient_session_c_api
        tests/test_spikes_transient_session_c_api.cpp)
    target_link_libraries(test_spikes_transient_session_c_api PRIVATE spikes_c_api)
    add_test(NAME test_spikes_transient_session_c_api
        COMMAND test_spikes_transient_session_c_api)

    add_executable(test_spikes_console_dashboard
        tests/test_spikes_console_dashboard.cpp)
    target_link_libraries(test_spikes_console_dashboard PRIVATE spikes_dashboard)
    add_test(NAME test_spikes_console_dashboard
        COMMAND test_spikes_console_dashboard)
    add_test(NAME test_spikes_console_script
        COMMAND spikes_console
            ${CMAKE_CURRENT_SOURCE_DIR}/examples/spikes/electrothermal_dashboard.spkc
            --script ${CMAKE_CURRENT_SOURCE_DIR}/examples/spikes/dashboard_commands.txt
            --capacity 32)

    # These native suites use assert() as their fail-fast test primitive. Keep
    # assertions active in Release qualification builds instead of allowing
    # NDEBUG to turn the executables into no-op smoke tests.
    foreach(SPIKE_ASSERT_TEST IN ITEMS
            test_peec test_via_transition_mesh_input test_reference_plane_antipad_mesh_input test_generalized_reference_plane_mesh_input test_planar_topology test_spikes_core
            test_spikes_c_api test_spikes_transient test_spikes_transient_c_api
            test_spikes_transient_session test_spikes_transient_session_c_api
            test_spikes_console_dashboard)
        if(MSVC)
            target_compile_options(${SPIKE_ASSERT_TEST} PRIVATE /UNDEBUG)
        else()
            target_compile_options(${SPIKE_ASSERT_TEST} PRIVATE -UNDEBUG)
        endif()
    endforeach()
endif()

# ============================================================================
# Python Bindings (nanobind)
# ============================================================================

option(BUILD_PYTHON_BINDINGS "Build Python bindings" ON)
if(BUILD_PYTHON_BINDINGS)
    message(STATUS "Building Python bindings with nanobind...")
    
    # Find Python (nanobind requires "Python" not "Python3")
    find_package(Python COMPONENTS Interpreter Development REQUIRED)
    message(STATUS "Python: ${Python_VERSION}")
    message(STATUS "Python Include: ${Python_INCLUDE_DIRS}")
    message(STATUS "Python Library: ${Python_LIBRARIES}")
    
    # Find nanobind
    find_package(nanobind CONFIG REQUIRED)
    message(STATUS "nanobind: Found")
    
    # Create Python module
    nanobind_add_module(spike_peec_native
        python/bindings/spike_bindings.cpp
    )
    spike_enable_legacy_hpc(spike_peec_native)
    
    # Link against SPIKE libraries
    target_link_libraries(spike_peec_native PRIVATE
        spike_peec
        spike_transition_handoff
        spike_geometry
        spike_thermal
        spike_math
        spike_peec_volume_matrix
    )
    
    # Set output directory
    set_target_properties(spike_peec_native PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/python"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/python"
    )
    
    message(STATUS "Python module will be built as: spike_peec_native")
    message(STATUS "Output directory: ${CMAKE_SOURCE_DIR}/python")
endif()

# ============================================================================
# Documentation
# ============================================================================

message(STATUS "SPIKE v${PROJECT_VERSION} - ${CMAKE_BUILD_TYPE} build")
message(STATUS "C++ Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "C++ Standard: C++${CMAKE_CXX_STANDARD}")
message(STATUS "OpenMP: ${OpenMP_CXX_VERSION}")
message(STATUS "Eigen3: ${Eigen3_VERSION}")
