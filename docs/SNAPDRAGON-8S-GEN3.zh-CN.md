# Blender Linux ARM64（骁龙 8s Gen 3 / proot）构建与交接指南

目标设备只使用三个后端：

- **CPU Cycles**
- **Vulkan**
- **OpenGL**

因此本项目**保留 Blender 正常 release 功能**，只移除 Linux ARM64 设备用不上的 GPU 计算后端和非应用构建目标，并针对 proot 容器的设备、运行时目录、Wayland/X11、Mesa Freedreno/Turnip 做兼容适配。

## 1. 目标与边界

| 项目 | 决策 |
| --- | --- |
| 目标设备 | 骁龙 8s Gen 3：Cortex-X4 + Cortex-A720 + Cortex-A520 |
| 运行环境 | Android 上的 proot/chroot Linux 容器 |
| 构建 runner | GitHub `ubuntu-26.04-arm` |
| 编译器 | Clang 21 + LLD 21 |
| 优化 | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| 计算后端 | CPU Cycles |
| 图形后端 | Vulkan、OpenGL |
| 移除的后端 | CUDA、OptiX、HIP、HIPRT、oneAPI、Metal、对应 kernel builder |
| 依赖 | Blender 官方 ARM64 预编译库 |

> 必须禁用 SVE/SVE2。Cortex-X4 硬件支持 SVE2，但 Android 内核和 proot 经常不暴露对应 HWCAP；执行 SVE 指令会直接 `Illegal instruction`。`build-blender.sh` 会拒绝不含 `+nosve+nosve2` 的 CPU flag 覆盖，并检查全部 C/C++ 编译命令。

## 2. 保留与移除的内容

保留 Blender release 的常规功能：

- CPU Cycles、OSL、Embree、Path Guiding、OpenImageDenoise；
- USD、Hydra、MaterialX、Alembic、OpenVDB、NanoVDB；
- Freestyle、流体/海洋模拟、OpenXR；
- FFmpeg、libsndfile、Audaspace、OpenAL、PulseAudio、JACK；
- Python/NumPy、常用图像和网格 IO、OpenSubdiv、TBB、OpenColorIO；
- 国际化、正常 Python add-on；
- Vulkan/OpenGL 视口。

移除：

- CUDA、OptiX、HIP、HIPRT、oneAPI 设备和 binary kernel builder；
- Metal（Apple-only）；
- Cycles standalone、standalone GUI、standalone Hydra render delegate；
- 可导入的 `bpy` Python module target；
- TBB malloc proxy（使用普通 TBB allocator）；
- 打包阶段删除 tests、静态库、开发头文件、CMake/pkg-config、Python 字节码缓存。

这不是把 Blender 主体功能删掉，而是让构建只包含该设备可用的后端，并清除构建/测试残留。

## 3. 编译策略

```text
-mcpu=cortex-x4+nosve+nosve2
-O3
-flto=thin
-fuse-ld=lld
```

`build-blender.sh` 会：

1. 检查 Clang 21、LLD 21；
2. 用探针编译验证 CPU target；
3. 校验 CMake 后端矩阵：CPU Cycles、Vulkan、OpenGL 开，GPU compute 关；
4. 检查 `compile_commands.json` 中所有 C/C++ translation unit 均使用 CPU flag 和 ThinLTO；
5. 检查安装后的 Blender 是 AArch64；
6. 运行 `prune-install.py` 删除测试/开发残留；
7. 将 feature/backend 矩阵、Freedreno 文件、install size 写入 `BUILD-INFO.json`。

## 4. Proot 兼容适配

`blender-launcher.py` 对非 `--version/--help` 启动执行以下修复：

1. **XDG_RUNTIME_DIR**
   - 如果宿主 runtime 目录在 proot 内不存在或不可写，创建
     `${TMPDIR:-/tmp}/runtime-<uid>`。
2. **Wayland socket**
   - 如果 `WAYLAND_DISPLAY` 指向的 socket 不可见，移除该变量；
   - 如果存在 X11 `DISPLAY`，设置 `XDG_SESSION_TYPE=x11`，避免 Blender 卡在不可用的 Wayland。
3. **Mesa shader cache**
   - 设置可写的 `MESA_SHADER_CACHE_DIR`，避免只读 HOME 或 proot 临时目录导致 shader cache 失败。
4. **Freedreno/Turnip**
   - 检测 `msm_dri.so`、`freedreno_dri.so`、`kgsl_dri.so`；
   - 检测 `freedreno_icd*.json`、`turnip_icd*.json`；
   - 仅在用户未显式指定驱动时设置 loader 环境。
5. **用户覆盖**
   - 已设置的 `MESA_LOADER_DRIVER_OVERRIDE`、`GALLIUM_DRIVER`、`VK_DRIVER_FILES`、`VK_ICD_FILENAMES` 不会被覆盖。

报告文件：

```sh
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/proot.json"
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/freedreno.json"
```

可分别关闭：

```sh
BLENDER_PROOT_COMPAT=0 blender
BLENDER_FREEDRENO_COMPAT=0 blender
```

## 5. Mesa Freedreno / Turnip 对应关系

| 检测目标 | 自动设置 |
| --- | --- |
| `msm_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=msm` |
| `freedreno_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=freedreno` |
| `kgsl_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=kgsl` |
| `freedreno_icd*.json` / `turnip_icd*.json` | `VK_DRIVER_FILES` + `VK_ICD_FILENAMES` |

图形设备路径支持：

```text
/dev/dri/renderD*
/dev/kgsl-3d0
```

如果 proot 没挂载 render node，硬件 Vulkan/OpenGL 本身不可用，Auto 会回退软件 OpenGL；这属于容器设备可见性问题，不是 Blender 包的 bug。

## 6. 工作流结构

`.github/workflows/manual-build.yml`：

1. 设置 runner 路径、清理磁盘；
2. 安装 Clang 21、LLD 21、Mesa DRI/Vulkan、`libdrm-freedreno1`、音频开发头文件和 Xvfb；
3. 输出 Mesa/Freedreno DRI、Vulkan ICD 版本和文件；
4. 运行 `verify-proot.py`，测试 proot 和 Freedreno 自动配置逻辑；
5. 恢复 `source/` 缓存；
6. `prepare-source.sh` 解析并锁定 Blender/ARM64 库 commit；
7. `actions/cache/save@v4` + `if: always()` 保存源码/LFS；
8. `build-blender.sh` 编译、验证后端矩阵、剪除 build-only payload；
9. Xvfb 下验证 CPU Cycles、软件 OpenGL、GUI 和完整 feature matrix；
10. 非阻断探测 Vulkan/Freedreno ICD；
11. 打包 `.deb`，安装后验证 Auto/proot/Freedreno；
12. 默认只上传 artifact；`publish_release=true` 才发布 Release。

`build_jobs` 可选 2/4/6。ThinLTO 最终链接固定单并发，降低 proot OOM 风险。

## 7. 包体处理

`prune-install.py` 只删除非运行时内容：

- Python tests；
- `__pycache__`、`.pyc`、`config-*`；
- 静态库 `.a`、libtool `.la`、`.prl`；
- `include`、`lib/cmake`、`pkg-config`、手工页。

`package-deb.py`：

- 对所有 ELF 执行 `strip --strip-unneeded`；
- 使用 xz level 9 压缩；
- 保留 README/许可证/BUILD-INFO；
- 运行时依赖加入正常音频库；
- 推荐 Mesa Vulkan 和 `libdrm-freedreno1`。

可用 `BLENDER_STRIP_BINARIES=0 ./package-release.sh` 跳过 strip 保留调试符号。

## 8. 本地构建

安装依赖（Ubuntu 26.04 ARM64）：

```sh
sudo apt update
sudo apt install -y \
  git git-lfs cmake ninja-build build-essential pkg-config dpkg-dev binutils \
  clang-21 lld-21 llvm-21 libclang-rt-21-dev python3 python3-dev xz-utils \
  libx11-dev libxxf86vm-dev libxi-dev libxfixes-dev libxrender-dev \
  libxrandr-dev libxcursor-dev libxinerama-dev libegl-dev libegl1-mesa-dev \
  libwayland-dev libdecor-0-dev libdbus-1-dev libxkbcommon-dev \
  libsm-dev libice-dev libvulkan-dev vulkan-tools \
  libpulse-dev libjack-jackd2-dev libasound2-dev \
  mesa-vulkan-drivers libgl1-mesa-dri libegl-mesa0 libopengl0 libdrm-freedreno1 \
  xvfb xauth
```

构建：

```sh
git clone https://github.com/CELEFT/blender-linux-arm64-clang21.git
cd blender-linux-arm64-clang21
./prepare-source.sh
BLENDER_BUILD_JOBS=2 ./build-blender.sh
```

固定版本：

```sh
BLENDER_VERSION=5.2.3 ./prepare-source.sh
```

Git 源镜像：

```sh
BLENDER_SOURCE_URL=https://mirror.example/blender.git
BLENDER_LIBRARY_URL=https://mirror.example/lib-linux_arm64.git
```

依赖源码下载：

```sh
python3 fetch-dependency-source.py --all --output dependency-sources
```

## 9. 验证

```sh
project_dir="$PWD"
source ./build-settings.sh

xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --background --factory-startup \
  --python-exit-code 1 --python verify-build.py

python3 verify-proot.py
vulkaninfo --summary

xvfb-run -a -s '-screen 0 1280x720x24' \
  "$install_dir/blender" --gpu-backend vulkan -noaudio \
  --factory-startup --python-exit-code 1 --python verify-vulkan.py
```

应看到：

- `BACKEND_MATRIX_VERIFIED`
- `FEATURE_MATRIX_VERIFIED`
- `BUILD_VERIFIED`
- `CPU_FLAGS_VERIFIED`
- `PROOT_FREEDRENO_COMPAT_VERIFIED`
- `UI_VERIFIED`
- 有可用 Vulkan ICD 时出现 `VULKAN_VERIFIED`

## 10. 真机检查与避坑

- 不要用 `-march=native` / `-mcpu=native` 重编；proot 的 CPU 信息不可信。
- 确认 `/dev/dri/renderD128` 或 `/dev/kgsl-3d0` 在容器内可见。
- 检查 `proot.json` 和 `freedreno.json`。
- 若 Wayland 不可用，X11 `DISPLAY` 是否可用；launcher 会删除失效 Wayland socket。
- 若 Vulkan 崩溃，先用 `--gpu-backend opengl` 或 `BLENDER_GRAPHICS_MODE=software` 判断问题层。
- 长时 Cycles 渲染必须散热；否则会撞温度墙。
- OOM 时使用 `BLENDER_BUILD_JOBS=2`、配置 swap、关闭后台应用。

## 11. 产物与验收

- `blender-linux-arm64_*.deb`；
- `blender-<version>-source.tar.xz`；
- `BUILD-INFO.json`：source/dependency commit、CPU flags、backend/feature matrix、Mesa/Freedreno、install size；
- `SHA256SUMS`；
- CI logs：`mesa-freedreno.log`、`vulkaninfo.log`、`verify.log`、`prune-install.json`、`compile-flags.json`、`package-proot.json`、`package-freedreno.json`。

CI 通过不等于真机通过。必须单独验证 Vulkan、OpenGL、Freedreno 检测和 Cycles CPU 渲染。
