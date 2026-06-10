cmake_minimum_required(VERSION 3.8)
project(fleet_safe_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch worlds
  DESTINATION share/${PROJECT_NAME}
)
install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

ament_package()
