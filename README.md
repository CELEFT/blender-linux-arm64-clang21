# Blender Linux ARM64 — Snapdragon 8s Gen 3

Unofficial Blender 5.2+ builds for ARM64 Linux containers (proot/chroot) on Snapdragon 8s Gen 3 devices.

The build targets Cortex-X4, uses Clang 21 + LLD 21 + ThinLTO, renders with CPU Cycles, and exposes Vulkan and OpenGL viewport backends. SVE and SVE2 code generation is deliberately disabled: the silicon supports SVE2, but Android kernels/containers commonly hide the feature from `HWCAP`, so an SVE instruction would crash with `SIGILL` on the device.

This project is not affiliated with or endorsed by the Blender Foundation. A Chinese build/handoff guide is available at [docs/SNAPDRAGON-8S-GEN3.zh-CN.md](docs/SNAPDRAGON-8S-GEN3.zh-CN.md).

## Fixed build policy

| Item | Value |
| --- | --- |
| Target device | Snapdragon 8s Gen 3 (Cortex-X4 + Cortex-A720 + Cortex-A520) |
| Build runner | Ubuntu 26.04 ARM64 / GitHub `ubuntu-26.04-arm` |
| Blender | Newest stable 5.2.x, or 5.3.x once upstream publishes a stable tag |
| Compiler | Clang 21 + LLD 21 |
| CPU flags | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| Graphics | CPU Cycles + Vulkan/OpenGL viewport |
| Disabled compute | CUDA, OptiX, HIP/HIPRT, oneAPI and their binary kernels |
| Optional libraries | Embree and OpenImageDenoise ON by default; both can be disabled together |

The recipe uses Blender's official pre-compiled ARM64 dependency bundle by default. This avoids most `make deps` failures on ARM64 while still recording exact source, library and dependency commits. `fetch-dependency-source.py` is available when the corresponding dependency sources are needed for auditing or a future source build.

## Install and run

Download the `.deb` installer and `SHA256SUMS` from one release into one directory:

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

## Graphics selection on the phone

The installed command defaults to **Auto**:

1. Try hardware Vulkan.
2. Fall back to hardware OpenGL.
3. Fall back to Mesa software OpenGL.

Auto runs a tiny factory-settings render for each candidate and caches the result in `${XDG_CACHE_HOME:-~/.cache}/blender-linux-arm64/`. Batch CPU jobs skip the probe and use software OpenGL.

Override for one run:

```sh
BLENDER_GRAPHICS_MODE=hardware blender
BLENDER_GRAPHICS_MODE=software blender
```

To force a specific backend:

```sh
blender --gpu-backend vulkan
blender --gpu-backend opengl
```

Vulkan is provided by the device's Mesa/Turnip installation, not bundled in the Blender `.deb`. A known-good target combination is Mesa 26.2.6/Turnip exposed through the container. Check it before blaming Blender:

```sh
vulkaninfo --summary
```

If the viewport crashes on Vulkan but works with OpenGL, set:

```sh
export BLENDER_GRAPHICS_MODE=software
```

or select OpenGL in Blender preferences. The build itself still requires Vulkan headers/libs at compile time.

## Build from source

Build natively on ARM64. Cross-compilation is not supported by this recipe.

Ubuntu 26.04 ARM64 is the CI/reference build environment. Install the toolchain and runtime headers:

```sh
sudo apt update
sudo apt install -y \
  git git-lfs cmake ninja-build build-essential pkg-config dpkg-dev binutils \
  clang-21 lld-21 llvm-21 libclang-rt-21-dev python3 python3-dev xz-utils \
  libx11-dev libxxf86vm-dev libxi-dev libxfixes-dev libxrender-dev \
  libxrandr-dev libxcursor-dev libxinerama-dev libegl-dev libegl1-mesa-dev \
  libwayland-dev libdecor-0-dev libdbus-1-dev libxkbcommon-dev \
  libsm-dev libice-dev libvulkan-dev vulkan-tools mesa-vulkan-drivers \
  libpulse-dev libjack-jackd2-dev libasound2-dev libgl1-mesa-dri libegl-mesa0 libopengl0 \
  xvfb xauth
```

Clone the recipe and fetch Blender plus the matching official ARM64 libraries:

```sh
git clone https://github.com/CELEFT/blender-linux-arm64-clang21.git
cd blender-linux-arm64-clang21
./prepare-source.sh
```

Pin a supported stable release when required:

```sh
BLENDER_VERSION=5.2.3 ./prepare-source.sh
```

The source downloader uses the Blender Git host first and GitHub as a fallback. Override either endpoint with `BLENDER_SOURCE_URL` / `BLENDER_LIBRARY_URL` for a domestic or private mirror.

Build and install:

```sh
./build-blender.sh
```

Useful controls:

```sh
# Low-memory phone/container: two compile jobs and one link job.
BLENDER_BUILD_JOBS=2 ./build-blender.sh

# If Embree or OpenImageDenoise fails to build/link, use the documented fallback.
BLENDER_MINIMAL_FEATURES=1 ./build-blender.sh

# Reuse a different build/install location.
BLENDER_BUILD_DIR=/path/to/build BLENDER_INSTALL_DIR=/path/to/install ./build-blender.sh
```

`build-blender.sh` refuses to run unless the compiler accepts the exact Cortex-X4 no-SVE target, verifies every C/C++/ASM translation unit through `compile_commands.json`, and records the policy in `logs/build-info.json`. If `BLENDER_CPU_FLAGS` is overridden it must still contain both `+nosve` and `+nosve2`.

The default install directory is `~/.local/opt/blender-<version>-linux-arm64`. The default build directory is `build/<version>`.

## Verify a build

CPU Cycles, build features, software OpenGL and a small render:

```sh
project_dir="$PWD"
source ./build-settings.sh
xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --background --factory-startup \
  --python-exit-code 1 --python verify-build.py
```

A graphics desktop is needed for the GUI startup test:

```sh
xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --factory-startup \
  --python-exit-code 1 --python verify-ui.py
```

Vulkan backend check (requires a usable Vulkan ICD):

```sh
xvfb-run -a -s '-screen 0 1280x720x24' \
  "$install_dir/blender" --gpu-backend vulkan -noaudio \
  --factory-startup --python-exit-code 1 --python verify-vulkan.py
```

Expected markers:

- `BUILD_VERIFIED`
- `CPU_FLAGS_VERIFIED`
- `UI_VERIFIED`
- `VULKAN_VERIFIED` when a Vulkan ICD is available

## GitHub Actions

The manual workflow [`.github/workflows/manual-build.yml`](.github/workflows/manual-build.yml) runs on `ubuntu-26.04-arm`. It:

- installs Clang 21/LLD 21 and optionally the Mesa PPA;
- restores/stores the prepared source and LFS cache around the download stage, including `if: always()` cache saving;
- optionally downloads all pinned dependency source archives into the cache;
- builds with `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin`;
- verifies CPU Cycles, software OpenGL and GUI startup;
- treats a Vulkan probe failure on a GPU-less hosted runner as a warning, not a build verdict;
- packages the `.deb`, source archive, `BUILD-INFO.json` and checksums;
- publishes a GitHub Release only when `publish_release` is enabled.

Use the `minimal_features` input when Embree/OIDN are the failure point, and `build_jobs=2` when the runner or device is RAM-constrained. The default is no automatic release, so artifacts can be inspected first.

## Device checklist before reporting a Blender bug

1. Record the container OS, kernel, Mesa/Turnip version and `vulkaninfo --summary` output.
2. Confirm SVE is hidden in the actual execution environment. A proot shell may see a different `HWCAP` than the host.
3. Run `blender --version` and a small Cycles CPU render.
4. Test Vulkan and OpenGL separately with `--gpu-backend vulkan` / `--gpu-backend opengl`.
5. Use a cooling fan. A sustained Cycles render on this SoC hits a thermal wall quickly.
6. On OOM during link or while rendering, reduce `BLENDER_BUILD_JOBS`, close background apps, and provide swap. The final ThinLTO link is deliberately limited to one job.

## Compatibility and limitations

- Generated code is tuned for Cortex-X4. It is not intended for older ARM64 CPUs.
- SVE/SVE2 are explicitly absent from Blender's own generated code, but device Mesa/Turnip and system libraries must also be built compatibly.
- Hosted `.deb` packages target Ubuntu 26.04 ARM64. Other distributions require a native rebuild and separate testing.
- CPU Cycles is the rendering path. Hardware GPU compute backends are not shipped.
- Exact source and ARM64 library commits are recorded in `BUILD-INFO.json`.

## Source and licensing

Blender source is unmodified. The binary distribution and repository scripts use **GPL-3.0-or-later**; see [LICENSE](LICENSE). Third-party copyright and license notices are preserved in the installation's `license/` directory. No warranty is provided.

Upstream projects: [Blender](https://projects.blender.org/blender/blender), [Linux ARM64 libraries](https://projects.blender.org/blender/lib-linux_arm64).
