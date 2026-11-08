#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build Blender 5.2+ for native Linux ARM64 on Snapdragon 8s Gen 3.
# The generated code targets Cortex-X4 but forcibly disables SVE/SVE2 because
# Android/proot commonly hides SVE from HWCAP even when the silicon has it.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
source "$project_dir/build-settings.sh"

# Prefer locally extracted tools only when explicitly present.
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

# Hard-code the target CPU. Native detection is unreliable inside proot and
# would also make CI artifacts depend on whichever runner happened to execute.
cpu_flag="${BLENDER_CPU_FLAGS:--mcpu=cortex-x4+nosve+nosve2}"
[[ "$cpu_flag" != *[[:space:]]* ]] || { echo 'BLENDER_CPU_FLAGS must be one -mcpu token.' >&2; exit 1; }
[[ "$cpu_flag" == *cortex-x4* ]] || { echo 'BLENDER_CPU_FLAGS must target cortex-x4.' >&2; exit 1; }
[[ "$cpu_flag" == *+nosve* && "$cpu_flag" == *+nosve2* ]] || {
  echo 'BLENDER_CPU_FLAGS must contain both +nosve and +nosve2.' >&2
  exit 1
}
optimization_flag="${BLENDER_OPTIMIZATION_FLAG:--O3}"
# Fail early if this Clang cannot emit the exact requested CPU target.
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

as_bool() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) printf 'ON' ;;
    0|false|FALSE|no|NO|off|OFF|'') printf 'OFF' ;;
    *) echo "Invalid boolean value: $1" >&2; return 1 ;;
  esac
}
minimal_features="$(as_bool "${BLENDER_MINIMAL_FEATURES:-0}")"
if [[ "$minimal_features" == ON ]]; then
  with_embree=OFF
  with_oidn=OFF
else
  with_embree="$(as_bool "${BLENDER_WITH_EMBREE:-1}")"
  with_oidn="$(as_bool "${BLENDER_WITH_OIDN:-1}")"
fi

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
  -DWITH_CYCLES_EMBREE="$with_embree"
  -DWITH_OPENIMAGEDENOISE="$with_oidn"
)

echo "Configuring Blender $blender_version with Clang 21 / LLD / ThinLTO"
echo "  CPU flags: $cpu_flag"
echo "  Jobs: compile=$jobs heavy=$heavy_jobs link=$link_jobs"
echo "  Optional libraries: Embree=$with_embree OpenImageDenoise=$with_oidn"
"$cmake_bin" "${cmake_args[@]}" 2>&1 | tee logs/configure.log

python3 - "$build_dir/CMakeCache.txt" "$with_embree" "$with_oidn" <<'PYFEATURES'
import sys
from pathlib import Path

cache = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    if '=' in line and not line.startswith(('#', '//')):
        raw_key, value = line.split('=', 1)
        cache[raw_key.split(':', 1)[0]] = value.upper()

required = {
    'WITH_CYCLES': 'ON',
    'WITH_VULKAN_BACKEND': 'ON',
    'WITH_OPENGL_BACKEND': 'ON',
    'WITH_CYCLES_EMBREE': sys.argv[2],
    'WITH_OPENIMAGEDENOISE': sys.argv[3],
}
disabled = (
    'WITH_CYCLES_DEVICE_CUDA',
    'WITH_CYCLES_DEVICE_OPTIX',
    'WITH_CYCLES_DEVICE_HIP',
    'WITH_CYCLES_DEVICE_HIPRT',
    'WITH_CYCLES_DEVICE_ONEAPI',
)
errors = []
for key, expected in required.items():
    actual = cache.get(key)
    if actual != expected:
        errors.append(f'{key}: expected {expected}, got {actual or "missing"}')
for key in disabled:
    if cache.get(key) == 'ON':
        errors.append(f'{key}: must be OFF')
if errors:
    raise SystemExit('Feature matrix validation failed:\n' + '\n'.join(errors))
print('FEATURE_MATRIX_VERIFIED CPU Cycles, Vulkan, OpenGL; GPU compute backends OFF',
      'Embree=' + sys.argv[2], 'OpenImageDenoise=' + sys.argv[3], flush=True)
PYFEATURES

python3 verify-compile-flags.py \
  "$build_dir/compile_commands.json" \
  --cpu-flag="$cpu_flag" \
  --lto-flag=-flto=thin \
  --output logs/compile-flags.json

"$cmake_bin" --build "$build_dir" --parallel "$jobs" 2>&1 | tee -a logs/build.log
"$cmake_bin" --install "$build_dir" 2>&1 | tee logs/install.log

python3 verify-compile-flags.py \
  "$build_dir/compile_commands.json" \
  --cpu-flag="$cpu_flag" \
  --lto-flag=-flto=thin \
  --binary "$install_dir/blender" \
  --output logs/compile-flags.json
"$install_dir/blender" --version | tee logs/version.log

python3 - "$metadata_file" "$build_dir" "$cpu_flag" "$optimization_flag" \
  "$jobs" "$heavy_jobs" "$link_jobs" "$with_embree" "$with_oidn" <<'PYINFO'
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
with_embree, with_oidn = sys.argv[8:10]

cache = {}
for line in (build_dir / 'CMakeCache.txt').read_text().splitlines():
    if '=' in line and not line.startswith(('#', '//')):
        raw_key, value = line.split('=', 1)
        cache[raw_key.split(':', 1)[0]] = value

def compiler_version(path):
    if not path:
        return None
    return subprocess.check_output([path, '--version'], text=True).splitlines()[0]

def package_version(name):
    try:
        return subprocess.check_output(
            ['dpkg-query', '-W', '-f=${Version}', name],
            text=True, stderr=subprocess.DEVNULL).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None

info = json.loads(metadata_file.read_text())
try:
    if platform.freedesktop_os_release:
        build_os = platform.freedesktop_os_release()
    else:
        build_os = None
except (AttributeError, OSError):
    build_os = None
try:
    recipe_commit = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
except (OSError, subprocess.CalledProcessError):
    recipe_commit = None

def cache_bool(name, default=False):
    value = cache.get(name, '').upper()
    if not value:
        return default
    if value in {'ON', 'TRUE', '1', 'YES'}:
        return True
    if value in {'OFF', 'FALSE', '0', 'NO'}:
        return False
    return default

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
    vulkan_backend=cache_bool('WITH_VULKAN_BACKEND'),
    opengl_backend=cache_bool('WITH_OPENGL_BACKEND'),
    cycles_device_cpu=True,
    embree=cache_bool('WITH_CYCLES_EMBREE', with_embree == 'ON'),
    openimagedenoise=cache_bool('WITH_OPENIMAGEDENOISE', with_oidn == 'ON'),
    mesa_vulkan_drivers=package_version('mesa-vulkan-drivers'),
    libgl1_mesa_dri=package_version('libgl1-mesa-dri'),
    libvulkan1=package_version('libvulkan1'),
    mesa_ppa=os.environ.get('MESA_PPA_USED') or None,
    runner_image=os.environ.get('ImageOS') or os.environ.get('RUNNER_IMAGE') or None,
    recipe_commit=recipe_commit,
)
metadata_file.write_text(json.dumps(info, indent=2) + '\n')
print(f'Updated {metadata_file}', flush=True)
PYINFO

echo "Blender installed under: $install_dir"
