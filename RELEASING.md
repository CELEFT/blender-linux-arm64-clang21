# Releasing Blender Linux ARM64 (CPU/Vulkan/OpenGL)

This document covers packaging and publishing. Installation, proot/Freedreno compatibility, build controls and device checks are in [README.md](README.md). Chinese guide: [docs/SNAPDRAGON-8S-GEN3.zh-CN.md](docs/SNAPDRAGON-8S-GEN3.zh-CN.md).

## Publish through GitHub Actions

Open **Actions → Build Blender Linux ARM64 (CPU/Vulkan/OpenGL) → Run workflow**.

- **Blender version:** blank selects the newest stable upstream tag. Pin a version such as `5.2.3` for reproducible output; use a 5.3.x stable tag once available.
- **Dependency ref:** normally blank. Supply a compatible official ARM64 library commit/branch only when automatic selection fails.
- **Build jobs:** choose 2, 4 or 6. Use 2 on low-memory devices/runners; the final ThinLTO link remains a single job.
- **Mesa PPA:** defaults to `ppa:kisak/kisak-mesa`. It is optional and non-fatal; the workflow records the actual Mesa version and falls back to the Ubuntu archive if unavailable.
- **Publish release:** off by default. Inspect the artifact first, then rerun with publishing enabled if desired.

The workflow:

- builds natively on Ubuntu 26.04 ARM64;
- uses Clang 21, LLD 21 and ThinLTO with `-mcpu=cortex-x4+nosve+nosve2`;
- installs Mesa DRI/Vulkan, `libdrm-freedreno1` and normal Blender audio headers;
- logs Freedreno `msm`/DRI modules and Freedreno/Turnip Vulkan ICDs;
- runs `verify-proot.py` against proot runtime-path and Freedreno detection logic;
- saves prepared source/LFS with `actions/cache/save@v4` and `if: always()`;
- builds Blender's normal release features with only unsupported GPU compute backends disabled;
- checks CPU Cycles, software OpenGL, GUI startup and the complete feature matrix under Xvfb;
- runs a non-blocking Vulkan probe (hosted runners usually have no Adreno GPU);
- prunes tests/static/development payload, strips ELF files and creates an xz-9 `.deb`;
- installs the `.deb` and verifies its Auto/proot/Freedreno launcher.

Vulkan failures on a hosted runner are warnings, not build failures. A release still needs a real-device Vulkan/OpenGL/Cycles and Freedreno checklist before handoff.

## Release contents

| File | Contents |
| --- | --- |
| `blender-linux-arm64_<version>-<revision>+<build-os>_arm64.deb` | Installer with CLI/desktop launchers, Auto graphics, proot adaptation and Freedreno detection. |
| `blender-<version>-source.tar.xz` | Blender source, build scripts, backend profile, docs, workflow and dependency manifest. |
| `BUILD-INFO.json` | Source/dependency commits, compiler, CPU flags, LTO, backend/feature matrix, Mesa/Freedreno files and install size. |
| `SHA256SUMS` | Checksums for installer, source archive and metadata. |

GitHub also provides source ZIP/tarball for the tagged recipe commit. The attached source archive includes Blender's source.

Tags include the Blender version, target, run number and attempt, for example `v5.2.3-linux-arm64-cpu-vulkan-opengl-r12-a1`.

## Package a local build

Build and verify Blender first, then run:

```sh
./package-release.sh
```

Keep the same `BLENDER_INSTALL_DIR` used by the build. Packaging writes to `release/`, preserves third-party notices, adds the Auto/proot/Freedreno launcher and desktop integration, resolves system dependencies with `dpkg-shlibdeps`, strips ELF files and compresses the package with xz level 9.

To retain debug symbols:

```sh
BLENDER_STRIP_BINARIES=0 ./package-release.sh
```

Set a positive revision for another build of the same version:

```sh
BLENDER_PACKAGE_REVISION=2 ./package-release.sh
```

Validate assets:

```sh
cd release
sha256sum -c SHA256SUMS
```

The source archive includes unmodified Blender source plus the exact recipe and dependency source manifest needed to audit/rebuild. It excludes Git metadata and the precompiled library payload. `BUILD-INFO.json` records the exact library commit and backend/feature matrix.

Source checkouts, libraries, build directories, logs and generated release files are ignored by Git. Commit recipe/documentation changes and attach installers/archives to releases rather than committing binaries.
