cmake_minimum_required(VERSION 3.24)

project(spike_wx_desktop VERSION 0.2.5 LANGUAGES CXX)

if(NOT WIN32)
    message(FATAL_ERROR "The first SPIKE wxWidgets client milestone is Windows-only.")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(wxWidgets REQUIRED COMPONENTS base core aui html webview gl)
include(${wxWidgets_USE_FILE})
find_package(nlohmann_json CONFIG REQUIRED)
find_package(VTK CONFIG REQUIRED COMPONENTS
    CommonCore
    CommonDataModel
    FiltersCore
    FiltersGeneral
    FiltersSources
    InteractionStyle
    RenderingAnnotation
    RenderingCore
    RenderingOpenGL2
)

add_executable(spike-wx WIN32
    src/main.cpp
    src/domain_contracts.cpp
    src/native_frame.cpp
    src/report_writer.cpp
    src/request_builder.cpp
    src/vtk_viewport.cpp
    src/worker_client.cpp
)
target_include_directories(spike-wx PRIVATE include)
target_compile_definitions(spike-wx PRIVATE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
    SPIKE_WX_VERSION="${PROJECT_VERSION}"
)
target_link_libraries(spike-wx PRIVATE
    ${wxWidgets_LIBRARIES}
    nlohmann_json::nlohmann_json
    ${VTK_LIBRARIES}
)
if(MSVC)
    target_compile_options(spike-wx PRIVATE /W4 /permissive- /EHsc /utf-8)
endif()
vtk_module_autoinit(TARGETS spike-wx MODULES ${VTK_LIBRARIES})

include(CTest)
if(BUILD_TESTING)
    add_executable(spike-wx-request-tests
        tests/request_builder_test.cpp
        src/request_builder.cpp
    )
    target_include_directories(spike-wx-request-tests PRIVATE include)
    target_link_libraries(spike-wx-request-tests PRIVATE nlohmann_json::nlohmann_json)
    if(MSVC)
        target_compile_options(spike-wx-request-tests PRIVATE /W4 /permissive- /EHsc)
    endif()
    add_test(NAME spike-wx-request-tests COMMAND spike-wx-request-tests)

    add_executable(spike-wx-domain-contract-tests
        tests/domain_contracts_test.cpp
        src/domain_contracts.cpp
    )
    target_include_directories(spike-wx-domain-contract-tests PRIVATE include)
    target_link_libraries(spike-wx-domain-contract-tests PRIVATE nlohmann_json::nlohmann_json)
    if(MSVC)
        target_compile_options(spike-wx-domain-contract-tests PRIVATE /W4 /permissive- /EHsc)
    endif()
    add_test(NAME spike-wx-domain-contract-tests COMMAND spike-wx-domain-contract-tests)
endif()

install(TARGETS spike-wx RUNTIME DESTINATION .)
