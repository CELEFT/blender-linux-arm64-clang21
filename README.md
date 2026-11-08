# Slim Blender Linux ARM64 — Snapdragon 8s Gen 3

Unofficial **slim** Blender 5.2+ builds for ARM64 Linux containers (proot/chroot) on Snapdragon 8s Gen 3 devices.

The build targets Cortex-X4 with Clang 21 + LLD 21 + ThinLTO, renders with CPU Cycles, and exposes Vulkan and OpenGL viewport backends. SVE/SVE2 code generation is deliberately disabled because Android kernels and containers commonly hide SVE from `HWCAP`; executing an SVE instruction would otherwise terminate Blender with `SIGILL`.

The installed launcher also detects Mesa **Freedreno** (`msm` DRI) and **Turnip/Freedreno** Vulkan ICDs, so Adreno graphics can work in containers without manually exporting loader variables.

This project is not affiliated with or endorsed by the Blender Foundation. Chinese guide: [docs/SNAPDRAGON-8S-GEN3.zh-CN.md](docs/SNAPDRAGON-8S-GEN3.zh-CN.md).

## Slim feature profile

Enabled:

- CPU Cycles with the default SVM shading path
- Python and NumPy for Blender scripts
- OpenGL and Vulkan viewport backends
- Common image and mesh import/export
- OpenSubdiv, TBB, OpenColorIO and core modelling tools
- Adreno/Freedreno OpenGL and Turnip Vulkan auto-detection

Disabled to keep the package small:

- Cycles OSL, Embree, path guiding and OpenImageDenoise
- USD, Hydra, MaterialX, Alembic, OpenVDB and NanoVDB
- Freestyle, fluid/ocean simulation and OpenXR
- FFmpeg, libsndfile, Audaspace, OpenAL, PulseAudio and JACK
- Internationalization, Libmv, Draco/Meshoptimizer, Potrace/Haru
- Development headers, static libraries, Python tests and bytecode caches
- CUDA, OptiX, HIP/HIPRT, oneAPI and their binary kernels

Cycles rendering remains functional, but it is slower than a full build because Embree and OpenImageDenoise are intentionally absent.

## Fixed build policy

| Item | Value |
| --- | --- |
| Target device | Snapdragon 8s Gen 3 (Cortex-X4 + Cortex-A720 + Cortex-A520) |
| CI runner | Ubuntu 26.04 ARM64 / `ubuntu-26.04-arm` |
| Blender | Newest stable 5.2.x, or 5.3.x once a stable tag exists |
| Compiler | Clang 21 + LLD 21 |
| CPU flags | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| Graphics | CPU Cycles + Vulkan/OpenGL |
| Dependency source | Blender official precompiled ARM64 libraries by default |

The official precompiled ARM64 dependency bundle is used to avoid most `make deps` failures on ARM64 while source/library commits are recorded in `BUILD-INFO.json`. `fetch-dependency-source.py` remains available for auditing or mirror download of dependency sources.

## Install and run

Download the `.deb` and `SHA256SUMS` from one release into one directory:

```sh
sha256sum --ignore-missing -c SHA256SUMS
sudo apt install ./blender-linux-arm64_*.deb
blender
```

The package installs Blender under `/usr/lib/blender-linux-arm64`, adds `/usr/bin/blender`, and provides a desktop entry. It conflicts with a distribution `blender` package because both provide `/usr/bin/blender`.

```sh
blender --version
blender --background scene.blend --render-frame 1
```

The raw executable is `/usr/lib/blender-linux-arm64/blender`.

## Mesa Freedreno / Turnip compatibility

The packaged launcher applies these compatibility hints only when a graphics device is present and the user has not already chosen a driver:

| Detected item | Applied environment |
| --- | --- |
| `msm_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=msm` |
| `freedreno_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=freedreno` |
| `kgsl_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=kgsl` |
| `freedreno_icd*.json` / `turnip_icd*.json` | `VK_DRIVER_FILES` and legacy `VK_ICD_FILENAMES` |

It accepts DRM render nodes (`/dev/dri/renderD*`) and `/dev/kgsl-3d0`. Explicit user settings such as `MESA_LOADER_DRIVER_OVERRIDE=zink` or a custom `VK_DRIVER_FILES` are preserved. Disable auto detection with:

```sh
BLENDER_FREEDRENO_COMPAT=0 blender
```

Inspect what was selected:

```sh
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/freedreno.json"
```

Before blaming Blender, verify the container graphics stack:

```sh
vulkaninfo --summary
ls -l /dev/dri /dev/kgsl-3d0 2>/dev/null
find /usr/lib/aarch64-linux-gnu/dri -maxdepth 1 -iname '*msm*' -o -iname '*freedreno*'
```

The `.deb` does not bundle Mesa/Turnip. Install the matching Mesa ARM64 package for the container, and ensure `/dev/dri/renderD128` or `/dev/kgsl-3d0` is visible through proot/chroot.

## Graphics selection

The installed command defaults to **Auto**:

1. Try hardware Vulkan.
2. Fall back to hardware OpenGL.
3. Fall back to Mesa software OpenGL.

Auto runs a small factory-settings render for each candidate and caches the result in `${XDG_CACHE_HOME:-~/.cache}/blender-linux-arm64/`. Batch CPU jobs skip the probe and use software OpenGL.

Override for one run:

```sh
BLENDER_GRAPHICS_MODE=hardware blender
BLENDER_GRAPHICS_MODE=software blender
blender --gpu-backend vulkan
blender --gpu-backend opengl
```

If Vulkan viewport rendering fails:

```sh
export BLENDER_GRAPHICS_MODE=software
```

## Build from source

Build natively on ARM64; cross-compilation is not supported by this recipe.

```sh
sudo apt update
sudo apt install -y \
  git git-lfs cmake ninja-build build-essential pkg-config dpkg-dev binutils \
  clang-21 lld-21 llvm-21 libclang-rt-21-dev python3 python3-dev xz-utils \
  libx11-dev libxxf86vm-dev libxi-dev libxfixes-dev libxrender-dev \
  libxrandr-dev libxcursor-dev libxinerama-dev libegl-dev libegl1-mesa-dev \
  libwayland-dev libdecor-0-dev libdbus-1-dev libxkbcommon-dev \
  libsm-dev libice-dev libvulkan-dev vulkan-tools \
  mesa-vulkan-drivers libgl1-mesa-dri libegl-mesa0 libopengl0 libdrm-freedreno1 \
  xvfb xauth
```

Clone and prepare:

```sh
git clone https://github.com/CELEFT/blender-linux-arm64-clang21.git
cd blender-linux-arm64-clang21
./prepare-source.sh
```

Pin a stable release:

```sh
BLENDER_VERSION=5.2.3 ./prepare-source.sh
```

The source downloader tries the Blender Git host first and GitHub as fallback. Override endpoints with `BLENDER_SOURCE_URL` / `BLENDER_LIBRARY_URL` when using a domestic or private mirror.

Build and slim-install:

```sh
./build-blender.sh
```

Useful controls:

```sh
BLENDER_BUILD_JOBS=2 ./build-blender.sh
BLENDER_BUILD_DIR=/path/to/build BLENDER_INSTALL_DIR=/path/to/install ./build-blender.sh
```

`build-blender.sh`:

- requires Clang 21 and LLD 21;
- verifies the exact Cortex-X4 no-SVE compiler target;
- validates the slim feature matrix from CMake cache;
- checks every C/C++ translation unit through `compile_commands.json`;
- removes test/development payload with `slim-install.py`;
- records CPU flags, features, Freedreno files and package size in `logs/build-info.json`.

The default install directory is `~/.local/opt/blender-<version>-linux-arm64`; the default build directory is `build/<version>`.

## Verify a build

```sh
project_dir="$PWD"
source ./build-settings.sh

xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --background --factory-startup \
  --python-exit-code 1 --python verify-build.py

xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --factory-startup \
  --python-exit-code 1 --python verify-ui.py

xvfb-run -a -s '-screen 0 1280x720x24' \
  "$install_dir/blender" --gpu-backend vulkan -noaudio \
  --factory-startup --python-exit-code 1 --python verify-vulkan.py
```

Expected markers:

- `BUILD_VERIFIED`
- `SLIM_FEATURES_VERIFIED`
- `CPU_FLAGS_VERIFIED`
- `UI_VERIFIED`
- `FREEDRENO_COMPAT_VERIFIED`
- `VULKAN_VERIFIED` when a usable Vulkan ICD exists

## GitHub Actions

The manual workflow [`.github/workflows/manual-build.yml`](.github/workflows/manual-build.yml) runs on `ubuntu-26.04-arm` and:

- installs Clang 21/LLD 21 and optionally a Mesa PPA;
- installs Mesa DRI/Vulkan drivers plus `libdrm-freedreno1`;
- logs available `msm`/Freedreno DRI modules and Freedreno/Turnip ICDs;
- runs the Freedreno environment-detection self-test;
- caches prepared source/LFS with `actions/cache/save@v4` and `if: always()`;
- builds the slim profile with exact CPU/LTO flags;
- verifies CPU Cycles, software OpenGL, GUI startup and the feature matrix;
- treats a Vulkan probe failure on a GPU-less hosted runner as a warning;
- strips runtime binaries, prunes test/dev payload and compresses the `.deb` with xz level 9;
- uploads artifacts and publishes a release only when `publish_release` is enabled.

The `build_jobs` input offers 2/4/6 parallel jobs. No automatic release is performed by default.

## Device checklist

1. Record container OS, kernel, Mesa/Turnip version and `vulkaninfo --summary`.
2. Confirm `/dev/dri/renderD128` or `/dev/kgsl-3d0` is visible.
3. Check the launcher report at `~/.cache/blender-linux-arm64/freedreno.json`.
4. Confirm SVE is hidden in the actual execution environment.
5. Run a small Cycles CPU render and separate Vulkan/OpenGL viewport tests.
6. Use cooling during sustained Cycles rendering; the SoC hits a thermal wall quickly.
7. On OOM during link or rendering, use `BLENDER_BUILD_JOBS=2`, close background apps and provide swap. ThinLTO final linking is limited to one job by default.

## Compatibility and limitations

- Generated code is tuned for Cortex-X4 and is not intended for older ARM64 CPUs.
- Blender's generated code excludes SVE/SVE2, but system Mesa/Turnip libraries must also be built compatibly.
- Freedreno auto-detection requires a visible render node and Mesa `msm`/Freedreno modules.
- Hosted `.deb` packages target Ubuntu 26.04 ARM64; other distributions require a native rebuild.
- CPU Cycles is the only compute path. Optional heavy integrations listed above are absent by design.
- Exact source and ARM64 library commits, enabled features and install size are recorded in `BUILD-INFO.json`.

## Source and licensing

Blender source is unmodified. The binary distribution and repository scripts use **GPL-3.0-or-later**; see [LICENSE](LICENSE). Third-party copyright and license notices are preserved in the installation's `license/` directory. No warranty is provided.

Upstream projects: [Blender](https://projects.blender.org/blender/blender), [Linux ARM64 libraries](https://projects.blender.org/blender/lib-linux_arm64).
