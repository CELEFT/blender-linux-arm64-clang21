# Blender Linux ARM64 for Snapdragon 8s Gen 3

Unofficial Blender 5.2+ builds for ARM64 Linux containers (proot/chroot) on Snapdragon 8s Gen 3.

Releases are distributed as portable `bin/lib/share` `.tar.xz` archives, not `.deb` packages. The tree includes `bin/blender`, `lib/blender/`, a `.desktop` file and a desktop-entry installer.

The device only exposes three usable rendering/graphics backends:

- **CPU Cycles**
- **Vulkan**
- **OpenGL**

This recipe therefore retains normal Blender release features and removes only unsupported GPU compute backends and non-application targets. CUDA, OptiX, HIP/HIPRT and oneAPI are disabled, and SVE/SVE2 code generation is forcibly disabled because Android/proot commonly hides SVE from `HWCAP`. The installed launcher additionally detects Mesa Freedreno (`msm` DRI), Turnip/Freedreno Vulkan ICDs and repairs runtime paths that commonly break inside proot.

This project is not affiliated with or endorsed by the Blender Foundation. Chinese guide: [docs/SNAPDRAGON-8S-GEN3.zh-CN.md](docs/SNAPDRAGON-8S-GEN3.zh-CN.md).

## What is kept and removed

Retained from Blender's normal release feature profile:

- CPU Cycles, OSL, Embree, path guiding and OpenImageDenoise
- USD/Hydra/MaterialX, Alembic, OpenVDB/NanoVDB
- Freestyle, fluid/ocean simulation and OpenXR
- FFmpeg, libsndfile, Audaspace, OpenAL, PulseAudio and JACK
- Python/NumPy, common image and mesh IO, OpenSubdiv, TBB and OpenColorIO
- Internationalization and normal Blender Python add-on support
- Vulkan and OpenGL viewport backends

Removed because they are unusable or not applicable on this target:

- CUDA, OptiX, HIP, HIPRT and oneAPI devices
- CUDA/HIP/oneAPI binary kernel builders
- Metal backend (Apple-only)
- Cycles standalone, standalone GUI and standalone Hydra render delegate
- Importable `bpy` Python module target
- TBB malloc proxy (normal TBB allocator is used)
- Tests, static libraries, development headers, CMake/pkg-config files and Python bytecode caches during packaging

The portable archive still contains the normal Blender application; trimming only removes unsupported backends, non-application build targets and build-only payload.

## Fixed build policy

| Item | Value |
| --- | --- |
| Target device | Snapdragon 8s Gen 3 (Cortex-X4 + Cortex-A720 + Cortex-A520) |
| CI runner | Ubuntu 26.04 ARM64 / `ubuntu-26.04-arm` |
| Blender | Newest stable 5.2.x, or 5.3.x once a stable tag exists |
| Compiler | Clang 21 + LLD 21 |
| CPU flags | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| Execution backend | CPU Cycles |
| Graphics backends | Vulkan + OpenGL |
| GPU compute | Disabled |
| Dependencies | Blender official precompiled ARM64 libraries |

The official precompiled ARM64 dependency bundle avoids most `make deps` failures on ARM64. Source and library commits are recorded in `BUILD-INFO.json`. `fetch-dependency-source.py` remains available for dependency-source auditing or mirror download.

Blender's default ARM64 `-march=armv8.2-a+dotprod+fp16+lse` SIMD flag is disabled (`WITH_COMPILER_SIMD=OFF`). Otherwise it is appended after `-mcpu` and overrides the Cortex-X4 target/scheduling policy. The build verifier rejects any conflicting `-march=` or `-mtune=` option in a translation unit.

## Install and run

Download the portable `.tar.xz` and `SHA256SUMS` from one release:

```sh
sha256sum --ignore-missing -c SHA256SUMS
tar -xJf blender-*-linux-arm64-*-snapdragon8s.tar.xz
cd blender-*-linux-arm64-*-snapdragon8s
./bin/blender --version
./bin/blender --background scene.blend --render-frame 1
```

No system installation is required. The archive uses this portable layout:

```text
blender-<version>-linux-arm64-<os>-snapdragon8s/
├── bin/blender                    # launcher
├── lib/blender/
│   ├── blender                    # raw executable
│   ├── blender-launcher.py
│   ├── BUILD-INFO.json
│   ├── <version>/                 # datafiles, python, scripts
│   ├── lib/                       # bundled shared libraries
│   └── license/
├── share/applications/blender-linux-arm64.desktop
├── share/icons/hicolor/scalable/apps/blender-linux-arm64.svg
├── share/doc/blender-linux-arm64/
├── install-desktop.sh
├── README.md
├── RELEASING.md
└── LICENSE
```

The raw executable is `lib/blender/blender`. Prefer `bin/blender`, because the launcher applies proot and Freedreno compatibility automatically.

### Desktop entry

The archive includes:

- `share/applications/blender-linux-arm64.desktop`
- `share/icons/hicolor/scalable/apps/blender-linux-arm64.svg`
- `install-desktop.sh`

For a user-specific desktop entry with the correct absolute path:

```sh
./install-desktop.sh
```

This writes `~/.local/share/applications/blender-linux-arm64.desktop` and copies the icon under `~/.local/share/icons`. Re-run the script if you move the extracted directory.

The bundled `share/applications/blender-linux-arm64.desktop` uses `Exec=blender`; it is suitable for manual installation when `bin/` is in `PATH`.

## Proot/chroot compatibility

The launcher applies the following fixes outside information-only commands such as `--version`:

1. Creates a writable `XDG_RUNTIME_DIR` fallback when the host runtime directory is missing or inaccessible.
2. Removes a stale `WAYLAND_DISPLAY` when its socket is not visible, allowing X11 fallback.
3. Sets a writable `MESA_SHADER_CACHE_DIR` under the Blender cache directory.
4. Detects Mesa Freedreno/Turnip driver files and sets loader hints.
5. Preserves explicit user choices for display and GPU driver environment variables.

Inspect the reports:

```sh
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/proot.json"
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/freedreno.json"
```

Disable either compatibility layer:

```sh
BLENDER_PROOT_COMPAT=0 blender
BLENDER_FREEDRENO_COMPAT=0 blender
```

## Mesa Freedreno / Turnip compatibility

When a graphics device is present and the user has not chosen a driver explicitly:

| Detected item | Applied environment |
| --- | --- |
| `msm_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=msm` |
| `freedreno_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=freedreno` |
| `kgsl_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=kgsl` |
| `freedreno_icd*.json` / `turnip_icd*.json` | `VK_DRIVER_FILES` and legacy `VK_ICD_FILENAMES` |

The launcher recognizes `/dev/dri/renderD*` and `/dev/kgsl-3d0`. Existing `MESA_LOADER_DRIVER_OVERRIDE`, `GALLIUM_DRIVER`, `VK_DRIVER_FILES` or `VK_ICD_FILENAMES` values are preserved.

Before blaming Blender, verify the container graphics stack:

```sh
vulkaninfo --summary
ls -l /dev/dri /dev/kgsl-3d0 2>/dev/null
find /usr/lib/aarch64-linux-gnu/dri -maxdepth 1 \
  \( -iname '*msm*' -o -iname '*freedreno*' \)
```

The portable archive does not bundle Mesa/Turnip. Install matching Mesa ARM64 packages in the container and ensure the render node is mounted.

## Graphics selection

The installed command defaults to **Auto**:

1. Try hardware Vulkan.
2. Fall back to hardware OpenGL.
3. Fall back to Mesa software OpenGL.

Auto runs a small factory-settings render for each candidate and caches the result in `${XDG_CACHE_HOME:-~/.cache}/blender-linux-arm64/`. Batch CPU jobs skip the probe and use software OpenGL.

```sh
BLENDER_GRAPHICS_MODE=hardware blender
BLENDER_GRAPHICS_MODE=software blender
blender --gpu-backend vulkan
blender --gpu-backend opengl
```

If the Vulkan viewport fails, use `BLENDER_GRAPHICS_MODE=software` or select OpenGL in Blender preferences.

## Build from source

Build natively on ARM64; cross-compilation is not supported by this recipe.

```sh
sudo apt update
sudo apt install -y \
  git git-lfs cmake ninja-build build-essential pkg-config binutils desktop-file-utils \
  clang-21 lld-21 llvm-21 libclang-rt-21-dev python3 python3-dev xz-utils \
  libx11-dev libxxf86vm-dev libxi-dev libxfixes-dev libxrender-dev \
  libxrandr-dev libxcursor-dev libxinerama-dev libegl-dev libegl1-mesa-dev \
  libwayland-dev libdecor-0-dev libdbus-1-dev libxkbcommon-dev \
  libsm-dev libice-dev libvulkan-dev vulkan-tools \
  libpulse-dev libjack-jackd2-dev libasound2-dev \
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

Build:

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
- validates the backend matrix from CMake cache;
- checks every C++/C translation unit through `compile_commands.json`;
- removes build-only/test payload with `prune-install.py`;
- records CPU flags, complete feature flags, Freedreno files and install size in `logs/build-info.json`.

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

python3 verify-proot.py
```

Expected markers:

- `BUILD_VERIFIED`
- `FEATURE_MATRIX_VERIFIED`
- `BACKEND_MATRIX_VERIFIED`
- `CPU_FLAGS_VERIFIED`
- `PROOT_FREEDRENO_COMPAT_VERIFIED`
- `UI_VERIFIED`
- `VULKAN_VERIFIED` when a usable Vulkan ICD exists

## GitHub Actions

The manual workflow [`.github/workflows/manual-build.yml`](.github/workflows/manual-build.yml) runs on `ubuntu-26.04-arm` and:

- installs Clang 21/LLD 21 and optionally a Mesa PPA;
- installs Mesa DRI/Vulkan, `libdrm-freedreno1` and the normal audio development headers;
- logs available `msm`/Freedreno DRI modules and Freedreno/Turnip ICDs;
- runs the proot/Freedreno launcher self-test;
- caches prepared source/LFS with `actions/cache/save@v4` and `if: always()`;
- builds with the exact CPU/LTO flags and validates that only CPU/Vulkan/OpenGL remain enabled;
- verifies CPU Cycles, software OpenGL, GUI startup and the full feature matrix;
- treats a Vulkan probe failure on a GPU-less hosted runner as a warning;
- prunes build-only payload, strips ELF files and creates a portable `bin/lib/share` `.tar.xz` with xz level 9;
- uploads artifacts and publishes a release only when `publish_release` is enabled.

The `build_jobs` input offers 2/4/6 parallel jobs. No automatic release is performed by default.

## Device checklist

1. Record container OS, kernel, Mesa/Turnip version and `vulkaninfo --summary`.
2. Confirm `/dev/dri/renderD128` or `/dev/kgsl-3d0` is visible.
3. Check `~/.cache/blender-linux-arm64/proot.json` and `freedreno.json`.
4. Confirm SVE is hidden in the actual execution environment.
5. Run a small Cycles CPU render and separate Vulkan/OpenGL viewport tests.
6. Use cooling during sustained Cycles rendering; the SoC hits a thermal wall quickly.
7. On OOM during link or rendering, use `BLENDER_BUILD_JOBS=2`, close background apps and provide swap. ThinLTO final linking is limited to one job by default.

## Compatibility and limitations

- Generated code is tuned for Cortex-X4 and is not intended for older ARM64 CPUs.
- Blender's generated code excludes SVE/SVE2, but system Mesa/Turnip libraries must also be built compatibly.
- Freedreno auto-detection requires a visible render node and Mesa `msm`/Freedreno modules.
- The hosted portable archive is built on Ubuntu 26.04 ARM64; other distributions require a native rebuild.
- CPU Cycles is the only compute path. CUDA/OptiX/HIP/HIPRT/oneAPI are not shipped.
- Exact source and ARM64 library commits, enabled features and install size are recorded in `BUILD-INFO.json`.

## Source and licensing

Blender source is unmodified. The binary distribution and repository scripts use **GPL-3.0-or-later**; see [LICENSE](LICENSE). Third-party copyright and license notices are preserved in the installation's `license/` directory. No warranty is provided.

Upstream projects: [Blender](https://projects.blender.org/blender/blender), [Linux ARM64 libraries](https://projects.blender.org/blender/lib-linux_arm64).
