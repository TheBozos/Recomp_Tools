cmake_minimum_required(VERSION 3.21)
project(@PROJECT@ LANGUAGES CXX)

# @TITLE@ (@REGION@, @SERIAL@) on BozoEngine: the game's EE code recompiled by bozo-recomp, every library and kernel
# call answered natively by the engine's runtime. No PS2 hardware model.
# The ELF comes from the player's own disc (scripts/extract_iso.sh puts it in game/).
#
# A SKELETON: it imports the engine and checks the ELF. The rest (the prepared image, the externals list, bozo-recomp's
# translation, the port's runtime and the executables @PREFIX@-headless and @EXE_NAME@) is this port's own work: copy
# it from a finished port (Onimusha_Recomp, Shinobido_WOTN_Recomp or Amplitude_Recomp) and rename.

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

set(@PREFIXU@_GAME_DIR "${CMAKE_SOURCE_DIR}/game" CACHE PATH "User-owned extracted disc files")
set(BOZO_ENGINE_DIR "${CMAKE_SOURCE_DIR}/BozoEngine" CACHE PATH "Pinned native engine source")
option(@PREFIXU@_WINDOW "Build the SDL3 native game window (@EXE_NAME@) next to @PREFIX@-headless" ON)
set(BOZO_APP ${@PREFIXU@_WINDOW} CACHE BOOL "" FORCE)
set(BOZO_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
add_subdirectory("${BOZO_ENGINE_DIR}" BozoEngine)

set(@PREFIX@_elf ${@PREFIXU@_GAME_DIR}/@ELFNAME@)
if(NOT EXISTS ${@PREFIX@_elf})
  message(FATAL_ERROR "${@PREFIX@_elf} not found: run scripts/extract_iso.sh <iso> first")
endif()
