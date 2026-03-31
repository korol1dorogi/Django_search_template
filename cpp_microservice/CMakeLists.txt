cmake_minimum_required(VERSION 3.16)
project(cpp_microservice VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(cpp_microservice
    main.cpp
    TextHandler.cpp
)

target_include_directories(cpp_microservice PRIVATE include)

# Для Windows линкуем Winsock
if(WIN32)
    target_link_libraries(cpp_microservice ws2_32)
    if(MINGW)
    add_definitions(-D_WIN32_WINNT=0x0A00)  # Windows 10
endif()
endif()

# Для Linux линкуем pthread
if(UNIX AND NOT APPLE)
    target_link_libraries(cpp_microservice pthread)
endif()

include(GNUInstallDirs)
install(TARGETS cpp_microservice
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
