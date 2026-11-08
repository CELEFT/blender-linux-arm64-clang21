#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Blender 5.2+ build for native Linux ARM64 on Snapdragon 8s Gen 3.
# The generated code targets Cortex-X4 with SVE/SVE2 forcibly disabled because
# Android/proot commonly hides SVE from HWCAP even when the silicon has it.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
source "$project_dir/build-settings.sh"

if [[ -d "$project_dir/tools/usr/bin" ]]; then
  export PATH="$project_dir/tools/usr/bin:$PATH"
fi
if [[ -d "$project_dir/tools/usr/lib/aarch64-linux-gnu" ]]; then
  export LD_LIBRARY_PATH="$project_dir/tools/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

export CC="${CC:-clang-21}"
export CXX="${CXX:-clang++-21}"
export LD="${LD:-ld.lld-21}"
export AR="${AR:-llvm-ar-21}"
export RANLIB="${RANLIB:-llvm-ranlib-21}"

[[ "$(uname -m)" == aarch64 ]] || { echo 'This recipe targets native Linux ARM64.' >&2; exit 1; }
[[ -f source/CMakeLists.txt && -d source/lib/linux_arm64 ]] || {
  echo 'Run ./prepare-source.sh first.' >&2
  exit 1
}

find_tool() {
  local command_name="$1" resolved
  resolved="$(command -v "$command_name" 2>/dev/null || true)"
  [[ -n "$resolved" ]] || { echo "Missing build tool: $command_name" >&2; exit 1; }
  printf '%s\n' "$resolved"
}

cmake_bin="$(find_tool cmake)"
ninja_bin="$(find_tool ninja)"
cc_bin="$(find_tool "$CC")"
cxx_bin="$(find_tool "$CXX")"
ld_bin="$(find_tool "$LD")"
ar_bin="$(find_tool "$AR")"
ranlib_bin="$(find_tool "$RANLIB")"
readelf_bin="$(find_tool readelf)"

cc_version="$("$cc_bin" --version | head -1)"
cxx_version="$("$cxx_bin" --version | head -1)"
for version in "$cc_version" "$cxx_version"; do
  [[ "$version" == *"clang version 21."* ]] || {
    echo "This recipe requires Clang 21, got: $version" >&2
    exit 1
  }
done
ld_version="$("$ld_bin" --version | head -1)"
[[ "$ld_version" == *"LLD 21."* ]] || {
  echo "This recipe requires LLD 21, got: $ld_version" >&2
  exit 1
}
echo "Compiler verified: $cc_version"
echo "Linker verified: $ld_version"

# Native CPU detection is unreliable inside proot and makes artifacts depend on
# whichever runner compiled them. This must remain an explicit one-token policy.
cpu_flag="${BLENDER_CPU_FLAGS:--mcpu=cortex-x4+nosve+nosve2}"
[[ "$cpu_flag" != *[[:space:]]* ]] || { echo 'BLENDER_CPU_FLAGS must be one -mcpu token.' >&2; exit 1; }
[[ "$cpu_flag" == *cortex-x4* ]] || { echo 'BLENDER_CPU_FLAGS must target cortex-x4.' >&2; exit 1; }
[[ "$cpu_flag" == *+nosve* && "$cpu_flag" == *+nosve2* ]] || {
  echo 'BLENDER_CPU_FLAGS must contain both +nosve and +nosve2.' >&2
  exit 1
}
optimization_flag="${BLENDER_OPTIMIZATION_FLAG:--O3}"

probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/blender-cpu-probe.XXXXXX")"
trap 'rm -rf -- "$probe_dir"' EXIT
printf 'int main(void) { return 0; }\n' > "$probe_dir/probe.c"
"$cc_bin" "$cpu_flag" "$optimization_flag" -flto=thin -fuse-ld=lld \
  "$probe_dir/probe.c" -o "$probe_dir/probe"
"$readelf_bin" -h "$probe_dir/probe" | grep -q 'AArch64' || {
  echo 'Compiler probe did not produce an AArch64 executable.' >&2
  exit 1
}
echo "CPU target verified: $cpu_flag"

jobs="${BLENDER_BUILD_JOBS:-2}"
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'BLENDER_BUILD_JOBS must be a positive integer.' >&2; exit 1; }
heavy_jobs="${BLENDER_HEAVY_JOBS:-$(( jobs > 1 ? jobs - 1 : 1 ))}"
[[ "$heavy_jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'BLENDER_HEAVY_JOBS must be a positive integer.' >&2; exit 1; }
link_jobs="${BLENDER_LINK_JOBS:-1}"
[[ "$link_jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'BLENDER_LINK_JOBS must be a positive integer.' >&2; exit 1; }

mkdir -p logs
: > logs/configure.log
: > logs/build.log
: > logs/install.log

cmake_args=(
  -S source
  -B "$build_dir"
  -G Ninja
  -DCMAKE_MAKE_PROGRAM="$ninja_bin"
  -C config/snapdragon-8s-gen3.cmake
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_C_COMPILER="$cc_bin"
  -DCMAKE_CXX_COMPILER="$cxx_bin"
  -DCMAKE_ASM_COMPILER="$cc_bin"
  -DCMAKE_LINKER="$ld_bin"
  -DCMAKE_AR="$ar_bin"
  -DCMAKE_RANLIB="$ranlib_bin"
  -DCMAKE_C_COMPILER_AR="$ar_bin"
  -DCMAKE_CXX_COMPILER_AR="$ar_bin"
  -DCMAKE_C_COMPILER_RANLIB="$ranlib_bin"
  -DCMAKE_CXX_COMPILER_RANLIB="$ranlib_bin"
  -DCMAKE_C_FLAGS="$cpu_flag $optimization_flag -flto=thin"
  -DCMAKE_CXX_FLAGS="$cpu_flag $optimization_flag -flto=thin"
  -DCMAKE_ASM_FLAGS="$cpu_flag"
  -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld"
  -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld"
  -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld"
  -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
  -DCMAKE_INSTALL_PREFIX="$install_dir"
  -DNINJA_MAX_NUM_PARALLEL_COMPILE_JOBS="$jobs"
  -DNINJA_MAX_NUM_PARALLEL_COMPILE_HEAVY_JOBS="$heavy_jobs"
  -DNINJA_MAX_NUM_PARALLEL_LINK_JOBS="$link_jobs"
  -DWITH_INSTALL_PORTABLE=ON
  -DWITH_CPU_CHECK=OFF
  -DWITH_COMPILER_SIMD=OFF
  -DWITH_CYCLES_NATIVE_ONLY=OFF
  -DWITH_VULKAN_BACKEND=ON
  -DWITH_OPENGL_BACKEND=ON
  -DWITH_CYCLES=ON
  # Blender builds the CPU device whenever WITH_CYCLES is ON. Keep this marker
  # for compatibility with the project brief's requested CMake matrix.
  -DWITH_CYCLES_DEVICE_CPU=ON
  -DWITH_CYCLES_DEVICE_CUDA=OFF
  -DWITH_CYCLES_DEVICE_OPTIX=OFF
  -DWITH_CYCLES_DEVICE_HIP=OFF
  -DWITH_CYCLES_DEVICE_HIPRT=OFF
  -DWITH_CYCLES_DEVICE_ONEAPI=OFF
  -DWITH_CYCLES_CUDA_BINARIES=OFF
  -DWITH_CYCLES_HIP_BINARIES=OFF
  -DWITH_CYCLES_ONEAPI_BINARIES=OFF
)

echo "Configuring Blender $blender_version with Clang 21 / LLD / ThinLTO"
echo "  CPU flags: $cpu_flag"
echo "  Jobs: compile=$jobs heavy=$heavy_jobs link=$link_jobs"
"$cmake_bin" "${cmake_args[@]}" 2>&1 | tee logs/configure.log

python3 - "$build_dir/CMakeCache.txt" <<'PYFEATURES'
import sys
from pathlib import Path

cache = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    if '=' in line and not line.startswith(('#', '//')):
        raw_key, value = line.split('=', 1)
        cache[raw_key.split(':', 1)[0]] = value.upper()

required_on = (
    'WITH_CYCLES',
    'WITH_PYTHON_INSTALL',
    'WITH_VULKAN_BACKEND',
    'WITH_OPENGL_BACKEND',
    'WITH_CYCLES_OSL',
    'WITH_CYCLES_EMBREE',
    'WITH_CYCLES_PATH_GUIDING',
    'WITH_OPENIMAGEDENOISE',
    'WITH_USD',
    'WITH_HYDRA',
    'WITH_MATERIALX',
    'WITH_ALEMBIC',
    'WITH_OPENVDB',
    'WITH_NANOVDB',
    'WITH_FREESTYLE',
    'WITH_MOD_FLUID',
    'WITH_MOD_OCEANSIM',
    'WITH_XR_OPENXR',
    'WITH_CODEC_FFMPEG',
    'WITH_CODEC_SNDFILE',
    'WITH_AUDASPACE',
    'WITH_OPENAL',
    'WITH_PULSEAUDIO',
    'WITH_JACK',
    'WITH_INTERNATIONAL',
    'WITH_LIBMV',
    'WITH_DRACO',
    'WITH_MESHOPTIMIZER',
    'WITH_POTRACE',
    'WITH_HARU',
)
required_off = (
    'WITH_CYCLES_DEVICE_CUDA',
    'WITH_CYCLES_DEVICE_OPTIX',
    'WITH_CYCLES_DEVICE_HIP',
    'WITH_CYCLES_DEVICE_HIPRT',
    'WITH_CYCLES_DEVICE_ONEAPI',
    'WITH_CYCLES_DEVICE_METAL',
    'WITH_CYCLES_CUDA_BINARIES',
    'WITH_CYCLES_HIP_BINARIES',
    'WITH_CYCLES_ONEAPI_BINARIES',
    'WITH_CYCLES_STANDALONE',
    'WITH_CYCLES_STANDALONE_GUI',
    'WITH_CYCLES_HYDRA_RENDER_DELEGATE',
    'WITH_PYTHON_MODULE',
    'WITH_TBB_MALLOC_PROXY',
    'WITH_COMPILER_SIMD',
)
errors = []
for key in required_on:
    if cache.get(key) != 'ON':
        errors.append(f'{key}: expected ON, got {cache.get(key, "missing")}')
for key in required_off:
    if cache.get(key) == 'ON':
        errors.append(f'{key}: must be OFF')
if cache.get('CMAKE_BUILD_TYPE') != 'RELEASE':
    errors.append(f'CMAKE_BUILD_TYPE: expected RELEASE, got {cache.get("CMAKE_BUILD_TYPE", "missing")}')
if errors:
    raise SystemExit('Backend feature matrix validation failed:\n' + '\n'.join(errors))
print('BACKEND_MATRIX_VERIFIED CPU Cycles/Vulkan/OpenGL; GPU compute backends disabled', flush=True)
PYFEATURES

python3 verify-compile-flags.py \
  "$build_dir/compile_commands.json" \
  --cpu-flag="$cpu_flag" \
  --lto-flag=-flto=thin \
  --output logs/compile-flags.json

"$cmake_bin" --build "$build_dir" --parallel "$jobs" 2>&1 | tee -a logs/build.log
"$cmake_bin" --install "$build_dir" 2>&1 | tee logs/install.log

python3 prune-install.py "$install_dir" --report logs/prune-install.json
python3 verify-compile-flags.py \
  "$build_dir/compile_commands.json" \
  --cpu-flag="$cpu_flag" \
  --lto-flag=-flto=thin \
  --binary "$install_dir/blender" \
  --output logs/compile-flags.json
"$install_dir/blender" --version | tee logs/version.log

python3 - "$metadata_file" "$build_dir" "$cpu_flag" "$optimization_flag" \
  "$jobs" "$heavy_jobs" "$link_jobs" "$install_dir" <<'PYINFO'
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

metadata_file = Path(sys.argv[1])
build_dir = Path(sys.argv[2])
cpu_flag = sys.argv[3]
optimization_flag = sys.argv[4]
jobs, heavy_jobs, link_jobs = map(int, sys.argv[5:8])
install_dir = Path(sys.argv[8])

cache = {}
for line in (build_dir / 'CMakeCache.txt').read_text().splitlines():
    if '=' in line and not line.startswith(('#', '//')):
        raw_key, value = line.split('=', 1)
        cache[raw_key.split(':', 1)[0]] = value

FEATURE_OPTIONS = (
    'WITH_CYCLES', 'WITH_CYCLES_OSL', 'WITH_CYCLES_EMBREE',
    'WITH_CYCLES_PATH_GUIDING', 'WITH_OPENIMAGEDENOISE',
    'WITH_VULKAN_BACKEND', 'WITH_OPENGL_BACKEND', 'WITH_PYTHON_INSTALL',
    'WITH_USD', 'WITH_HYDRA', 'WITH_MATERIALX', 'WITH_ALEMBIC',
    'WITH_OPENVDB', 'WITH_NANOVDB', 'WITH_FREESTYLE', 'WITH_MOD_FLUID',
    'WITH_MOD_OCEANSIM', 'WITH_XR_OPENXR', 'WITH_CODEC_FFMPEG',
    'WITH_CODEC_SNDFILE', 'WITH_AUDASPACE', 'WITH_OPENAL',
    'WITH_PULSEAUDIO', 'WITH_JACK', 'WITH_PIPEWIRE',
    'WITH_PIPEWIRE_DYNLOAD', 'WITH_JACK_DYNLOAD', 'WITH_PULSEAUDIO_DYNLOAD',
    'WITH_SDL_AUDIO', 'WITH_INTERNATIONAL', 'WITH_LIBMV', 'WITH_DRACO',
    'WITH_MESHOPTIMIZER', 'WITH_OPENVDB_BLOSC',
    'WITH_OPENVDB_3_ABI_COMPATIBLE', 'WITH_PYTHON_INSTALL_REQUESTS',
    'WITH_DOC_MANPAGE', 'WITH_TBB_MALLOC_PROXY', 'WITH_CYCLES_STANDALONE',
    'WITH_CYCLES_STANDALONE_GUI', 'WITH_CYCLES_HYDRA_RENDER_DELEGATE',
    'WITH_PYTHON_MODULE', 'WITH_CYCLES_DEVICE_CUDA',
    'WITH_CYCLES_DEVICE_OPTIX', 'WITH_CYCLES_DEVICE_HIP',
    'WITH_CYCLES_DEVICE_HIPRT', 'WITH_CYCLES_DEVICE_ONEAPI',
    'WITH_CYCLES_DEVICE_METAL', 'WITH_CYCLES_CUDA_BINARIES',
    'WITH_CYCLES_HIP_BINARIES', 'WITH_CYCLES_ONEAPI_BINARIES',
    'WITH_POTRACE', 'WITH_HARU', 'WITH_FFTW3', 'WITH_OPENSUBDIV',
)

def cache_bool(name, default=False):
    value = cache.get(name, '').upper()
    if value in {'ON', 'TRUE', '1', 'YES'}:
        return True
    if value in {'OFF', 'FALSE', '0', 'NO'}:
        return False
    return default

def compiler_version(path):
    if not path or not Path(path).is_file():
        return None
    try:
        return subprocess.check_output([path, '--version'], text=True).splitlines()[0]
    except (OSError, subprocess.CalledProcessError):
        return None

def package_version(name):
    try:
        return subprocess.check_output(
            ['dpkg-query', '-W', '-f=${Version}', name],
            text=True, stderr=subprocess.DEVNULL).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None

def mesa_files(patterns, directories):
    found = []
    for directory in map(Path, directories):
        if not directory.is_dir():
            continue
        for pattern in patterns:
            found.extend(str(path) for path in sorted(directory.glob(pattern)))
    return sorted(set(found))

info = json.loads(metadata_file.read_text())
try:
    build_os = platform.freedesktop_os_release()
except (AttributeError, OSError):
    build_os = None
try:
    recipe_commit = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
except (OSError, subprocess.CalledProcessError):
    recipe_commit = None

features = {name: cache_bool(name) for name in FEATURE_OPTIONS}
install_size = sum(path.stat().st_size for path in install_dir.rglob('*')
                   if path.is_file() and not path.is_symlink())
info.update(
    build_os=build_os,
    build_machine=platform.machine(),
    target_device='Snapdragon 8s Gen 3 (Cortex-X4 + Cortex-A720 + Cortex-A520)',
    target_cpu='cortex-x4',
    cpu_flags=cpu_flag,
    optimization_flag=optimization_flag,
    sve='disabled',
    sve2='disabled',
    lto='thin',
    compiler=compiler_version(cache.get('CMAKE_C_COMPILER')),
    compiler_cxx=compiler_version(cache.get('CMAKE_CXX_COMPILER')),
    linker='lld',
    build_jobs={'compile': jobs, 'heavy': heavy_jobs, 'link': link_jobs},
    cycles_native_only=cache_bool('WITH_CYCLES_NATIVE_ONLY'),
    compiler_default_simd=cache_bool('WITH_COMPILER_SIMD', True),
    features=features,
    feature_profile='cpu-vulkan-opengl',
    execution_backends=['CPU'],
    graphics_backends=['VULKAN', 'OPENGL'],
    gpu_compute_backends_disabled=['CUDA', 'OPTIX', 'HIP', 'HIPRT', 'ONEAPI'],
    vulkan_backend=features['WITH_VULKAN_BACKEND'],
    opengl_backend=features['WITH_OPENGL_BACKEND'],
    cycles_device_cpu=True,
    embree=features['WITH_CYCLES_EMBREE'],
    openimagedenoise=features['WITH_OPENIMAGEDENOISE'],
    prune_install=True,
    install_size_bytes=install_size,
    mesa_vulkan_drivers=package_version('mesa-vulkan-drivers'),
    libgl1_mesa_dri=package_version('libgl1-mesa-dri'),
    libdrm_freedreno=package_version('libdrm-freedreno1'),
    libvulkan1=package_version('libvulkan1'),
    mesa_ppa=os.environ.get('MESA_PPA_USED') or None,
    runner_image=os.environ.get('ImageOS') or os.environ.get('RUNNER_IMAGE') or None,
    freedreno={
        'dri': mesa_files(('*msm_dri.so', '*freedreno*dri.so'),
                          ('/usr/lib/aarch64-linux-gnu/dri', '/usr/local/lib/aarch64-linux-gnu/dri',
                           '/usr/lib/dri', '/usr/lib64/dri', '/vendor/lib64/dri',
                           '/system/lib64/dri')),
        'vulkan_icd': mesa_files(('*freedreno*icd*.json', '*turnip*icd*.json'),
                                 ('/usr/share/vulkan/icd.d', '/usr/local/share/vulkan/icd.d',
                                  '/etc/vulkan/icd.d', '/vendor/etc/vulkan/icd.d')),
    },
    recipe_commit=recipe_commit,
)
metadata_file.write_text(json.dumps(info, indent=2) + '\n')
print(f'Updated {metadata_file}', flush=True)
PYINFO

echo "Blender installed under: $install_dir"
