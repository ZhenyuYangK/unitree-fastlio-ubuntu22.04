cmake_minimum_required(VERSION 3.5)
project(g1_relocalization)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(pcl_conversions REQUIRED)
find_package(pcl_ros REQUIRED)

find_package(PCL REQUIRED COMPONENTS
  common
  io
  filters
  registration
)

include_directories(
  include
  ${PCL_INCLUDE_DIRS}
)

add_definitions(${PCL_DEFINITIONS})

add_library(global_matcher src/global_matcher.cpp)
target_link_libraries(global_matcher ${PCL_LIBRARIES})

add_executable(
  g1_relocalization_node
  src/g1_relocalization_node.cpp
)

ament_target_dependencies(
  g1_relocalization_node
  rclcpp
  sensor_msgs
  geometry_msgs
  nav_msgs
  std_msgs
  tf2
  tf2_ros
  tf2_geometry_msgs
  pcl_conversions
  pcl_ros
)

target_link_libraries(
  g1_relocalization_node
  global_matcher
  ${PCL_LIBRARIES}
)

install(
  TARGETS g1_relocalization_node global_matcher
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_global_matcher test/test_global_matcher.cpp)
  target_link_libraries(test_global_matcher global_matcher ${PCL_LIBRARIES})
  ament_add_gtest(test_pose_buffer test/test_pose_buffer.cpp)
endif()

ament_package()
