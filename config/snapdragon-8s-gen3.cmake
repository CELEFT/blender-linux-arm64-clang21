# SPDX-License-Identifier: GPL-3.0-or-later
#
# Linux ARM64 application profile for Snapdragon 8s Gen 3 / proot containers.
# The device exposes three usable execution/graphics backends:
#   CPU Cycles, Vulkan, OpenGL.
#
# Keep Blender's normal release features. Only remove GPU compute backends and
# standalone targets that cannot be used by this Linux ARM64 configuration.

include("${CMAKE_CURRENT_LIST_DIR}/../source/build_files/cmake/config/blender_release.cmake")

# The three supported backends.
set(WITH_CYCLES ON CACHE BOOL "" FORCE)
# Blender builds the CPU device as part of WITH_CYCLES. This marker is kept for
# compatibility with the requested CMake matrix.
set(WITH_CYCLES_DEVICE_CPU ON CACHE BOOL "" FORCE)
set(WITH_VULKAN_BACKEND ON CACHE BOOL "" FORCE)
set(WITH_OPENGL_BACKEND ON CACHE BOOL "" FORCE)

# Never emit runtime CPU detection (-march=native). The exact Cortex-X4 +
# no-SVE policy is injected by build-blender.sh and validated per translation
# unit, because proot does not expose reliable CPU/HWCAP information.
set(WITH_CYCLES_NATIVE_ONLY OFF CACHE BOOL "" FORCE)
set(WITH_CPU_CHECK OFF CACHE BOOL "" FORCE)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON CACHE BOOL "" FORCE)

# Unsupported GPU compute backends: disable devices and their kernel builders.
set(WITH_CYCLES_DEVICE_CUDA OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_OPTIX OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_HIP OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_HIPRT OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_ONEAPI OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_METAL OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_CUDA_BINARIES OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_HIP_BINARIES OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_ONEAPI_BINARIES OFF CACHE BOOL "" FORCE)

# Not application backends: keep only the normal Blender application target.
set(WITH_CYCLES_STANDALONE OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_STANDALONE_GUI OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_HYDRA_RENDER_DELEGATE OFF CACHE BOOL "" FORCE)
set(WITH_PYTHON_MODULE OFF CACHE BOOL "" FORCE)

# TBB malloc proxy is known to be problematic on ARM64; the regular allocator
# is used instead. This does not remove any Blender feature.
set(WITH_TBB_MALLOC_PROXY OFF CACHE BOOL "" FORCE)
