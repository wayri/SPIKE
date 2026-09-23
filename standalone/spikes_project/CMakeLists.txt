cmake_minimum_required(VERSION 3.24)
project(SPIKES VERSION 0.3.0 LANGUAGES CXX)

set(SPIKES_ENGINE_PRERELEASE "beta.1" CACHE STRING
    "SPIKES engine prerelease identifier")
set(SPIKES_ENGINE_VERSION
    "${PROJECT_VERSION}-${SPIKES_ENGINE_PRERELEASE}")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BUILD_TESTING "Build the native SPIKES tests" ON)
option(SPIKES_BUILD_STUDIO "Build the SPIKES Studio desktop workbench" OFF)

find_package(Eigen3 3.4 REQUIRED NO_MODULE)
find_package(OpenMP REQUIRED)

set(SPIKES_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/engine/src/spikes")

add_library(spikes_core STATIC
    ${SPIKES_SOURCE_DIR}/dc_solver.cpp
    ${SPIKES_SOURCE_DIR}/osdi_device.cpp
    ${SPIKES_SOURCE_DIR}/transient_solver.cpp
    ${SPIKES_SOURCE_DIR}/transient_session.cpp
)
target_include_directories(spikes_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/engine/src")
target_link_libraries(spikes_core PRIVATE Eigen3::Eigen OpenMP::OpenMP_CXX)
set_target_properties(spikes_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(spikes_c_api SHARED ${SPIKES_SOURCE_DIR}/c_api.cpp)
target_include_directories(spikes_c_api PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/engine/src")
target_link_libraries(spikes_c_api PRIVATE spikes_core)
target_compile_definitions(spikes_c_api PUBLIC SPIKES_SHARED PRIVATE SPIKES_BUILDING_LIBRARY)

add_library(spikes_dashboard STATIC ${SPIKES_SOURCE_DIR}/console_dashboard.cpp)
target_include_directories(spikes_dashboard PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/engine/src")
target_link_libraries(spikes_dashboard PUBLIC spikes_core)
set_target_properties(spikes_dashboard PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_executable(spikes_console ${SPIKES_SOURCE_DIR}/console_main.cpp)
target_link_libraries(spikes_console PRIVATE spikes_dashboard)
target_compile_definitions(spikes_console PRIVATE
    SPIKES_ENGINE_VERSION="${SPIKES_ENGINE_VERSION}")

add_executable(spikes_osdi_worker ${SPIKES_SOURCE_DIR}/osdi_worker_main.cpp)
target_link_libraries(spikes_osdi_worker PRIVATE spikes_core)

if(WIN32)
    add_executable(spikes_appcontainer_launcher ${SPIKES_SOURCE_DIR}/appcontainer_launcher.cpp)
    target_link_libraries(spikes_appcontainer_launcher PRIVATE userenv advapi32)
endif()

if(MSVC)
    target_compile_options(spikes_core PRIVATE /EHsc /fp:strict /W4 /permissive-)
    target_compile_options(spikes_dashboard PRIVATE /EHsc /fp:strict /W4 /permissive-)
    target_compile_options(spikes_c_api PRIVATE /EHsc /W4 /permissive-)
    target_compile_options(spikes_console PRIVATE /EHsc /fp:strict /W4 /permissive-)
    target_compile_options(spikes_osdi_worker PRIVATE /EHsc /fp:strict /W4 /permissive-)
else()
    target_compile_options(spikes_core PRIVATE -fno-fast-math -ffp-contract=off -Wall -Wextra)
    target_compile_options(spikes_dashboard PRIVATE -fno-fast-math -ffp-contract=off -Wall -Wextra)
endif()

install(TARGETS spikes_core spikes_c_api spikes_dashboard spikes_console spikes_osdi_worker
    LIBRARY DESTINATION lib ARCHIVE DESTINATION lib RUNTIME DESTINATION bin)
if(WIN32)
    install(TARGETS spikes_appcontainer_launcher RUNTIME DESTINATION bin)
endif()
install(DIRECTORY "${SPIKES_SOURCE_DIR}/" DESTINATION include/spikes
    FILES_MATCHING PATTERN "*.h" PATTERN "*.hpp")
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/studio/schemas/"
    DESTINATION share/spikes/studio/schemas)
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/studio/library/"
    DESTINATION share/spikes/studio/library)
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/studio/docs/"
    DESTINATION share/spikes/studio/docs)

if(BUILD_TESTING)
    enable_testing()
    foreach(TEST_NAME IN ITEMS
            test_spikes_dc test_spikes_c_api test_spikes_transient
            test_spikes_transient_c_api test_spikes_transient_session
            test_spikes_transient_session_c_api test_spikes_console_dashboard)
        add_executable(${TEST_NAME} "${CMAKE_CURRENT_SOURCE_DIR}/tests/native/${TEST_NAME}.cpp")
    endforeach()
    target_link_libraries(test_spikes_dc PRIVATE spikes_core)
    target_link_libraries(test_spikes_c_api PRIVATE spikes_c_api)
    target_link_libraries(test_spikes_transient PRIVATE spikes_core)
    target_link_libraries(test_spikes_transient_c_api PRIVATE spikes_c_api)
    target_link_libraries(test_spikes_transient_session PRIVATE spikes_core)
    target_link_libraries(test_spikes_transient_session_c_api PRIVATE spikes_c_api)
    target_link_libraries(test_spikes_console_dashboard PRIVATE spikes_dashboard)
    target_compile_definitions(test_spikes_dc PRIVATE
        SPIKES_TEST_OSDI_ARTIFACT="${CMAKE_CURRENT_SOURCE_DIR}/models/fixtures/spikes_linear_resistor.osdi"
        SPIKES_TEST_OSDI04_CAPACITOR="${CMAKE_CURRENT_SOURCE_DIR}/models/fixtures/hdl-qualification-wave5-capacitor.osdi"
        SPIKES_TEST_OSDI04_NOISE="${CMAKE_CURRENT_SOURCE_DIR}/models/fixtures/hdl-qualification-wave5-noise.osdi"
        SPIKES_TEST_BSIM_BULK_OSDI="${CMAKE_CURRENT_SOURCE_DIR}/models/bsimbulk-107.2.1-windows-x64.osdi"
        SPIKES_TEST_BSIM_CMG_OSDI="${CMAKE_CURRENT_SOURCE_DIR}/models/bsimcmg-112.1.0-windows-x64.osdi")
    target_compile_definitions(test_spikes_transient PRIVATE
        SPIKES_TEST_OSDI04_CAPACITOR="${CMAKE_CURRENT_SOURCE_DIR}/models/fixtures/hdl-qualification-wave5-capacitor.osdi")
    foreach(TEST_NAME IN ITEMS
            test_spikes_dc test_spikes_c_api test_spikes_transient
            test_spikes_transient_c_api test_spikes_transient_session
            test_spikes_transient_session_c_api test_spikes_console_dashboard)
        if(MSVC)
            target_compile_options(${TEST_NAME} PRIVATE /UNDEBUG)
        else()
            target_compile_options(${TEST_NAME} PRIVATE -UNDEBUG)
        endif()
        add_test(NAME ${TEST_NAME} COMMAND ${TEST_NAME})
    endforeach()
    add_test(NAME test_spikes_console_script COMMAND spikes_console
        "${CMAKE_CURRENT_SOURCE_DIR}/examples/spikes/electrothermal_dashboard.spkc"
        --script "${CMAKE_CURRENT_SOURCE_DIR}/examples/spikes/dashboard_commands.txt"
        --capacity 32)
endif()

if(SPIKES_BUILD_STUDIO)
    add_subdirectory(studio/native)
endif()
