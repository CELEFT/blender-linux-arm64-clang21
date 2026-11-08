# SPDX-License-Identifier: GPL-3.0-or-later
#
# Blender release options for Snapdragon 8s Gen 3 Linux containers
# (Cortex-X4 + Cortex-A720 + Cortex-A520, proot/chroot, CPU Cycles).
#
# The compiler/CPU flags are injected by build-blender.sh so they can be
# validated before CMake configures the tree. This file only fixes the
# feature matrix that must stay identical across local and CI builds.

include("${CMAKE_CURRENT_LIST_DIR}/windows-arm64-features.cmake")

# Render with the CPU and expose the Vulkan/OpenGL viewport backends. All GPU
# compute backends are force-disabled by windows-arm64-features.cmake.
set(WITH_CYCLES ON CACHE BOOL "" FORCE)
# Blender has no separate device-CPU option; CPU is part of WITH_CYCLES.
# The marker is retained for compatibility with the requested CMake matrix.
set(WITH_CYCLES_DEVICE_CPU ON CACHE BOOL "" FORCE)
set(WITH_OPENGL_BACKEND ON CACHE BOOL "" FORCE)
set(WITH_VULKAN_BACKEND ON CACHE BOOL "" FORCE)

# Never emit runtime CPU detection or -march=native code paths: the phone is
# often inside proot where /proc/cpuinfo and HWCAP cannot be trusted. The exact
# Cortex-X4 target and the no-SVE decision are supplied from the command line.
set(WITH_CYCLES_NATIVE_ONLY OFF CACHE BOOL "" FORCE)
set(WITH_CPU_CHECK OFF CACHE BOOL "" FORCE)

# ThinLTO is enabled through CMAKE_INTERPROCEDURAL_OPTIMIZATION. CMake's Clang
# support uses -flto=thin. Keep one link job to avoid OOM during the final LTO
# link on 8-12 GiB phones and constrained runners.
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON CACHE BOOL "" FORCE)

# Optional libraries are deliberately switchable. They are enabled by default
# when using Blender's official ARM64 prebuilt libraries, and can be disabled
# with BLENDER_MINIMAL_FEATURES=1 when either dependency fails to build.
if(DEFINED ENV{BLENDER_WITH_EMBREE})
  set(WITH_CYCLES_EMBREE "$ENV{BLENDER_WITH_EMBREE}" CACHE BOOL "" FORCE)
endif()
if(DEFINED ENV{BLENDER_WITH_OIDN})
  set(WITH_OPENIMAGEDENOISE "$ENV{BLENDER_WITH_OIDN}" CACHE BOOL "" FORCE)
endif()
