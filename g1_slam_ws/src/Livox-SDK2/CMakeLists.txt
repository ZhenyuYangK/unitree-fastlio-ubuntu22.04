cmake_minimum_required(VERSION 3.14)

project(livox_sdk2 VERSION 0.0.2)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
find_package(Threads REQUIRED)
option(LIVOX_BUILD_SAMPLES "Build Livox SDK example programs" OFF)

set(CMAKE_CXX_STANDARD 11)

message(STATUS "main project dir: " ${PROJECT_SOURCE_DIR})

if (CMAKE_CROSSCOMPILING)
	set(THREADS_PTHREAD_ARG
		"PLEASE_FILL_OUT-FAILED_TO_RUN"
		CACHE STRING "Result from TRY_RUN" FORCE)
endif()

if (UNIX)
	set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -pthread")
endif(UNIX)

add_subdirectory(sdk_core)
if(LIVOX_BUILD_SAMPLES)
  add_subdirectory(samples)
endif()

configure_package_config_file(
  cmake/livox_sdk2Config.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/livox_sdk2Config.cmake"
  INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/livox_sdk2"
)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/livox_sdk2ConfigVersion.cmake"
  VERSION "${PROJECT_VERSION}"
  COMPATIBILITY SameMajorVersion
)
install(EXPORT livox_sdk2Targets
  FILE livox_sdk2Targets.cmake
  NAMESPACE livox_sdk2::
  DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/livox_sdk2"
)
install(FILES
  "${CMAKE_CURRENT_BINARY_DIR}/livox_sdk2Config.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/livox_sdk2ConfigVersion.cmake"
  DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/livox_sdk2"
)
