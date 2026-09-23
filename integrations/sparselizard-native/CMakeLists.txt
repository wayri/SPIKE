# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.24)

project(spike_sparselizard_runtime LANGUAGES CXX)

if(WIN32 AND NOT MINGW)
  message(FATAL_ERROR
    "The reproducible Windows build currently targets native MSYS2 UCRT64/MinGW. "
    "MSVC support requires a separately pinned PETSc/MUMPS/SLEPc ABI bundle.")
endif()

set(SPARSELIZARD_SOURCE_DIR "" CACHE PATH "Path to the official sparseLizard source tree")
if(NOT EXISTS "${SPARSELIZARD_SOURCE_DIR}/src/sparselizard.h")
  message(FATAL_ERROR "SPARSELIZARD_SOURCE_DIR must point to an official sparseLizard source tree")
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(SLEPC REQUIRED IMPORTED_TARGET slepc-dmo)
pkg_check_modules(PETSC REQUIRED IMPORTED_TARGET petsc-dmo)
pkg_check_modules(MUMPS REQUIRED IMPORTED_TARGET mumps-dmo)
pkg_check_modules(OPENBLAS REQUIRED IMPORTED_TARGET openblas)
pkg_check_modules(METIS REQUIRED IMPORTED_TARGET metis)
pkg_check_modules(MSMPI REQUIRED IMPORTED_TARGET msmpi)

file(GLOB_RECURSE SPARSELIZARD_SOURCES CONFIGURE_DEPENDS
  "${SPARSELIZARD_SOURCE_DIR}/src/*.cpp")
file(GLOB_RECURSE SPARSELIZARD_HEADERS CONFIGURE_DEPENDS
  "${SPARSELIZARD_SOURCE_DIR}/src/*.h")

set(SPARSELIZARD_INCLUDE_DIRS "${SPARSELIZARD_SOURCE_DIR}/src")
foreach(header IN LISTS SPARSELIZARD_HEADERS)
  get_filename_component(header_dir "${header}" DIRECTORY)
  list(APPEND SPARSELIZARD_INCLUDE_DIRS "${header_dir}")
endforeach()
list(REMOVE_DUPLICATES SPARSELIZARD_INCLUDE_DIRS)

add_library(spike_sparselizard_core STATIC ${SPARSELIZARD_SOURCES})
target_include_directories(spike_sparselizard_core PUBLIC ${SPARSELIZARD_INCLUDE_DIRS})
target_compile_features(spike_sparselizard_core PUBLIC cxx_std_17)
target_compile_definitions(spike_sparselizard_core PUBLIC
  HAVE_BLAS
  HAVE_METIS
  HAVE_MPI
  HAVE_MUMPS
  HAVE_PETSC
  HAVE_SLEPC
  NOMINMAX
  # The MSYS2 PETSc package is configured as a C library. Its headers still
  # expose the C++ entry path, so supply the compiler intrinsics that a PETSc
  # C++ configuration would normally publish in petscconf.h.
  PETSC_FUNCTION_NAME_CXX=__func__
  PETSC_CXX_RESTRICT=__restrict__)
target_compile_options(spike_sparselizard_core PRIVATE
  $<$<CXX_COMPILER_ID:GNU>:-O3;-fopenmp;-Wno-return-type>)
target_link_options(spike_sparselizard_core PUBLIC
  $<$<CXX_COMPILER_ID:GNU>:-fopenmp>)
target_link_libraries(spike_sparselizard_core PUBLIC
  PkgConfig::SLEPC
  PkgConfig::PETSC
  PkgConfig::MUMPS
  PkgConfig::OPENBLAS
  PkgConfig::METIS
  PkgConfig::MSMPI)

add_executable(spike-sparselizard-runtime src/main.cpp)
target_link_libraries(spike-sparselizard-runtime PRIVATE spike_sparselizard_core)

install(TARGETS spike-sparselizard-runtime RUNTIME DESTINATION bin)
