# Releasing Blender Linux ARM64 (Snapdragon 8s Gen 3)

This document covers packaging and publishing. Installation, build controls, verification and the device checklist are in [README.md](README.md). The Chinese handoff guide is [docs/SNAPDRAGON-8S-GEN3.zh-CN.md](docs/SNAPDRAGON-8S-GEN3.zh-CN.md).

## Publish through GitHub Actions

Open **Actions → Build Blender ARM64 Snapdragon → Run workflow**.

- **Blender version:** blank selects the newest stable upstream tag. Pin a version such as `5.2.3` for a reproducible release; use a 5.3.x stable tag once upstream publishes one.
- **Dependency ref:** normally leave blank. Supply a compatible official ARM64 library commit or branch when automatic selection cannot find a matching bundle. The resolved commit is always recorded.
- **Runner:** defaults to `ubuntu-26.04-arm`. Override only with another native ARM64 runner when that label is unavailable.
- **Build jobs:** default `4`. Use `2` for memory-constrained runners or device builds.
- **Mesa PPA:** defaults to `ppa:kisak/kisak-mesa`. It is attempted but non-fatal; CI may fall back to the Ubuntu archive Mesa. Record the actual installed version in `logs/runtime-versions.txt` and `BUILD-INFO.json`.
- **Minimal features:** disables Embree and OpenImageDenoise if those dependencies are the failure point.
- **Download dependency sources:** warms and caches the pinned `dependency-sources/` directory.
- **Publish release:** off by default. Download and inspect artifacts before enabling a release run.

The workflow:

- builds natively on Ubuntu 26.04 ARM64;
- uses Clang 21, LLD 21 and ThinLTO with `-mcpu=cortex-x4+nosve+nosve2`;
- saves the prepared source/LFS cache after download with `actions/cache/save@v4` and `if: always()`;
- checks CPU Cycles, software OpenGL and GUI startup under Xvfb;
- runs a non-blocking Vulkan probe (hosted runners usually have no Turnip-compatible GPU);
- creates the Debian package, source archive, metadata and checksums;
- installs the generated `.deb` on the runner and verifies its Auto graphics launcher.

Vulkan failures on a hosted runner are reported as warnings, not build failures. A release still needs a real-device Vulkan/OpenGL/Cycles checklist before it should be handed to users.

## Release contents

| File | Contents |
| --- | --- |
| `blender-linux-arm64_<version>-<revision>+<build-os>_arm64.deb` | Installer with CLI/desktop launchers and Auto graphics selection. |
| `blender-<version>-source.tar.xz` | Blender source, recipe scripts, feature configuration, docs, workflow and dependency source manifest. |
| `BUILD-INFO.json` | Source/dependency commits, compiler, CPU flags, LTO, Vulkan/Embree/OIDN state and packaging metadata. |
| `SHA256SUMS` | Checksums for installer, source archive and metadata. |

GitHub also provides source ZIP/tarball of the tagged recipe repository. The attached source archive is the one that includes Blender's source.

Tags include the Blender version, target, run number and attempt, for example `v5.2.3-snapdragon8s-arm64-r12-a1`. Rebuilds receive separate tags/releases when publishing is enabled.

## Package a local build

Build and verify Blender first, then run:

```sh
./package-release.sh
```

Keep the same `BLENDER_INSTALL_DIR` setting used by the build. Packaging writes files to `release/`. It preserves third-party notices, adds the Auto launcher and desktop integration, and resolves system dependencies with `dpkg-shlibdeps`.

Set a positive revision if packaging another build of the same Blender version:

```sh
BLENDER_PACKAGE_REVISION=2 ./package-release.sh
```

Validate the assets:

```sh
cd release
sha256sum -c SHA256SUMS
```

The source archive intentionally includes the unmodified Blender source plus the exact recipe and dependency source manifest needed to audit/rebuild. It excludes Git metadata and the precompiled library payload. `BUILD-INFO.json` records the exact library commit so the dependency bundle can be fetched separately.

Source checkouts, downloaded libraries, build directories, logs and generated release files are ignored by Git. Commit recipe/documentation changes and attach generated installers/archives to releases rather than committing binaries.
